import asyncio
from datetime import datetime

from app import models
from app.database import SessionLocal
from app.runner import run_generated_tests
from app.test_generation import generate_for_endpoint


CANCELLED_RUNS: set[int] = set()


def cancel_run(run_id: int) -> None:
    CANCELLED_RUNS.add(run_id)


async def execute_run(
    run_id: int,
    api_token: str,
    base_url_override: str | None,
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
            generated.extend(
                await generate_for_endpoint(
                    db=db,
                    run_id=run.id,
                    endpoint=endpoint,
                    provider_name=run.provider,
                    model=run.model,
                    api_token=api_token,
                    intensity=intensity,
                    custom_base_url=custom_base_url,
                )
            )
            run.total_tests = len(generated)
            db.commit()
            await asyncio.sleep(0)

        run.status = "running"
        run.stage = "executing requests"
        db.commit()
        await run_generated_tests(db, run, generated, base_url_override, timeout_seconds, concurrency)

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
