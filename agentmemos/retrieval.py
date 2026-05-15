import math
import re
from collections import Counter

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agentmemos.enums import AgentRole, MemoryScope, MemoryStatus, MemoryType
from agentmemos.models import MemoryRecordModel, MemoryRelationModel, RetrievalTraceModel
from agentmemos.schemas import RetrieveRequest


ROLE_TYPE_WEIGHTS = {
    AgentRole.planner: {MemoryType.working: 1.0, MemoryType.episodic: 0.5, MemoryType.procedural: 0.7},
    AgentRole.coder: {MemoryType.working: 0.8, MemoryType.episodic: 0.8, MemoryType.procedural: 1.0},
    AgentRole.reviewer: {MemoryType.working: 0.6, MemoryType.episodic: 1.0, MemoryType.procedural: 0.8},
    AgentRole.user: {MemoryType.working: 0.7, MemoryType.episodic: 1.0, MemoryType.procedural: 0.6},
    AgentRole.assistant: {MemoryType.working: 0.8, MemoryType.episodic: 0.8, MemoryType.procedural: 0.8},
}

SCOPE_WEIGHTS = {
    MemoryScope.agent_local: 0.45,
    MemoryScope.task_local: 0.75,
    MemoryScope.team_shared: 1.0,
    MemoryScope.project_global: 0.9,
}

STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "how",
    "did",
    "does",
    "was",
    "were",
    "are",
    "is",
    "has",
    "have",
    "had",
}


def _tokenize(text: str) -> list[str]:
    tokens = []
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text.casefold()):
        if len(raw) > 2 and raw not in STOPWORDS:
            tokens.append(raw)
    return tokens


def _memory_text(memory: MemoryRecordModel) -> str:
    return f"{memory.summary} {memory.content}"


def _keyword_score(query: str, memory: MemoryRecordModel) -> float:
    terms = set(_tokenize(query))
    if not terms:
        return 0.0
    haystack = _memory_text(memory).lower()
    hits = sum(1 for term in terms if term in haystack)
    return hits / len(terms)


def _bm25_scores(query: str, memories: list[MemoryRecordModel]) -> dict[str, float]:
    query_terms = _tokenize(query)
    if not query_terms or not memories:
        return {}
    docs = {memory.memory_id: _tokenize(_memory_text(memory)) for memory in memories}
    doc_count = len(docs)
    avg_doc_len = sum(len(tokens) for tokens in docs.values()) / max(1, doc_count)
    document_frequency: Counter[str] = Counter()
    for tokens in docs.values():
        document_frequency.update(set(tokens))

    k1 = 1.5
    b = 0.75
    raw_scores: dict[str, float] = {}
    for memory_id, tokens in docs.items():
        if not tokens:
            raw_scores[memory_id] = 0.0
            continue
        term_counts = Counter(tokens)
        score = 0.0
        for term in query_terms:
            freq = term_counts.get(term, 0)
            if not freq:
                continue
            idf = math.log(1 + (doc_count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            denominator = freq + k1 * (1 - b + b * (len(tokens) / max(1, avg_doc_len)))
            score += idf * ((freq * (k1 + 1)) / denominator)
        raw_scores[memory_id] = score

    max_score = max(raw_scores.values(), default=0.0)
    if max_score <= 0:
        return raw_scores
    return {memory_id: score / max_score for memory_id, score in raw_scores.items()}


def _important_terms(text: str) -> set[str]:
    terms = set(_tokenize(text))
    entities = {item.casefold() for item in re.findall(r"\b[A-Z][A-Za-z0-9_-]{2,}\b", text)}
    numbers = {item.casefold() for item in re.findall(r"\b\d{1,4}(?:[-/]\d{1,2})?(?:[-/]\d{1,4})?\b", text)}
    return terms | entities | numbers


def _rerank_bonus(query: str, memory: MemoryRecordModel) -> float:
    query_terms = _important_terms(query)
    if not query_terms:
        return 0.0
    memory_text = _memory_text(memory)
    memory_terms = _important_terms(memory_text)
    overlap = len(query_terms & memory_terms) / len(query_terms)
    phrase_bonus = 0.0
    lowered_memory = memory_text.casefold()
    for phrase in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*(?:\s+[A-Za-z0-9][A-Za-z0-9_-]*)+", query):
        normalized = phrase.casefold()
        if len(normalized) >= 8 and normalized in lowered_memory:
            phrase_bonus = 0.15
            break
    return min(1.0, overlap + phrase_bonus)


def _score_memory(
    req: RetrieveRequest,
    memory: MemoryRecordModel,
    *,
    bm25_score: float = 0.0,
    rerank_bonus: float = 0.0,
    embedding_score: float = 0.0,
    embedding_weight: float = 0.0,
) -> tuple[float, dict[str, float]]:
    type_weights = ROLE_TYPE_WEIGHTS[req.agent_role]
    parts = {
        "importance": memory.importance * 0.25,
        "confidence": memory.confidence * 0.18,
        "scope": SCOPE_WEIGHTS[MemoryScope(memory.scope)] * 0.2,
        "role_type": type_weights[MemoryType(memory.memory_type)] * 0.1,
        "keyword": _keyword_score(req.query, memory) * 0.06,
        "bm25": bm25_score * 0.25,
        "rerank": rerank_bonus * 0.18,
    }
    if embedding_score:
        parts["embedding"] = embedding_score * embedding_weight
    return sum(parts.values()), parts


def _is_visible(req: RetrieveRequest, memory: MemoryRecordModel) -> tuple[bool, str | None]:
    scope = MemoryScope(memory.scope)
    if scope == MemoryScope.agent_local and memory.agent_id != req.agent_id:
        return False, "Filtered another agent's local memory."
    if scope != MemoryScope.project_global and memory.task_id != req.task_id:
        return False, "Filtered memory from another task."
    return True, None


def _relations_for_candidates(db: Session, memory_ids: list[str]) -> dict[str, list[MemoryRelationModel]]:
    if not memory_ids:
        return {}
    stmt = (
        select(MemoryRelationModel)
        .where(MemoryRelationModel.status == "open")
        .where(
            or_(
                MemoryRelationModel.source_memory_id.in_(memory_ids),
                MemoryRelationModel.target_memory_id.in_(memory_ids),
            )
        )
    )
    relations_by_memory: dict[str, list[MemoryRelationModel]] = {memory_id: [] for memory_id in memory_ids}
    for relation in db.scalars(stmt):
        relations_by_memory.setdefault(relation.source_memory_id, []).append(relation)
        relations_by_memory.setdefault(relation.target_memory_id, []).append(relation)
    return relations_by_memory


def _governance_filter_reason(memory: MemoryRecordModel, relations: list[MemoryRelationModel]) -> str | None:
    status = MemoryStatus(memory.status)
    if status == MemoryStatus.archived:
        return "Filtered archived memory."
    if status == MemoryStatus.superseded:
        superseding = next(
            (
                relation.source_memory_id
                for relation in relations
                if relation.relation_type == "supersedes" and relation.target_memory_id == memory.memory_id
            ),
            None,
        )
        if superseding:
            return f"Filtered superseded memory; replaced by {superseding}."
        return "Filtered superseded memory."
    return None


def _governance_warnings(memory: MemoryRecordModel, relations: list[MemoryRelationModel]) -> list[dict[str, str]]:
    warnings = []
    for relation in relations:
        other_memory_id = (
            relation.target_memory_id if relation.source_memory_id == memory.memory_id else relation.source_memory_id
        )
        if relation.relation_type == "conflicts_with":
            message = f"Open conflict with {other_memory_id}."
        elif relation.relation_type == "duplicates":
            message = f"Possible duplicate of {other_memory_id}."
        elif relation.relation_type == "supersedes" and relation.source_memory_id == memory.memory_id:
            message = f"Supersedes {other_memory_id}."
        else:
            continue
        warnings.append(
            {
                "relation_id": relation.relation_id,
                "relation_type": relation.relation_type,
                "other_memory_id": other_memory_id,
                "message": message,
            }
        )
    return warnings


def retrieve_memories(
    db: Session,
    req: RetrieveRequest,
    *,
    embedding_scores: dict[str, float] | None = None,
    embedding_weight: float = 0.0,
) -> tuple[list[MemoryRecordModel], RetrievalTraceModel]:
    allowed = [scope.value for scope in req.allowed_scopes]
    stmt = (
        select(MemoryRecordModel)
        .where(MemoryRecordModel.status.in_([MemoryStatus.active, MemoryStatus.superseded, MemoryStatus.archived]))
        .where(MemoryRecordModel.scope.in_(allowed))
        .where(or_(MemoryRecordModel.task_id == req.task_id, MemoryRecordModel.scope == MemoryScope.project_global))
    )
    candidates = list(db.scalars(stmt))
    relations_by_memory = _relations_for_candidates(db, [memory.memory_id for memory in candidates])
    bm25_scores = _bm25_scores(req.query, candidates)

    filtered: list[str] = []
    scored: list[tuple[float, MemoryRecordModel]] = []
    filter_reasons: dict[str, str] = {}
    scored_memories: list[dict] = []
    reasons: list[str] = []
    governance_seen = False

    for memory in candidates:
        relations = relations_by_memory.get(memory.memory_id, [])
        governance_reason = _governance_filter_reason(memory, relations)
        if governance_reason:
            filtered.append(memory.memory_id)
            filter_reasons[memory.memory_id] = governance_reason
            if governance_reason not in reasons:
                reasons.append(governance_reason)
            governance_seen = True
            continue

        visible, reason = _is_visible(req, memory)
        if not visible:
            filtered.append(memory.memory_id)
            if reason:
                filter_reasons[memory.memory_id] = reason
            if reason and reason not in reasons:
                reasons.append(reason)
            continue
        score, parts = _score_memory(
            req,
            memory,
            bm25_score=bm25_scores.get(memory.memory_id, 0.0),
            rerank_bonus=_rerank_bonus(req.query, memory),
            embedding_score=(embedding_scores or {}).get(memory.memory_id, 0.0),
            embedding_weight=embedding_weight,
        )
        warnings = _governance_warnings(memory, relations)
        if warnings:
            governance_seen = True
        scored.append((score, memory))
        scored_memories.append(
            {
                "memory_id": memory.memory_id,
                "score": round(score, 4),
                "selected": False,
                "scope": memory.scope,
                "memory_type": memory.memory_type,
                "score_parts": {key: round(value, 4) for key, value in parts.items()},
                "governance": warnings,
            }
        )

    selected = [memory for _, memory in sorted(scored, key=lambda item: item[0], reverse=True)[: req.limit]]
    selected_ids = {memory.memory_id for memory in selected}
    scored_memories = sorted(scored_memories, key=lambda item: item["score"], reverse=True)
    for item in scored_memories:
        item["selected"] = item["memory_id"] in selected_ids
    reason = (
        "Selected memories by scope visibility, role/type affinity, confidence, importance, "
        "BM25 sparse retrieval, keyword overlap, and deterministic rerank signals."
    )
    if embedding_scores and embedding_weight:
        reason = f"{reason} Applied vector similarity scoring."
    if governance_seen:
        reason = f"{reason} Applied memory governance: excluded archived/superseded memories and surfaced open relations."
    if reasons:
        reason = f"{reason} {' '.join(reasons)}"

    trace = RetrievalTraceModel(
        task_id=req.task_id,
        agent_id=req.agent_id,
        agent_role=req.agent_role,
        query=req.query,
        searched_scopes=[scope.value for scope in req.allowed_scopes],
        selected_memories=[memory.memory_id for memory in selected],
        filtered_memories=filtered,
        scored_memories=scored_memories,
        filter_reasons=filter_reasons,
        reason=reason,
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return selected, trace


def pack_context(memories: list[MemoryRecordModel]) -> str:
    if not memories:
        return ""
    lines = []
    for memory in memories:
        lines.append(f"- [{memory.scope}/{memory.memory_type}] {memory.summary}")
    return "\n".join(lines)
