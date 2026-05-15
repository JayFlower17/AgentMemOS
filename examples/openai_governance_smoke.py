"""Smoke test for OpenAI-compatible LLM governance reviewer.

The reviewer only generates relation suggestions. This script verifies that no
memory relation is created by the LLM review itself.

Local default:

    python examples/openai_governance_smoke.py

Environment overrides:

    AGENTMEMOS_OPENAI_API_KEY
    AGENTMEMOS_OPENAI_API_KEY_FILE
    AGENTMEMOS_OPENAI_API_KEY_LABEL
    AGENTMEMOS_OPENAI_BASE_URL
    AGENTMEMOS_OPENAI_GOVERNANCE_MODEL
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentmemos.config import get_settings
from agentmemos.database import SessionLocal, init_db
from agentmemos.governance import OpenAIGovernanceReviewer
from agentmemos.models import MemoryRelationModel
from agentmemos.worker import create_memory
from agentmemos.schemas import MemoryCreate


def configure_local_defaults() -> None:
    key_file = Path.home() / "Desktop" / "LLM-API-KEY.txt"
    if key_file.exists():
        os.environ.setdefault("AGENTMEMOS_OPENAI_API_KEY_FILE", str(key_file))
        os.environ.setdefault("AGENTMEMOS_OPENAI_API_KEY_LABEL", "DeepSeek")
        os.environ.setdefault("AGENTMEMOS_OPENAI_BASE_URL", "https://api.deepseek.com/v1")
        os.environ.setdefault("AGENTMEMOS_OPENAI_GOVERNANCE_MODEL", "deepseek-chat")


def relation_count(db, left_id: str, right_id: str) -> int:
    return (
        db.query(MemoryRelationModel)
        .filter(
            (
                (MemoryRelationModel.source_memory_id == left_id)
                & (MemoryRelationModel.target_memory_id == right_id)
            )
            | (
                (MemoryRelationModel.source_memory_id == right_id)
                & (MemoryRelationModel.target_memory_id == left_id)
            )
        )
        .count()
    )


def main() -> None:
    configure_local_defaults()
    get_settings.cache_clear()
    settings = get_settings()
    if not settings.openai_api_key:
        raise SystemExit("No OpenAI-compatible API key configured for governance smoke test.")

    init_db()
    task_id = f"task_governance_smoke_{uuid4().hex[:8]}"
    with SessionLocal() as db:
        first = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_governance_smoke",
                memory_type="episodic",
                scope="team-shared",
                content="Redis queue should decouple memory extraction and embedding indexing from API writes.",
                summary="Redis queue decouples memory jobs from API writes.",
                confidence=0.82,
                importance=0.84,
            ),
            decision_type="manual",
            decision_reason="Governance smoke seed memory A.",
        )
        second = create_memory(
            db,
            MemoryCreate(
                task_id=task_id,
                agent_id="reviewer_governance_smoke",
                memory_type="episodic",
                scope="team-shared",
                content="Redis queue keeps memory extraction and vector indexing outside the request path.",
                summary="Redis queue keeps memory jobs outside the request path.",
                confidence=0.8,
                importance=0.82,
            ),
            decision_type="manual",
            decision_reason="Governance smoke seed memory B.",
        )
        before = relation_count(db, first.memory_id, second.memory_id)
        reviewer = OpenAIGovernanceReviewer(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_governance_model,
            timeout_seconds=settings.openai_governance_timeout_seconds,
            min_confidence=settings.governance_reviewer_min_confidence,
        )
        suggestion = reviewer.suggest(db, first, second)
        after = relation_count(db, first.memory_id, second.memory_id)

    if suggestion is None:
        raise RuntimeError("LLM governance reviewer returned no suggestion for the smoke pair.")
    if before != after:
        raise RuntimeError("LLM governance reviewer mutated memory relations, which should never happen.")

    print("OpenAI-compatible governance smoke passed.")
    print(f"Base URL: {settings.openai_base_url}")
    print(f"Model: {settings.openai_governance_model}")
    print(f"Suggestion: {suggestion.relation_type}")
    print(f"Confidence: {suggestion.confidence:.4f}")
    print(f"Source memory: {suggestion.source_memory_id}")
    print(f"Target memory: {suggestion.target_memory_id}")
    print("Relation mutated: false")
    print(f"Reason: {suggestion.reason}")


if __name__ == "__main__":
    main()
