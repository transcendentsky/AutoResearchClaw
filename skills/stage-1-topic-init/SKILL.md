---
name: stage-1-topic-init
description: Generate ResearchClaw Stage 1 TOPIC_INIT artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce Stage 1 outputs (`goal.md` and `hardware_profile.json`) from a research topic, project metadata, and local or SSH hardware detection.
---

# Stage 1 Topic Init

## Overview

Use `scripts/stage1_topic_init.py` to generate the Stage 1 contract outputs:

- `goal.md`
- `hardware_profile.json`

The script is self-contained and uses only Python standard library modules. It does not import `researchclaw`, project configs, prompt managers, adapters, or pipeline helpers.

## Quick Start

Run the script with direct arguments:

```bash
python scripts/stage1_topic_init.py \
  --output-dir ./stage-01 \
  --topic "Efficient retrieval-augmented scientific hypothesis generation" \
  --project-name "ResearchClaw" \
  --domains "ml,nlp" \
  --quality-threshold 0.8 \
  --daily-paper-count 5
```

The command prints a StageResult-like JSON object and writes the two artifacts into `--output-dir`.

## Python API

Import the reusable function when another script should call Stage 1 directly:

```python
from pathlib import Path
from stage1_topic_init import Stage1Config, generate_stage1_artifacts

result = generate_stage1_artifacts(
    Path("stage-01"),
    Stage1Config(
        topic="Efficient retrieval-augmented scientific hypothesis generation",
        project_name="ResearchClaw",
        domains=("ml", "nlp"),
        quality_threshold=0.8,
        daily_paper_count=5,
    ),
)
```

The return value contains `stage`, `stage_name`, `status`, `artifacts`, `evidence_refs`, `paths`, and `hardware`.

## Config Input

Use `--config config.json` for either flat JSON:

```json
{
  "topic": "Robust graph neural networks under distribution shift",
  "project_name": "ResearchClaw",
  "domains": ["ml", "graph"],
  "quality_threshold": 0.8,
  "daily_paper_count": 5
}
```

or ResearchClaw-like nested JSON:

```json
{
  "project": {"name": "ResearchClaw"},
  "research": {
    "topic": "Robust graph neural networks under distribution shift",
    "domains": ["ml", "graph"],
    "quality_threshold": 0.8,
    "daily_paper_count": 5
  },
  "experiment": {
    "mode": "sandbox",
    "sandbox": {"python_path": "python"}
  }
}
```

Command-line arguments override config values.

## Goal Generation

By default, the script renders the deterministic fallback `goal.md` used by Stage 1 when no LLM client is available.

To preserve an LLM-generated goal while keeping this skill independent, generate the markdown outside the script and pass it with:

```bash
python scripts/stage1_topic_init.py \
  --output-dir ./stage-01 \
  --topic "..." \
  --goal-text-file ./llm_goal.md
```

For Python callers, pass either `goal_markdown="..."` or a `goal_generator(context) -> str` callback to `generate_stage1_artifacts`.

## Hardware Detection

The script detects hardware in this order:

1. NVIDIA GPU via `nvidia-smi`
2. Apple Silicon MPS on local macOS
3. CPU-only fallback

For remote NVIDIA detection, pass SSH details:

```bash
python scripts/stage1_topic_init.py \
  --output-dir ./stage-01 \
  --topic "..." \
  --ssh-host gpu.example.org \
  --ssh-user ubuntu \
  --ssh-key-path ~/.ssh/id_rsa
```

To mirror the original Stage 1 optional PyTorch check/install behavior for sandbox GPU runs, add `--ensure-torch`. Leave it off when artifact generation should avoid package installation side effects.

## Output Contract

Treat a successful run as complete when:

- `goal.md` contains topic, scope, SMART goal, constraints, success criteria, and generated timestamp.
- `hardware_profile.json` contains `has_gpu`, `gpu_type`, `gpu_name`, `vram_mb`, `tier`, and `warning`.
- The printed JSON reports `stage: 1`, `stage_name: "TOPIC_INIT"`, `status: "done"`, and evidence refs for `stage-01/goal.md` and `stage-01/hardware_profile.json`.
