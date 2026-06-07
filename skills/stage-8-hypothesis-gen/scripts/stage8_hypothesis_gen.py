#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 8 hypothesis generator."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


HypothesisGenerator = Callable[[Mapping[str, Any]], str]
NoveltyChecker = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]


@dataclass(frozen=True)
class Stage8Config:
    topic: str
    stage_ref: str = "stage-08"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage8Config":
        research = _mapping(data.get("research"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 8 requires a non-empty topic")
        return cls(topic=str(topic), stage_ref=str(data.get("stage_ref") or "stage-08"))


def generate_stage8_artifacts(
    output_dir: str | Path,
    config: Stage8Config | Mapping[str, Any],
    *,
    synthesis: str = "",
    hypotheses_markdown: str | None = None,
    hypothesis_generator: HypothesisGenerator | None = None,
    perspectives: Sequence[Mapping[str, Any]] | None = None,
    hitl_guidance: str = "",
    papers_seen: Sequence[Mapping[str, Any]] | None = None,
    novelty_report: Mapping[str, Any] | None = None,
    novelty_checker: NoveltyChecker | None = None,
) -> dict[str, Any]:
    """Generate Stage 8 `hypotheses.md` and optional `novelty_report.json`."""
    cfg = config if isinstance(config, Stage8Config) else Stage8Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if hypotheses_markdown is None and hypothesis_generator is not None:
        hypotheses_markdown = hypothesis_generator(
            {
                "topic": cfg.topic,
                "synthesis": synthesis,
                "perspectives": list(perspectives or []),
                "hitl_guidance": hitl_guidance,
            }
        )
    if hypotheses_markdown is None:
        hypotheses_markdown = default_hypotheses(cfg.topic)

    if hitl_guidance.strip() and hypothesis_generator is None:
        hypotheses_markdown = append_hitl_guidance(hypotheses_markdown, hitl_guidance)

    hypotheses_path = out / "hypotheses.md"
    hypotheses_path.write_text(hypotheses_markdown, encoding="utf-8")

    artifacts = ["hypotheses.md"]
    evidence_refs = [f"{cfg.stage_ref}/hypotheses.md"]
    paths = {"hypotheses_md": str(hypotheses_path.resolve())}

    report = novelty_report
    if report is None and novelty_checker is not None:
        report = novelty_checker(
            {
                "topic": cfg.topic,
                "hypotheses_text": hypotheses_markdown,
                "papers_already_seen": list(papers_seen or []),
            }
        )
    if report is None and papers_seen:
        report = heuristic_novelty_report(cfg.topic, hypotheses_markdown, papers_seen)
    if isinstance(report, Mapping):
        novelty_path = out / "novelty_report.json"
        novelty_path.write_text(json.dumps(dict(report), indent=2, ensure_ascii=False), encoding="utf-8")
        artifacts.append("novelty_report.json")
        paths["novelty_report_json"] = str(novelty_path.resolve())

    return {
        "stage": 8,
        "stage_name": "HYPOTHESIS_GEN",
        "status": "done",
        "artifacts": artifacts,
        "evidence_refs": evidence_refs,
        "paths": paths,
        "perspectives_used": bool(perspectives),
        "hitl_guidance_used": bool(hitl_guidance.strip()),
    }


def default_hypotheses(topic: str) -> str:
    """Render the deterministic fallback hypotheses used by Stage 8."""
    return f"""# Hypotheses

## H1
Increasing protocol control for {topic} improves metric stability across random seeds.

## H2
Adding robustness-aware objectives for {topic} improves out-of-domain performance without major in-domain regression.

## H3
The combined approach outperforms either component under fixed compute budget.

## Generated
{utcnow_iso()}
"""


def append_hitl_guidance(hypotheses_md: str, guidance: str) -> str:
    return (
        hypotheses_md.rstrip()
        + "\n\n## Human Guidance To Apply\n"
        + guidance.strip()
        + "\n"
    )


def heuristic_novelty_report(
    topic: str,
    hypotheses_text: str,
    papers_seen: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Lightweight local novelty report when external novelty checking is unavailable."""
    hyp_terms = set(extract_terms(hypotheses_text))
    title_terms = set()
    for paper in papers_seen:
        title_terms.update(extract_terms(str(paper.get("title", ""))))
        title_terms.update(extract_terms(str(paper.get("abstract", ""))[:300]))
    overlap = hyp_terms.intersection(title_terms)
    novelty_score = 1.0
    if hyp_terms:
        novelty_score = max(0.0, 1.0 - len(overlap) / max(len(hyp_terms), 1))
    if novelty_score >= 0.7:
        assessment = "likely_novel"
        recommendation = "proceed"
    elif novelty_score >= 0.4:
        assessment = "partially_overlapping"
        recommendation = "refine"
    else:
        assessment = "high_overlap"
        recommendation = "pivot_or_refine"
    return {
        "topic": topic,
        "novelty_score": round(novelty_score, 3),
        "assessment": assessment,
        "recommendation": recommendation,
        "papers_seen": len(papers_seen),
        "overlap_terms": sorted(overlap)[:30],
        "method": "local_term_overlap_heuristic",
        "generated": utcnow_iso(),
    }


def extract_terms(text: str) -> list[str]:
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "into", "under",
        "over", "using", "based", "between", "various", "different", "study",
        "method", "methods", "approach", "research", "paper", "hypothesis",
        "improves", "performance", "major", "fixed", "budget",
    }
    return [
        token.lower()
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", text)
        if len(token) >= 4 and token.lower() not in stop
    ]


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate standalone ResearchClaw Stage 8 artifacts.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--topic")
    parser.add_argument("--synthesis-file", help="Stage 7 synthesis.md")
    parser.add_argument("--hypotheses-text-file", help="Optional externally generated hypotheses markdown")
    parser.add_argument("--perspectives-json", help="Optional debate perspectives JSON list")
    parser.add_argument("--hitl-guidance-file", help="Optional human guidance markdown")
    parser.add_argument("--candidates-jsonl", help="Optional candidates.jsonl for heuristic novelty report")
    parser.add_argument("--novelty-report-json", help="Optional externally generated novelty report")
    parser.add_argument("--stage-ref", default="stage-08")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_config = _load_json(args.config) if args.config else {}
    raw_config.update(
        {
            k: v
            for k, v in {"topic": args.topic, "stage_ref": args.stage_ref}.items()
            if v is not None and v != ""
        }
    )
    synthesis = Path(args.synthesis_file).read_text(encoding="utf-8") if args.synthesis_file else ""
    hypotheses_markdown = (
        Path(args.hypotheses_text_file).read_text(encoding="utf-8")
        if args.hypotheses_text_file
        else None
    )
    hitl_guidance = (
        Path(args.hitl_guidance_file).read_text(encoding="utf-8")
        if args.hitl_guidance_file
        else ""
    )
    perspectives = None
    if args.perspectives_json:
        payload = _load_json(args.perspectives_json)
        perspectives = payload.get("perspectives", payload) if isinstance(payload, dict) else payload
    papers_seen = read_jsonl(args.candidates_jsonl) if args.candidates_jsonl else None
    novelty_report = _load_json(args.novelty_report_json) if args.novelty_report_json else None
    result = generate_stage8_artifacts(
        args.output_dir,
        raw_config,
        synthesis=synthesis,
        hypotheses_markdown=hypotheses_markdown,
        perspectives=perspectives,
        hitl_guidance=hitl_guidance,
        papers_seen=papers_seen,
        novelty_report=novelty_report,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
