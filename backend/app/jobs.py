import asyncio
import json
from datetime import datetime

from app import models
from app.database import SessionLocal
from app.providers import DeterministicProvider, ProviderRateLimitError
from app.runner import run_generated_tests
from app.test_generation import generate_for_endpoint
from app.schemas import EndpointSummary
from sqlalchemy.orm import Session


CANCELLED_RUNS: set[int] = set()


def cancel_run(run_id: int) -> None:
    CANCELLED_RUNS.add(run_id)


async def execute_run(
    run_id: int,
    api_token: str,
    base_url_override: str | None,
    api_docs: str | None,
    intensity: str,
    timeout_seconds: int,
    concurrency: int,
    custom_base_url: str | None,
) -> None:
    db = SessionLocal()
    try:
        run = db.get(models.TestRun, run_id)
        if not run:
            return
        run.status = "parsing"
        run.stage = "parsing collection"
        run.started_at = datetime.utcnow()
        db.commit()

        endpoints = db.query(models.Endpoint).filter(models.Endpoint.collection_id == run.collection_id).all()
        run.total_endpoints = len(endpoints)
        run.status = "generating"
        run.stage = "generating AI tests"
        db.commit()

        generated = []
        for endpoint in endpoints:
            if run_id in CANCELLED_RUNS:
                mark_cancelled(db, run)
                return
            try:
                endpoint_tests = await generate_for_endpoint(
                    db=db,
                    run_id=run.id,
                    endpoint=endpoint,
                    provider_name=run.provider,
                    model=run.model,
                    api_token=api_token,
                    api_docs=api_docs or run.api_docs,
                    intensity=intensity,
                    custom_base_url=custom_base_url,
                )
            except json.JSONDecodeError:
                endpoint_tests = await generate_deterministic_for_endpoint(
                    db=db,
                    run_id=run.id,
                    endpoint=endpoint,
                    model=run.model,
                    api_token=api_token,
                    intensity=intensity,
                    custom_base_url=custom_base_url,
                    fallback_reason="Provider returned malformed JSON.",
                )
            except ProviderRateLimitError:
                endpoint_tests = await generate_deterministic_for_endpoint(
                    db=db,
                    run_id=run.id,
                    endpoint=endpoint,
                    model=run.model,
                    api_token=api_token,
                    intensity=intensity,
                    custom_base_url=custom_base_url,
                    fallback_reason="Provider rate limit was reached.",
                )
            generated.extend(endpoint_tests)
            run.total_tests = len(generated)
            db.commit()
            await asyncio.sleep(0)

        run.status = "running"
        run.stage = "executing requests"
        db.commit()
        await run_generated_tests(db, run, generated, base_url_override or run.collection.project.base_url, timeout_seconds, concurrency)

        if run_id in CANCELLED_RUNS:
            mark_cancelled(db, run)
            return
        run.status = "completed"
        run.stage = "report ready"
        run.completed_at = datetime.utcnow()
        db.commit()
    except Exception as exc:
        run = db.get(models.TestRun, run_id)
        if run:
            run.status = "failed"
            run.stage = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def mark_cancelled(db, run: models.TestRun) -> None:
    run.status = "cancelled"
    run.stage = "cancelled"
    run.completed_at = datetime.utcnow()
    db.commit()


async def generate_deterministic_for_endpoint(
    db: Session,
    run_id: int,
    endpoint: models.Endpoint,
    model: str,
    api_token: str,
    intensity: str,
    custom_base_url: str | None,
    fallback_reason: str,
) -> list[models.GeneratedTest]:
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
    generated = await DeterministicProvider(model, api_token, custom_base_url).generate_tests(endpoint_summary, intensity)
    rows = []
    for item in generated["tests"][:12]:
        expected = item.get("expected", {})
        row = models.GeneratedTest(
            test_run_id=run_id,
            endpoint_id=endpoint.id,
            name=item["name"],
            category=item["category"],
            severity=item["severity"],
            request_override_json=json.dumps(item["request"]),
            expected_behavior=json.dumps(expected),
            ai_reasoning=f"{item['reasoning']} {fallback_reason} AeroAPI used local deterministic generation.",
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
