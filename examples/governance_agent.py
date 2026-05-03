import json
import os
import urllib.error
import urllib.parse
import urllib.request


BASE_URL = os.getenv("AGENTMEMOS_BASE_URL", "http://127.0.0.1:8014")
MIN_DUPLICATE_CONFIDENCE = float(os.getenv("AGENTMEMOS_GOVERNANCE_DUPLICATE_CONFIDENCE", "0.85"))
MAX_ACCEPTS = int(os.getenv("AGENTMEMOS_GOVERNANCE_MAX_ACCEPTS", "10"))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path: str, method: str = "GET", payload: dict | None = None) -> dict | list:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with OPENER.open(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {error.code} {detail}") from error


def get_json(path: str) -> dict | list:
    return api(path)


def post_json(path: str, payload: dict) -> dict | list:
    return api(path, method="POST", payload=payload)


def main() -> None:
    print(f"Governance agent connected to {BASE_URL}")
    insights = get_json("/memory-insights?limit=20")
    suggestions = get_json("/memory-relation-suggestions?limit=50")

    open_conflicts = [item for item in insights if item.get("insight_type") == "open_conflicts_with"]
    duplicate_suggestions = [
        item
        for item in suggestions
        if item.get("relation_type") == "duplicates"
        and float(item.get("confidence") or 0) >= MIN_DUPLICATE_CONFIDENCE
    ]

    print(f"insights={len(insights)} open_conflicts={len(open_conflicts)}")
    print(
        "high_confidence_duplicate_suggestions="
        f"{len(duplicate_suggestions)} threshold={MIN_DUPLICATE_CONFIDENCE} max_accepts={MAX_ACCEPTS}"
    )

    accepted = []
    for suggestion in duplicate_suggestions[:MAX_ACCEPTS]:
        suggestion_id = urllib.parse.quote(suggestion["suggestion_id"])
        result = post_json(
            f"/memory-relation-suggestions/{suggestion_id}/accept",
            {
                "actor": "governance_agent",
                "reason": "Accepted high-confidence duplicate suggestion for canonical cleanup.",
            },
        )
        accepted.append(result)
        relation = result["relation"]
        print(
            "accepted",
            suggestion["suggestion_id"],
            relation["relation_id"],
            relation["relation_type"],
            suggestion["confidence"],
        )

    for conflict in open_conflicts[:10]:
        print("conflict_needs_review", conflict["insight_id"], ",".join(conflict.get("memory_ids", [])))

    print(f"accepted_duplicate_suggestions={len(accepted)}")


if __name__ == "__main__":
    main()
