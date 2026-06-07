#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 2 artifact generator.

The script does not import ResearchClaw modules. It can be copied with this
skill folder and run anywhere with Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ProblemGenerator = Callable[[Mapping[str, Any]], str]
TopicEvaluator = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class Stage2Config:
    """Minimal, project-independent config for Stage 2."""

    topic: str
    domains: tuple[str, ...] = ()
    stage_ref: str = "stage-02"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage2Config":
        research = _mapping(data.get("research"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 2 requires a non-empty topic")

        domains_value = data.get("domains", research.get("domains", ()))
        if isinstance(domains_value, str):
            domains = tuple(
                part.strip() for part in domains_value.split(",") if part.strip()
            )
        elif isinstance(domains_value, Sequence):
            domains = tuple(str(part).strip() for part in domains_value if str(part).strip())
        else:
            domains = ()

        return cls(
            topic=str(topic),
            domains=domains,
            stage_ref=str(data.get("stage_ref") or "stage-02"),
        )

    def to_prompt_context(self, goal_text: str) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "domains": ", ".join(self.domains) if self.domains else "general",
            "goal_text": goal_text,
        }


def generate_stage2_artifacts(
    output_dir: str | Path,
    config: Stage2Config | Mapping[str, Any],
    *,
    goal_text: str = "",
    problem_markdown: str | None = None,
    problem_generator: ProblemGenerator | None = None,
    topic_evaluation: Mapping[str, Any] | None = None,
    topic_evaluator: TopicEvaluator | None = None,
) -> dict[str, Any]:
    """Generate Stage 2 artifacts in *output_dir*.

    Writes `problem_tree.md`. Also writes `topic_evaluation.json` when
    evaluation data is supplied by the caller.
    """
    cfg = config if isinstance(config, Stage2Config) else Stage2Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if problem_markdown is None and problem_generator is not None:
        problem_markdown = problem_generator(cfg.to_prompt_context(goal_text))
    if problem_markdown is None:
        problem_markdown = render_default_problem_tree(cfg, goal_text=goal_text)

    problem_path = out / "problem_tree.md"
    problem_path.write_text(problem_markdown, encoding="utf-8")

    artifacts = ["problem_tree.md"]
    evidence_refs = [f"{cfg.stage_ref}/problem_tree.md"]
    paths: dict[str, str] = {"problem_tree_md": str(problem_path.resolve())}

    evaluation = topic_evaluation
    if evaluation is None and topic_evaluator is not None:
        evaluation = topic_evaluator(cfg.to_prompt_context(goal_text))
    if isinstance(evaluation, Mapping):
        eval_path = out / "topic_evaluation.json"
        eval_path.write_text(
            json.dumps(dict(evaluation), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        artifacts.append("topic_evaluation.json")
        evidence_refs.append(f"{cfg.stage_ref}/topic_evaluation.json")
        paths["topic_evaluation_json"] = str(eval_path.resolve())

    return {
        "stage": 2,
        "stage_name": "PROBLEM_DECOMPOSE",
        "status": "done",
        "artifacts": artifacts,
        "evidence_refs": evidence_refs,
        "paths": paths,
    }


def render_default_problem_tree(config: Stage2Config, *, goal_text: str = "") -> str:
    """Render the deterministic fallback problem tree used by Stage 2."""
    source_note = "Derived from `goal.md`"
    if goal_text.strip():
        source_note = "Derived from supplied `goal.md`"

    return f"""# Problem Decomposition

## Source
{source_note} for topic: {config.topic}

## Sub-questions
1. Which problem settings and benchmarks define current SOTA?
2. Which methodological gaps remain unresolved?
3. Which hypotheses are testable under realistic constraints?
4. Which datasets and metrics best discriminate method quality?
5. Which failure modes can invalidate expected gains?

## Priority Ranking
1. Problem framing and benchmark setup
2. Gap identification and hypothesis formulation
3. Experiment and metric design
4. Failure analysis and robustness checks

## Risks
- Ambiguous task definition
- Dataset leakage or metric mismatch

## Generated
{utcnow_iso()}
"""


def infer_topic_from_goal(goal_text: str) -> str:
    """Best-effort topic extraction from a Stage 1 `goal.md` file."""
    lines = goal_text.splitlines()
    for idx, line in enumerate(lines):
        normalized = re.sub(r"^[#\s]+", "", line).replace("*", "").strip().lower()
        if normalized == "topic":
            for following in lines[idx + 1 : idx + 6]:
                candidate = following.strip()
                if candidate and not candidate.startswith("#"):
                    return candidate.strip("*").strip()
    match = re.search(r"topic\s*[:：]\s*(.+)", goal_text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate standalone ResearchClaw Stage 2 artifacts.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for problem_tree.md.")
    parser.add_argument("--config", help="Optional JSON config file, flat or ResearchClaw-like.")
    parser.add_argument("--topic", help="Research topic. Overrides --config.")
    parser.add_argument("--domains", help="Comma-separated domain list. Overrides --config.")
    parser.add_argument("--goal-file", help="Stage 1 goal.md input.")
    parser.add_argument("--problem-text-file", help="Use this markdown file instead of fallback generation.")
    parser.add_argument("--topic-evaluation-json", help="Optional topic evaluation JSON to write.")
    parser.add_argument("--stage-ref", default="stage-02", help="Evidence ref prefix.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_config: dict[str, Any] = _load_json(args.config) if args.config else {}
    goal_text = (
        Path(args.goal_file).read_text(encoding="utf-8") if args.goal_file else ""
    )

    inferred_topic = infer_topic_from_goal(goal_text) if goal_text else ""
    overrides = {
        "topic": args.topic or inferred_topic,
        "domains": args.domains,
        "stage_ref": args.stage_ref,
    }
    raw_config.update({k: v for k, v in overrides.items() if v is not None and v != ""})

    problem_markdown = None
    if args.problem_text_file:
        problem_markdown = Path(args.problem_text_file).read_text(encoding="utf-8")

    topic_evaluation = None
    if args.topic_evaluation_json:
        topic_evaluation = _load_json(args.topic_evaluation_json)

    result = generate_stage2_artifacts(
        args.output_dir,
        raw_config,
        goal_text=goal_text,
        problem_markdown=problem_markdown,
        topic_evaluation=topic_evaluation,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
