import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

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
    if event.event_type == EventType.conversation_turn_observed:
        return ExtractionDecision(
            MemoryType.episodic,
            MemoryScope.task_local,
            0.7,
            0.6,
            "Observed conversation turns are captured as task-local episodic memory for benchmark replay.",
            ("event:conversation_turn",),
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


LLMTransport = Callable[[dict[str, Any]], dict[str, Any]]


class OpenAIChatExtractor:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 20.0,
        fallback_provider: ExtractorProvider | None = None,
        transport: LLMTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.fallback_provider = fallback_provider or RuleBasedExtractor()
        self.transport = transport

    def extract(self, event: AgentEventModel) -> ExtractionResult:
        if not self.api_key and self.transport is None:
            return self._fallback(event, "OpenAI-compatible extractor is not configured with an API key.")
        try:
            raw = self._call_model(event)
            return self._result_from_model(event, raw)
        except Exception as exc:
            return self._fallback(event, f"OpenAI-compatible extractor failed: {_redact_secret(str(exc))}")

    def _call_model(self, event: AgentEventModel) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are AgentMemOS memory extraction classifier. Return only JSON. "
                        "Choose whether an agent event should become memory. Use memory_type one of "
                        "working, episodic, semantic, procedural. Use scope one of agent-local, "
                        "task-local, team-shared, project-global. Confidence and importance must be 0..1."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "event_id": event.event_id,
                            "event_type": str(event.event_type),
                            "task_id": event.task_id,
                            "agent_id": event.agent_id,
                            "agent_role": str(event.agent_role),
                            "content": event.content,
                            "metadata": event.event_metadata or {},
                            "required_json_schema": {
                                "should_write": "boolean",
                                "memory_type": "working|episodic|semantic|procedural",
                                "scope": "agent-local|task-local|team-shared|project-global",
                                "content": "string; usually the original event content unless a tighter memory statement is safer",
                                "summary": "string",
                                "confidence": "number 0..1",
                                "importance": "number 0..1",
                                "reason": "string",
                                "signals": "object with concise evidence flags or notes",
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        if self.transport is not None:
            return self.transport(payload)

        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

    def _result_from_model(self, event: AgentEventModel, raw: dict[str, Any]) -> ExtractionResult:
        content = raw["choices"][0]["message"]["content"]
        data = _parse_json_object(content)
        should_write = bool(data.get("should_write"))
        signals = dict(data.get("signals") or {})
        signals.update(
            {
                "extractor": "openai-compatible-llm-v1",
                "model": self.model,
                "fallback": False,
            }
        )
        if not should_write:
            return ExtractionResult(
                should_write=False,
                memory=None,
                reason=str(data.get("reason") or "LLM extractor decided not to write memory."),
                signals=signals,
                provider=self.name,
            )
        memory = MemoryCreate(
            task_id=event.task_id,
            agent_id=event.agent_id,
            memory_type=MemoryType(str(data["memory_type"])),
            scope=MemoryScope(str(data["scope"])),
            content=str(data.get("content") or event.content),
            summary=summarize(str(data.get("summary") or event.content)),
            confidence=_clamp(float(data.get("confidence", 0.75))),
            importance=_clamp(float(data.get("importance", 0.5))),
            source_event_id=event.event_id,
        )
        signals.update(
            {
                "event_type": str(event.event_type),
                "agent_role": str(event.agent_role),
                "content_length": len(event.content),
                "memory_type": str(memory.memory_type),
                "scope": str(memory.scope),
            }
        )
        return ExtractionResult(
            should_write=True,
            memory=memory,
            reason=str(data.get("reason") or "LLM extractor selected this event for memory."),
            signals=signals,
            provider=self.name,
        )

    def _fallback(self, event: AgentEventModel, reason: str) -> ExtractionResult:
        result = self.fallback_provider.extract(event)
        signals = {
            **result.signals,
            "extractor": "openai-compatible-llm-v1",
            "fallback": True,
            "fallback_extractor": result.provider,
            "fallback_reason": reason,
        }
        return ExtractionResult(
            should_write=result.should_write,
            memory=result.memory,
            reason=f"{result.reason} Fallback note: {reason}",
            signals=signals,
            provider=self.name,
        )


def _parse_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(cleaned[start : end + 1])


def _redact_secret(message: str) -> str:
    words = []
    for word in message.split():
        if word.startswith(("sk-", "sk_", "Bearer")) or len(word) > 24 and any(ch.isdigit() for ch in word):
            words.append("[redacted]")
        else:
            words.append(word)
    return " ".join(words)


def create_extractor_provider(*, backend: str = "rule") -> ExtractorProvider:
    if backend == "rule":
        return RuleBasedExtractor()
    if backend == "openai":
        from agentmemos.config import get_settings

        settings = get_settings()
        return OpenAIChatExtractor(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_extractor_model,
            timeout_seconds=settings.openai_extractor_timeout_seconds,
        )
    raise ValueError(f"Unsupported extractor backend: {backend}")


def explain_extraction(event: AgentEventModel, memory: MemoryCreate) -> tuple[str, dict]:
    result = RuleBasedExtractor().extract(event)
    if result.memory is None:
        return result.reason, result.signals
    return result.reason, build_extraction_signals(event, memory, classify_event_with_signals(event))


def extract_memory(event: AgentEventModel) -> MemoryCreate | None:
    return RuleBasedExtractor().extract(event).memory
