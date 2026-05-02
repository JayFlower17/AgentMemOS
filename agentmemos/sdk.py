from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener


class AgentMemOSError(RuntimeError):
    """Raised when the AgentMemOS API request fails."""


Transport = Callable[[str, str, dict[str, Any] | None], Any]


@dataclass(frozen=True)
class AgentMemOSClient:
    """Small synchronous SDK for integrating agent runtimes with AgentMemOS."""

    base_url: str = "http://127.0.0.1:8000"
    timeout: float = 10.0
    transport: Transport | None = None

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def emit_event(
        self,
        *,
        event_type: str,
        task_id: str,
        agent_id: str,
        agent_role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        event_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "event_type": event_type,
            "task_id": task_id,
            "agent_id": agent_id,
            "agent_role": agent_role,
            "content": content,
            "metadata": metadata or {},
        }
        if event_id:
            payload["event_id"] = event_id
        if created_at:
            payload["created_at"] = created_at
        return self._request("POST", "/events", payload)

    def retrieve(
        self,
        *,
        task_id: str,
        agent_id: str,
        agent_role: str,
        query: str,
        allowed_scopes: list[str] | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/retrieve",
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_role": agent_role,
                "query": query,
                "allowed_scopes": allowed_scopes
                or ["task-local", "team-shared", "project-global"],
                "limit": limit,
            },
        )

    def create_memory(
        self,
        *,
        memory_type: str,
        scope: str,
        content: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        summary: str | None = None,
        confidence: float = 0.75,
        importance: float = 0.5,
        source_event_id: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/memories",
            {
                "task_id": task_id,
                "agent_id": agent_id,
                "memory_type": memory_type,
                "scope": scope,
                "content": content,
                "summary": summary,
                "confidence": confidence,
                "importance": importance,
                "source_event_id": source_event_id,
            },
        )

    def promote_memory(self, memory_id: str, *, to_scope: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/memories/{memory_id}/promote",
            {"to_scope": to_scope, "reason": reason},
        )

    def update_memory_status(self, memory_id: str, *, status: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/memories/{memory_id}/status",
            {"status": status, "reason": reason},
        )

    def archive_memory(self, memory_id: str, *, reason: str) -> dict[str, Any]:
        return self.update_memory_status(memory_id, status="archived", reason=reason)

    def restore_memory(self, memory_id: str, *, reason: str) -> dict[str, Any]:
        return self.update_memory_status(memory_id, status="active", reason=reason)

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        return self._request("GET", f"/traces/{trace_id}")

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        return self._request("GET", f"/memories/{memory_id}")

    def list_promotions(self, *, memory_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        path = f"/memories/{memory_id}/promotions" if memory_id else f"/promotions?limit={limit}"
        result = self._request("GET", path)
        if not isinstance(result, list):
            raise AgentMemOSError("Expected promotions endpoint to return a list")
        return result

    def list_status_decisions(self, memory_id: str) -> list[dict[str, Any]]:
        result = self._request("GET", f"/memories/{memory_id}/status-decisions")
        if not isinstance(result, list):
            raise AgentMemOSError("Expected status decisions endpoint to return a list")
        return result

    def list_memories(
        self,
        *,
        task_id: str | None = None,
        scope: str | None = None,
        memory_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params = {
            "task_id": task_id,
            "scope": scope,
            "memory_type": memory_type,
            "limit": limit,
        }
        query = urlencode({key: value for key, value in params.items() if value is not None})
        suffix = f"?{query}" if query else ""
        result = self._request("GET", f"/memories{suffix}")
        if not isinstance(result, list):
            raise AgentMemOSError("Expected /memories to return a list")
        return result

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        if self.transport:
            return self.transport(method, path, payload)

        url = f"{self.base_url.rstrip('/')}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            opener = build_opener(ProxyHandler({}))
            with opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentMemOSError(f"AgentMemOS API returned {exc.code}: {detail}") from exc
        except URLError as exc:
            raise AgentMemOSError(f"AgentMemOS API request failed: {exc.reason}") from exc
