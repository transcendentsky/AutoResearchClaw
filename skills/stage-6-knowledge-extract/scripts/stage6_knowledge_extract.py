#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 6 knowledge-card extractor."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Stage6Config:
    topic: str
    stage_ref: str = "stage-06"
    max_template_cards: int = 6

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage6Config":
        research = _mapping(data.get("research"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 6 requires a non-empty topic")
        return cls(
            topic=str(topic),
            stage_ref=str(data.get("stage_ref") or "stage-06"),
            max_template_cards=int(data.get("max_template_cards") or 6),
        )


def generate_stage6_artifacts(
    output_dir: str | Path,
    config: Stage6Config | Mapping[str, Any],
    *,
    shortlist: Sequence[Mapping[str, Any]],
    web_context: str = "",
    cards: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate Stage 6 `cards/` markdown artifacts."""
    cfg = config if isinstance(config, Stage6Config) else Stage6Config.from_mapping(config)
    out = Path(output_dir)
    cards_dir = out / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    card_rows = [dict(card) for card in cards] if cards else []
    if not card_rows:
        card_rows = template_cards(
            shortlist,
            topic=cfg.topic,
            max_cards=cfg.max_template_cards,
            web_context=web_context,
        )

    written = []
    for idx, card in enumerate(card_rows):
        card_id = safe_filename(str(card.get("card_id", f"card-{idx + 1}")))
        path = cards_dir / f"{card_id}.md"
        path.write_text(render_card_markdown(card, fallback_title=card_id), encoding="utf-8")
        written.append(path)

    index_path = out / "cards_index.json"
    index_path.write_text(
        json.dumps(
            {
                "count": len(written),
                "cards": [path.name for path in written],
                "web_context_used": bool(web_context.strip()),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "stage": 6,
        "stage_name": "KNOWLEDGE_EXTRACT",
        "status": "done",
        "artifacts": ["cards/", "cards_index.json"],
        "evidence_refs": [f"{cfg.stage_ref}/cards/", f"{cfg.stage_ref}/cards_index.json"],
        "paths": {
            "cards_dir": str(cards_dir.resolve()),
            "cards_index_json": str(index_path.resolve()),
        },
    }


def template_cards(
    shortlist: Sequence[Mapping[str, Any]],
    *,
    topic: str,
    max_cards: int,
    web_context: str = "",
) -> list[dict[str, Any]]:
    cards = []
    context_note = ""
    if web_context.strip():
        context_note = " Web context was supplied for downstream interpretation."
    for idx, paper in enumerate(shortlist[:max_cards]):
        title = str(paper.get("title", f"Paper {idx + 1}"))
        cards.append(
            {
                "card_id": f"card-{idx + 1}",
                "title": title,
                "cite_key": str(paper.get("cite_key", "")),
                "problem": f"How to improve {topic}",
                "method": "Template method summary",
                "data": "Template dataset",
                "metrics": "Template metric",
                "findings": f"Template key finding based on shortlisted paper.{context_note}",
                "limitations": "Template limitation",
                "citation": str(paper.get("url", "")),
            }
        )
    return cards


def render_card_markdown(card: Mapping[str, Any], *, fallback_title: str) -> str:
    parts = [f"# {card.get('title', fallback_title)}", ""]
    for key in (
        "cite_key",
        "problem",
        "method",
        "data",
        "metrics",
        "findings",
        "limitations",
        "citation",
    ):
        parts.append(f"## {key.title()}")
        parts.append(str(card.get(key, "")))
        parts.append("")
    return "\n".join(parts)


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


def safe_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value)
    return value.strip("-") or "card"


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
    parser = argparse.ArgumentParser(description="Generate standalone ResearchClaw Stage 6 artifacts.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--topic")
    parser.add_argument("--shortlist-jsonl", required=True)
    parser.add_argument("--cards-json", help="Optional externally generated cards list JSON")
    parser.add_argument("--web-context-file", help="Optional Stage 4 web_context.md")
    parser.add_argument("--stage-ref", default="stage-06")
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
    shortlist = read_jsonl(args.shortlist_jsonl)
    cards = None
    if args.cards_json:
        payload = _load_json(args.cards_json)
        cards = payload.get("cards", payload) if isinstance(payload, dict) else payload
    web_context = (
        Path(args.web_context_file).read_text(encoding="utf-8")
        if args.web_context_file
        else ""
    )
    result = generate_stage6_artifacts(
        args.output_dir,
        raw_config,
        shortlist=shortlist,
        web_context=web_context,
        cards=cards,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
