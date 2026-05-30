from app.runner import normalize_dependencies, render_template
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
    assert request["headers"]["Authorization"] == "Bearer {{token}}"
    assert request["body"]["cartId"] == "{{cartId}}"


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
    assert product_step["headers"]["Authorization"] == "Bearer {{token}}"
