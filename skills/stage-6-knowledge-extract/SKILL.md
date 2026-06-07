---
name: stage-6-knowledge-extract
description: Generate ResearchClaw Stage 6 KNOWLEDGE_EXTRACT artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `cards/` knowledge-card markdown files from Stage 5 `shortlist.jsonl`, optional web context, or externally supplied LLM card JSON.
---

# Stage 6 Knowledge Extract

## Overview

Use `scripts/stage6_knowledge_extract.py` to generate Stage 6 knowledge cards under `cards/`. The script is self-contained and uses only Python standard library modules.

## Quick Start

```bash
python scripts/stage6_knowledge_extract.py \
  --output-dir ./stage-06 \
  --topic "Agent trajectory analysis" \
  --shortlist-jsonl ../stage-05/shortlist.jsonl
```

## LLM-Compatible Injection

To preserve externally generated or LLM-generated knowledge cards while keeping this skill independent:

```bash
python scripts/stage6_knowledge_extract.py \
  --output-dir ./stage-06 \
  --topic "..." \
  --shortlist-jsonl ../stage-05/shortlist.jsonl \
  --cards-json ./llm_cards.json
```

The cards file may be a list or `{"cards": [...]}`. Each card can include `card_id`, `title`, `cite_key`, `problem`, `method`, `data`, `metrics`, `findings`, `limitations`, and `citation`.

## Python API

```python
from stage6_knowledge_extract import Stage6Config, generate_stage6_artifacts, read_jsonl

shortlist = read_jsonl("stage-05/shortlist.jsonl")
result = generate_stage6_artifacts(
    "stage-06",
    Stage6Config(topic="Agent trajectory analysis"),
    shortlist=shortlist,
)
```

## Output Contract

Treat a successful run as complete when:

- `cards/` exists.
- At least one `card-*.md` file exists when shortlist rows are available.
- Each card contains title, problem, method, data, metrics, findings, limitations, and citation sections.
- `cards_index.json` records the generated card filenames.
- The printed JSON reports `stage: 6`, `stage_name: "KNOWLEDGE_EXTRACT"`, and evidence refs under `stage-06/`.
