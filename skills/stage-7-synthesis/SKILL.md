---
name: stage-7-synthesis
description: Generate ResearchClaw Stage 7 SYNTHESIS artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `synthesis.md` from Stage 6 `cards/`, with optional externally supplied or LLM-generated synthesis markdown.
---

# Stage 7 Synthesis

## Overview

Use `scripts/stage7_synthesis.py` to generate the Stage 7 contract output `synthesis.md`. The script is self-contained and uses only Python standard library modules.

## Quick Start

```bash
python scripts/stage7_synthesis.py \
  --output-dir ./stage-07 \
  --topic "Agent trajectory analysis" \
  --cards-dir ../stage-06/cards
```

The command reads up to 24 markdown cards, prints a StageResult-like JSON object, and writes `synthesis.md`.

## LLM-Compatible Injection

By default, the script renders the deterministic fallback synthesis used when no LLM is available.

To preserve an externally generated or LLM-generated synthesis while keeping this skill independent:

```bash
python scripts/stage7_synthesis.py \
  --output-dir ./stage-07 \
  --topic "..." \
  --synthesis-text-file ./llm_synthesis.md
```

For Python callers, pass either `synthesis_markdown="..."` or a `synthesis_generator(context) -> str` callback to `generate_stage7_artifacts`.

## Python API

```python
from stage7_synthesis import Stage7Config, generate_stage7_artifacts, load_cards_context

cards_context = load_cards_context("stage-06/cards")
result = generate_stage7_artifacts(
    "stage-07",
    Stage7Config(topic="Agent trajectory analysis"),
    cards_context=cards_context,
)
```

## Output Contract

Treat a successful run as complete when:

- `synthesis.md` exists.
- It contains cluster overview, at least two gaps, prioritized opportunities, and generated timestamp.
- The printed JSON reports `stage: 7`, `stage_name: "SYNTHESIS"`, `status: "done"`, and an evidence ref under `stage-07/`.
