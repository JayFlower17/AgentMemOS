import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentmemos.enums import AgentRole, EventType
from agentmemos.config import _extract_secret
from agentmemos.extractor import OpenAIChatExtractor
from agentmemos.models import AgentEventModel


def main() -> None:
    api_key = os.environ.get("AGENTMEMOS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    key_file = os.environ.get("AGENTMEMOS_OPENAI_API_KEY_FILE") or os.environ.get("OPENAI_API_KEY_FILE")
    default_key_file = Path.home() / "Desktop" / "LLM-API-KEY.txt"
    if not key_file and default_key_file.exists():
        key_file = str(default_key_file)
    base_url = os.environ.get("AGENTMEMOS_OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("AGENTMEMOS_OPENAI_EXTRACTOR_MODEL", "gpt-4o-mini")
    if not api_key and key_file:
        inferred_label = "DeepSeek" if "deepseek" in base_url.casefold() else ""
        raw_secret_file = Path(key_file).read_text(encoding="utf-8")
        if not inferred_label and "DeepSeek:" in raw_secret_file and "AGENTMEMOS_OPENAI_BASE_URL" not in os.environ:
            inferred_label = "DeepSeek"
            base_url = "https://api.deepseek.com/v1"
            model = "deepseek-chat"
        label = os.environ.get("AGENTMEMOS_OPENAI_API_KEY_LABEL", inferred_label)
        api_key = _extract_secret(raw_secret_file, label)
    if not api_key:
        raise SystemExit("Set AGENTMEMOS_OPENAI_API_KEY or OPENAI_API_KEY before running this smoke test.")

    extractor = OpenAIChatExtractor(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=float(os.environ.get("AGENTMEMOS_OPENAI_EXTRACTOR_TIMEOUT_SECONDS", "20")),
    )
    event = AgentEventModel(
        event_id="evt_openai_extractor_smoke",
        event_type=EventType.review_finding_created,
        task_id="task_openai_extractor_smoke",
        agent_id="reviewer_1",
        agent_role=AgentRole.reviewer,
        content="The reviewer found that retries need bounded backoff before approval.",
        event_metadata={},
    )
    result = extractor.extract(event)
    print("provider:", result.provider)
    print("should_write:", result.should_write)
    print("reason:", result.reason)
    print("signals:", result.signals)
    if result.memory:
        print("memory_type:", result.memory.memory_type)
        print("scope:", result.memory.scope)
        print("summary:", result.memory.summary)
        print("confidence:", result.memory.confidence)
        print("importance:", result.memory.importance)


if __name__ == "__main__":
    main()
