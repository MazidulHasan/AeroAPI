import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.reports import render_html_report, render_postman_collection


def test_render_postman_collection_includes_scripts():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    project = models.Project(name="Demo", base_url="https://api.example.com")
    collection = models.Collection(project=project, name="Demo API", raw_json="{}", parsed_summary="{}")
    endpoint = models.Endpoint(
        collection=collection,
        name="Create user",
        method="POST",
        path="/users",
        url="https://api.example.com/users",
        headers_json="{}",
        params_json="{}",
        body_json="{}",
    )
    run = models.TestRun(project=project, collection=collection, provider="demo", model="demo")
    session.add_all([project, collection, endpoint, run])
    session.flush()
    test = models.GeneratedTest(
        test_run_id=run.id,
        endpoint_id=endpoint.id,
        name="Create valid user",
        category="functional",
        severity="info",
        request_override_json=json.dumps({"method": "POST", "path": "/users", "body": {"email": "a@example.com"}}),
        expected_behavior=json.dumps({"status_codes": [201], "behavior": "Creates user"}),
        ai_reasoning="Validates the user signup workflow.",
    )
    session.add(test)
    session.commit()

    exported = render_postman_collection(session, run.id)

    item = exported["item"][0]["item"][0]
    assert exported["info"]["schema"].endswith("collection/v2.1.0/collection.json")
    assert item["event"][0]["listen"] == "prerequest"
    assert item["event"][1]["listen"] == "test"
    assert "expectedStatusCodes = [201]" in "\n".join(item["event"][1]["script"]["exec"])
    session.close()


def test_render_postman_collection_exports_dependency_folder():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    project = models.Project(name="Demo", base_url="https://api.example.com")
    collection = models.Collection(project=project, name="Checkout API", raw_json="{}", parsed_summary="{}")
    endpoint = models.Endpoint(
        collection=collection,
        name="Checkout",
        method="POST",
        path="/checkout",
        url="https://api.example.com/checkout",
        headers_json="{}",
        params_json="{}",
        body_json="{}",
    )
    run = models.TestRun(project=project, collection=collection, provider="demo", model="demo")
    session.add_all([project, collection, endpoint, run])
    session.flush()
    test = models.GeneratedTest(
        test_run_id=run.id,
        endpoint_id=endpoint.id,
        name="Checkout with cart token",
        category="functional",
        severity="info",
        request_override_json=json.dumps(
            {
                "method": "POST",
                "path": "/checkout",
                "headers": {"Authorization": "Bearer {{token}}"},
                "body": {"cartId": "{{cartId}}"},
                "dependencies": {
                    "before": [
                        {"name": "Login", "method": "POST", "path": "/login", "body": {"email": "a@example.com"}, "extract": {"token": "$.token"}},
                        {"name": "Create cart", "method": "POST", "path": "/cart", "headers": {"Authorization": "Bearer {{token}}"}, "extract": {"cartId": "$.id"}},
                    ],
                    "after": [
                        {"name": "Delete cart", "method": "DELETE", "path": "/cart/{{cartId}}", "headers": {"Authorization": "Bearer {{token}}"}},
                    ],
                },
            }
        ),
        expected_behavior=json.dumps({"status_codes": [200], "behavior": "Checkout succeeds"}),
        ai_reasoning="Validates checkout workflow.",
    )
    session.add(test)
    session.commit()

    exported = render_postman_collection(session, run.id)

    case_folder = exported["item"][0]["item"][0]
    assert [item["name"] for item in case_folder["item"]] == ["Login", "Create cart", "INFO - Checkout with cart token", "Delete cart"]
    setup_script = "\n".join(case_folder["item"][0]["event"][1]["script"]["exec"])
    assert "pm.collectionVariables.set('token'" in setup_script
    session.close()


def test_render_html_report_escapes_evidence_and_explains_security_counts():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    project = models.Project(name="Demo", base_url="https://api.example.com")
    collection = models.Collection(project=project, name="Demo API", raw_json="{}", parsed_summary="{}")
    endpoint = models.Endpoint(
        collection=collection,
        name="Search",
        method="GET",
        path="/search",
        url="https://api.example.com/search",
        headers_json="{}",
        params_json="{}",
        body_json="{}",
    )
    run = models.TestRun(
        project=project,
        collection=collection,
        provider="demo",
        model="demo",
        status="completed",
        total_tests=1,
        completed_tests=1,
        passed_count=1,
        security_count=0,
        regression_count=0,
    )
    session.add_all([project, collection, endpoint, run])
    session.flush()
    test = models.GeneratedTest(
        test_run_id=run.id,
        endpoint_id=endpoint.id,
        name="Reflected script payload",
        category="security",
        severity="medium",
        request_override_json=json.dumps({"method": "GET", "path": "/search", "query": {"q": "<script>alert(1)</script>"}}),
        expected_behavior=json.dumps({"status_codes": [400], "behavior": "Rejects scripts"}),
        ai_reasoning="Checks script-like input.",
    )
    session.add(test)
    session.flush()
    session.add(
        models.TestResult(
            test_run_id=run.id,
            generated_test_id=test.id,
            status="passed",
            request_json=json.dumps({"main": {"query": {"q": "<script>alert(1)</script>"}}}),
            response_status=400,
            response_headers_json="{}",
            response_body_preview="<script>alert(1)</script>",
            latency_ms=12,
            finding_summary="Security probe was rejected or constrained.",
            suggested_fix="No action needed.",
        )
    )
    session.commit()

    report = render_html_report(session, run.id)

    assert "1 security probe(s) ran" in report
    assert "Security findings</span>" in report
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in report
    assert "<script>alert(1)</script>" not in report
    assert 'id="search"' in report
    session.close()
