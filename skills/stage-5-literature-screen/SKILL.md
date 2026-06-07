---
name: stage-5-literature-screen
description: Generate ResearchClaw Stage 5 LITERATURE_SCREEN artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `shortlist.jsonl` from Stage 4 `candidates.jsonl`, including keyword prefiltering, fallback scoring, minimum shortlist supplementation, and optional externally supplied LLM shortlist data.
---

# Stage 5 Literature Screen

## Overview

Use `scripts/stage5_literature_screen.py` to screen Stage 4 candidates and generate `shortlist.jsonl`. The script is self-contained and uses only Python standard library modules.

## Quick Start

```bash
python scripts/stage5_literature_screen.py \
  --output-dir ./stage-05 \
  --topic "Agent trajectory analysis" \
  --domains "ml,agents" \
  --candidates-jsonl ../stage-04/candidates.jsonl
```

## LLM-Compatible Injection

To preserve an externally generated or LLM-generated shortlist while keeping the skill independent:

```bash
python scripts/stage5_literature_screen.py \
  --output-dir ./stage-05 \
  --topic "..." \
  --candidates-jsonl ../stage-04/candidates.jsonl \
  --shortlist-json ./llm_shortlist.json
```

The shortlist file may be a list or `{"shortlist": [...]}`.

Use `--model-rejected-all` to mirror the strict-screen paused path. The script writes `screen_meta.json` and returns `status: "paused"` instead of backfilling rejected papers.

## Python API

```python
from stage5_literature_screen import Stage5Config, generate_stage5_artifacts, read_jsonl

candidates = read_jsonl("stage-04/candidates.jsonl")
result = generate_stage5_artifacts(
    "stage-05",
    Stage5Config(topic="Agent trajectory analysis", domains=("ml", "agents")),
    candidates=candidates,
)
```

## Output Contract

Treat a successful run as complete when:

- `shortlist.jsonl` exists and contains one JSON object per selected paper.
- `screen_meta.json` records candidate counts, keyword filtering, shortlist size, and timestamp.
- Fallback rows include `relevance_score`, `quality_score`, and `keep_reason`.
- The printed JSON reports `stage: 5`, `stage_name: "LITERATURE_SCREEN"`, and evidence refs under `stage-05/`.
