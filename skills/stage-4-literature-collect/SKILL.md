---
name: stage-4-literature-collect
description: Generate ResearchClaw Stage 4 LITERATURE_COLLECT artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `candidates.jsonl`, `references.bib`, and `search_meta.json` from Stage 3 `queries.json` and optional search plan or externally supplied candidate papers.
---

# Stage 4 Literature Collect

## Overview

Use `scripts/stage4_literature_collect.py` to generate Stage 4 literature collection artifacts. The script is self-contained and uses only Python standard library modules.

## Quick Start

```bash
python scripts/stage4_literature_collect.py \
  --output-dir ./stage-04 \
  --topic "Agent trajectory analysis" \
  --queries-json ../stage-03/queries.json
```

The script tries public scholarly APIs, deduplicates papers, writes `candidates.jsonl`, generates `references.bib` for non-placeholder papers, and writes `search_meta.json`.

## Offline Or Controlled Runs

Use `--skip-real-search` when network access is unavailable or deterministic fallback output is desired:

```bash
python scripts/stage4_literature_collect.py \
  --output-dir ./stage-04 \
  --topic "Agent trajectory analysis" \
  --queries-json ../stage-03/queries.json \
  --skip-real-search
```

To inject externally generated or LLM-generated candidates while keeping the skill independent:

```bash
python scripts/stage4_literature_collect.py \
  --output-dir ./stage-04 \
  --topic "..." \
  --queries-json ../stage-03/queries.json \
  --candidates-json ./candidate_papers.json
```

`candidate_papers.json` may be either a list of candidate objects or `{"candidates": [...]}`.

## Python API

```python
from stage4_literature_collect import Stage4Config, generate_stage4_artifacts

result = generate_stage4_artifacts(
    "stage-04",
    Stage4Config(topic="Agent trajectory analysis", real_search=False),
    queries_data={"queries": ["agent trajectory analysis"], "year_min": 2020},
)
```

## Output Contract

Treat a successful run as complete when:

- `candidates.jsonl` exists and contains one JSON object per line.
- `search_meta.json` records queries, year, candidate count, and whether real search succeeded.
- `references.bib` exists when at least one non-placeholder candidate is available.
- The printed JSON reports `stage: 4`, `stage_name: "LITERATURE_COLLECT"`, and evidence refs under `stage-04/`.
