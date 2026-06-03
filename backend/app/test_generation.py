import json
import re

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
        request = normalize_request(item, available_endpoints, endpoint_summary, api_docs)
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
    api_docs: str | None = None,
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
    if endpoint:
        apply_endpoint_defaults(request, endpoint, item)
    if is_missing_auth_case(item):
        request["dependencies"] = {"before": [], "after": []}
        remove_authorization(request)
        return request
    if endpoint and available_endpoints:
        apply_workflow_dependencies(request, endpoint, available_endpoints, api_docs)
    return request


def normalize_step(step: dict) -> dict:
    method = str(step.get("method", "GET")).upper()
    path = step.get("path", "/")
    body = step.get("body")
    if method == "POST" and normalize_path(str(path)) == "/cart":
        body = ensure_cart_body(body)
    return {
        "name": step.get("name") or f"{step.get('method', 'GET')} {step.get('path', '/')}",
        "method": method,
        "path": path,
        "headers": step.get("headers") if isinstance(step.get("headers"), dict) else {},
        "query": step.get("query") if isinstance(step.get("query"), dict) else {},
        "body": body,
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


def apply_workflow_dependencies(request: dict, endpoint: EndpointSummary, available_endpoints: list[EndpointReference], api_docs: str | None) -> None:
    dependencies = request.setdefault("dependencies", {"before": [], "after": []})
    dependencies["before"] = dependencies.get("before", [])
    dependencies["after"] = dependencies.get("after", [])
    path_text = endpoint.path.lower()
    needs_auth = needs_authenticated_flow(endpoint, request)
    register = find_endpoint_or_docs(available_endpoints, api_docs, ("register",), "POST", "/auth/register", body=register_body())
    login = find_endpoint_or_docs(available_endpoints, api_docs, ("login", "signin", "auth"), "POST", "/auth/login", body=user_login_body())
    product_lookup = find_endpoint_or_docs(available_endpoints, api_docs, ("products",), "GET", "/products", params={"page": "1", "limit": "5"})
    product_create = find_endpoint_or_docs(available_endpoints, api_docs, ("products",), "POST", "/products", body=product_body())
    add_cart = find_endpoint(available_endpoints, ("cart",), ("POST",))
    delete_cart = find_endpoint(available_endpoints, ("cart",), ("DELETE",))

    if needs_auth and login:
        auth_steps = []
        if register:
            auth_steps.append(register_step(register))
        auth_steps.append(login_step(login))
        ensure_auth_prefix(dependencies["before"], auth_steps)
        ensure_bearer_header(request)
        for step in dependencies["before"] + dependencies["after"]:
            if normalize_path(str(step.get("path", ""))) not in {normalize_path(login.path), normalize_path(register.path) if register else ""}:
                step["headers"] = with_bearer(step.get("headers", {}), "accessToken")

    if "checkout" in path_text:
        if product_create:
            insert_after_auth(dependencies["before"], admin_login_step())
            upsert_step(dependencies["before"], product_create_step(product_create))
        elif product_lookup:
            upsert_step(dependencies["before"], product_lookup_step(product_lookup))
        if add_cart and normalize_path(add_cart.path) != normalize_path(endpoint.path):
            upsert_step(dependencies["before"], cart_step(add_cart))
        if delete_cart:
            append_unique_step(dependencies["after"], cleanup_step(delete_cart))
    elif "cart" in path_text and endpoint.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        if endpoint.method.upper() == "POST":
            if product_create:
                insert_after_auth(dependencies["before"], admin_login_step())
                upsert_step(dependencies["before"], product_create_step(product_create))
            elif product_lookup:
                upsert_step(dependencies["before"], product_lookup_step(product_lookup))
        if delete_cart and endpoint.method.upper() != "DELETE":
            append_unique_step(dependencies["after"], cleanup_step(delete_cart))
    elif "order" in path_text:
        if product_create:
            insert_after_auth(dependencies["before"], admin_login_step())
            upsert_step(dependencies["before"], product_create_step(product_create))
        elif product_lookup:
            upsert_step(dependencies["before"], product_lookup_step(product_lookup))
        if add_cart:
            upsert_step(dependencies["before"], cart_step(add_cart))
        checkout = find_endpoint(available_endpoints, ("checkout",), ("POST",)) or find_endpoint_or_docs(available_endpoints, api_docs, ("checkout",), "POST", "/checkout")
        if checkout and normalize_path(checkout.path) != normalize_path(endpoint.path):
            upsert_step(dependencies["before"], checkout_step(checkout))


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


def find_endpoint_or_docs(
    endpoints: list[EndpointReference],
    api_docs: str | None,
    keywords: tuple[str, ...],
    method: str,
    path: str,
    headers: dict | None = None,
    params: dict | None = None,
    body=None,
) -> EndpointReference | None:
    found = find_endpoint(endpoints, keywords, (method,))
    if found:
        return found
    if doc_mentions_endpoint(api_docs, method, path):
        return EndpointReference(name=f"Documented {method} {path}", method=method, path=path, headers=headers or {}, params=params or {}, body=body)
    return None


def doc_mentions_endpoint(api_docs: str | None, method: str, path: str) -> bool:
    if not api_docs:
        return False
    pattern = rf"\b{re.escape(method.upper())}\b\s+`?{re.escape(path)}`?\b"
    return re.search(pattern, api_docs, re.IGNORECASE) is not None


def register_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Register dynamic user",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": endpoint.headers,
            "query": endpoint.params,
            "body": endpoint.body or register_body(),
        }
    )


def login_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Login and capture auth token",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": endpoint.headers,
            "query": endpoint.params,
            "body": endpoint.body or user_login_body(),
            "extract": {
                "token": "$.accessToken",
                "accessToken": "$.accessToken",
                "access_token": "$.access_token",
                "refreshToken": "$.refreshToken",
                "cartId": "$.cartId",
            },
        }
    )


def admin_login_step() -> dict:
    return normalize_step(
        {
            "name": "Login as admin",
            "method": "POST",
            "path": "/auth/login",
            "headers": {"Content-Type": "application/json"},
            "body": {"email": "admin@practice.com", "password": "password123"},
            "extract": {"adminAccessToken": "$.accessToken"},
        }
    )


def product_lookup_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Fetch product catalogue",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": endpoint.headers,
            "query": endpoint.params or {"page": "1", "limit": "5"},
            "body": endpoint.body,
            "extract": {"customProductId": "$.data.0.id", "productId": "$.data.0.id", "firstProductId": "$.data.0.id"},
        }
    )


def product_create_step(endpoint: EndpointReference) -> dict:
    headers = endpoint.headers.copy() if isinstance(endpoint.headers, dict) else {}
    headers["Authorization"] = "Bearer {{adminAccessToken}}"
    return normalize_step(
        {
            "name": "Create product for checkout",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": headers,
            "query": endpoint.params,
            "body": endpoint.body or product_body(),
            "extract": {"customProductId": "$.product.id", "productId": "$.product.id", "firstProductId": "$.product.id"},
        }
    )


def cart_step(endpoint: EndpointReference) -> dict:
    body = ensure_cart_body(endpoint.body)
    return normalize_step(
        {
            "name": "Create or add cart item",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": with_bearer(endpoint.headers, "accessToken"),
            "query": endpoint.params,
            "body": body,
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
            "headers": with_bearer(endpoint.headers, "accessToken"),
            "query": endpoint.params,
            "body": endpoint.body,
        }
    )


def checkout_step(endpoint: EndpointReference) -> dict:
    return normalize_step(
        {
            "name": "Checkout cart",
            "method": endpoint.method,
            "path": endpoint.path,
            "headers": with_bearer(endpoint.headers, "accessToken"),
            "query": endpoint.params,
            "body": endpoint.body,
            "extract": {"latestOrderId": "$.orderId", "orderId": "$.orderId", "checkoutId": "$.checkoutId"},
        }
    )


def apply_endpoint_defaults(request: dict, endpoint: EndpointSummary, item: dict) -> None:
    path = endpoint.path.lower()
    method = endpoint.method.upper()
    if method == "POST" and "cart" in path and is_positive_case(item):
        request["body"] = ensure_cart_body(request.get("body"), quantity=2)
    if method == "POST" and "checkout" in path and is_positive_case(item):
        request["body"] = None
    if method == "GET" and "order" in path:
        request["body"] = None
    if method == "DELETE" and "cart" in path:
        request["body"] = None


def is_positive_case(item: dict) -> bool:
    name = str(item.get("name", "")).lower()
    category = str(item.get("category", "")).lower()
    negative_words = ("missing", "invalid", "malformed", "injection", "idor", "boundary", "unauthorized", "forbidden", "empty")
    return category == "functional" and not any(word in name for word in negative_words)


def is_missing_auth_case(item: dict) -> bool:
    name = str(item.get("name", "")).lower()
    return "missing authentication" in name or "without token" in name or "no token" in name


def remove_authorization(request: dict) -> None:
    headers = request.setdefault("headers", {})
    for key in list(headers.keys()):
        if str(key).lower() == "authorization":
            headers.pop(key, None)


def ensure_bearer_header(request: dict) -> None:
    headers = request.setdefault("headers", {})
    current = str(headers.get("Authorization") or headers.get("authorization") or "")
    if not current or current.strip() == "Bearer":
        headers["Authorization"] = "Bearer {{accessToken}}"


def with_bearer(headers: dict, token_name: str = "token") -> dict:
    next_headers = headers.copy() if isinstance(headers, dict) else {}
    current = str(next_headers.get("Authorization") or next_headers.get("authorization") or "")
    if not current or current.strip() == "Bearer":
        next_headers["Authorization"] = f"Bearer {{{{{token_name}}}}}"
    return next_headers


def ensure_checkout_body(request: dict) -> None:
    body = request.get("body")
    if not isinstance(body, dict):
        request["body"] = {"cartId": "{{cartId}}"}
        return
    if not any(str(key).lower() in {"cartid", "cart_id"} for key in body.keys()):
        body["cartId"] = "{{cartId}}"


def ensure_cart_body(body, quantity: int = 1) -> dict:
    next_body = body.copy() if isinstance(body, dict) else {}
    product_id = next_body.get("productId") or next_body.get("product_id")
    if not product_id or str(product_id).strip().lower() in {"undefined", "null", "none"}:
        next_body["productId"] = "{{customProductId}}"
    if "quantity" not in next_body or next_body.get("quantity") in {"", None}:
        next_body["quantity"] = quantity
    return next_body


def register_body() -> dict:
    return {
        "email": "{{dynamicEmail}}",
        "password": "{{dynamicPassword}}",
        "firstName": "{{dynamicFirstName}}",
        "lastName": "{{dynamicLastName}}",
    }


def user_login_body() -> dict:
    return {"email": "{{dynamicEmail}}", "password": "{{dynamicPassword}}"}


def product_body() -> dict:
    return {
        "name": "{{dynamicProductName}}",
        "price": 149.99,
        "category": "Electronics",
        "stock": 10,
        "description": "An amazing QA creation",
    }


def prepend_unique_step(steps: list[dict], step: dict) -> None:
    if not has_step(steps, step):
        steps.insert(0, step)


def append_unique_step(steps: list[dict], step: dict) -> None:
    if not has_step(steps, step):
        steps.append(step)


def upsert_step(steps: list[dict], step: dict) -> None:
    for index, item in enumerate(steps):
        if item.get("method") == step.get("method") and normalize_path(str(item.get("path", ""))) == normalize_path(str(step.get("path", ""))):
            merged = item.copy()
            merged.update(step)
            steps[index] = merged
            return
    steps.append(step)


def ensure_auth_prefix(steps: list[dict], auth_steps: list[dict]) -> None:
    rest = [step for step in steps if not any(step.get("method") == auth.get("method") and normalize_path(str(step.get("path", ""))) == normalize_path(str(auth.get("path", ""))) for auth in auth_steps)]
    steps[:] = auth_steps + rest


def insert_after_auth(steps: list[dict], step: dict) -> None:
    if any(
        item.get("method") == step.get("method")
        and normalize_path(str(item.get("path", ""))) == normalize_path(str(step.get("path", "")))
        and item.get("name") == step.get("name")
        for item in steps
    ):
        return
    last_auth_index = -1
    for index, item in enumerate(steps):
        if normalize_path(str(item.get("path", ""))) in {"/auth/register", "/auth/login"}:
            last_auth_index = index
    steps.insert(last_auth_index + 1 if last_auth_index >= 0 else 0, step)


def has_step(steps: list[dict], step: dict) -> bool:
    return any(item.get("method") == step.get("method") and normalize_path(str(item.get("path", ""))) == normalize_path(str(step.get("path", ""))) for item in steps)
