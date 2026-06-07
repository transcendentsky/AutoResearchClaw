#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 4 literature collector."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class Stage4Config:
    topic: str
    daily_paper_count: int = 20
    year_min: int = 2020
    stage_ref: str = "stage-04"
    s2_api_key: str = ""
    real_search: bool = True
    limit_per_query: int = 40

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage4Config":
        research = _mapping(data.get("research"))
        llm = _mapping(data.get("llm"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 4 requires a non-empty topic")
        return cls(
            topic=str(topic),
            daily_paper_count=int(
                _first_nonempty(data.get("daily_paper_count"), research.get("daily_paper_count"))
                or 20
            ),
            year_min=int(_first_nonempty(data.get("year_min"), data.get("min_year")) or 2020),
            stage_ref=str(data.get("stage_ref") or "stage-04"),
            s2_api_key=str(_first_nonempty(data.get("s2_api_key"), llm.get("s2_api_key")) or ""),
            real_search=bool(data.get("real_search", True)),
            limit_per_query=int(data.get("limit_per_query") or 40),
        )


def generate_stage4_artifacts(
    output_dir: str | Path,
    config: Stage4Config | Mapping[str, Any],
    *,
    queries_data: Mapping[str, Any] | None = None,
    search_plan_text: str = "",
    injected_candidates: Sequence[Mapping[str, Any]] | None = None,
    seminal_papers: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate Stage 4 literature collection artifacts."""
    cfg = config if isinstance(config, Stage4Config) else Stage4Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    queries = list(queries_data.get("queries", [cfg.topic]) if queries_data else [cfg.topic])
    queries = [str(q).strip() for q in queries if str(q).strip()]
    year_min = int(queries_data.get("year_min", cfg.year_min) if queries_data else cfg.year_min)
    expanded_queries = expand_search_queries(queries, cfg.topic)

    candidates: list[dict[str, Any]] = []
    bibtex_entries: list[str] = []
    real_search_succeeded = False

    if cfg.real_search:
        candidates = search_public_apis(
            expanded_queries,
            year_min=year_min,
            limit_per_query=cfg.limit_per_query,
            s2_api_key=cfg.s2_api_key,
        )
        real_search_succeeded = bool(candidates)

    if injected_candidates:
        candidates.extend(dict(item) for item in injected_candidates)

    if seminal_papers:
        candidates.extend(inject_seminal_papers(seminal_papers, candidates))

    candidates = dedupe_candidates(candidates)
    if not candidates:
        candidates = placeholder_candidates(cfg.topic, max(20, cfg.daily_paper_count or 20))

    for row in candidates:
        row.setdefault("collected_at", utcnow_iso())
        if not row.get("is_placeholder"):
            bibtex_entries.append(candidate_to_bibtex(row))

    candidates_path = out / "candidates.jsonl"
    write_jsonl(candidates_path, candidates)

    artifacts = ["candidates.jsonl"]
    if bibtex_entries:
        references_path = out / "references.bib"
        references_path.write_text("\n\n".join(bibtex_entries) + "\n", encoding="utf-8")
        artifacts.append("references.bib")

    meta = {
        "real_search": real_search_succeeded,
        "queries_used": queries,
        "expanded_queries": expanded_queries,
        "year_min": year_min,
        "total_candidates": len(candidates),
        "bibtex_entries": len(bibtex_entries),
        "search_plan_supplied": bool(search_plan_text.strip()),
        "ts": utcnow_iso(),
    }
    search_meta_path = out / "search_meta.json"
    search_meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    artifacts.append("search_meta.json")

    return {
        "stage": 4,
        "stage_name": "LITERATURE_COLLECT",
        "status": "done",
        "artifacts": artifacts,
        "evidence_refs": [f"{cfg.stage_ref}/{name}" for name in artifacts],
        "paths": {
            "candidates_jsonl": str(candidates_path.resolve()),
            "search_meta_json": str(search_meta_path.resolve()),
        },
    }


def search_public_apis(
    queries: Sequence[str],
    *,
    year_min: int,
    limit_per_query: int,
    s2_api_key: str = "",
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for query in queries:
        candidates.extend(search_openalex(query, year_min, limit_per_query))
        candidates.extend(search_semantic_scholar(query, year_min, limit_per_query, s2_api_key))
        candidates.extend(search_arxiv(query, year_min, limit_per_query))
        time.sleep(0.2)
    return dedupe_candidates(candidates)


def search_openalex(query: str, year_min: int, limit: int) -> list[dict[str, Any]]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{year_min}-01-01",
        "per-page": str(min(limit, 50)),
    }
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    data = fetch_json(url)
    rows: list[dict[str, Any]] = []
    for item in data.get("results", []) if isinstance(data, dict) else []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        authors = []
        for auth in item.get("authorships", []) or []:
            author = _mapping(auth.get("author"))
            if author.get("display_name"):
                authors.append({"name": author["display_name"]})
        rows.append(
            {
                "id": str(item.get("id") or stable_id(title)),
                "title": title,
                "source": "openalex",
                "url": str(item.get("doi") or item.get("id") or ""),
                "year": int(item.get("publication_year") or year_min),
                "abstract": openalex_abstract(item.get("abstract_inverted_index")),
                "authors": authors,
                "venue": str(_mapping(item.get("primary_location")).get("source", {}).get("display_name", "")),
                "query": query,
            }
        )
    return rows


def search_semantic_scholar(query: str, year_min: int, limit: int, api_key: str = "") -> list[dict[str, Any]]:
    params = {
        "query": query,
        "limit": str(min(limit, 100)),
        "fields": "title,abstract,year,url,authors,venue",
        "year": f"{year_min}-",
    }
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    headers = {"x-api-key": api_key} if api_key else None
    data = fetch_json(url, headers=headers)
    rows = []
    for item in data.get("data", []) if isinstance(data, dict) else []:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        rows.append(
            {
                "id": str(item.get("paperId") or stable_id(title)),
                "title": title,
                "source": "semantic_scholar",
                "url": str(item.get("url") or ""),
                "year": int(item.get("year") or year_min),
                "abstract": str(item.get("abstract") or ""),
                "authors": [{"name": a.get("name", "")} for a in item.get("authors", []) if isinstance(a, dict)],
                "venue": str(item.get("venue") or ""),
                "query": query,
            }
        )
    return rows


def search_arxiv(query: str, year_min: int, limit: int) -> list[dict[str, Any]]:
    params = {"search_query": f"all:{query}", "start": "0", "max_results": str(min(limit, 50))}
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
    try:
        text = fetch_text(url)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    for entry in root.findall("atom:entry", ns):
        title = text_of(entry, "atom:title", ns)
        published = text_of(entry, "atom:published", ns)
        year = int(published[:4]) if re.match(r"\d{4}", published) else year_min
        if year < year_min or not title:
            continue
        authors = [{"name": text_of(a, "atom:name", ns)} for a in entry.findall("atom:author", ns)]
        rows.append(
            {
                "id": text_of(entry, "atom:id", ns) or stable_id(title),
                "title": " ".join(title.split()),
                "source": "arxiv",
                "url": text_of(entry, "atom:id", ns),
                "year": year,
                "abstract": " ".join(text_of(entry, "atom:summary", ns).split()),
                "authors": authors,
                "venue": "arXiv",
                "query": query,
            }
        )
    return rows


def expand_search_queries(queries: Sequence[str], topic: str) -> list[str]:
    expanded = list(queries)
    seen = {q.lower().strip() for q in expanded}
    topic_words = topic.split()
    if len(topic_words) > 5:
        for variant in (" ".join(topic_words[:5]), " ".join(topic_words[-5:])):
            if variant.lower().strip() not in seen:
                expanded.append(variant)
                seen.add(variant.lower().strip())
    for suffix in ("survey", "benchmark", "comparison"):
        short_topic = " ".join(topic_words[:4])
        variant = f"{short_topic} {suffix}".strip()
        if variant and variant.lower() not in seen:
            expanded.append(variant)
            seen.add(variant.lower())
    return expanded


def inject_seminal_papers(
    seminal_papers: Sequence[Mapping[str, Any]],
    existing: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    existing_titles = {str(c.get("title", "")).lower() for c in existing}
    rows = []
    for paper in seminal_papers:
        title = str(paper.get("title", "")).strip()
        if not title or title.lower() in existing_titles:
            continue
        rows.append(
            {
                "id": f"seminal-{paper.get('cite_key', stable_id(title))}",
                "title": title,
                "source": "seminal_library",
                "url": str(paper.get("url", "")),
                "year": int(paper.get("year", 2020)),
                "abstract": str(paper.get("abstract") or f"Foundational paper on {title}."),
                "authors": [{"name": str(paper.get("authors", ""))}],
                "cite_key": str(paper.get("cite_key", "")),
                "venue": str(paper.get("venue", "")),
            }
        )
    return rows


def placeholder_candidates(topic: str, count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": f"candidate-{idx + 1}",
            "title": f"[Placeholder] Study {idx + 1} on {topic}",
            "source": "arxiv" if idx % 2 == 0 else "semantic_scholar",
            "url": f"https://example.org/{safe_filename(topic.lower())}/{idx + 1}",
            "year": 2024,
            "abstract": f"This candidate investigates {topic} and reports preliminary findings.",
            "collected_at": utcnow_iso(),
            "is_placeholder": True,
        }
        for idx in range(count)
    ]


def candidate_to_bibtex(row: Mapping[str, Any]) -> str:
    cite_key = str(row.get("cite_key") or "")
    if not cite_key:
        authors = row.get("authors", [])
        surname = "unknown"
        if isinstance(authors, list) and authors:
            first = authors[0]
            name = first if isinstance(first, str) else _mapping(first).get("name", "")
            surname = str(name).split()[-1].lower() if str(name).strip() else "unknown"
        title_word = "".join(w[0] for w in str(row.get("title", "study")).split()[:3]).lower()
        cite_key = f"{surname}{row.get('year', 2024)}{title_word}"
    authors = row.get("authors", [])
    names = []
    if isinstance(authors, list):
        for author in authors:
            names.append(author if isinstance(author, str) else str(_mapping(author).get("name", "")))
    return (
        f"@article{{{safe_bibtex_key(cite_key)},\n"
        f"  title={{{row.get('title', 'Untitled')}}},\n"
        f"  author={{{' and '.join(n for n in names if n) or 'Unknown'}}},\n"
        f"  year={{{row.get('year', 2024)}}},\n"
        f"  url={{{row.get('url', '')}}},\n"
        f"}}"
    )


def fetch_json(url: str, headers: Mapping[str, str] | None = None) -> Any:
    text = fetch_text(url, headers=headers)
    return json.loads(text)


def fetch_text(url: str, headers: Mapping[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers=dict(headers or {}))
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def openalex_abstract(index: Any) -> str:
    if not isinstance(index, Mapping):
        return ""
    positions: dict[int, str] = {}
    for word, offsets in index.items():
        if isinstance(offsets, list):
            for offset in offsets:
                try:
                    positions[int(offset)] = str(word)
                except (TypeError, ValueError):
                    pass
    return " ".join(positions[i] for i in sorted(positions))


def text_of(node: ET.Element, path: str, ns: Mapping[str, str]) -> str:
    found = node.find(path, ns)
    return found.text.strip() if found is not None and found.text else ""


def dedupe_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for row in candidates:
        title = str(row.get("title", "")).lower().strip()
        key = title or str(row.get("id", "")).lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(dict(row))
    return unique


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "topic"


def safe_bibtex_key(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9:_-]+", "", value) or "unknown2024"


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


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


def _load_json_or_list(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate standalone ResearchClaw Stage 4 artifacts.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config")
    parser.add_argument("--topic")
    parser.add_argument("--queries-json", help="Stage 3 queries.json")
    parser.add_argument("--search-plan-file", help="Stage 3 search_plan.yaml text")
    parser.add_argument("--candidates-json", help="Optional externally generated candidates list JSON")
    parser.add_argument("--seminal-json", help="Optional seminal papers JSON list")
    parser.add_argument("--skip-real-search", action="store_true")
    parser.add_argument("--s2-api-key", default="")
    parser.add_argument("--stage-ref", default="stage-04")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_config = _load_json(args.config) if args.config else {}
    queries_data = _load_json(args.queries_json) if args.queries_json else {}
    topic = args.topic or raw_config.get("topic") or _mapping(raw_config.get("research")).get("topic")
    if not topic:
        topic = " ".join(queries_data.get("queries", [])[:1])
    raw_config.update(
        {
            "topic": topic,
            "stage_ref": args.stage_ref,
            "s2_api_key": args.s2_api_key or raw_config.get("s2_api_key", ""),
            "real_search": not args.skip_real_search,
        }
    )
    search_plan_text = Path(args.search_plan_file).read_text(encoding="utf-8") if args.search_plan_file else ""
    injected = None
    if args.candidates_json:
        payload = _load_json_or_list(args.candidates_json)
        injected = payload.get("candidates", payload) if isinstance(payload, dict) else payload
    seminal = None
    if args.seminal_json:
        payload = _load_json_or_list(args.seminal_json)
        seminal = payload.get("papers", payload) if isinstance(payload, dict) else payload

    result = generate_stage4_artifacts(
        args.output_dir,
        raw_config,
        queries_data=queries_data,
        search_plan_text=search_plan_text,
        injected_candidates=injected,
        seminal_papers=seminal,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
