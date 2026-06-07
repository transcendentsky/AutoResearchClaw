---
name: stage-2-problem-decompose
description: Generate ResearchClaw Stage 2 PROBLEM_DECOMPOSE artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `problem_tree.md` from a research topic and optional Stage 1 `goal.md`, with optional externally supplied LLM decomposition or topic evaluation JSON.
---

# Stage 2 Problem Decompose

## Overview

Use `scripts/stage2_problem_decompose.py` to generate the Stage 2 contract output `problem_tree.md`. The script is self-contained and uses only Python standard library modules.

## Quick Start

Run from the skill directory:

```bash
python scripts/stage2_problem_decompose.py \
  --output-dir ./stage-02 \
  --topic "Agent trajectory analysis" \
  --goal-file ../stage-01/goal.md
```

The command prints a StageResult-like JSON object and writes `problem_tree.md`.

## Python API

```python
from pathlib import Path
from stage2_problem_decompose import Stage2Config, generate_stage2_artifacts

goal_text = Path("stage-01/goal.md").read_text(encoding="utf-8")
result = generate_stage2_artifacts(
    "stage-02",
    Stage2Config(topic="Agent trajectory analysis"),
    goal_text=goal_text,
)
```

The return value contains `stage`, `stage_name`, `status`, `artifacts`, `evidence_refs`, and `paths`.

## Inputs

Use either direct arguments or `--config config.json`. The config may be flat:

```json
{
  "topic": "Agent trajectory analysis",
  "domains": ["ml", "agents"]
}
```

or ResearchClaw-like nested JSON:

```json
{
  "research": {
    "topic": "Agent trajectory analysis",
    "domains": ["ml", "agents"]
  }
}
```

If `--topic` is omitted, the script tries to infer the topic from `--goal-file`.

For non-ASCII topics on Windows shells, prefer `--goal-file` or `--config` over passing the topic directly on the command line.

## LLM-Compatible Injection

By default, the script renders the deterministic fallback decomposition used when no LLM is available.

To preserve an LLM-generated Stage 2 decomposition while keeping this skill independent, generate the markdown outside the script and pass:

```bash
python scripts/stage2_problem_decompose.py \
  --output-dir ./stage-02 \
  --topic "..." \
  --problem-text-file ./llm_problem_tree.md
```

For Python callers, pass either `problem_markdown="..."` or a `problem_generator(context) -> str` callback to `generate_stage2_artifacts`.

To mirror the optional topic-quality check, pass `--topic-evaluation-json eval.json` or `topic_evaluation={...}`. The script writes `topic_evaluation.json` only when evaluation data is supplied.

## Output Contract

Treat a successful run as complete when:

- `problem_tree.md` exists.
- It contains source, at least five sub-questions, priority ranking, risks, and generated timestamp.
- The printed JSON reports `stage: 2`, `stage_name: "PROBLEM_DECOMPOSE"`, `status: "done"`, and evidence refs under `stage-02/`.
