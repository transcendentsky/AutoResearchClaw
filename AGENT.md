# Agent Guide: Stage 1-8 Standalone Skills

本项目的 `skills/` 目录下包含 8 个可独立运行的 ResearchClaw 前半段流水线 skills。它们被设计成可搬走的小工具包：每个 skill 都包含一个 `SKILL.md` 和一个 `scripts/` 下的 Python 脚本函数，脚本只使用 Python 标准库，不依赖 `researchclaw` 项目包或原项目文件。

这些 skills 通常按 Stage 1 到 Stage 8 顺序生成 artifacts。前一阶段的输出会成为后一阶段的输入。

## Recommended Order

1. `stage-1-topic-init`
2. `stage-2-problem-decompose`
3. `stage-3-search-strategy`
4. `stage-4-literature-collect`
5. `stage-5-literature-screen`
6. `stage-6-knowledge-extract`
7. `stage-7-synthesis`
8. `stage-8-hypothesis-gen`

## Skill Summary

### Stage 1: `stage-1-topic-init`

Path: `skills/stage-1-topic-init`

Purpose: Initialize the research topic and hardware profile.

Main script: `scripts/stage1_topic_init.py`

Typical outputs:

- `goal.md`
- `hardware_profile.json`

Use this first when starting from a topic. It creates the research goal artifact and detects local or SSH hardware.

### Stage 2: `stage-2-problem-decompose`

Path: `skills/stage-2-problem-decompose`

Purpose: Decompose the research goal into sub-questions, priorities, and risks.

Main script: `scripts/stage2_problem_decompose.py`

Typical input:

- Stage 1 `goal.md`

Typical output:

- `problem_tree.md`

Use this after Stage 1 to create the problem decomposition needed by search planning.

### Stage 3: `stage-3-search-strategy`

Path: `skills/stage-3-search-strategy`

Purpose: Build a literature search plan, source registry, and sanitized query list.

Main script: `scripts/stage3_search_strategy.py`

Typical input:

- Stage 2 `problem_tree.md`

Typical outputs:

- `search_plan.yaml`
- `sources.json`
- `queries.json`

Use this before collecting papers. It creates query strings and source metadata for Stage 4.

### Stage 4: `stage-4-literature-collect`

Path: `skills/stage-4-literature-collect`

Purpose: Collect candidate literature from public scholarly APIs or offline fallback generation.

Main script: `scripts/stage4_literature_collect.py`

Typical inputs:

- Stage 3 `queries.json`
- Optional Stage 3 `search_plan.yaml`

Typical outputs:

- `candidates.jsonl`
- `search_meta.json`
- `references.bib` when non-placeholder papers are available

Use this after Stage 3. For deterministic or offline runs, pass the script's skip-real-search option.

### Stage 5: `stage-5-literature-screen`

Path: `skills/stage-5-literature-screen`

Purpose: Screen candidate papers into a shortlist using keyword prefiltering, fallback scores, and minimum shortlist supplementation.

Main script: `scripts/stage5_literature_screen.py`

Typical input:

- Stage 4 `candidates.jsonl`

Typical outputs:

- `shortlist.jsonl`
- `screen_meta.json`

Use this after Stage 4 to select the papers that should be summarized into knowledge cards.

### Stage 6: `stage-6-knowledge-extract`

Path: `skills/stage-6-knowledge-extract`

Purpose: Convert shortlisted papers into structured markdown knowledge cards.

Main script: `scripts/stage6_knowledge_extract.py`

Typical input:

- Stage 5 `shortlist.jsonl`

Typical outputs:

- `cards/`
- `cards_index.json`

Use this after Stage 5. Each generated card contains problem, method, data, metrics, findings, limitations, and citation sections.

### Stage 7: `stage-7-synthesis`

Path: `skills/stage-7-synthesis`

Purpose: Synthesize knowledge cards into topic clusters, gaps, and prioritized opportunities.

Main script: `scripts/stage7_synthesis.py`

Typical input:

- Stage 6 `cards/`

Typical output:

- `synthesis.md`

Use this after Stage 6 to produce the knowledge synthesis that informs hypothesis generation.

### Stage 8: `stage-8-hypothesis-gen`

Path: `skills/stage-8-hypothesis-gen`

Purpose: Generate falsifiable research hypotheses from the synthesis.

Main script: `scripts/stage8_hypothesis_gen.py`

Typical inputs:

- Stage 7 `synthesis.md`
- Optional Stage 4 `candidates.jsonl` for local heuristic novelty reporting

Typical outputs:

- `hypotheses.md`
- `novelty_report.json` when candidates or an external novelty report are supplied

Use this after Stage 7 to produce the hypothesis artifact consumed by later experiment-design stages.

## General Notes

- Each skill can be run independently, but the normal workflow is sequential.
- Each script exposes a reusable `generate_stage*_artifacts(...)` function and a CLI entry point.
- Each skill supports deterministic fallback output when no LLM output is supplied.
- LLM-generated content can be injected through the script arguments described in each skill's `SKILL.md`.
- For non-ASCII topics on Windows shells, prefer passing UTF-8 files or JSON config files instead of raw command-line topic text.
- The `agents/openai.yaml` files provide UI metadata only; the operational instructions live in each `SKILL.md`.
