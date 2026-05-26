import json

from sqlalchemy.orm import Session

from app import models
from app.providers import DeterministicProvider, get_provider
from app.schemas import EndpointSummary


REQUIRED_TEST_KEYS = {"name", "category", "severity", "request", "expected", "reasoning"}


async def generate_for_endpoint(
    db: Session,
    run_id: int,
    endpoint: models.Endpoint,
    provider_name: str,
    model: str,
    api_token: str,
    api_docs: str | None,
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
        generated = await provider.generate_tests(endpoint_summary, intensity, api_docs)
    except json.JSONDecodeError:
        used_fallback = True
        generated = await DeterministicProvider(model, api_token, custom_base_url).generate_tests(endpoint_summary, intensity)
    tests = validate_generated_tests(generated)
    rows = []
    for item in tests:
        expected = item.get("expected", {})
        row = models.GeneratedTest(
            test_run_id=run_id,
            endpoint_id=endpoint.id,
            name=item["name"],
            category=item["category"],
            severity=item["severity"],
            request_override_json=json.dumps(item["request"]),
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
    return valid[:12]
