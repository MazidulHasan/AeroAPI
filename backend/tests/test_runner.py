import asyncio

from app.providers import DeterministicProvider
from app.runner import extract_values, normalize_dependencies, read_json_path, repair_cart_body, render_template
import httpx
from app.schemas import EndpointReference, EndpointSummary
from app.test_generation import normalize_request


def test_normalize_request_converts_null_dependency_fields():
    request = normalize_request(
        {
            "request": {
                "method": "POST",
                "path": "/checkout",
                "headers": None,
                "query": None,
                "dependencies": {"before": None, "after": [{"name": "cleanup", "headers": None, "query": None, "extract": None}]},
            }
        }
    )

    assert request["headers"] == {}
    assert request["query"] == {}
    assert request["dependencies"]["before"] == []
    assert request["dependencies"]["after"][0]["headers"] == {}
    assert request["dependencies"]["after"][0]["query"] == {}
    assert request["dependencies"]["after"][0]["extract"] == {}


def test_normalize_dependencies_handles_none():
    assert normalize_dependencies(None) == {"before": [], "after": []}


def test_render_template_keeps_null_body():
    rendered = render_template({"body": None, "headers": {"Authorization": "Bearer {{token}}"}}, {"token": "abc"})

    assert rendered == {"body": None, "headers": {"Authorization": "Bearer abc"}}


def test_render_template_supports_single_brace_variables():
    rendered = render_template({"path": "/cart/{cartId}", "body": {"productId": "{productId}"}}, {"cartId": "c1", "productId": "p1"})

    assert rendered == {"path": "/cart/c1", "body": {"productId": "p1"}}


def test_normalize_request_drops_unknown_dependency_endpoint():
    request = normalize_request(
        {
            "request": {
                "method": "POST",
                "path": "/cart",
                "dependencies": {
                    "before": [
                        {"name": "login", "method": "POST", "path": "/auth/login"},
                        {"name": "invented product", "method": "POST", "path": "/products"},
                    ]
                },
            }
        },
        [EndpointReference(name="Login", method="POST", path="/auth/login"), EndpointReference(name="Cart", method="POST", path="/cart")],
    )

    assert [step["path"] for step in request["dependencies"]["before"]] == ["/auth/login"]


def test_checkout_request_gets_collection_workflow_dependencies():
    request = normalize_request(
        {
            "request": {
                "method": "POST",
                "path": "/checkout",
                "headers": {},
                "body": {},
            }
        },
        [
            EndpointReference(name="Login", method="POST", path="/auth/login", body={"email": "a@example.com", "password": "secret"}),
            EndpointReference(name="Add to cart", method="POST", path="/cart", body={"productId": "p1", "quantity": 1}),
            EndpointReference(name="Delete cart", method="DELETE", path="/cart/{id}"),
            EndpointReference(name="Checkout", method="POST", path="/checkout"),
        ],
        EndpointSummary(name="Checkout", method="POST", path="/checkout", url="/checkout", auth_type="bearer", headers={}, params={}, body={}),
    )

    assert [step["path"] for step in request["dependencies"]["before"]] == ["/auth/login", "/cart"]
    assert request["dependencies"]["after"][0]["path"] == "/cart/{id}"
    assert request["headers"]["Authorization"] == "Bearer {{accessToken}}"
    assert "cartId" not in request["body"]


def test_checkout_dependency_repairs_blank_cart_product_id():
    request = normalize_request(
        {
            "request": {
                "method": "POST",
                "path": "/checkout",
                "headers": {},
                "body": {},
            }
        },
        [
            EndpointReference(name="Login", method="POST", path="/auth/login"),
            EndpointReference(name="Create product", method="POST", path="/products"),
            EndpointReference(name="Add to cart", method="POST", path="/cart", body={"productId": "", "quantity": 1}),
            EndpointReference(name="Checkout", method="POST", path="/checkout"),
        ],
        EndpointSummary(name="Checkout", method="POST", path="/checkout", url="/checkout", auth_type="bearer", headers={}, params={}, body={}),
    )

    cart_step = next(step for step in request["dependencies"]["before"] if step["path"] == "/cart")
    assert cart_step["body"]["productId"] == "{{customProductId}}"
    assert cart_step["body"]["quantity"] == 1


def test_ai_supplied_cart_dependency_repairs_blank_product_id():
    request = normalize_request(
        {
            "request": {
                "method": "GET",
                "path": "/orders",
                "headers": {},
                "dependencies": {
                    "before": [
                        {"name": "Create or add cart item", "method": "POST", "path": "/cart", "body": {"productId": "", "quantity": 2}},
                    ]
                },
            }
        },
        [
            EndpointReference(name="Add to cart", method="POST", path="/cart", body={"productId": "", "quantity": 2}),
            EndpointReference(name="Orders", method="GET", path="/orders"),
        ],
        EndpointSummary(name="Orders", method="GET", path="/orders", url="/orders", auth_type="bearer", headers={}, params={}, body={}),
    )

    cart_step = next(step for step in request["dependencies"]["before"] if step["path"] == "/cart")
    assert cart_step["body"]["productId"] == "{{customProductId}}"
    assert cart_step["body"]["quantity"] == 2


def test_runner_repairs_stored_blank_cart_product_id():
    request = {"body": {"productId": "", "quantity": 2}}

    repair_cart_body(request, "POST", "/cart", {"customProductId": "prod-1"})

    assert request["body"] == {"productId": "prod-1", "quantity": 2}


def test_authenticated_dependency_steps_receive_bearer_header():
    request = normalize_request(
        {
            "request": {
                "method": "POST",
                "path": "/checkout",
                "headers": {},
                "dependencies": {
                    "before": [
                        {"name": "Create product", "method": "POST", "path": "/products", "headers": {}},
                    ]
                },
            }
        },
        [
            EndpointReference(name="Login", method="POST", path="/auth/login"),
            EndpointReference(name="Create product", method="POST", path="/products"),
            EndpointReference(name="Checkout", method="POST", path="/checkout"),
        ],
        EndpointSummary(name="Checkout", method="POST", path="/checkout", url="/checkout", auth_type="bearer", headers={}, params={}, body={}),
    )

    product_step = next(step for step in request["dependencies"]["before"] if step["path"] == "/products")
    assert product_step["headers"]["Authorization"] == "Bearer {{adminAccessToken}}"


def test_checkout_request_builds_doc_only_workflow_dependencies():
    docs = """
    POST /auth/register
    POST /auth/login
    POST /products
    POST /cart
    POST /checkout
    DELETE /cart
    """
    request = normalize_request(
        {
            "request": {
                "method": "POST",
                "path": "/checkout",
                "headers": {"Authorization": "Bearer "},
                "body": {},
            }
        },
        [
            EndpointReference(name="Add to cart", method="POST", path="/cart", body={"productId": "{{customProductId}}", "quantity": 1}),
            EndpointReference(name="Delete cart", method="DELETE", path="/cart/{id}"),
            EndpointReference(name="Checkout", method="POST", path="/checkout"),
        ],
        EndpointSummary(name="Checkout", method="POST", path="/checkout", url="/checkout", auth_type="bearer", headers={}, params={}, body={}),
        docs,
    )

    assert [(step["method"], step["path"], step["name"]) for step in request["dependencies"]["before"]] == [
        ("POST", "/auth/register", "Register dynamic user"),
        ("POST", "/auth/login", "Login and capture auth token"),
        ("POST", "/auth/login", "Login as admin"),
        ("POST", "/products", "Create product for checkout"),
        ("POST", "/cart", "Create or add cart item"),
    ]
    assert request["dependencies"]["before"][3]["headers"]["Authorization"] == "Bearer {{adminAccessToken}}"
    assert request["dependencies"]["before"][3]["extract"]["customProductId"] == "$.product.id"
    assert request["dependencies"]["before"][4]["headers"]["Authorization"] == "Bearer {{accessToken}}"
    assert request["headers"]["Authorization"] == "Bearer {{accessToken}}"


def test_read_json_path_supports_array_indexes():
    assert read_json_path({"data": [{"id": "p1"}]}, "$.data.0.id") == "p1"


def test_product_response_extracts_nested_product_id_aliases():
    response = httpx.Response(201, json={"product": {"id": "prod-1"}})
    context = {}
    recorded = {}

    extract_values(response, {"customProductId": "$.product.id"}, context, recorded)

    assert context["customProductId"] == "prod-1"
    assert context["productId"] == "prod-1"
    assert context["firstProductId"] == "prod-1"


def test_missing_auth_case_drops_dependencies_and_authorization():
    request = normalize_request(
        {
            "name": "Missing authentication",
            "category": "security",
            "request": {
                "method": "GET",
                "path": "/orders",
                "headers": {"Authorization": "Bearer {{accessToken}}"},
            },
        },
        [EndpointReference(name="Login", method="POST", path="/auth/login"), EndpointReference(name="Orders", method="GET", path="/orders")],
        EndpointSummary(name="Orders", method="GET", path="/orders", url="/orders", auth_type="bearer", headers={}, params={}, body={}),
    )

    assert request["dependencies"] == {"before": [], "after": []}
    assert "Authorization" not in request["headers"]


def test_deterministic_provider_generates_basic_to_medium_security_coverage():
    endpoint = EndpointSummary(
        name="Update profile",
        method="POST",
        path="/profile/{id}",
        url="/profile/{id}",
        auth_type="bearer",
        headers={"Authorization": "Bearer {{accessToken}}"},
        params={},
        body={"email": "user@example.com", "name": "Aero"},
    )

    generated = asyncio.run(DeterministicProvider("demo", "demo").generate_tests(endpoint, "deep"))
    tests = generated["tests"]
    names = {item["name"] for item in tests}
    security_names = {item["name"] for item in tests if item["category"] == "security"}

    assert len(tests) >= 16
    assert "Sensitive field exposure regression" in names
    assert {
        "Missing authentication",
        "Invalid bearer token rejection",
        "Privilege escalation role override",
        "SQL injection probe",
        "IDOR identifier mutation",
        "Reflected script payload",
        "Path traversal input",
        "Mass assignment payload",
        "ORM bypass object payload",
        "HTTP method tampering",
        "Prototype pollution payload",
        "Oversized nested payload",
    }.issubset(security_names)
