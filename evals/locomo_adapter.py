from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocomoQuestion:
    question_id: str
    question: str
    answer: str = ""
    evidence_dialog_ids: set[str] = field(default_factory=set)
    evidence_event_ids: set[str] = field(default_factory=set)
    evidence_texts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LocomoSample:
    sample_id: str
    task_id: str
    events: list[dict[str, Any]]
    questions: list[LocomoQuestion]


def load_locomo_samples(path: str | Path, *, limit_samples: int | None = None) -> list[LocomoSample]:
    with Path(path).open(encoding="utf-8") as dataset_file:
        raw = json.load(dataset_file)
    rows = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError("LoCoMo dataset must be a list or a dict with a data list")
    samples = [parse_locomo_sample(row, index=index) for index, row in enumerate(rows)]
    if limit_samples is not None:
        return samples[:limit_samples]
    return samples


def parse_locomo_sample(raw: dict[str, Any], *, index: int = 0) -> LocomoSample:
    sample_id = str(raw.get("sample_id") or raw.get("id") or f"locomo_{index}")
    task_id = f"locomo_{_safe_id(sample_id)}"
    conversation = raw.get("conversation") or raw.get("conversations") or raw
    events, dia_to_event = _conversation_events(conversation, sample_id=sample_id, task_id=task_id)
    questions = _extract_questions(raw, sample_id=sample_id, dia_to_event=dia_to_event)
    return LocomoSample(sample_id=sample_id, task_id=task_id, events=events, questions=questions)


def _conversation_events(
    conversation: dict[str, Any],
    *,
    sample_id: str,
    task_id: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    speaker_a = str(conversation.get("speaker_a") or "speaker_a")
    speaker_b = str(conversation.get("speaker_b") or "speaker_b")
    session_keys = sorted(
        [key for key, value in conversation.items() if re.fullmatch(r"session_\d+", str(key)) and isinstance(value, list)],
        key=lambda key: int(str(key).split("_")[1]),
    )
    events: list[dict[str, Any]] = []
    dia_to_event: dict[str, str] = {}
    for session_key in session_keys:
        session_index = int(session_key.split("_")[1])
        timestamp = conversation.get(f"{session_key}_date_time") or conversation.get(f"{session_key}_date")
        for turn_index, turn in enumerate(conversation.get(session_key) or []):
            if not isinstance(turn, dict):
                continue
            text = str(turn.get("text") or turn.get("content") or "").strip()
            if not text:
                continue
            dia_id = str(turn.get("dia_id") or f"{session_key}_{turn_index}")
            speaker = str(turn.get("speaker") or "")
            event_id = _stable_event_id(sample_id, dia_id)
            role = "user" if speaker == speaker_a else "assistant" if speaker == speaker_b else "assistant"
            agent_id = _safe_id(speaker or role)
            metadata = {
                "dataset": "locomo",
                "sample_id": sample_id,
                "session": session_key,
                "session_index": session_index,
                "session_timestamp": timestamp,
                "dia_id": dia_id,
                "speaker": speaker,
            }
            if turn.get("img_url"):
                metadata["img_url"] = turn.get("img_url")
            if turn.get("blip_caption"):
                metadata["blip_caption"] = turn.get("blip_caption")
                text = f"{text}\nImage caption: {turn['blip_caption']}"
            event = {
                "event_id": event_id,
                "event_type": "conversation.turn.observed",
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_role": role,
                "content": text,
                "metadata": metadata,
            }
            events.append(event)
            dia_to_event[dia_id] = event_id
    return events, dia_to_event


def _extract_questions(
    raw: dict[str, Any],
    *,
    sample_id: str,
    dia_to_event: dict[str, str],
) -> list[LocomoQuestion]:
    candidates: list[dict[str, Any]] = []
    for key in ("qa", "qas", "qa_pairs", "qa_annotations", "question_answering"):
        value = raw.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))
    if not candidates:
        candidates = _find_question_dicts(raw)

    questions: list[LocomoQuestion] = []
    seen: set[str] = set()
    for index, item in enumerate(candidates):
        question = str(item.get("question") or item.get("query") or "").strip()
        if not question:
            continue
        question_id = str(item.get("question_id") or item.get("qa_id") or f"{sample_id}_q{index}")
        if question_id in seen:
            continue
        seen.add(question_id)
        answer = str(item.get("answer") or item.get("gold_answer") or "")
        evidence = item.get("evidence") or item.get("evidences") or item.get("supporting_evidence") or []
        evidence_dialog_ids, evidence_texts = _evidence_parts(evidence)
        evidence_event_ids = {dia_to_event[dia_id] for dia_id in evidence_dialog_ids if dia_id in dia_to_event}
        questions.append(
            LocomoQuestion(
                question_id=question_id,
                question=question,
                answer=answer,
                evidence_dialog_ids=evidence_dialog_ids,
                evidence_event_ids=evidence_event_ids,
                evidence_texts=evidence_texts,
            )
        )
    return questions


def _find_question_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("question"), str) or isinstance(value.get("query"), str):
            found.append(value)
        for child in value.values():
            found.extend(_find_question_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_question_dicts(child))
    return found


def _evidence_parts(value: Any) -> tuple[set[str], list[str]]:
    dialog_ids: set[str] = set()
    texts: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key in ("dia_id", "dialog_id", "turn_id"):
                if item.get(key) is not None:
                    dialog_ids.add(str(item[key]))
            for key in ("text", "content", "evidence"):
                if isinstance(item.get(key), str):
                    texts.append(item[key])
            for key, child in item.items():
                if key in {"dia_id", "dialog_id", "turn_id", "text", "content", "evidence"}:
                    continue
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            if re.fullmatch(r"dia[_-]?\d+|[\w-]+_\d+|[A-Za-z]\d+:\d+", item):
                dialog_ids.add(item)
            else:
                texts.append(item)
        elif isinstance(item, int):
            dialog_ids.add(str(item))

    visit(value)
    return dialog_ids, texts


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return cleaned or "unknown"


def _stable_event_id(sample_id: str, dia_id: str) -> str:
    return f"evt_{sha1(f'locomo|{sample_id}|{dia_id}'.encode()).hexdigest()[:16]}"
