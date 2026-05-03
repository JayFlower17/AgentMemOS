from functools import lru_cache
import os

from pydantic import BaseModel, Field


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = "AgentMemOS"
    database_url: str = Field(default="sqlite:///./agentmemos.db")
    extraction_delay_seconds: float = 0.0
    job_queue_backend: str = Field(default="memory", pattern="^(memory|redis)$")
    api_worker_enabled: bool = True
    job_max_attempts: int = Field(default=3, ge=1, le=20)
    job_retry_backoff_seconds: float = Field(default=1.0, ge=0, le=3600)
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_name: str = "agentmemos:jobs"
    vector_retrieval_enabled: bool = False
    vector_retrieval_weight: float = Field(default=0.0, ge=0, le=1)
    vector_store_backend: str = Field(default="memory", pattern="^(memory|sqlite)$")
    governance_scheduler_enabled: bool = False
    governance_scheduler_interval_seconds: float = Field(default=0.0, ge=0)
    governance_scheduler_actor: str = "governance_scheduler"
    governance_duplicate_confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    governance_max_accepts: int = Field(default=10, ge=0, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("AGENTMEMOS_APP_NAME", "AgentMemOS"),
        database_url=os.getenv("AGENTMEMOS_DATABASE_URL", "sqlite:///./agentmemos.db"),
        extraction_delay_seconds=float(os.getenv("AGENTMEMOS_EXTRACTION_DELAY_SECONDS", "0")),
        job_queue_backend=os.getenv("AGENTMEMOS_JOB_QUEUE_BACKEND", "memory"),
        api_worker_enabled=env_bool("AGENTMEMOS_API_WORKER_ENABLED", True),
        job_max_attempts=int(os.getenv("AGENTMEMOS_JOB_MAX_ATTEMPTS", "3")),
        job_retry_backoff_seconds=float(os.getenv("AGENTMEMOS_JOB_RETRY_BACKOFF_SECONDS", "1")),
        redis_url=os.getenv("AGENTMEMOS_REDIS_URL", "redis://localhost:6379/0"),
        redis_queue_name=os.getenv("AGENTMEMOS_REDIS_QUEUE_NAME", "agentmemos:jobs"),
        vector_retrieval_enabled=env_bool("AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED", False),
        vector_retrieval_weight=float(os.getenv("AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT", "0")),
        vector_store_backend=os.getenv("AGENTMEMOS_VECTOR_STORE_BACKEND", "memory"),
        governance_scheduler_enabled=env_bool("AGENTMEMOS_GOVERNANCE_SCHEDULER_ENABLED", False),
        governance_scheduler_interval_seconds=float(
            os.getenv("AGENTMEMOS_GOVERNANCE_SCHEDULER_INTERVAL_SECONDS", "0")
        ),
        governance_scheduler_actor=os.getenv("AGENTMEMOS_GOVERNANCE_SCHEDULER_ACTOR", "governance_scheduler"),
        governance_duplicate_confidence_threshold=float(
            os.getenv("AGENTMEMOS_GOVERNANCE_DUPLICATE_CONFIDENCE_THRESHOLD", "0.85")
        ),
        governance_max_accepts=int(os.getenv("AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS", "10")),
    )
