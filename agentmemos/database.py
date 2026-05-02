from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from agentmemos.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, future=True, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from agentmemos import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        _ensure_sqlite_trace_columns()


def _ensure_sqlite_trace_columns() -> None:
    inspector = inspect(engine)
    if "retrieval_traces" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("retrieval_traces")}
    missing_columns = {
        "scored_memories": "JSON DEFAULT '[]'",
        "filter_reasons": "JSON DEFAULT '{}'",
    }
    with engine.begin() as connection:
        for column_name, column_type in missing_columns.items():
            if column_name not in columns:
                connection.execute(text(f"ALTER TABLE retrieval_traces ADD COLUMN {column_name} {column_type}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
