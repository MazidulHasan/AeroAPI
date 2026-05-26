from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="Default Project")
    base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    raw_json: Mapped[str] = mapped_column(Text)
    env_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    project: Mapped[Project] = relationship()
    endpoints: Mapped[list["Endpoint"]] = relationship(cascade="all, delete-orphan")


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    name: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(2048))
    url: Mapped[str] = mapped_column(String(4096))
    auth_type: Mapped[str] = mapped_column(String(128), default="none")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    body_json: Mapped[str] = mapped_column(Text, default="{}")

    collection: Mapped[Collection] = relationship(back_populates="endpoints")


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    stage: Mapped[str] = mapped_column(String(64), default="queued")
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(255))
    api_docs: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_endpoints: Mapped[int] = mapped_column(Integer, default=0)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    completed_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    security_count: Mapped[int] = mapped_column(Integer, default=0)
    regression_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    collection: Mapped[Collection] = relationship()
    project: Mapped[Project] = relationship()


class GeneratedTest(Base):
    __tablename__ = "generated_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"))
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id"))
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32), default="info")
    request_override_json: Mapped[str] = mapped_column(Text, default="{}")
    expected_behavior: Mapped[str] = mapped_column(Text)
    ai_reasoning: Mapped[str] = mapped_column(Text)


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    test_run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id"))
    generated_test_id: Mapped[int] = mapped_column(ForeignKey("generated_tests.id"))
    status: Mapped[str] = mapped_column(String(32))
    request_json: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers_json: Mapped[str] = mapped_column(Text, default="{}")
    response_body_preview: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    finding_summary: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
