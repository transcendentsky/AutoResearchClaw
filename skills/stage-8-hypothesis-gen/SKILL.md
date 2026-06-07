---
name: stage-8-hypothesis-gen
description: Generate ResearchClaw Stage 8 HYPOTHESIS_GEN artifacts as a standalone skill, without importing or depending on the ResearchClaw project. Use when Codex needs to create or reproduce `hypotheses.md` from Stage 7 `synthesis.md`, with optional debate perspectives, human guidance, candidates for novelty checking, or externally supplied LLM hypotheses.
---

# Stage 8 Hypothesis Gen

## Overview

Use `scripts/stage8_hypothesis_gen.py` to generate the Stage 8 contract output `hypotheses.md`. The script is self-contained and uses only Python standard library modules.

## Quick Start

```bash
python scripts/stage8_hypothesis_gen.py \
  --output-dir ./stage-08 \
  --topic "Agent trajectory analysis" \
  --synthesis-file ../stage-07/synthesis.md
```

## LLM-Compatible Injection

By default, the script renders the deterministic fallback hypotheses used when no LLM is available.

To preserve externally generated or LLM-generated hypotheses:

```bash
python scripts/stage8_hypothesis_gen.py \
  --output-dir ./stage-08 \
  --topic "..." \
  --synthesis-file ../stage-07/synthesis.md \
  --hypotheses-text-file ./llm_hypotheses.md
```

Use `--perspectives-json` to pass debate outputs and `--hitl-guidance-file` to include human guidance. Without an external generator, guidance is appended as a section for later refinement.

Use `--candidates-jsonl ../stage-04/candidates.jsonl` to write a local heuristic `novelty_report.json`. Use `--novelty-report-json` to preserve an externally generated novelty report.

## Python API

```python
from stage8_hypothesis_gen import Stage8Config, generate_stage8_artifacts

synthesis = open("stage-07/synthesis.md", encoding="utf-8").read()
result = generate_stage8_artifacts(
    "stage-08",
    Stage8Config(topic="Agent trajectory analysis"),
    synthesis=synthesis,
)
```

## Output Contract

Treat a successful run as complete when:

- `hypotheses.md` exists.
- It contains at least H1, H2, and H3.
- `novelty_report.json` exists when candidates or an external novelty report are supplied.
- The printed JSON reports `stage: 8`, `stage_name: "HYPOTHESIS_GEN"`, `status: "done"`, and an evidence ref under `stage-08/`.
