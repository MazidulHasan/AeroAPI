import csv
import io
import json
from urllib.parse import urlencode, urlparse

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


def render_postman_collection(db: Session, run_id: int) -> dict:
    run = db.get(models.TestRun, run_id)
    if not run:
        return {}
    rows = (
        db.query(models.GeneratedTest, models.Endpoint)
        .join(models.Endpoint, models.Endpoint.id == models.GeneratedTest.endpoint_id)
        .filter(models.GeneratedTest.test_run_id == run_id)
        .order_by(models.Endpoint.path, models.GeneratedTest.category, models.GeneratedTest.name)
        .all()
    )
    grouped: dict[int, dict] = {}
    for test, endpoint in rows:
        folder = grouped.setdefault(
            endpoint.id,
            {
                "name": f"{endpoint.method} {endpoint.path}",
                "item": [],
            },
        )
        folder["item"].append(postman_item_for_test(test, endpoint, run))

    base_url = run.collection.project.base_url if run.collection and run.collection.project else None
    return {
        "info": {
            "name": f"AeroAPI Generated Tests - Run {run_id}",
            "_postman_id": f"aeroapi-run-{run_id}",
            "description": "Generated by AeroAPI. Import into Postman and run with a matching environment.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": list(grouped.values()),
        "variable": [
            {"key": "baseUrl", "value": base_url or "", "type": "string"},
        ],
    }


def postman_item_for_test(test: models.GeneratedTest, endpoint: models.Endpoint, run: models.TestRun) -> dict:
    override = json.loads(test.request_override_json)
    method = str(override.get("method") or endpoint.method).upper()
    path = str(override.get("path") or endpoint.path or "/")
    headers = normalize_headers(override.get("headers", {}))
    query = override.get("query", {})
    body = override.get("body")
    expected = parse_expected_status_codes(test.expected_behavior)
    url = postman_url(path, query)
    item = {
        "name": f"{test.severity.upper()} - {test.name}",
        "description": f"Category: {test.category}\nSeverity: {test.severity}\nReasoning: {test.ai_reasoning}",
        "event": [
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": prerequest_script(test)}},
            {"listen": "test", "script": {"type": "text/javascript", "exec": postrequest_script(test, expected)}},
        ],
        "request": {
            "method": method,
            "header": headers,
            "url": url,
        },
    }
    if body is not None and method not in {"GET", "HEAD"}:
        if not any(header["key"].lower() == "content-type" for header in headers):
            item["request"]["header"].append({"key": "Content-Type", "value": "application/json"})
        item["request"]["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return item


def normalize_headers(headers: dict) -> list[dict]:
    if not isinstance(headers, dict):
        return []
    return [{"key": str(key), "value": str(value)} for key, value in headers.items() if key]


def postman_url(path: str, query: dict) -> dict:
    parsed = urlparse(path)
    raw = path if parsed.scheme else "{{baseUrl}}" + (path if path.startswith("/") else f"/{path}")
    if isinstance(query, dict) and query:
        separator = "&" if "?" in raw else "?"
        raw = f"{raw}{separator}{urlencode(query)}"
    return {
        "raw": raw,
        "host": ["{{baseUrl}}"] if not parsed.scheme else [parsed.scheme + "://" + parsed.netloc],
        "path": [segment for segment in parsed.path.lstrip("/").split("/") if segment],
        "query": [{"key": str(key), "value": str(value)} for key, value in query.items()] if isinstance(query, dict) else [],
    }


def parse_expected_status_codes(expected_behavior: str) -> list[int]:
    if not expected_behavior:
        return []
    try:
        parsed = json.loads(expected_behavior)
        if isinstance(parsed, dict) and isinstance(parsed.get("status_codes"), list):
            return [int(code) for code in parsed["status_codes"] if isinstance(code, int | str)]
    except Exception:
        pass
    return []


def prerequest_script(test: models.GeneratedTest) -> list[str]:
    return [
        f"// AeroAPI generated case: {js_string(test.name)}",
        f"// Category: {js_string(test.category)} | Severity: {js_string(test.severity)}",
        "pm.variables.set('aeroapi_run_at', new Date().toISOString());",
        "if (!pm.collectionVariables.get('baseUrl') && !pm.environment.get('baseUrl')) {",
        "  console.warn('Set baseUrl as a collection or environment variable before running this request.');",
        "}",
    ]


def postrequest_script(test: models.GeneratedTest, expected_status_codes: list[int]) -> list[str]:
    expected = expected_status_codes or ([200, 201, 202, 204] if test.category == "functional" else [400, 401, 403, 404, 422])
    lines = [
        f"// AeroAPI reasoning: {js_string(test.ai_reasoning)}",
        f"const expectedStatusCodes = {json.dumps(expected)};",
        "pm.test('Status code matches expected behavior', function () {",
        "  pm.expect(expectedStatusCodes).to.include(pm.response.code);",
        "});",
        "pm.test('Response time is under 5 seconds', function () {",
        "  pm.expect(pm.response.responseTime).to.be.below(5000);",
        "});",
    ]
    if test.category == "security":
        lines.extend(
            [
                "pm.test('Security probe is not accepted as a normal success response', function () {",
                "  pm.expect([200, 201, 202, 204]).to.not.include(pm.response.code);",
                "});",
            ]
        )
    return lines


def js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")[:500]


async def send_slack_alert(db: Session, run_id: int, webhook_url: str) -> dict:
    run = db.get(models.TestRun, run_id)
    text = (
        f"AeroAPI run #{run_id} completed: {run.failed_count} failed, "
        f"{run.security_count} security findings, {run.regression_count} regressions."
    )
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(webhook_url, json={"text": text})
    return {"ok": response.status_code < 300, "status_code": response.status_code}
