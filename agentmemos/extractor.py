from dataclasses import dataclass
from typing import Protocol

from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryType
from agentmemos.models import AgentEventModel
from agentmemos.schemas import MemoryCreate


@dataclass(frozen=True)
class ExtractionDecision:
    memory_type: MemoryType
    scope: MemoryScope
    confidence: float
    importance: float
    reason: str
    applied_rules: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionResult:
    should_write: bool
    memory: MemoryCreate | None
    reason: str
    signals: dict
    provider: str


class ExtractorProvider(Protocol):
    name: str

    def extract(self, event: AgentEventModel) -> ExtractionResult: ...


def summarize(text: str, max_chars: int = 140) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "..."


def detect_content_signals(text: str) -> dict[str, bool]:
    normalized = text.casefold()
    risk_terms = (
        "risk",
        "blocker",
        "blocked",
        "unsafe",
        "conflict",
        "regression",
        "bug",
        "issue",
        "风险",
        "阻塞",
        "冲突",
        "缺陷",
    )
    failure_terms = ("fail", "failed", "failure", "error", "exception", "timeout", "失败", "错误", "异常", "超时")
    decision_terms = (
        "approved",
        "rejected",
        "decided",
        "decision",
        "confirmed",
        "requires",
        "found that",
        "决定",
        "确认",
        "同意",
        "审批",
        "要求",
    )
    procedure_terms = (
        "should",
        "must",
        "always",
        "never",
        "when ",
        "before",
        "after",
        "checklist",
        "rule",
        "policy",
        "需要",
        "必须",
        "应该",
        "不要",
        "当",
        "之前",
        "之后",
        "规则",
        "策略",
    )
    scratch_terms = ("scratch", "note to self", "local note", "temporary", "临时", "草稿", "本地笔记")
    return {
        "risk_signal": any(term in normalized for term in risk_terms),
        "failure_signal": any(term in normalized for term in failure_terms),
        "decision_signal": any(term in normalized for term in decision_terms),
        "procedure_signal": any(term in normalized for term in procedure_terms),
        "scratch_signal": any(term in normalized for term in scratch_terms),
    }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 2)))


def _base_decision(event: AgentEventModel, signals: dict[str, bool]) -> ExtractionDecision:
    if event.event_type == EventType.task_created:
        return ExtractionDecision(
            MemoryType.working,
            MemoryScope.task_local,
            0.83,
            0.72,
            "Task creation starts as task-local working memory because it defines current task context.",
            ("event:task_created",),
        )
    if event.event_type == EventType.review_finding_created:
        return ExtractionDecision(
            MemoryType.episodic,
            MemoryScope.team_shared,
            0.86,
            0.9,
            "Review findings are shared as high-importance episodic memories for downstream review and coding context.",
            ("event:review_finding", "scope:team_shared"),
        )
    if event.event_type == EventType.subtask_completed:
        return ExtractionDecision(
            MemoryType.working,
            MemoryScope.task_local,
            0.8,
            0.7,
            "Subtask completion updates task-local working memory until the outcome is promoted or generalized.",
            ("event:subtask_completed",),
        )
    if event.event_type == EventType.task_completed:
        if signals["procedure_signal"]:
            return ExtractionDecision(
                MemoryType.procedural,
                MemoryScope.team_shared,
                0.82,
                0.86,
                "Completed task content contains procedural language, so it becomes reusable team guidance.",
                ("event:task_completed", "content:procedure"),
            )
        return ExtractionDecision(
            MemoryType.episodic,
            MemoryScope.team_shared,
            0.78,
            0.8,
            "Completed task outcomes are team-shared episodic memory unless they read like reusable procedure.",
            ("event:task_completed",),
        )
    if event.event_type == EventType.tool_result_observed:
        scope = MemoryScope.agent_local if event.agent_role == AgentRole.coder and signals["scratch_signal"] else MemoryScope.task_local
        return ExtractionDecision(
            MemoryType.episodic,
            scope,
            0.72,
            0.65,
            "Tool observations are episodic evidence; explicit scratch notes stay agent-local.",
            ("event:tool_result", f"scope:{scope}"),
        )
    if event.event_type == EventType.agent_message_sent and signals["decision_signal"]:
        return ExtractionDecision(
            MemoryType.episodic,
            MemoryScope.task_local,
            0.72,
            0.62,
            "Agent messages that contain decisions are captured as task-local episodic memory.",
            ("event:agent_message", "content:decision"),
        )
    return ExtractionDecision(
        MemoryType.working,
        MemoryScope.agent_local,
        0.65,
        0.45,
        "Unclassified agent activity is kept as local working memory until promoted or refined.",
        ("event:fallback",),
    )


def classify_event(event: AgentEventModel) -> tuple[MemoryType, MemoryScope, float, float]:
    decision = classify_event_with_signals(event)
    return decision.memory_type, decision.scope, decision.confidence, decision.importance


def classify_event_with_signals(event: AgentEventModel) -> ExtractionDecision:
    signals = detect_content_signals(event.content)
    decision = _base_decision(event, signals)
    confidence = decision.confidence
    importance = decision.importance
    applied_rules = list(decision.applied_rules)

    if signals["failure_signal"] or signals["risk_signal"]:
        importance += 0.1
        confidence += 0.03
        applied_rules.append("content:risk_or_failure")
    if signals["decision_signal"]:
        importance += 0.05
        applied_rules.append("content:decision")
    if signals["scratch_signal"] and event.agent_role == AgentRole.coder:
        confidence += 0.03
        applied_rules.append("content:scratch")

    return ExtractionDecision(
        decision.memory_type,
        decision.scope,
        _clamp(confidence),
        _clamp(importance),
        decision.reason,
        tuple(applied_rules),
    )


def build_extraction_signals(event: AgentEventModel, memory: MemoryCreate, decision: ExtractionDecision) -> dict:
    signals = detect_content_signals(event.content)
    return {
        **signals,
        "event_type": str(event.event_type),
        "agent_role": str(event.agent_role),
        "content_length": len(event.content),
        "memory_type": str(memory.memory_type),
        "scope": str(memory.scope),
        "applied_rules": list(decision.applied_rules),
        "extractor": "structured-rule-v2",
    }


class RuleBasedExtractor:
    name = "rule"

    def extract(self, event: AgentEventModel) -> ExtractionResult:
        if not event.content.strip():
            return ExtractionResult(
                should_write=False,
                memory=None,
                reason="Empty event content is not written to memory.",
                signals={
                    "event_type": str(event.event_type),
                    "agent_role": str(event.agent_role),
                    "content_length": len(event.content),
                    "extractor": "structured-rule-v2",
                    "applied_rules": ["content:empty"],
                },
                provider=self.name,
            )
        decision = classify_event_with_signals(event)
        memory = MemoryCreate(
            task_id=event.task_id,
            agent_id=event.agent_id,
            memory_type=decision.memory_type,
            scope=decision.scope,
            content=event.content,
            summary=summarize(event.content),
            confidence=decision.confidence,
            importance=decision.importance,
            source_event_id=event.event_id,
        )
        return ExtractionResult(
            should_write=True,
            memory=memory,
            reason=decision.reason,
            signals=build_extraction_signals(event, memory, decision),
            provider=self.name,
        )


def create_extractor_provider(*, backend: str = "rule") -> ExtractorProvider:
    if backend == "rule":
        return RuleBasedExtractor()
    raise ValueError(f"Unsupported extractor backend: {backend}")


def explain_extraction(event: AgentEventModel, memory: MemoryCreate) -> tuple[str, dict]:
    result = RuleBasedExtractor().extract(event)
    if result.memory is None:
        return result.reason, result.signals
    return result.reason, build_extraction_signals(event, memory, classify_event_with_signals(event))
    return decision.reason, signals


def extract_memory(event: AgentEventModel) -> MemoryCreate | None:
    return RuleBasedExtractor().extract(event).memory
