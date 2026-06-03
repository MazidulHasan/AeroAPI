import asyncio
import json
import re
import time
import uuid
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.security import redact

VARIABLE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}|{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}")


async def run_generated_tests(
    db: Session,
    run: models.TestRun,
    generated_tests: list[models.GeneratedTest],
    base_url_override: str | None,
    timeout_seconds: int,
    concurrency: int,
) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    shared_context = initial_context()
    setup_cache: dict[str, dict] = {}
    setup_lock = asyncio.Lock()
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        tasks = [
            execute_one(run.id, test, client, semaphore, base_url_override, shared_context, setup_cache, setup_lock)
            for test in generated_tests
        ]
        await asyncio.gather(*tasks)


async def execute_one(
    run_id: int,
    test: models.GeneratedTest,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url_override: str | None,
    shared_context: dict[str, str] | None = None,
    setup_cache: dict[str, dict] | None = None,
    setup_lock: asyncio.Lock | None = None,
) -> models.TestResult:
    async with semaphore:
        override = json.loads(test.request_override_json)
        dependencies = normalize_dependencies(override.get("dependencies"))
        context: dict[str, str] = dict(shared_context or initial_context())
        before_results: list[dict] = []
        after_results: list[dict] = []
        dependency_failed = False
        for step in dependencies.get("before", []) or []:
            step_result = await execute_dependency_step(client, base_url_override, step, context, shared_context, setup_cache, setup_lock)
            before_results.append(step_result)
            if step_result.get("error") or int(step_result.get("status") or 0) >= 400:
                dependency_failed = True
                break

        resolved = render_template(override, context)
        method = resolved.get("method", "GET").upper()
        path = resolved.get("path", "/")
        url = build_url(base_url_override, path)
        headers = ensure_dict(resolved.get("headers"))
        query = ensure_dict(resolved.get("query"))
        body = resolved.get("body")
        started = time.perf_counter()
        response_status = None
        response_headers = {}
        body_preview = ""
        status = "warning"
        finding = "Request was prepared but no base URL was supplied."
        suggested = "Set a base URL override before running live tests."

        if dependency_failed:
            status = "error"
            finding = "A required dependency request failed before the main request ran."
            suggested = "Review the dependency flow, credentials, extracted variables, and API documentation."
        elif base_url_override:
            try:
                response = await client.request(method, url, headers=headers, params=query, json=body if method not in {"GET", "HEAD"} else None)
                response_status = response.status_code
                response_headers = dict(response.headers)
                body_preview = response.text[:4000]
                status, finding, suggested = classify_result(test, response.status_code)
            except Exception as exc:
                status = "error"
                finding = f"Request failed: {exc.__class__.__name__}"
                suggested = "Confirm the base URL, network access, TLS settings, and endpoint availability."

        for step in dependencies.get("after", []):
            after_results.append(await execute_dependency_step(client, base_url_override, step, context))

        latency_ms = int((time.perf_counter() - started) * 1000)
        db = SessionLocal()
        try:
            result = models.TestResult(
                test_run_id=run_id,
                generated_test_id=test.id,
                status=status,
                request_json=json.dumps(
                    redact(
                        {
                            "dependencies": {"before": before_results, "after": after_results},
                            "main": {"method": method, "url": url, "headers": headers, "query": query, "body": body},
                        }
                    )
                ),
                response_status=response_status,
                response_headers_json=json.dumps(redact(response_headers)),
                response_body_preview=body_preview,
                latency_ms=latency_ms,
                finding_summary=finding,
                suggested_fix=suggested,
            )
            db.add(result)
            db.commit()
            db.refresh(result)
            update_counts(db, run_id, result)
        finally:
            db.close()


def build_url(base_url: str | None, path: str) -> str:
    if urlparse(path).scheme in {"http", "https"}:
        return path
    if not base_url:
        return path
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


async def execute_dependency_step(
    client: httpx.AsyncClient,
    base_url: str | None,
    step: dict,
    context: dict[str, str],
    shared_context: dict[str, str] | None = None,
    setup_cache: dict[str, dict] | None = None,
    setup_lock: asyncio.Lock | None = None,
) -> dict:
    cache_key = setup_cache_key(step)
    if cache_key and setup_cache is not None and setup_lock is not None:
        async with setup_lock:
            cached = setup_cache.get(cache_key)
            if cached:
                context.update(cached.get("context", {}))
                record = json.loads(json.dumps(cached["record"]))
                record["cached"] = True
                return record
            record = await execute_dependency_step_uncached(client, base_url, step, context)
            if int(record.get("status") or 0) < 400 and not record.get("error"):
                shared_values = pick_shared_context(context)
                if shared_context is not None:
                    shared_context.update(shared_values)
                setup_cache[cache_key] = {"record": record, "context": shared_values}
            return record
    return await execute_dependency_step_uncached(client, base_url, step, context)


async def execute_dependency_step_uncached(client: httpx.AsyncClient, base_url: str | None, step: dict, context: dict[str, str]) -> dict:
    resolved = render_template(step, context)
    method = str(resolved.get("method", "GET")).upper()
    path = str(resolved.get("path", "/"))
    repair_cart_body(resolved, method, path, context)
    url = build_url(base_url, path)
    headers = ensure_dict(resolved.get("headers"))
    query = ensure_dict(resolved.get("query"))
    body = resolved.get("body")
    record = {
        "name": resolved.get("name") or f"{method} {path}",
        "method": method,
        "url": url,
        "status": None,
        "extracts": {},
        "request": redact({"method": method, "url": url, "headers": headers, "query": query, "body": body}),
        "response": {"status": None, "headers": {}, "body": ""},
    }
    if not base_url:
        record["error"] = "No base URL supplied"
        return record
    try:
        response = await client.request(method, url, headers=headers, params=query, json=body if method not in {"GET", "HEAD"} else None)
        record["status"] = response.status_code
        record["response"] = {
            "status": response.status_code,
            "headers": redact(dict(response.headers)),
            "body": response.text[:4000],
        }
        extract_values(response, ensure_dict(resolved.get("extract")), context, record["extracts"])
    except Exception as exc:
        record["error"] = exc.__class__.__name__
        record["response"] = {"status": None, "headers": {}, "body": str(exc)}
    return record


def setup_cache_key(step: dict) -> str | None:
    name = str(step.get("name") or "").lower()
    method = str(step.get("method") or "").upper()
    path = str(step.get("path") or "")
    if name in {"register dynamic user", "login and capture auth token", "login as admin", "create product for checkout"}:
        return f"{method} {path} {name}"
    return None


def pick_shared_context(context: dict[str, str]) -> dict[str, str]:
    keys = {
        "dynamicEmail",
        "dynamicPassword",
        "dynamicFirstName",
        "dynamicLastName",
        "dynamicProductName",
        "token",
        "accessToken",
        "access_token",
        "refreshToken",
        "adminAccessToken",
        "customProductId",
        "productId",
        "firstProductId",
    }
    return {key: value for key, value in context.items() if key in keys}


def render_template(value, context: dict[str, str]):
    if isinstance(value, str):
        return VARIABLE_PATTERN.sub(lambda match: str(context.get(match.group(1) or match.group(2), match.group(0))), value)
    if isinstance(value, dict):
        return {key: render_template(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template(item, context) for item in value]
    return value


def normalize_dependencies(value) -> dict[str, list[dict]]:
    if not isinstance(value, dict):
        return {"before": [], "after": []}
    before = value.get("before") if isinstance(value.get("before"), list) else []
    after = value.get("after") if isinstance(value.get("after"), list) else []
    return {
        "before": [step for step in before if isinstance(step, dict)],
        "after": [step for step in after if isinstance(step, dict)],
    }


def ensure_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def repair_cart_body(request: dict, method: str, path: str, context: dict[str, str]) -> None:
    if method != "POST" or normalize_path(path) != "/cart":
        return
    body = request.get("body") if isinstance(request.get("body"), dict) else {}
    product_id = body.get("productId") or body.get("product_id")
    if not product_id or str(product_id).strip().lower() in {"undefined", "null", "none"}:
        fallback = context.get("customProductId") or context.get("productId") or context.get("firstProductId")
        if fallback:
            body["productId"] = fallback
    if "quantity" not in body or body.get("quantity") in {"", None}:
        body["quantity"] = 1
    request["body"] = body


def normalize_path(path: str) -> str:
    return path.split("?", 1)[0].rstrip("/") or "/"


def initial_context() -> dict[str, str]:
    suffix = uuid.uuid4().hex
    return {
        "dynamicEmail": f"aeroapi_{suffix}@example.com",
        "dynamicPassword": f"Pass123!{suffix[-8:]}",
        "dynamicFirstName": "Aero",
        "dynamicLastName": "Tester",
        "dynamicProductName": f"AeroAPI Test Product {suffix}",
    }


def extract_values(response: httpx.Response, extract: dict, context: dict[str, str], recorded: dict) -> None:
    payload = None
    for key, path in extract.items():
        value = None
        if isinstance(path, str) and path.lower().startswith("header."):
            value = response.headers.get(path.split(".", 1)[1])
        else:
            if payload is None:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
            value = read_json_path(payload, str(path))
        if value is not None:
            context[str(key)] = str(value)
            recorded[str(key)] = str(value)
            if str(key) in {"access_token", "accessToken"} and "token" not in context:
                context["token"] = str(value)
                recorded["token"] = str(value)
            if str(key) == "token" and "accessToken" not in context:
                context["accessToken"] = str(value)
                recorded["accessToken"] = str(value)
            if str(key) in {"customProductId", "productId", "firstProductId"}:
                for alias in ("customProductId", "productId", "firstProductId"):
                    context.setdefault(alias, str(value))
                    recorded.setdefault(alias, str(value))
            if str(key) in {"latestOrderId", "orderId"}:
                for alias in ("latestOrderId", "orderId"):
                    context.setdefault(alias, str(value))
                    recorded.setdefault(alias, str(value))
            if str(key) in {"cartId", "cart_id", "cartItemId"} and "id" not in context:
                context["id"] = str(value)
                recorded["id"] = str(value)
    if not extract:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        for key in ("token", "accessToken", "access_token", "cartId", "cart_id", "checkoutId", "orderId", "latestOrderId", "id"):
            value = payload.get(key) if isinstance(payload, dict) else None
            if value is not None:
                context[key] = str(value)
                recorded[key] = str(value)
                if key in {"access_token", "accessToken"} and "token" not in context:
                    context["token"] = str(value)
                    recorded["token"] = str(value)
                if key == "token" and "accessToken" not in context:
                    context["accessToken"] = str(value)
                    recorded["accessToken"] = str(value)
                if key in {"cartId", "cart_id", "cartItemId"} and "id" not in context:
                    context["id"] = str(value)
                    recorded["id"] = str(value)
        nested_product_id = read_json_path(payload, "$.product.id")
        if nested_product_id is not None:
            for alias in ("customProductId", "productId", "firstProductId"):
                context.setdefault(alias, str(nested_product_id))
                recorded.setdefault(alias, str(nested_product_id))
        nested_order_id = read_json_path(payload, "$.orderId")
        if nested_order_id is not None:
            for alias in ("latestOrderId", "orderId"):
                context.setdefault(alias, str(nested_order_id))
                recorded.setdefault(alias, str(nested_order_id))


def read_json_path(payload, path: str):
    if not path.startswith("$."):
        return None
    current = payload
    for part in path[2:].split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def classify_result(test: models.GeneratedTest, status_code: int) -> tuple[str, str, str]:
    if test.category == "functional":
        if 200 <= status_code < 300:
            return "passed", "Functional check passed.", "No action needed."
        return "failed", f"Expected a successful response but received {status_code}.", "Review endpoint behavior or update the collection example."
    if test.category == "security":
        if status_code in {200, 201, 202, 204}:
            return "failed", f"Security probe was accepted with HTTP {status_code}.", "Validate authorization and input sanitization for this route."
        return "passed", "Security probe was rejected or constrained.", "No action needed."
    if status_code >= 500:
        return "failed", f"Edge-case input caused server error {status_code}.", "Add validation and safer error handling."
    return "passed", "Endpoint handled the edge case without a server failure.", "No action needed."


def update_counts(db: Session, run_id: int, result: models.TestResult) -> None:
    run = db.get(models.TestRun, run_id)
    if not run or run.status == "cancelled":
        return
    run.completed_tests += 1
    if result.status == "passed":
        run.passed_count += 1
    if result.status in {"failed", "error"}:
        run.failed_count += 1
    test = db.get(models.GeneratedTest, result.generated_test_id)
    if test and test.category == "security" and result.status in {"failed", "warning"}:
        run.security_count += 1
    if test and result.status in {"failed", "error"} and is_regression(db, run, test):
        run.regression_count += 1
    db.commit()


def is_regression(db: Session, run: models.TestRun, test: models.GeneratedTest) -> bool:
    previous_run = (
        db.query(models.TestRun)
        .filter(
            models.TestRun.collection_id == run.collection_id,
            models.TestRun.id < run.id,
            models.TestRun.status == "completed",
        )
        .order_by(models.TestRun.id.desc())
        .first()
    )
    if not previous_run:
        return False
    previous = (
        db.query(models.TestResult)
        .join(models.GeneratedTest, models.GeneratedTest.id == models.TestResult.generated_test_id)
        .filter(
            models.TestResult.test_run_id == previous_run.id,
            models.GeneratedTest.endpoint_id == test.endpoint_id,
            models.GeneratedTest.name == test.name,
            models.TestResult.status == "passed",
        )
        .first()
    )
    return previous is not None
