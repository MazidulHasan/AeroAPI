import asyncio
import json

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import Session

from app import models
from app.collections import find_base_url, parse_collection, parse_environment, parse_json_bytes
from app.database import get_db, init_db
from app.jobs import cancel_run, execute_run
from app.reports import collect_results, render_csv_report, render_html_report, render_postman_collection, send_slack_alert
from app.schemas import CollectionUploadResponse, EndpointSummary, ResultRow, RunCreate, RunSummary


app = FastAPI(title="AeroAPI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "AeroAPI", "generation_fallback": True}


@app.post("/api/collections/upload", response_model=CollectionUploadResponse)
async def upload_collection(
    collection_file: UploadFile = File(...),
    env_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> CollectionUploadResponse:
    raw = await collection_file.read()
    collection_json = parse_json_bytes(raw, "collection")
    env_json = parse_json_bytes(await env_file.read(), "environment") if env_file else None
    env_vars = parse_environment(env_json)
    name, endpoints, variables = parse_collection(collection_json, env_vars)
    merged_variables = variables | env_vars
    project = ensure_project(db)
    if not project.base_url:
        project.base_url = find_base_url(merged_variables)
    collection = models.Collection(
        project_id=project.id,
        name=name,
        raw_json=json.dumps(collection_json),
        env_json=json.dumps(env_json) if env_json else None,
        parsed_summary=json.dumps({"endpoint_count": len(endpoints), "variables": merged_variables, "base_url": project.base_url}),
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)

    endpoint_rows = []
    for endpoint in endpoints:
        row = models.Endpoint(
            collection_id=collection.id,
            name=endpoint.name,
            method=endpoint.method,
            path=endpoint.path,
            url=endpoint.url,
            auth_type=endpoint.auth_type,
            headers_json=json.dumps(endpoint.headers),
            params_json=json.dumps(endpoint.params),
            body_json=json.dumps(endpoint.body),
        )
        db.add(row)
        endpoint_rows.append((row, endpoint))
    db.commit()
    for row, endpoint in endpoint_rows:
        db.refresh(row)
        endpoint.id = row.id

    return CollectionUploadResponse(
        collection_id=collection.id,
        name=name,
        endpoint_count=len(endpoints),
        endpoints=endpoints,
        variables=merged_variables,
    )


@app.post("/api/runs", response_model=RunSummary)
async def create_run(payload: RunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> RunSummary:
    collection = db.get(models.Collection, payload.collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    run = models.TestRun(
        project_id=collection.project_id,
        collection_id=collection.id,
        provider=payload.provider,
        model=payload.model,
        api_docs=payload.api_docs,
        status="pending",
        stage="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(
        execute_run,
        run.id,
        payload.api_token,
        payload.base_url_override,
        payload.api_docs,
        payload.test_intensity,
        payload.timeout_seconds,
        payload.concurrency,
        payload.custom_base_url,
    )
    return to_run_summary(run)


@app.get("/api/runs", response_model=list[RunSummary])
def list_runs(db: Session = Depends(get_db)) -> list[RunSummary]:
    runs = db.query(models.TestRun).order_by(models.TestRun.created_at.desc()).limit(50).all()
    return [to_run_summary(run) for run in runs]


@app.get("/api/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: int, db: Session = Depends(get_db)) -> RunSummary:
    run = db.get(models.TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return to_run_summary(run)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: int):
    async def stream():
        while True:
            db = next(get_db())
            try:
                run = db.get(models.TestRun, run_id)
                if not run:
                    yield "event: error\ndata: {\"detail\":\"Run not found\"}\n\n"
                    return
                data = to_run_summary(run).model_dump_json()
                yield f"event: progress\ndata: {data}\n\n"
                if run.status in {"completed", "failed", "cancelled"}:
                    return
            finally:
                db.close()
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/runs/{run_id}/cancel", response_model=RunSummary)
def cancel(run_id: int, db: Session = Depends(get_db)) -> RunSummary:
    run = db.get(models.TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    cancel_run(run_id)
    run.status = "cancelled"
    run.stage = "cancel requested"
    db.commit()
    db.refresh(run)
    return to_run_summary(run)


@app.get("/api/runs/{run_id}/results", response_model=list[ResultRow])
def get_results(run_id: int, db: Session = Depends(get_db)) -> list[ResultRow]:
    if not db.get(models.TestRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    rows = []
    for item in collect_results(db, run_id):
        endpoint = item["endpoint"]
        test = item["test"]
        result = item["result"]
        rows.append(
            ResultRow(
                id=result.id,
                endpoint=EndpointSummary(
                    id=endpoint.id,
                    name=endpoint.name,
                    method=endpoint.method,
                    path=endpoint.path,
                    url=endpoint.url,
                    auth_type=endpoint.auth_type,
                    headers=json.loads(endpoint.headers_json),
                    params=json.loads(endpoint.params_json),
                    body=json.loads(endpoint.body_json),
                ),
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                status=result.status,
                request=item["request"],
                response_status=result.response_status,
                response_headers=item["response_headers"],
                response_body_preview=result.response_body_preview,
                latency_ms=result.latency_ms,
                finding_summary=result.finding_summary,
                suggested_fix=result.suggested_fix,
                ai_reasoning=test.ai_reasoning,
            )
        )
    return rows


@app.get("/api/runs/{run_id}/export/html")
def export_html(run_id: int, db: Session = Depends(get_db)) -> HTMLResponse:
    if not db.get(models.TestRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return HTMLResponse(render_html_report(db, run_id), headers={"Content-Disposition": f"attachment; filename=aeroapi-run-{run_id}.html"})


@app.get("/api/runs/{run_id}/export/csv")
def export_csv(run_id: int, db: Session = Depends(get_db)) -> PlainTextResponse:
    if not db.get(models.TestRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return PlainTextResponse(render_csv_report(db, run_id), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=aeroapi-run-{run_id}.csv"})


@app.get("/api/runs/{run_id}/export/postman")
def export_postman(run_id: int, db: Session = Depends(get_db)) -> JSONResponse:
    if not db.get(models.TestRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse(
        render_postman_collection(db, run_id),
        headers={"Content-Disposition": f"attachment; filename=aeroapi-run-{run_id}.postman_collection.json"},
    )


@app.post("/api/runs/{run_id}/slack")
async def slack(run_id: int, webhook_url: str, db: Session = Depends(get_db)) -> dict:
    if not db.get(models.TestRun, run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    return await send_slack_alert(db, run_id, webhook_url)


def ensure_project(db: Session) -> models.Project:
    project = db.query(models.Project).first()
    if project:
        return project
    project = models.Project(name="Default Project")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def to_run_summary(run: models.TestRun) -> RunSummary:
    return RunSummary(
        id=run.id,
        status=run.status,
        stage=run.stage,
        provider=run.provider,
        model=run.model,
        total_endpoints=run.total_endpoints,
        total_tests=run.total_tests,
        completed_tests=run.completed_tests,
        passed_count=run.passed_count,
        failed_count=run.failed_count,
        security_count=run.security_count,
        regression_count=run.regression_count,
        error_message=run.error_message,
    )
