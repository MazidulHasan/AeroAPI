import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.reports import render_postman_collection


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
