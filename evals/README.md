# AgentMemOS Evals

This directory contains interview-oriented evaluation entrypoints for AgentMemOS.

## LoCoMo Retrieval Eval

Download the official LoCoMo dataset from https://github.com/snap-research/locomo and place it at:

```text
evals/datasets/locomo10.json
```

Run a small retrieval eval against a running AgentMemOS API:

```powershell
python evals/run_retrieval_eval.py --dataset evals/datasets/locomo10.json --base-url http://127.0.0.1:8000 --limit-samples 3
```

The script replays conversation turns as `conversation.turn.observed` events, waits for memory extraction, retrieves against each QA question, and reports Recall@1/3/5, MRR, average latency, and memory count.

## Governance Eval

Run the local gold-set governance eval:

```powershell
python evals/run_governance_eval.py --dataset evals/datasets/agentmemos_governance_gold.json --base-url http://127.0.0.1:8000
```

This eval creates duplicate, conflict, and supersedes memory cases, checks relation suggestions, and verifies superseded-memory filtering for the supersedes case.

