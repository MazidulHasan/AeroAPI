import csv
import io
import json
import re
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
    dependencies = override.get("dependencies", {}) if isinstance(override.get("dependencies"), dict) else {}
    before = dependencies.get("before", []) or []
    after = dependencies.get("after", []) or []
    main_item = postman_request_item(test, endpoint, override)
    if before or after:
        items = []
        items.extend(postman_dependency_item(step, f"Setup {index + 1}") for index, step in enumerate(before) if isinstance(step, dict))
        items.append(main_item)
        items.extend(postman_dependency_item(step, f"Cleanup {index + 1}") for index, step in enumerate(after) if isinstance(step, dict))
        return {
            "name": f"{test.severity.upper()} - {test.name}",
            "description": f"Dependency-aware case. Category: {test.category}. Severity: {test.severity}.",
            "item": items,
        }
    return main_item


def postman_request_item(test: models.GeneratedTest, endpoint: models.Endpoint, override: dict) -> dict:
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


def postman_dependency_item(step: dict, fallback_name: str) -> dict:
    method = str(step.get("method", "GET")).upper()
    path = str(step.get("path", "/"))
    query = step.get("query", {}) if isinstance(step.get("query"), dict) else {}
    headers = normalize_headers(step.get("headers", {}) if isinstance(step.get("headers"), dict) else {})
    body = step.get("body")
    item = {
        "name": step.get("name") or fallback_name,
        "event": [
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": dynamic_variable_script()}},
            {"listen": "test", "script": {"type": "text/javascript", "exec": dependency_test_script(step)}},
        ],
        "request": {
            "method": method,
            "header": headers,
            "url": postman_url(path, query),
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
    return dynamic_variable_script() + [
        f"// AeroAPI generated case: {js_string(test.name)}",
        f"// Category: {js_string(test.category)} | Severity: {js_string(test.severity)}",
        "pm.variables.set('aeroapi_run_at', new Date().toISOString());",
        "if (!pm.collectionVariables.get('baseUrl') && !pm.environment.get('baseUrl')) {",
        "  console.warn('Set baseUrl as a collection or environment variable before running this request.');",
        "}",
    ]


def dynamic_variable_script() -> list[str]:
    return [
        "const aeroapiSuffix = Date.now();",
        "if (!pm.collectionVariables.get('dynamicEmail')) pm.collectionVariables.set('dynamicEmail', `aeroapi_${aeroapiSuffix}@example.com`);",
        "if (!pm.collectionVariables.get('dynamicPassword')) pm.collectionVariables.set('dynamicPassword', `Pass123!${String(aeroapiSuffix).slice(-6)}`);",
        "if (!pm.collectionVariables.get('dynamicFirstName')) pm.collectionVariables.set('dynamicFirstName', 'Aero');",
        "if (!pm.collectionVariables.get('dynamicLastName')) pm.collectionVariables.set('dynamicLastName', 'Tester');",
        "if (!pm.collectionVariables.get('dynamicProductName')) pm.collectionVariables.set('dynamicProductName', `AeroAPI Test Product ${aeroapiSuffix}`);",
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


def dependency_test_script(step: dict) -> list[str]:
    lines = [
        "pm.test('Dependency request completed successfully', function () {",
        "  pm.expect(pm.response.code).to.be.below(400);",
        "});",
    ]
    extract = step.get("extract") if isinstance(step.get("extract"), dict) else {}
    if extract:
        lines.extend(
            [
                "let aeroapiJson = {};",
                "try { aeroapiJson = pm.response.json(); } catch (error) { aeroapiJson = {}; }",
                "function aeroapiReadPath(source, parts) {",
                "  return parts.reduce(function (current, part) { return current === null || current === undefined ? undefined : current[part]; }, source);",
                "}",
            ]
        )
        for variable, path in extract.items():
            lines.extend(postman_extract_lines(str(variable), str(path)))
    else:
        lines.extend(
            [
                "let aeroapiJson = {};",
                "try { aeroapiJson = pm.response.json(); } catch (error) { aeroapiJson = {}; }",
                "['token', 'accessToken', 'access_token', 'cartId', 'cart_id', 'checkoutId', 'orderId', 'id'].forEach(function (key) {",
                "  if (aeroapiJson[key] !== undefined) pm.collectionVariables.set(key, String(aeroapiJson[key]));",
                "});",
                "if (aeroapiJson.accessToken !== undefined && !pm.collectionVariables.get('token')) pm.collectionVariables.set('token', String(aeroapiJson.accessToken));",
                "if (aeroapiJson.token !== undefined && !pm.collectionVariables.get('accessToken')) pm.collectionVariables.set('accessToken', String(aeroapiJson.token));",
            ]
        )
    return lines


def postman_extract_lines(variable: str, path: str) -> list[str]:
    if path.lower().startswith("header."):
        header = path.split(".", 1)[1]
        return [
            f"const {safe_js_identifier(variable)} = pm.response.headers.get('{js_string(header)}');",
            f"if ({safe_js_identifier(variable)} !== null && {safe_js_identifier(variable)} !== undefined) pm.collectionVariables.set('{js_string(variable)}', String({safe_js_identifier(variable)}));",
            *postman_alias_lines(variable, safe_js_identifier(variable)),
        ]
    parts = [part for part in path.removeprefix("$.").split(".") if part]
    accessor = f"aeroapiReadPath(aeroapiJson, {json.dumps(parts)})"
    identifier = safe_js_identifier(variable)
    return [
        f"const {identifier} = {accessor};",
        f"if ({identifier} !== null && {identifier} !== undefined) pm.collectionVariables.set('{js_string(variable)}', String({identifier}));",
        *postman_alias_lines(variable, identifier),
    ]


def postman_alias_lines(variable: str, identifier: str) -> list[str]:
    lines = []
    if variable in {"accessToken", "access_token"}:
        lines.append(f"if ({identifier} !== null && {identifier} !== undefined && !pm.collectionVariables.get('token')) pm.collectionVariables.set('token', String({identifier}));")
    if variable == "token":
        lines.append(f"if ({identifier} !== null && {identifier} !== undefined && !pm.collectionVariables.get('accessToken')) pm.collectionVariables.set('accessToken', String({identifier}));")
    if variable in {"customProductId", "productId", "firstProductId"}:
        lines.extend(
            [
                f"if ({identifier} !== null && {identifier} !== undefined && !pm.collectionVariables.get('customProductId')) pm.collectionVariables.set('customProductId', String({identifier}));",
                f"if ({identifier} !== null && {identifier} !== undefined && !pm.collectionVariables.get('productId')) pm.collectionVariables.set('productId', String({identifier}));",
                f"if ({identifier} !== null && {identifier} !== undefined && !pm.collectionVariables.get('firstProductId')) pm.collectionVariables.set('firstProductId', String({identifier}));",
            ]
        )
    return lines


def safe_js_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_$]", "_", value)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"value_{cleaned}"
    return cleaned


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
