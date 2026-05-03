# AgentMemOS Project Build Log

This document records implementation progress, design decisions, verification, and next-step direction for the AgentMemOS MVP.

Current branch: `JayFlower`

## Current Stage

AgentMemOS has completed the first MVP loop and is now in the memory governance and self-maintenance phase.

Completed core loop:

1. Event ingestion through `POST /events`.
2. Worker-based memory extraction.
3. Scoped memory persistence with `agent-local`, `task-local`, `team-shared`, and `project-global`.
4. Role-aware retrieval through `POST /retrieve`.
5. Retrieval trace recording and explainability.
6. Memory write decision traces.
7. Memory status governance with `active`, `superseded`, and `archived`.
8. Memory relation governance with `supersedes`, `conflicts_with`, and `duplicates`.
9. Governance-aware retrieval.
10. Agent-readable governance insights and relation suggestions.

The dashboard remains a development aid for inspecting the system, not the primary product surface.

## Build History

### `46b5979` Initial AgentMemOS MVP

- Built the initial FastAPI MVP.
- Added event ingestion, memory persistence, and scoped retrieval.
- Established the SQLite local development path.

Verification:

- Initial test suite passed.

### `0d5059c` Add memory status audit history

- Added memory status transitions.
- Added auditable status decision history.
- Introduced active/archive/supersede lifecycle semantics.

### `165406a` Explain retrieval trace scoring

- Added score parts for retrieval candidates.
- Made retrieval scoring explainable by importance, confidence, scope, role/type affinity, and keyword overlap.

### `eff895b` Add dashboard trace explain view

- Added a trace explain panel to inspect retrieval behavior.
- Exposed selected, scored, and filtered memories.

### `5b4858d` Improve trace explain dashboard guidance

- Improved dashboard guidance for reading trace explain output.
- Clarified selected and filtered memory panels.

### `523ba89` Add memory write decision traces

- Added write decision traces for memory creation.
- Recorded why a memory was extracted or manually created, including type, scope, confidence, importance, reason, and signals.

### `222c911` Show memory write decisions on dashboard

- Exposed memory write decisions in the dashboard.
- Made write path and classification visible during development.

### `cafc5aa` Add demo data seeding script

- Added `examples/seed_demo_data.py`.
- Seed script creates demo events, memories, and retrieval traces.

### `a4b8a41` Prefer extracted memory decisions in dashboard

- Adjusted dashboard selection to prefer more informative extracted decisions.

### `9f5dbfc` Inline memory decisions in memory cards

- Moved memory write decision details into memory cards.
- Reduced the need for a separate decision-only panel.

### `229934a` Document memory write paths in dashboard guide

- Added guide text explaining `manual`, `extracted`, and memory type distinctions.

### `350e625` Deduplicate repeated memory writes

- Added exact normalized duplicate detection.
- Reused existing active memory for repeated writes.
- Added `deduplicated` memory decision trace instead of silently dropping duplicate writes.

Verification:

- `pytest -q`: passed.
- `node --check agentmemos/static/app.js`: passed.

### `54c8b24` Add memory governance relations

- Added memory relation model and APIs.
- Supported `supersedes`, `conflicts_with`, and `duplicates`.
- `supersedes` automatically marks the target memory as `superseded`.
- Added relation display to memory cards for development inspection.

Verification:

- `pytest -q`: 13 passed.

### `540de6b` Clarify memory relation guide copy

- Expanded the help card explanation for memory relations.
- Clarified source/target direction and the effect of `supersedes`.

### `149cae3` Apply memory governance during retrieval

- Retrieval now applies memory governance.
- `archived` and `superseded` memories are filtered out of selected results.
- Retrieval trace records governance filter reasons.
- Trace scored candidates can include open relation warnings.

Verification:

- `pytest -q`: 13 passed.
- `node --check agentmemos/static/app.js`: passed.
- Confirmed `/traces?limit=1` showed governance-aware filtering.

### `2dfe92b` Add memory governance insights API

- Added `GET /memory-insights`.
- Aggregates open memory relations and retrieval traces into agent-readable action items.
- Added insight types:
  - `open_conflicts_with`
  - `retrieval_miss`
  - `low_confidence_selection`
  - `governance_warning_selected`
  - `open_duplicates`
  - `open_supersedes`

Verification:

- `pytest -q`: 14 passed.
- Confirmed `/memory-insights?limit=3` returned structured governance action items.

### `cdd7e18` Suggest memory governance relations

- Added `GET /memory-relation-suggestions`.
- Suggests possible `duplicates` and `conflicts_with` relations between active memories.
- Suggestions are read-only and do not mutate memory state.
- Each suggestion includes confidence, evidence, reason, and suggested action.

Verification:

- `pytest -q`: 15 passed.
- Confirmed `/memory-relation-suggestions?limit=3` returned duplicate candidates.

### Accept memory governance suggestions

- Added an acceptance path for still-valid memory relation suggestions.
- Accepting a suggestion creates the corresponding memory relation.
- Acceptance writes an auditable governance action.
- Added `GET /memory-governance-actions` for action history.

Verification:

- `pytest -q`: 16 passed.

### Add governance agent example

- Added `examples/governance_agent.py`.
- The example fetches `/memory-insights` and `/memory-relation-suggestions`.
- It accepts only high-confidence duplicate suggestions.
- The default run is capped by `AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS`.
- It prints unresolved conflicts for explicit review instead of resolving them automatically.

Verification:

- `python -m py_compile examples/governance_agent.py`: passed.
- `pytest -q`: 16 passed.
- Confirmed the script connected to local 8014 and accepted duplicate suggestions.

## Current System Capabilities

- Event-driven memory ingestion.
- Manual memory creation.
- Memory extraction from events.
- Scoped visibility enforcement.
- Role-aware retrieval.
- Retrieval trace explainability.
- Memory write decision traces.
- Memory status audit history.
- Memory relation governance.
- Governance-aware retrieval.
- Agent-readable memory insights.
- Automatic relation suggestions.
- Audited acceptance path for governance suggestions.
- Conservative governance agent example.
- Development dashboard for inspecting memories, events, traces, decisions, and relations.

## Known Gaps

- Extraction is still rule-based and MVP-level.
- Relation suggestions use lexical heuristics, not embeddings or LLM judgment.
- No persistent job queue yet.
- SQLite remains the default local store; Postgres/pgvector integration is still pending.
- Suggestions are not applied automatically; they require explicit acceptance.
- Governance agent workflow is still an example script, not a background service.
- SDK and adapters are still minimal.

## Next Recommended Step

Promote the governance agent workflow into a service-level capability:

1. Add a backend endpoint or worker job for running a governance pass.
2. Add configurable thresholds for duplicate acceptance.
3. Keep conflict resolution explicit and auditable.
4. Record governance pass summaries.

This would close the loop:

`scheduled governance pass -> accepted duplicate relations -> audited actions -> retrieval governance`
