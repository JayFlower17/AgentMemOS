from sqlalchemy import create_engine, inspect, text

from agentmemos.database import Base
from agentmemos.models import RetrievalTraceModel


def test_sqlite_schema_ensure_adds_missing_known_columns():
    from agentmemos import database

    original_engine = database.engine
    original_session_local = database.SessionLocal
    try:
        test_engine = create_engine("sqlite:///:memory:", future=True)
        database.engine = test_engine
        Base.metadata.create_all(bind=test_engine, tables=[RetrievalTraceModel.__table__])
        with test_engine.begin() as connection:
            connection.execute(text("ALTER TABLE retrieval_traces DROP COLUMN scored_memories"))

        database._ensure_sqlite_schema()

        columns = {column["name"] for column in inspect(test_engine).get_columns("retrieval_traces")}
        assert "scored_memories" in columns
        assert "filter_reasons" in columns
    finally:
        database.engine = original_engine
        database.SessionLocal = original_session_local
