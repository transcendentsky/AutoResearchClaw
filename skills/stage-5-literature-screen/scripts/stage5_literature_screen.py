#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 5 literature screener."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


MAX_ABSTRACT_LEN = 800
MAX_CANDIDATES_CHARS = 30_000
MIN_SHORTLIST = 15

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "of", "for", "to",
    "with", "by", "at", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "using", "based",
    "via", "toward", "towards", "new", "novel", "approach", "method",
    "study", "research", "paper", "work", "propose", "proposed",
}


@dataclass(frozen=True)
class Stage5Config:
    topic: str
    domains: tuple[str, ...] = ()
    quality_threshold: float = 0.8
    stage_ref: str = "stage-05"
    min_shortlist: int = MIN_SHORTLIST

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage5Config":
        research = _mapping(data.get("research"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 5 requires a non-empty topic")
        domains_value = data.get("domains", research.get("domains", ()))
        if isinstance(domains_value, str):
            domains = tuple(part.strip() for part in domains_value.split(",") if part.strip())
        elif isinstance(domains_value, Sequence):
            domains = tuple(str(part).strip() for part in domains_value if str(part).strip())
        else:
            domains = ()
        return cls(
            topic=str(topic),
            domains=domains,
            quality_threshold=float(
                _first_nonempty(data.get("quality_threshold"), research.get("quality_threshold")) or 0.8
            ),
            stage_ref=str(data.get("stage_ref") or "stage-05"),
            min_shortlist=int(data.get("min_shortlist") or MIN_SHORTLIST),
        )


def generate_stage5_artifacts(
    output_dir: str | Path,
    config: Stage5Config | Mapping[str, Any],
    *,
    candidates: Sequence[Mapping[str, Any]],
    shortlist: Sequence[Mapping[str, Any]] | None = None,
    model_rejected_all: bool = False,
) -> dict[str, Any]:
    """Generate Stage 5 `shortlist.jsonl` or pause metadata."""
    cfg = config if isinstance(config, Stage5Config) else Stage5Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    filtered_rows, dropped_count, keywords = prefilter_candidates(
        candidates,
        cfg.topic,
        cfg.domains,
    )
    if not filtered_rows:
        filtered_rows = [dict(row) for row in candidates]

    filtered_rows = prepare_candidates_for_screening(filtered_rows)
    if model_rejected_all:
        meta_path = out / "screen_meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "outcome": "model_rejected_all",
                    "candidates_screened": len(filtered_rows),
                    "shortlist_size": 0,
                    "note": (
                        "Strict screen returned empty shortlist. Refine search "
                        "or accept rejection before continuing."
                    ),
                    "ts": utcnow_iso(),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return {
            "stage": 5,
            "stage_name": "LITERATURE_SCREEN",
            "status": "paused",
            "artifacts": ["screen_meta.json"],
            "evidence_refs": [f"{cfg.stage_ref}/screen_meta.json"],
            "decision": "rejected_all",
            "paths": {"screen_meta_json": str(meta_path.resolve())},
        }

    selected = [dict(row) for row in shortlist] if shortlist is not None else []
    parse_failed = shortlist is None
    if not selected:
        selected = template_shortlist(filtered_rows, cfg.min_shortlist, parse_failed=parse_failed)
    elif len(selected) < cfg.min_shortlist:
        selected = supplement_shortlist(selected, filtered_rows, cfg.min_shortlist)

    shortlist_path = out / "shortlist.jsonl"
    write_jsonl(shortlist_path, selected)
    meta_path = out / "screen_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "outcome": "done",
                "topic_keywords": keywords,
                "candidates_input": len(candidates),
                "candidates_screened": len(filtered_rows),
                "dropped_by_keyword_prefilter": dropped_count,
                "shortlist_size": len(selected),
                "quality_threshold": cfg.quality_threshold,
                "ts": utcnow_iso(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "stage": 5,
        "stage_name": "LITERATURE_SCREEN",
        "status": "done",
        "artifacts": ["shortlist.jsonl", "screen_meta.json"],
        "evidence_refs": [f"{cfg.stage_ref}/shortlist.jsonl", f"{cfg.stage_ref}/screen_meta.json"],
        "paths": {
            "shortlist_jsonl": str(shortlist_path.resolve()),
            "screen_meta_json": str(meta_path.resolve()),
        },
    }


def prefilter_candidates(
    candidates: Sequence[Mapping[str, Any]],
    topic: str,
    domains: Sequence[str],
) -> tuple[list[dict[str, Any]], int, list[str]]:
    keywords = extract_topic_keywords(topic, domains)
    filtered: list[dict[str, Any]] = []
    dropped = 0
    for raw in candidates:
        row = dict(raw)
        text_blob = f"{row.get('title', '')} {row.get('abstract', '')}".lower()
        overlap = sum(1 for kw in keywords if kw in text_blob)
        if overlap >= 1:
            row["keyword_overlap"] = overlap
            filtered.append(row)
        else:
            dropped += 1
    return filtered, dropped, keywords


def prepare_candidates_for_screening(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    total_chars = 0
    for row in rows:
        item = dict(row)
        abstract = item.get("abstract", "")
        if isinstance(abstract, str) and len(abstract) > MAX_ABSTRACT_LEN:
            item["abstract"] = abstract[:MAX_ABSTRACT_LEN] + "..."
        item.pop("authors", None)
        line_len = len(json.dumps(item, ensure_ascii=False))
        if prepared and total_chars + line_len > MAX_CANDIDATES_CHARS:
            break
        total_chars += line_len
        prepared.append(item)
    return prepared


def template_shortlist(
    rows: Sequence[Mapping[str, Any]],
    min_shortlist: int,
    *,
    parse_failed: bool,
) -> list[dict[str, Any]]:
    selected = []
    for idx, item in enumerate(rows[:min_shortlist]):
        row = dict(item)
        row["relevance_score"] = round(0.75 - idx * 0.02, 3)
        row["quality_score"] = round(0.72 - idx * 0.015, 3)
        row["keep_reason"] = (
            "Template fallback (parse failure)"
            if parse_failed
            else "Template screened entry"
        )
        selected.append(row)
    return selected


def supplement_shortlist(
    selected: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    min_shortlist: int,
) -> list[dict[str, Any]]:
    result = [dict(row) for row in selected]
    existing_titles = {str(row.get("title", "")).lower().strip() for row in result}
    for candidate in candidates:
        if len(result) >= min_shortlist:
            break
        title = str(candidate.get("title", "")).lower().strip()
        if title and title not in existing_titles:
            row = dict(candidate)
            row.setdefault("relevance_score", 0.5)
            row.setdefault("quality_score", 0.5)
            row.setdefault("keep_reason", "Supplemented to meet minimum shortlist")
            result.append(row)
            existing_titles.add(title)
    return result


def extract_topic_keywords(topic: str, domains: Sequence[str] = ()) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", topic.lower())
    keywords = [token for token in tokens if token not in STOP_WORDS and len(token) >= 3]
    for domain in domains:
        for part in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]+", domain.lower()):
            if part not in STOP_WORDS and len(part) >= 2:
                keywords.append(part)
    seen = set()
    unique = []
    for keyword in keywords:
        if keyword not in seen:
            seen.add(keyword)
            unique.append(keyword)
    return unique


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


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


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
    parser = argparse.ArgumentParser(description="Generate standalone ResearchClaw Stage 5 artifacts.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--topic")
    parser.add_argument("--domains")
    parser.add_argument("--candidates-jsonl", required=True)
    parser.add_argument("--shortlist-json", help="Optional externally generated shortlist list JSON")
    parser.add_argument("--model-rejected-all", action="store_true")
    parser.add_argument("--stage-ref", default="stage-05")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_config = _load_json(args.config) if args.config else {}
    raw_config.update(
        {
            k: v
            for k, v in {
                "topic": args.topic,
                "domains": args.domains,
                "stage_ref": args.stage_ref,
            }.items()
            if v is not None and v != ""
        }
    )
    candidates = read_jsonl(args.candidates_jsonl)
    shortlist = None
    if args.shortlist_json:
        payload = _load_json(args.shortlist_json)
        shortlist = payload.get("shortlist", payload) if isinstance(payload, dict) else payload
    result = generate_stage5_artifacts(
        args.output_dir,
        raw_config,
        candidates=candidates,
        shortlist=shortlist,
        model_rejected_all=args.model_rejected_all,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
