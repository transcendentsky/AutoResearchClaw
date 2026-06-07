#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 7 synthesis generator."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SynthesisGenerator = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True)
class Stage7Config:
    topic: str
    stage_ref: str = "stage-07"
    max_cards: int = 24

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage7Config":
        research = _mapping(data.get("research"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 7 requires a non-empty topic")
        return cls(
            topic=str(topic),
            stage_ref=str(data.get("stage_ref") or "stage-07"),
            max_cards=int(data.get("max_cards") or 24),
        )


def generate_stage7_artifacts(
    output_dir: str | Path,
    config: Stage7Config | Mapping[str, Any],
    *,
    cards_context: str = "",
    synthesis_markdown: str | None = None,
    synthesis_generator: SynthesisGenerator | None = None,
) -> dict[str, Any]:
    """Generate Stage 7 `synthesis.md`."""
    cfg = config if isinstance(config, Stage7Config) else Stage7Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if synthesis_markdown is None and synthesis_generator is not None:
        synthesis_markdown = synthesis_generator(
            {"topic": cfg.topic, "cards_context": cards_context, "domain_context": ""}
        )
    if synthesis_markdown is None:
        synthesis_markdown = render_default_synthesis(cfg.topic)

    synthesis_path = out / "synthesis.md"
    synthesis_path.write_text(synthesis_markdown, encoding="utf-8")
    return {
        "stage": 7,
        "stage_name": "SYNTHESIS",
        "status": "done",
        "artifacts": ["synthesis.md"],
        "evidence_refs": [f"{cfg.stage_ref}/synthesis.md"],
        "paths": {"synthesis_md": str(synthesis_path.resolve())},
        "cards_context_used": bool(cards_context.strip()),
    }


def render_default_synthesis(topic: str) -> str:
    """Render the deterministic fallback synthesis used by Stage 7."""
    return f"""# Synthesis

## Cluster Overview
- Cluster A: Representation methods
- Cluster B: Training strategies
- Cluster C: Evaluation robustness

## Gap 1
Limited consistency across benchmark protocols.

## Gap 2
Under-reported failure behavior under distribution shift.

## Prioritized Opportunities
1. Unified experimental protocol
2. Robustness-aware evaluation suite

## Generated
{utcnow_iso()}
"""


def load_cards_context(cards_dir: str | Path, *, max_cards: int = 24) -> str:
    """Read up to *max_cards* markdown cards from a Stage 6 `cards/` directory."""
    path = Path(cards_dir)
    if not path.exists():
        return ""
    snippets = []
    for card_path in sorted(path.glob("*.md"))[:max_cards]:
        snippets.append(card_path.read_text(encoding="utf-8"))
    return "\n\n".join(snippets)


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
    parser = argparse.ArgumentParser(description="Generate standalone ResearchClaw Stage 7 artifacts.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--topic")
    parser.add_argument("--cards-dir", help="Stage 6 cards/ directory")
    parser.add_argument("--synthesis-text-file", help="Optional externally generated synthesis markdown")
    parser.add_argument("--stage-ref", default="stage-07")
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
    cfg = Stage7Config.from_mapping(raw_config)
    cards_context = load_cards_context(args.cards_dir, max_cards=cfg.max_cards) if args.cards_dir else ""
    synthesis_markdown = (
        Path(args.synthesis_text_file).read_text(encoding="utf-8")
        if args.synthesis_text_file
        else None
    )
    result = generate_stage7_artifacts(
        args.output_dir,
        cfg,
        cards_context=cards_context,
        synthesis_markdown=synthesis_markdown,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
