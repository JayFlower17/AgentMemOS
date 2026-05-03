import asyncio
from contextlib import suppress
from datetime import datetime
from typing import Any

from agentmemos.config import Settings, get_settings
from agentmemos.database import SessionLocal
from agentmemos.governance import run_governance
from agentmemos.models import utcnow
from agentmemos.schemas import RunGovernanceRequest


class GovernanceScheduler:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._task: asyncio.Task | None = None
        self._running = False
        self.last_run_at: datetime | None = None
        self.last_error: str | None = None
        self.last_summary: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        return (
            self.settings.governance_scheduler_enabled
            and self.settings.governance_scheduler_interval_seconds > 0
        )

    async def start(self) -> None:
        self._running = True
        if self.enabled:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def run_once(self) -> None:
        await asyncio.to_thread(self._run_once)

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self.settings.governance_scheduler_interval_seconds)
            if not self._running:
                break
            await self.run_once()

    def _run_once(self) -> None:
        try:
            payload = RunGovernanceRequest(
                actor=self.settings.governance_scheduler_actor,
                duplicate_confidence_threshold=self.settings.governance_duplicate_confidence_threshold,
                max_accepts=self.settings.governance_max_accepts,
            )
            with SessionLocal() as db:
                summary = run_governance(db, payload)
            self.last_run_at = utcnow()
            self.last_error = None
            self.last_summary = summary.model_dump(mode="json")
        except Exception as exc:
            self.last_run_at = utcnow()
            self.last_error = str(exc)
            raise

    def state(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._running,
            "interval_seconds": self.settings.governance_scheduler_interval_seconds,
            "duplicate_confidence_threshold": self.settings.governance_duplicate_confidence_threshold,
            "max_accepts": self.settings.governance_max_accepts,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "last_summary": self.last_summary,
        }
