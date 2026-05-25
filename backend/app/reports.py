import csv
import io
import json

import httpx
from sqlalchemy.orm import Session

from app import models


def collect_results(db: Session, run_id: int) -> list[dict]:
    rows = (
        db.query(models.TestResult, models.GeneratedTest, models.Endpoint)
        .join(models.GeneratedTest, models.GeneratedTest.id == models.TestResult.generated_test_id)
        .join(models.Endpoint, models.Endpoint.id == models.GeneratedTest.endpoint_id)
        .filter(models.TestResult.test_run_id == run_id)
        .order_by(models.Endpoint.path, models.GeneratedTest.category)
        .all()
    )
    return [
        {
            "result": result,
            "test": test,
            "endpoint": endpoint,
            "request": json.loads(result.request_json),
            "response_headers": json.loads(result.response_headers_json),
        }
        for result, test, endpoint in rows
    ]


def render_html_report(db: Session, run_id: int) -> str:
    run = db.get(models.TestRun, run_id)
    rows = collect_results(db, run_id)
    body = "\n".join(
        f"""
        <section class="case {item['result'].status}">
          <h2>{item['endpoint'].method} {item['endpoint'].path} - {item['test'].name}</h2>
          <p><strong>Status:</strong> {item['result'].status} | <strong>Severity:</strong> {item['test'].severity} | <strong>Latency:</strong> {item['result'].latency_ms}ms</p>
          <p>{item['result'].finding_summary}</p>
          <h3>Request</h3><pre>{json.dumps(item['request'], indent=2)}</pre>
          <h3>Response</h3><pre>HTTP {item['result'].response_status}\n{item['result'].response_body_preview}</pre>
          <h3>Suggested fix</h3><p>{item['result'].suggested_fix}</p>
        </section>
        """
        for item in rows
    )
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>AeroAPI Report #{run_id}</title>
        <style>
          body {{ font-family: Inter, Arial, sans-serif; margin: 32px; color: #111827; }}
          header {{ border-bottom: 1px solid #d1d5db; margin-bottom: 24px; }}
          .summary {{ display: flex; gap: 16px; flex-wrap: wrap; }}
          .metric {{ border: 1px solid #d1d5db; padding: 12px; min-width: 120px; }}
          .case {{ border-top: 1px solid #e5e7eb; padding: 18px 0; }}
          .failed h2, .error h2 {{ color: #b91c1c; }}
          .warning h2 {{ color: #b45309; }}
          pre {{ background: #111827; color: #f9fafb; padding: 12px; overflow-x: auto; }}
        </style>
      </head>
      <body>
        <header>
          <h1>AeroAPI Report #{run_id}</h1>
          <div class="summary">
            <div class="metric">Status<br><strong>{run.status}</strong></div>
            <div class="metric">Passed<br><strong>{run.passed_count}</strong></div>
            <div class="metric">Failed<br><strong>{run.failed_count}</strong></div>
            <div class="metric">Security<br><strong>{run.security_count}</strong></div>
            <div class="metric">Regressions<br><strong>{run.regression_count}</strong></div>
          </div>
        </header>
        {body}
      </body>
    </html>
    """


def render_csv_report(db: Session, run_id: int) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["endpoint", "method", "test", "category", "severity", "status", "response_status", "latency_ms", "finding", "suggested_fix"])
    for item in collect_results(db, run_id):
        writer.writerow(
            [
                item["endpoint"].path,
                item["endpoint"].method,
                item["test"].name,
                item["test"].category,
                item["test"].severity,
                item["result"].status,
                item["result"].response_status,
                item["result"].latency_ms,
                item["result"].finding_summary,
                item["result"].suggested_fix,
            ]
        )
    return output.getvalue()


async def send_slack_alert(db: Session, run_id: int, webhook_url: str) -> dict:
    run = db.get(models.TestRun, run_id)
    text = (
        f"AeroAPI run #{run_id} completed: {run.failed_count} failed, "
        f"{run.security_count} security findings, {run.regression_count} regressions."
    )
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json={"text": text})
    return {"ok": response.status_code < 300, "status_code": response.status_code}
