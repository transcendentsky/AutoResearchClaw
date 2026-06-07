---
name: stage-3-search-strategy
description: Generate ResearchClaw Stage 3 SEARCH_STRATEGY artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `search_plan.yaml`, `sources.json`, and `queries.json` from a research topic and optional Stage 2 `problem_tree.md`, including fallback query generation and query sanitization.
---

# Stage 3 Search Strategy

## Overview

Use `scripts/stage3_search_strategy.py` to generate the Stage 3 contract outputs:

- `search_plan.yaml`
- `sources.json`
- `queries.json`

The script is self-contained and uses only Python standard library modules. It does not import `researchclaw`, adapters, prompt managers, or pipeline helpers.

## Quick Start

Run from the skill directory:

```bash
python scripts/stage3_search_strategy.py \
  --output-dir ./stage-03 \
  --topic "Agent trajectory analysis" \
  --problem-tree-file ../stage-02/problem_tree.md
```

The command prints a StageResult-like JSON object and writes the three artifacts.

## Python API

```python
from pathlib import Path
from stage3_search_strategy import Stage3Config, generate_stage3_artifacts

problem_tree = Path("stage-02/problem_tree.md").read_text(encoding="utf-8")
result = generate_stage3_artifacts(
    "stage-03",
    Stage3Config(topic="Agent trajectory analysis"),
    problem_tree=problem_tree,
)
```

## Inputs

Use either direct arguments or `--config config.json`. The config may be flat:

```json
{
  "topic": "Agent trajectory analysis",
  "min_year": 2020
}
```

or ResearchClaw-like nested JSON:

```json
{
  "research": {"topic": "Agent trajectory analysis"},
  "openclaw_bridge": {"use_web_fetch": false}
}
```

If `--topic` is omitted, the script tries to infer the topic from `--problem-tree-file`.

For non-ASCII topics on Windows shells, prefer `--problem-tree-file` or `--config` over passing the topic directly on the command line.

## LLM-Compatible Injection

By default, the script builds the deterministic fallback plan:

- keyword-core search strategy
- backward/forward citation strategy
- arXiv and Semantic Scholar sources
- sanitized 3-8 word query strings

To preserve an externally generated plan while keeping this skill independent, pass one of:

```bash
python scripts/stage3_search_strategy.py \
  --output-dir ./stage-03 \
  --topic "..." \
  --plan-json-file ./search_plan.json
```

```bash
python scripts/stage3_search_strategy.py \
  --output-dir ./stage-03 \
  --topic "..." \
  --plan-yaml-file ./search_plan.yaml
```

Use `--sources-json-file sources.json` to override the default source list. The file can be either a list of source objects or an object with a `sources` list.

## Source Verification

Add `--verify-sources` only when network access is available and URL verification is desired. It performs simple HTTP HEAD checks using `urllib`; otherwise sources are written as `available`, matching the no-web-fetch fallback behavior.

## Output Contract

Treat a successful run as complete when:

- `search_plan.yaml` contains at least two search strategies.
- `sources.json` contains at least arXiv and Semantic Scholar source records.
- `queries.json` contains `queries`, `year_min`, `model_queries_extracted`, and `fallback_reason`.
- The printed JSON reports `stage: 3`, `stage_name: "SEARCH_STRATEGY"`, `status: "done"`, and evidence refs under `stage-03/`.
