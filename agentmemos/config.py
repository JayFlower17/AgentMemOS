from functools import lru_cache
import os

from pydantic import BaseModel, Field


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


def _extract_secret(raw: str, label: str = "") -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if label:
        prefix = f"{label.casefold()}:"
        for line in lines:
            if line.casefold().startswith(prefix):
                return line.split(":", 1)[1].strip()
    if len(lines) == 1 and ":" in lines[0]:
        return lines[0].split(":", 1)[1].strip()
    if lines:
        return lines[0].split(":", 1)[-1].strip()
    return raw.strip()


def env_secret(name: str, file_name: str, label_name: str = "") -> str:
    raw = os.getenv(name)
    if raw:
        return raw.strip()
    path = os.getenv(file_name)
    if not path:
        return ""
    label = os.getenv(label_name, "") if label_name else ""
    try:
        with open(path, encoding="utf-8") as secret_file:
            return _extract_secret(secret_file.read(), label)
    except OSError:
        return ""


class Settings(BaseModel):
    app_name: str = "AgentMemOS"
    database_url: str = Field(default="sqlite:///./agentmemos.db")
    extraction_delay_seconds: float = 0.0
    extractor_backend: str = Field(default="rule", pattern="^(rule|openai)$")
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_extractor_model: str = "gpt-4o-mini"
    openai_extractor_timeout_seconds: float = Field(default=20.0, ge=1, le=120)
    job_queue_backend: str = Field(default="memory", pattern="^(memory|redis)$")
    api_worker_enabled: bool = True
    worker_concurrency: int = Field(default=1, ge=1, le=64)
    job_max_attempts: int = Field(default=3, ge=1, le=20)
    job_retry_backoff_seconds: float = Field(default=1.0, ge=0, le=3600)
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_name: str = "agentmemos:jobs"
    redis_event_fanout_enabled: bool = False
    redis_event_channel: str = "agentmemos:events"
    vector_retrieval_enabled: bool = False
    vector_retrieval_weight: float = Field(default=0.0, ge=0, le=1)
    embedding_provider: str = Field(default="hashing", pattern="^(hashing|openai)$")
    vector_store_backend: str = Field(default="memory", pattern="^(memory|sqlite|pgvector)$")
    openai_embedding_api_key: str = ""
    openai_embedding_base_url: str = "https://api.openai.com/v1"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = Field(default=0, ge=0, le=4096)
    openai_embedding_timeout_seconds: float = Field(default=20.0, ge=1, le=120)
    pgvector_url: str = "postgresql://agentmemos:agentmemos@localhost:5432/agentmemos"
    pgvector_table_name: str = "memory_embeddings"
    pgvector_dimensions: int = Field(default=64, ge=1, le=4096)
    governance_scheduler_enabled: bool = False
    governance_scheduler_interval_seconds: float = Field(default=0.0, ge=0)
    governance_scheduler_actor: str = "governance_scheduler"
    governance_duplicate_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    governance_max_accepts: int = Field(default=10, ge=0, le=100)
    governance_reviewer_backend: str = Field(default="rule", pattern="^(rule|openai)$")
    governance_reviewer_max_pairs: int = Field(default=25, ge=0, le=500)
    governance_reviewer_min_confidence: float = Field(default=0.7, ge=0, le=1)
    openai_governance_model: str = "gpt-4o-mini"
    openai_governance_timeout_seconds: float = Field(default=20.0, ge=1, le=120)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("AGENTMEMOS_APP_NAME", "AgentMemOS"),
        database_url=os.getenv("AGENTMEMOS_DATABASE_URL", "sqlite:///./agentmemos.db"),
        extraction_delay_seconds=float(os.getenv("AGENTMEMOS_EXTRACTION_DELAY_SECONDS", "0")),
        extractor_backend=os.getenv("AGENTMEMOS_EXTRACTOR_BACKEND", "rule"),
        openai_api_key=env_secret(
            "AGENTMEMOS_OPENAI_API_KEY",
            "AGENTMEMOS_OPENAI_API_KEY_FILE",
            "AGENTMEMOS_OPENAI_API_KEY_LABEL",
        )
        or env_secret("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "OPENAI_API_KEY_LABEL"),
        openai_base_url=os.getenv("AGENTMEMOS_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_extractor_model=os.getenv("AGENTMEMOS_OPENAI_EXTRACTOR_MODEL", "gpt-4o-mini"),
        openai_extractor_timeout_seconds=float(os.getenv("AGENTMEMOS_OPENAI_EXTRACTOR_TIMEOUT_SECONDS", "20")),
        job_queue_backend=os.getenv("AGENTMEMOS_JOB_QUEUE_BACKEND", "memory"),
        api_worker_enabled=env_bool("AGENTMEMOS_API_WORKER_ENABLED", True),
        worker_concurrency=int(os.getenv("AGENTMEMOS_WORKER_CONCURRENCY", "1")),
        job_max_attempts=int(os.getenv("AGENTMEMOS_JOB_MAX_ATTEMPTS", "3")),
        job_retry_backoff_seconds=float(os.getenv("AGENTMEMOS_JOB_RETRY_BACKOFF_SECONDS", "1")),
        redis_url=os.getenv("AGENTMEMOS_REDIS_URL", "redis://localhost:6379/0"),
        redis_queue_name=os.getenv("AGENTMEMOS_REDIS_QUEUE_NAME", "agentmemos:jobs"),
        redis_event_fanout_enabled=env_bool("AGENTMEMOS_REDIS_EVENT_FANOUT_ENABLED", False),
        redis_event_channel=os.getenv("AGENTMEMOS_REDIS_EVENT_CHANNEL", "agentmemos:events"),
        vector_retrieval_enabled=env_bool("AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED", False),
        vector_retrieval_weight=float(os.getenv("AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT", "0")),
        embedding_provider=os.getenv("AGENTMEMOS_EMBEDDING_PROVIDER", "hashing"),
        vector_store_backend=os.getenv("AGENTMEMOS_VECTOR_STORE_BACKEND", "memory"),
        openai_embedding_api_key=(
            env_secret(
                "AGENTMEMOS_OPENAI_EMBEDDING_API_KEY",
                "AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE",
                "AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL",
            )
            or env_secret("OPENAI_EMBEDDING_API_KEY", "OPENAI_EMBEDDING_API_KEY_FILE", "OPENAI_EMBEDDING_API_KEY_LABEL")
            or env_secret(
                "AGENTMEMOS_OPENAI_API_KEY",
                "AGENTMEMOS_OPENAI_API_KEY_FILE",
                "AGENTMEMOS_OPENAI_API_KEY_LABEL",
            )
            or env_secret("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", "OPENAI_API_KEY_LABEL")
        ),
        openai_embedding_base_url=os.getenv(
            "AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL",
            os.getenv("AGENTMEMOS_OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ),
        openai_embedding_model=os.getenv("AGENTMEMOS_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        openai_embedding_dimensions=int(os.getenv("AGENTMEMOS_OPENAI_EMBEDDING_DIMENSIONS", "0")),
        openai_embedding_timeout_seconds=float(os.getenv("AGENTMEMOS_OPENAI_EMBEDDING_TIMEOUT_SECONDS", "20")),
        pgvector_url=os.getenv(
            "AGENTMEMOS_PGVECTOR_URL",
            "postgresql://agentmemos:agentmemos@localhost:5432/agentmemos",
        ),
        pgvector_table_name=os.getenv("AGENTMEMOS_PGVECTOR_TABLE_NAME", "memory_embeddings"),
        pgvector_dimensions=int(os.getenv("AGENTMEMOS_PGVECTOR_DIMENSIONS", "64")),
        governance_scheduler_enabled=env_bool("AGENTMEMOS_GOVERNANCE_SCHEDULER_ENABLED", False),
        governance_scheduler_interval_seconds=float(
            os.getenv("AGENTMEMOS_GOVERNANCE_SCHEDULER_INTERVAL_SECONDS", "0")
        ),
        governance_scheduler_actor=os.getenv("AGENTMEMOS_GOVERNANCE_SCHEDULER_ACTOR", "governance_scheduler"),
        governance_duplicate_confidence_threshold=float(
            os.getenv("AGENTMEMOS_GOVERNANCE_DUPLICATE_CONFIDENCE_THRESHOLD", "0.85")
        ),
        governance_max_accepts=int(os.getenv("AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS", "10")),
        governance_reviewer_backend=os.getenv("AGENTMEMOS_GOVERNANCE_REVIEWER_BACKEND", "rule"),
        governance_reviewer_max_pairs=int(os.getenv("AGENTMEMOS_GOVERNANCE_REVIEWER_MAX_PAIRS", "25")),
        governance_reviewer_min_confidence=float(os.getenv("AGENTMEMOS_GOVERNANCE_REVIEWER_MIN_CONFIDENCE", "0.7")),
        openai_governance_model=os.getenv("AGENTMEMOS_OPENAI_GOVERNANCE_MODEL", "gpt-4o-mini"),
        openai_governance_timeout_seconds=float(os.getenv("AGENTMEMOS_OPENAI_GOVERNANCE_TIMEOUT_SECONDS", "20")),
    )
