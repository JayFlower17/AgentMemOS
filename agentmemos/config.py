from functools import lru_cache
import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "AgentMemOS"
    database_url: str = Field(default="sqlite:///./agentmemos.db")
    extraction_delay_seconds: float = 0.0


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("AGENTMEMOS_APP_NAME", "AgentMemOS"),
        database_url=os.getenv("AGENTMEMOS_DATABASE_URL", "sqlite:///./agentmemos.db"),
        extraction_delay_seconds=float(os.getenv("AGENTMEMOS_EXTRACTION_DELAY_SECONDS", "0")),
    )
