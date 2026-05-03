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
        _ensure_sqlite_schema()


def _ensure_sqlite_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    table_columns = {
        "retrieval_traces": {
            "scored_memories": "JSON DEFAULT '[]'",
            "filter_reasons": "JSON DEFAULT '{}'",
        },
        "memory_relations": {
            "status": "VARCHAR(32) DEFAULT 'open'",
            "resolved_at": "DATETIME",
        },
        "memory_governance_actions": {
            "relation_id": "VARCHAR(64)",
            "suggestion_id": "VARCHAR(64)",
            "evidence": "JSON DEFAULT '{}'",
        },
    }
    with engine.begin() as connection:
        for table_name, missing_columns in table_columns.items():
            if table_name not in existing_tables:
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in missing_columns.items():
                if column_name not in columns:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
