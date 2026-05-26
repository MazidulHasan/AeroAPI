import asyncio
import json
import time
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.security import redact


async def run_generated_tests(
    db: Session,
    run: models.TestRun,
    generated_tests: list[models.GeneratedTest],
    base_url_override: str | None,
    timeout_seconds: int,
    concurrency: int,
) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        tasks = [
            execute_one(run.id, test, client, semaphore, base_url_override)
            for test in generated_tests
        ]
        await asyncio.gather(*tasks)


async def execute_one(
    run_id: int,
    test: models.GeneratedTest,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_url_override: str | None,
) -> models.TestResult:
    async with semaphore:
        override = json.loads(test.request_override_json)
        method = override.get("method", "GET").upper()
        path = override.get("path", "/")
        url = build_url(base_url_override, path)
        headers = override.get("headers", {})
        query = override.get("query", {})
        body = override.get("body")
        started = time.perf_counter()
        response_status = None
        response_headers = {}
        body_preview = ""
        status = "warning"
        finding = "Request was prepared but no base URL was supplied."
        suggested = "Set a base URL override before running live tests."

        if base_url_override:
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

        latency_ms = int((time.perf_counter() - started) * 1000)
        db = SessionLocal()
        try:
            result = models.TestResult(
                test_run_id=run_id,
                generated_test_id=test.id,
                status=status,
                request_json=json.dumps(redact({"method": method, "url": url, "headers": headers, "query": query, "body": body})),
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
