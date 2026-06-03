import csv
import html
import io
import json
import re
from collections import Counter
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
    status_counts = Counter(item["result"].status for item in rows)
    category_counts = Counter(item["test"].category for item in rows)
    severity_counts = Counter(item["test"].severity for item in rows)
    security_tests = category_counts.get("security", 0)
    regression_tests = category_counts.get("regression", 0)
    failure_rate = round((run.failed_count / run.completed_tests) * 100, 1) if run.completed_tests else 0
    body = "\n".join(render_html_case(item) for item in rows)
    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>AeroAPI Report #{run_id}</title>
        <style>
          :root {{ color-scheme: light; --ink: #111827; --muted: #64748b; --line: #dbe3ee; --panel: #f8fafc; --ok: #047857; --bad: #b91c1c; --warn: #b45309; --info: #0369a1; }}
          * {{ box-sizing: border-box; }}
          body {{ margin: 0; background: #f3f7fb; color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }}
          header {{ background: #ffffff; border-bottom: 1px solid var(--line); padding: 28px clamp(18px, 4vw, 48px); }}
          main {{ padding: 24px clamp(18px, 4vw, 48px) 48px; }}
          h1 {{ margin: 0; font-size: clamp(26px, 4vw, 40px); line-height: 1.1; letter-spacing: 0; }}
          h2, h3 {{ margin: 0; letter-spacing: 0; }}
          .muted {{ color: var(--muted); }}
          .topline {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 18px; }}
          .badge {{ display: inline-flex; align-items: center; min-height: 28px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); padding: 4px 10px; font-size: 12px; font-weight: 700; text-transform: uppercase; }}
          .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }}
          .metric {{ border: 1px solid var(--line); border-radius: 8px; background: #ffffff; padding: 14px; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06); }}
          .metric strong {{ display: block; margin-bottom: 4px; font-size: 26px; line-height: 1; }}
          .metric span {{ color: var(--muted); font-size: 12px; font-weight: 700; text-transform: uppercase; }}
          .insights, .toolbar, .case {{ border: 1px solid var(--line); border-radius: 8px; background: #ffffff; box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06); }}
          .insights {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px; padding: 16px; }}
          .insight {{ border-left: 3px solid #38bdf8; padding-left: 12px; }}
          .insight strong {{ display: block; margin-bottom: 4px; }}
          .toolbar {{ position: sticky; top: 0; z-index: 2; display: grid; grid-template-columns: minmax(180px, 1fr) repeat(3, minmax(130px, 180px)); gap: 10px; margin-bottom: 16px; padding: 12px; }}
          input, select {{ min-height: 40px; width: 100%; border: 1px solid var(--line); border-radius: 6px; background: #ffffff; padding: 8px 10px; color: var(--ink); font: inherit; font-size: 14px; }}
          .case {{ margin-bottom: 12px; overflow: hidden; }}
          .case[hidden] {{ display: none; }}
          .case-header {{ display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; border-bottom: 1px solid var(--line); padding: 14px; }}
          .case-title {{ font-size: 15px; }}
          .case-meta {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
          .pill {{ border-radius: 999px; padding: 4px 8px; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
          .passed {{ background: #dcfce7; color: #166534; }}
          .failed, .error {{ background: #fee2e2; color: #991b1b; }}
          .warning {{ background: #fef3c7; color: #92400e; }}
          .info {{ background: #e0f2fe; color: #075985; }}
          .case-body {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; padding: 14px; }}
          .finding {{ grid-column: 1 / -1; display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
          .note {{ border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 12px; }}
          .note h3 {{ margin-bottom: 6px; font-size: 12px; color: var(--muted); text-transform: uppercase; }}
          pre {{ max-height: 360px; overflow: auto; border-radius: 8px; background: #0f172a; color: #e2e8f0; padding: 12px; font-size: 12px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; }}
          @media (max-width: 840px) {{ .toolbar, .case-body {{ grid-template-columns: 1fr; }} .case-header {{ grid-template-columns: 1fr; }} }}
        </style>
      </head>
      <body>
        <header>
          <div class="topline">
            <div>
              <h1>AeroAPI Report #{run_id}</h1>
              <p class="muted">Completed tests, findings, regression signal, and request/response evidence.</p>
            </div>
            <span class="badge">{h(run.status)}</span>
          </div>
          <div class="summary">
            <div class="metric"><strong>{run.completed_tests}/{run.total_tests}</strong><span>Executed</span></div>
            <div class="metric"><strong>{run.passed_count}</strong><span>Passed</span></div>
            <div class="metric"><strong>{run.failed_count}</strong><span>Failed</span></div>
            <div class="metric"><strong>{run.security_count}</strong><span>Security findings</span></div>
            <div class="metric"><strong>{run.regression_count}</strong><span>Regressions found</span></div>
            <div class="metric"><strong>{failure_rate}%</strong><span>Failure rate</span></div>
          </div>
        </header>
        <main>
          <section class="insights">
            <div class="insight"><strong>Security coverage</strong><span class="muted">{security_tests} security probe(s) ran. The security finding count only rises when one is accepted, warns, or fails.</span></div>
            <div class="insight"><strong>Regression context</strong><span class="muted">{regression_tests} regression-oriented test(s) ran. A regression is counted when a test that passed in the previous completed run now fails.</span></div>
            <div class="insight"><strong>Result mix</strong><span class="muted">{format_counter(status_counts) or "No result statuses recorded."}</span></div>
            <div class="insight"><strong>Severity mix</strong><span class="muted">{format_counter(severity_counts) or "No severities recorded."}</span></div>
          </section>
          <section class="toolbar" aria-label="Report filters">
            <input id="search" type="search" placeholder="Search endpoint, test, finding, fix" />
            <select id="status"><option value="">All statuses</option>{options_for(status_counts)}</select>
            <select id="category"><option value="">All categories</option>{options_for(category_counts)}</select>
            <select id="severity"><option value="">All severities</option>{options_for(severity_counts)}</select>
          </section>
          <div id="resultCount" class="muted" style="margin: 0 0 12px 2px;">Showing {len(rows)} result(s)</div>
          {body or '<section class="case"><div class="case-header"><h2 class="case-title">No results recorded yet</h2></div></section>'}
        </main>
        <script>
          const controls = ["search", "status", "category", "severity"].map((id) => document.getElementById(id));
          const cases = Array.from(document.querySelectorAll(".case[data-search]"));
          const resultCount = document.getElementById("resultCount");
          function applyFilters() {{
            const [search, status, category, severity] = controls.map((control) => control.value.toLowerCase());
            let visible = 0;
            cases.forEach((item) => {{
              const matches = (!search || item.dataset.search.includes(search))
                && (!status || item.dataset.status === status)
                && (!category || item.dataset.category === category)
                && (!severity || item.dataset.severity === severity);
              item.hidden = !matches;
              if (matches) visible += 1;
            }});
            resultCount.textContent = `Showing ${{visible}} of ${{cases.length}} result(s)`;
          }}
          controls.forEach((control) => control.addEventListener("input", applyFilters));
        </script>
      </body>
    </html>
    """


def render_html_case(item: dict) -> str:
    result = item["result"]
    test = item["test"]
    endpoint = item["endpoint"]
    request = json.dumps(item["request"], indent=2)
    response = f"HTTP {result.response_status if result.response_status is not None else '-'}\n{result.response_body_preview or ''}"
    searchable = " ".join(
        str(value)
        for value in [
            endpoint.method,
            endpoint.path,
            test.name,
            test.category,
            test.severity,
            result.status,
            result.finding_summary,
            result.suggested_fix,
            test.ai_reasoning,
        ]
    ).lower()
    return f"""
      <section class="case" data-status="{h(result.status.lower())}" data-category="{h(test.category.lower())}" data-severity="{h(test.severity.lower())}" data-search="{h(searchable)}">
        <div class="case-header">
          <div>
            <h2 class="case-title">{h(endpoint.method)} {h(endpoint.path)} - {h(test.name)}</h2>
            <div class="case-meta">
              <span class="pill {h(result.status)}">{h(result.status)}</span>
              <span class="pill info">{h(test.category)}</span>
              <span class="pill info">{h(test.severity)}</span>
              <span class="pill info">HTTP {h(result.response_status if result.response_status is not None else "-")}</span>
              <span class="pill info">{h(result.latency_ms)}ms</span>
            </div>
          </div>
        </div>
        <div class="case-body">
          <div><h3 class="muted">Request</h3><pre>{h(request)}</pre></div>
          <div><h3 class="muted">Response</h3><pre>{h(response)}</pre></div>
          <div class="finding">
            <div class="note"><h3>Finding</h3><p>{h(result.finding_summary)}</p></div>
            <div class="note"><h3>Suggested fix</h3><p>{h(result.suggested_fix)}</p></div>
            <div class="note"><h3>Reasoning</h3><p>{h(test.ai_reasoning)}</p></div>
          </div>
        </div>
      </section>
    """


def h(value) -> str:
    return html.escape(str(value), quote=True)


def format_counter(counter: Counter) -> str:
    return ", ".join(f"{key}: {value}" for key, value in sorted(counter.items()))


def options_for(counter: Counter) -> str:
    return "".join(f'<option value="{h(key)}">{h(key)} ({value})</option>' for key, value in sorted(counter.items()))


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
