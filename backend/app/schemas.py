from pydantic import BaseModel, Field, HttpUrl


class EndpointSummary(BaseModel):
    id: int | None = None
    name: str
    method: str
    path: str
    url: str
    auth_type: str
    headers: dict = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)
    body: dict | list | str | None = None


class EndpointReference(BaseModel):
    name: str
    method: str
    path: str
    headers: dict = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)
    body: dict | list | str | None = None


class CollectionUploadResponse(BaseModel):
    collection_id: int
    name: str
    endpoint_count: int
    endpoints: list[EndpointSummary]
    variables: dict = Field(default_factory=dict)


class RunCreate(BaseModel):
    collection_id: int
    provider: str
    model: str
    api_token: str = Field(min_length=1)
    api_docs: str | None = None
    base_url_override: str | None = None
    test_intensity: str = "standard"
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    concurrency: int = Field(default=6, ge=1, le=25)
    slack_webhook: HttpUrl | None = None
    custom_base_url: str | None = None


class RunSummary(BaseModel):
    id: int
    status: str
    stage: str
    provider: str
    model: str
    total_endpoints: int
    total_tests: int
    completed_tests: int
    passed_count: int
    failed_count: int
    security_count: int
    regression_count: int
    error_message: str | None = None


class ResultRow(BaseModel):
    id: int
    endpoint: EndpointSummary
    test_name: str
    category: str
    severity: str
    status: str
    request: dict
    response_status: int | None
    response_headers: dict
    response_body_preview: str
    latency_ms: int
    finding_summary: str
    suggested_fix: str
    ai_reasoning: str
