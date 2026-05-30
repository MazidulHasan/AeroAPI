import json

from sqlalchemy.orm import Session

from app import models
from app.providers import DeterministicProvider, get_provider
from app.schemas import EndpointReference, EndpointSummary


REQUIRED_TEST_KEYS = {"name", "category", "severity", "request", "expected", "reasoning"}


async def generate_for_endpoint(
    db: Session,
    run_id: int,
    endpoint: models.Endpoint,
    provider_name: str,
    model: str,
    api_token: str,
    api_docs: str | None,
    available_endpoints: list[EndpointReference],
    intensity: str,
    custom_base_url: str | None,
) -> list[models.GeneratedTest]:
    provider = get_provider(provider_name, model, api_token, custom_base_url)
    endpoint_summary = EndpointSummary(
        id=endpoint.id,
        name=endpoint.name,
        method=endpoint.method,
        path=endpoint.path,
        url=endpoint.url,
        auth_type=endpoint.auth_type,
        headers=json.loads(endpoint.headers_json),
        params=json.loads(endpoint.params_json),
        body=json.loads(endpoint.body_json),
    )
    used_fallback = False
    try:
        generated = await provider.generate_tests(endpoint_summary, intensity, api_docs, available_endpoints)
    except json.JSONDecodeError:
        used_fallback = True
        generated = await DeterministicProvider(model, api_token, custom_base_url).generate_tests(endpoint_summary, intensity)
    tests = validate_generated_tests(generated)
    rows = []
    for item in tests:
        expected = item.get("expected", {})
        request = normalize_request(item, available_endpoints, endpoint_summary)
        row = models.GeneratedTest(
            test_run_id=run_id,
            endpoint_id=endpoint.id,
            name=item["name"],
            category=item["category"],
            severity=item["severity"],
            request_override_json=json.dumps(request),
            expected_behavior=json.dumps(expected),
            ai_reasoning=f"{item['reasoning']} Provider returned malformed JSON, so AeroAPI used local deterministic generation." if used_fallback else item["reasoning"],
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def validate_generated_tests(generated: dict) -> list[dict]:
    tests = generated.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("Provider did not return a tests array")
    valid = []
    for item in tests:
        if isinstance(item, dict) and REQUIRED_TEST_KEYS.issubset(item.keys()):
            valid.append(item)
    if not valid:
        raise ValueError("Provider returned no valid tests")
    return valid[:24]


def normalize_request(
    item: dict,
    available_endpoints: list[EndpointReference] | None = None,
    endpoint: EndpointSummary | None = None,
) -> dict:
    request = item.get("request") if isinstance(item.get("request"), dict) else {}
    dependencies = request.get("dependencies") or item.get("dependencies") or {}
    before = dependencies.get("before") if isinstance(dependencies, dict) and isinstance(dependencies.get("before"), list) else []
    after = dependencies.get("after") if isinstance(dependencies, dict) and isinstance(dependencies.get("after"), list) else []
    request["dependencies"] = {
        "before": [step for step in (normalize_step(step) for step in before if isinstance(step, dict)) if is_allowed_dependency(step, available_endpoints)],
        "after": [step for step in (normalize_step(step) for step in after if isinstance(step, dict)) if is_allowed_dependency(step, available_endpoints)],
    }
    request["headers"] = request.get("headers") if isinstance(request.get("headers"), dict) else {}
    request["query"] = request.get("query") if isinstance(request.get("query"), dict) else {}
    if endpoint and available_endpoints:
        apply_workflow_dependencies(request, endpoint, available_endpoints)
    return request


def normalize_step(step: dict) -> dict:
    return {
        "name": step.get("name") or f"{step.get('method', 'GET')} {step.get('path', '/')}",
        "method": str(step.get("method", "GET")).upper(),
        "path": step.get("path", "/"),
        "headers": step.get("headers") if isinstance(step.get("headers"), dict) else {},
        "query": step.get("query") if isinstance(step.get("query"), dict) else {},
        "body": step.get("body"),
        "extract": step.get("extract") if isinstance(step.get("extract"), dict) else {},
    }


def is_allowed_dependency(step: dict, available_endpoints: list[EndpointReference] | None) -> bool:
    if not available_endpoints:
        return True
    method = str(step.get("method", "")).upper()
    path = normalize_path(str(step.get("path", "")))
    return any(method == item.method.upper() and path == normalize_path(item.path) for item in available_endpoints)


def normalize_path(path: str) -> str:
    return path.split("?", 1)[0].rstrip("/") or "/"


def apply_workflow_dependencies(request: dict, endpoint: EndpointSummary, available_endpoints: list[EndpointReference]) -> None:
    dependencies = request.setdefault("dependencies", {"before": [], "after": []})
    dependencies["before"] = dependencies.get("before", [])
    dependencies["after"] = dependencies.get("after", [])
    path_text = endpoint.path.lower()
    needs_auth = needs_authenticated_flow(endpoint, request)
    login = find_endpoint(available_endpoints, ("login", "signin", "auth"), ("POST",))
    add_cart = find_endpoint(available_endpoints, ("cart",), ("POST",))
    delete_cart = find_endpoint(available_endpoints, ("cart",), ("DELETE",))

    if needs_auth and login:
        prepend_unique_step(dependencies["before"], login_step(login))
        ensure_bearer_header(request)
        for step in dependencies["before"] + dependencies["after"]:
            if normalize_path(str(step.get("path", ""))) != normalize_path(login.path):
                step["headers"] = with_bearer(step.get("headers", {}))

    if "checkout" in path_text:
        if add_cart and normalize_path(add_cart.path) != normalize_path(endpoint.path):
            append_unique_step(dependencies["before"], cart_step(add_cart))
            ensure_checkout_body(request)
        if delete_cart:
            append_unique_step(dependencies["after"], cleanup_step(delete_cart))
    elif "cart" in path_text and endpoint.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        if delete_cart and endpoint.method.upper() != "DELETE":
            append_unique_step(dependencies["after"], cleanup_step(delete_cart))


def needs_authenticated_flow(endpoint: EndpointSummary, request: dict) -> bool:
    path = endpoint.path.lower()
    headers = request.get("headers", {})
    auth_header = str(headers.get("Authorization") or headers.get("authorization") or "")
    return (
        endpoint.auth_type != "none"
        or "authorization" in {str(key).lower() for key in endpoint.headers.keys()}
        or auth_header.startswith("Bearer")
        or any(keyword in path for keyword in ("cart", "checkout", "order", "profile", "account"))
    )


def find_endpoint(endpoints: list[EndpointReference], keywords: tuple[str, ...], methods: tuple[str, ...]) -> EndpointReference | None:
    for endpoint in endpoints:
        haystack = f"{endpoint.name} {endpoint.path}".lower()
        if endpoint.method.upper() in methods and any(keyword in haystack for keyword in keywords):
            return endpoint
    return None


def login_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Login and capture auth token",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": endpoint.headers,
            "query": endpoint.params,
            "body": endpoint.body,
            "extract": {
                "token": "$.token",
                "access_token": "$.access_token",
                "cartId": "$.cartId",
            },
        }
    )


def cart_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Create or add cart item",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": with_bearer(endpoint.headers),
            "query": endpoint.params,
            "body": endpoint.body,
            "extract": {
                "cartId": "$.cartId",
                "cart_id": "$.cart_id",
                "cartItemId": "$.id",
                "productId": "$.productId",
            },
        }
    )


def cleanup_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Cleanup cart",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": with_bearer(endpoint.headers),
            "query": endpoint.params,
            "body": endpoint.body,
        }
    )


def ensure_bearer_header(request: dict) -> None:
    headers = request.setdefault("headers", {})
    current = str(headers.get("Authorization") or headers.get("authorization") or "")
    if not current or current.strip() == "Bearer":
        headers["Authorization"] = "Bearer {{token}}"


def with_bearer(headers: dict) -> dict:
    next_headers = headers.copy() if isinstance(headers, dict) else {}
    current = str(next_headers.get("Authorization") or next_headers.get("authorization") or "")
    if not current or current.strip() == "Bearer":
        next_headers["Authorization"] = "Bearer {{token}}"
    return next_headers


def ensure_checkout_body(request: dict) -> None:
    body = request.get("body")
    if not isinstance(body, dict):
        request["body"] = {"cartId": "{{cartId}}"}
        return
    if not any(str(key).lower() in {"cartid", "cart_id"} for key in body.keys()):
        body["cartId"] = "{{cartId}}"


def prepend_unique_step(steps: list[dict], step: dict) -> None:
    if not has_step(steps, step):
        steps.insert(0, step)


def append_unique_step(steps: list[dict], step: dict) -> None:
    if not has_step(steps, step):
        steps.append(step)


def has_step(steps: list[dict], step: dict) -> bool:
    return any(item.get("method") == step.get("method") and normalize_path(str(item.get("path", ""))) == normalize_path(str(step.get("path", ""))) for item in steps)
