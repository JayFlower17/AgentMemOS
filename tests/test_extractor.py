from agentmemos.enums import AgentRole, EventType, MemoryScope, MemoryType
from agentmemos.config import _extract_secret
from agentmemos.extractor import (
    OpenAIChatExtractor,
    RuleBasedExtractor,
    create_extractor_provider,
    detect_content_signals,
    explain_extraction,
    extract_memory,
)
from agentmemos.models import AgentEventModel


def make_event(event_type: EventType, role: AgentRole, content: str) -> AgentEventModel:
    return AgentEventModel(
        event_id="evt_extractor_test",
        event_type=event_type,
        task_id="task_extractor_test",
        agent_id=f"{role}_1",
        agent_role=role,
        content=content,
        event_metadata={},
    )


def test_review_finding_extracts_team_shared_episodic_memory_with_signals():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    memory = extract_memory(event)
    assert memory is not None
    assert memory.memory_type == MemoryType.episodic
    assert memory.scope == MemoryScope.team_shared
    assert memory.importance >= 0.9

    reason, signals = explain_extraction(event, memory)
    assert "Review findings" in reason
    assert signals["decision_signal"] is True
    assert signals["extractor"] == "structured-rule-v2"
    assert "event:review_finding" in signals["applied_rules"]


def test_completed_task_with_procedural_language_extracts_reusable_team_guidance():
    event = make_event(
        EventType.task_completed,
        AgentRole.planner,
        "When demoing AgentMemOS, seed extracted events before opening the dashboard.",
    )

    memory = extract_memory(event)
    assert memory is not None
    assert memory.memory_type == MemoryType.procedural
    assert memory.scope == MemoryScope.team_shared
    assert memory.importance >= 0.86

    _, signals = explain_extraction(event, memory)
    assert signals["procedure_signal"] is True
    assert "content:procedure" in signals["applied_rules"]


def test_coder_scratch_tool_observation_stays_agent_local():
    event = make_event(
        EventType.tool_result_observed,
        AgentRole.coder,
        "Temporary scratch: pytest failed because the retry timeout exceeded the limit.",
    )

    memory = extract_memory(event)
    assert memory is not None
    assert memory.memory_type == MemoryType.episodic
    assert memory.scope == MemoryScope.agent_local
    assert memory.importance > 0.65

    _, signals = explain_extraction(event, memory)
    assert signals["scratch_signal"] is True
    assert signals["failure_signal"] is True
    assert "content:risk_or_failure" in signals["applied_rules"]


def test_content_signal_detection_supports_chinese_project_notes():
    signals = detect_content_signals("必须先处理冲突，否则会出现失败风险。")
    assert signals["procedure_signal"] is True
    assert signals["risk_signal"] is True
    assert signals["failure_signal"] is True


def test_rule_based_extractor_returns_structured_result():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    result = RuleBasedExtractor().extract(event)

    assert result.should_write is True
    assert result.memory is not None
    assert result.memory.memory_type == MemoryType.episodic
    assert result.reason.startswith("Review findings")
    assert result.provider == "rule"
    assert result.signals["extractor"] == "structured-rule-v2"
    assert "event:review_finding" in result.signals["applied_rules"]


def test_rule_based_extractor_skips_empty_content_with_auditable_reason():
    event = make_event(EventType.agent_message_sent, AgentRole.coder, "   ")

    result = RuleBasedExtractor().extract(event)

    assert result.should_write is False
    assert result.memory is None
    assert "Empty event content" in result.reason
    assert "content:empty" in result.signals["applied_rules"]


def test_extractor_provider_factory_defaults_to_rule_backend():
    provider = create_extractor_provider()

    assert isinstance(provider, RuleBasedExtractor)


def test_openai_chat_extractor_maps_structured_response_to_memory():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    def fake_transport(payload):
        assert payload["model"] == "deepseek-chat"
        return {
            "choices": [
                {
                    "message": {
                        "content": """
                        {
                          "should_write": true,
                          "memory_type": "procedural",
                          "scope": "team-shared",
                          "content": "Retry approval requires bounded backoff.",
                          "summary": "Retry approval requires bounded backoff.",
                          "confidence": 0.89,
                          "importance": 0.93,
                          "reason": "This is reusable review guidance.",
                          "signals": {"decision_signal": true, "procedure_signal": true}
                        }
                        """
                    }
                }
            ]
        }

    result = OpenAIChatExtractor(
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        transport=fake_transport,
    ).extract(event)

    assert result.should_write is True
    assert result.memory is not None
    assert result.memory.memory_type == MemoryType.procedural
    assert result.memory.scope == MemoryScope.team_shared
    assert result.memory.summary == "Retry approval requires bounded backoff."
    assert result.reason == "This is reusable review guidance."
    assert result.signals["extractor"] == "openai-compatible-llm-v1"
    assert result.signals["fallback"] is False


def test_openai_chat_extractor_can_decline_memory_write():
    event = make_event(EventType.agent_message_sent, AgentRole.coder, "ok")

    def fake_transport(_payload):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"should_write": false, "reason": "Trivial acknowledgement.", "signals": {"trivial": true}}'
                    }
                }
            ]
        }

    result = OpenAIChatExtractor(api_key="test-key", transport=fake_transport).extract(event)

    assert result.should_write is False
    assert result.memory is None
    assert result.reason == "Trivial acknowledgement."
    assert result.signals["trivial"] is True


def test_openai_chat_extractor_falls_back_to_rule_provider_on_failure():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    def failing_transport(_payload):
        raise RuntimeError("network down")

    result = OpenAIChatExtractor(api_key="test-key", transport=failing_transport).extract(event)

    assert result.should_write is True
    assert result.memory is not None
    assert result.memory.memory_type == MemoryType.episodic
    assert result.provider == "openai"
    assert result.signals["fallback"] is True
    assert result.signals["fallback_extractor"] == "rule"
    assert "network down" in result.signals["fallback_reason"]


def test_openai_chat_extractor_redacts_secret_like_error_text():
    event = make_event(
        EventType.review_finding_created,
        AgentRole.reviewer,
        "The reviewer found that retries need bounded backoff before approval.",
    )

    def failing_transport(_payload):
        raise RuntimeError("Invalid header value Bearer sk-secret-token")

    result = OpenAIChatExtractor(api_key="test-key", transport=failing_transport).extract(event)

    assert "sk-secret-token" not in result.signals["fallback_reason"]
    assert "[redacted]" in result.signals["fallback_reason"]


def test_labeled_secret_file_parsing_supports_multi_provider_files():
    raw = "DeepSeek: sk-deepseek\nKimi: sk-kimi\nEmbedding: sk-embedding"

    assert _extract_secret(raw, "DeepSeek") == "sk-deepseek"
    assert _extract_secret(raw, "Kimi") == "sk-kimi"
