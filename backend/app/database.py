import os
from collections.abc import Generator

from sqlalchemy import inspect, text
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aeroapi.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    add_missing_columns()


def add_missing_columns() -> None:
    inspector = inspect(engine)
    if "test_runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("test_runs")}
    with engine.begin() as connection:
        if "api_docs" not in columns:
            connection.execute(text("ALTER TABLE test_runs ADD COLUMN api_docs TEXT"))
