#!/usr/bin/env python3
"""Standalone ResearchClaw Stage 3 artifact generator."""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SEARCH_SUFFIXES = ["benchmark", "survey", "seminal", "state of the art"]
MAX_QUERY_LEN = 60


@dataclass(frozen=True)
class Stage3Config:
    """Minimal, project-independent config for Stage 3."""

    topic: str
    stage_ref: str = "stage-03"
    min_year: int = 2020
    use_web_fetch: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Stage3Config":
        research = _mapping(data.get("research"))
        openclaw = _mapping(data.get("openclaw_bridge"))
        topic = _first_nonempty(data.get("topic"), research.get("topic"))
        if not topic:
            raise ValueError("Stage 3 requires a non-empty topic")
        return cls(
            topic=str(topic),
            stage_ref=str(data.get("stage_ref") or "stage-03"),
            min_year=int(
                _first_nonempty(data.get("min_year"), data.get("year_min")) or 2020
            ),
            use_web_fetch=bool(
                _first_nonempty(data.get("use_web_fetch"), openclaw.get("use_web_fetch"))
                or False
            ),
        )


def generate_stage3_artifacts(
    output_dir: str | Path,
    config: Stage3Config | Mapping[str, Any],
    *,
    problem_tree: str = "",
    plan: Mapping[str, Any] | None = None,
    plan_yaml_text: str | None = None,
    sources: Sequence[Mapping[str, Any]] | None = None,
    verify_sources: bool | None = None,
) -> dict[str, Any]:
    """Generate `search_plan.yaml`, `sources.json`, and `queries.json`."""
    cfg = config if isinstance(config, Stage3Config) else Stage3Config.from_mapping(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    model_plan_parsed = plan is not None or bool(plan_yaml_text)
    if plan is None and not plan_yaml_text:
        plan = build_default_search_plan(cfg.topic, min_year=cfg.min_year)

    search_plan_text = (
        extract_yaml_block(plan_yaml_text) if plan_yaml_text else dump_yaml(plan or {})
    )
    search_plan_path = out / "search_plan.yaml"
    search_plan_path.write_text(search_plan_text, encoding="utf-8")

    source_rows = [dict(item) for item in sources] if sources else default_sources(cfg.topic)
    should_verify = cfg.use_web_fetch if verify_sources is None else verify_sources
    if should_verify:
        for src in source_rows:
            status, http_status = verify_url(str(src.get("url", "")))
            src["status"] = status
            if http_status is not None:
                src["http_status"] = http_status

    sources_path = out / "sources.json"
    sources_path.write_text(
        json.dumps(
            {"sources": source_rows, "count": len(source_rows), "generated": utcnow_iso()},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    queries_list, year_min = extract_queries_and_year(
        plan or {},
        search_plan_text,
        default_year=cfg.min_year,
    )
    queries_list, fell_back = sanitize_or_build_queries(queries_list, cfg.topic)
    silent_fallback = fell_back and model_plan_parsed
    queries_meta = {
        "queries": queries_list,
        "year_min": year_min,
        "model_queries_extracted": model_plan_parsed and not fell_back,
        "fallback_reason": (
            "model_plan_used_unknown_schema" if silent_fallback else None
        ),
    }
    queries_path = out / "queries.json"
    queries_path.write_text(
        json.dumps(queries_meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "stage": 3,
        "stage_name": "SEARCH_STRATEGY",
        "status": "done",
        "artifacts": ["search_plan.yaml", "sources.json", "queries.json"],
        "evidence_refs": [
            f"{cfg.stage_ref}/search_plan.yaml",
            f"{cfg.stage_ref}/sources.json",
            f"{cfg.stage_ref}/queries.json",
        ],
        "paths": {
            "search_plan_yaml": str(search_plan_path.resolve()),
            "sources_json": str(sources_path.resolve()),
            "queries_json": str(queries_path.resolve()),
        },
        "problem_tree_used": bool(problem_tree.strip()),
    }


def build_default_search_plan(topic: str, *, min_year: int = 2020) -> dict[str, Any]:
    fallback_queries = build_fallback_queries(topic)
    return {
        "topic": topic,
        "generated": utcnow_iso(),
        "search_strategies": [
            {
                "name": "keyword_core",
                "queries": fallback_queries[:5],
                "sources": ["arxiv", "semantic_scholar", "openreview"],
                "max_results_per_query": 60,
            },
            {
                "name": "backward_forward_citation",
                "queries": fallback_queries[5:10] or fallback_queries[:3],
                "sources": ["semantic_scholar", "google_scholar"],
                "depth": 1,
            },
        ],
        "filters": {
            "min_year": min_year,
            "language": ["en"],
            "peer_review_preferred": True,
        },
        "deduplication": {"method": "title_doi_hash", "fuzzy_threshold": 0.9},
    }


def default_sources(topic: str) -> list[dict[str, Any]]:
    ts = utcnow_iso()
    return [
        {
            "id": "arxiv",
            "name": "arXiv",
            "type": "api",
            "url": "https://export.arxiv.org/api/query",
            "status": "available",
            "query": topic,
            "verified_at": ts,
        },
        {
            "id": "semantic_scholar",
            "name": "Semantic Scholar",
            "type": "api",
            "url": "https://api.semanticscholar.org/graph/v1/paper/search",
            "status": "available",
            "query": topic,
            "verified_at": ts,
        },
    ]


def build_fallback_queries(topic: str) -> list[str]:
    """Extract 5-10 targeted search queries from a long topic string."""
    chunks = re.split(r"[,:;()\[\]]+", topic)
    chunks = [c.strip() for c in chunks if len(c.strip()) > 8]
    cleaned_chunks = []
    for chunk in chunks:
        chunk = re.sub(
            r"^(and|or|the|a|an|in|of|for|with|across|multiple|three|various)\s+",
            "",
            chunk,
            flags=re.IGNORECASE,
        ).strip()
        if len(chunk) > 8:
            cleaned_chunks.append(chunk)

    stop = {
        "the", "and", "for", "with", "from", "that", "this", "into",
        "over", "across", "multiple", "three", "result", "comprehensive",
        "using", "based", "between", "various", "different", "several",
        "parameter", "parameters", "analysis", "approach", "method",
        "framework", "frameworks",
    }
    words = topic.lower().split()
    key_terms = [w for w in words if len(w) > 3 and w not in stop]

    queries: list[str] = []
    for chunk in cleaned_chunks[:4]:
        if len(chunk) > 60:
            chunk = " ".join(chunk.split()[:6])
        if chunk and chunk not in queries:
            queries.append(chunk)

    clean_terms = [t for t in key_terms if re.match(r"^[a-z]", t) and ":" not in t]
    for idx in range(min(len(clean_terms) - 1, 4)):
        bigram = f"{clean_terms[idx]} {clean_terms[idx + 1]}"
        if bigram not in queries:
            queries.append(bigram)

    unique = dedupe_preserve_order(queries)
    topic_short = topic[:60].strip()
    for suffix in ("survey", "review", "benchmark", "state of the art", "recent advances"):
        if len(unique) >= 5:
            break
        query = f"{topic_short} {suffix}"
        if query.lower() not in {q.lower() for q in unique}:
            unique.append(query)
    return unique[:10] or [topic_short or topic]


def extract_queries_and_year(
    plan: Mapping[str, Any],
    yaml_text: str,
    *,
    default_year: int = 2020,
) -> tuple[list[str], int]:
    queries: list[str] = []
    year_min = default_year

    strategies = plan.get("search_strategies", [])
    if isinstance(strategies, list):
        for strat in strategies:
            if isinstance(strat, Mapping):
                raw_queries = strat.get("queries", [])
                if isinstance(raw_queries, list):
                    queries.extend(str(q) for q in raw_queries if q)

    if not queries:
        qstrats = plan.get("query_strategies", {})
        if isinstance(qstrats, Mapping):
            for sub in qstrats.values():
                if not isinstance(sub, Mapping):
                    continue
                for key in ("boolean_seeds", "queries"):
                    raw_queries = sub.get(key, [])
                    if isinstance(raw_queries, list):
                        queries.extend(str(q) for q in raw_queries if q)

    filters = plan.get("filters", {})
    if isinstance(filters, Mapping):
        year_min = _safe_int(filters.get("min_year"), year_min)

    if not queries:
        queries.extend(scan_yaml_queries(yaml_text))
    yaml_year = scan_yaml_min_year(yaml_text)
    if yaml_year is not None:
        year_min = yaml_year
    return queries, year_min


def sanitize_or_build_queries(
    queries: Sequence[str],
    topic: str,
) -> tuple[list[str], bool]:
    fell_back_to_defaults = False
    sanitized: list[str] = []
    for query in queries:
        q = str(query).strip()
        if not q:
            continue
        if len(q) > MAX_QUERY_LEN:
            q = shorten_query(q)
        if q:
            sanitized.append(q)

    if not sanitized:
        sanitized = build_default_search_queries(topic)
        fell_back_to_defaults = True

    unique = dedupe_preserve_order(sanitized)
    all_kw = extract_search_terms(topic)
    if len(unique) < 5 and len(all_kw) >= 3:
        supplements = [
            " ".join(all_kw[:4]) + " survey",
            " ".join(all_kw[:4]) + " benchmark",
            " ".join(all_kw[1:5]),
            " ".join(all_kw[:3]) + " comparison",
            " ".join(all_kw[:3]) + " deep learning",
            " ".join(all_kw[2:6]),
        ]
        for supplement in supplements:
            if supplement.strip().lower() not in {q.lower() for q in unique}:
                unique.append(supplement.strip())
            if len(unique) >= 8:
                break
    return unique, fell_back_to_defaults


def build_default_search_queries(topic_text: str) -> list[str]:
    words = extract_search_terms(topic_text)
    if not words:
        return [topic_text[:60]]
    kw_primary = " ".join(words[:6])
    kw_short = " ".join(words[:4])
    kw_alt = " ".join(words[1:5]) if len(words) > 4 else kw_short
    return [
        kw_primary,
        f"{kw_short} benchmark",
        f"{kw_short} survey",
        kw_alt,
        f"{kw_short} recent advances",
    ]


def extract_search_terms(text: str) -> list[str]:
    stop = {
        "a", "an", "the", "of", "for", "in", "on", "and", "or", "with",
        "to", "by", "from", "its", "is", "are", "was", "be", "as", "at",
        "via", "using", "based", "study", "analysis", "empirical",
        "towards", "toward", "into", "exploring", "comparison", "tasks",
        "effectiveness", "investigation", "comprehensive", "novel",
        "challenge", "challenges", "gaps", "gap", "critical", "survey", "review",
    }
    return [
        word
        for word in re.split(r"[^a-zA-Z0-9]+", text)
        if word.lower() not in stop and len(word) > 1
    ]


def shorten_query(query: str, max_kw: int = 6) -> str:
    query = query.strip()
    suffix = ""
    core = query
    for candidate in SEARCH_SUFFIXES:
        if query.lower().endswith(candidate):
            suffix = candidate
            core = query[: -len(candidate)].strip()
            break
    keywords = extract_search_terms(core)
    shortened = " ".join(keywords[:max_kw])
    return f"{shortened} {suffix}".strip() if suffix else shortened


def scan_yaml_queries(yaml_text: str) -> list[str]:
    """Lightweight query scanner for common YAML list shapes."""
    queries: list[str] = []
    lines = yaml_text.splitlines()
    in_query_block = False
    query_indent = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if re.match(r"^(queries|boolean_seeds)\s*:\s*$", stripped):
            in_query_block = True
            query_indent = indent
            continue
        if in_query_block and indent <= query_indent and not stripped.startswith("-"):
            in_query_block = False
        if in_query_block and stripped.startswith("-"):
            value = stripped[1:].strip().strip("\"'")
            if value:
                queries.append(value)
    return queries


def scan_yaml_min_year(yaml_text: str) -> int | None:
    match = re.search(r"^\s*min_year\s*:\s*(\d{4})\s*$", yaml_text, re.MULTILINE)
    return int(match.group(1)) if match else None


def extract_yaml_block(text: str) -> str:
    cleaned = re.sub(r"\[thinking\].*?(?=\n```|\n[A-Z]|\Z)", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"\[plan\].*?\n\n", "", cleaned, flags=re.DOTALL)
    for candidate in (cleaned, text):
        for fence in ("```yaml", "```yml", "```"):
            if fence in candidate:
                block = candidate.split(fence, 1)[1].split("```", 1)[0].strip()
                if block:
                    return block
    yaml_lines: list[str] = []
    in_yaml = False
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not in_yaml and re.match(r"^[a-z_]+:", stripped):
            in_yaml = True
        if in_yaml:
            if stripped and not stripped.startswith("#"):
                yaml_lines.append(line)
            elif not stripped and yaml_lines:
                yaml_lines.append(line)
    return "\n".join(yaml_lines).strip() if yaml_lines else text.strip()


def dump_yaml(value: Any, indent: int = 0) -> str:
    """Small YAML emitter for dict/list/scalar data used by this stage."""
    spaces = " " * indent
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (Mapping, list, tuple)):
                lines.append(f"{spaces}{key}:")
                lines.append(dump_yaml(item, indent + 2))
            else:
                lines.append(f"{spaces}{key}: {format_yaml_scalar(item)}")
        return "\n".join(lines)
    if isinstance(value, (list, tuple)):
        lines = []
        for item in value:
            if isinstance(item, Mapping):
                lines.append(f"{spaces}-")
                lines.append(dump_yaml(item, indent + 2))
            elif isinstance(item, (list, tuple)):
                lines.append(f"{spaces}-")
                lines.append(dump_yaml(item, indent + 2))
            else:
                lines.append(f"{spaces}- {format_yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{spaces}{format_yaml_scalar(value)}"


def format_yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in "\n:#[]{}&,") or text.strip() != text:
        return json.dumps(text, ensure_ascii=False)
    return text


def verify_url(url: str) -> tuple[str, int | None]:
    if not url:
        return "unknown", None
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            code = int(response.status)
    except urllib.error.HTTPError as exc:
        code = int(exc.code)
    except Exception:
        return "unknown", None
    return ("verified" if code in (200, 301, 302, 405) else "unreachable"), code


def dedupe_preserve_order(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(value.strip())
    return unique


def infer_topic_from_problem_tree(problem_tree: str) -> str:
    match = re.search(r"topic\s*:\s*(.+)", problem_tree, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        description="Generate standalone ResearchClaw Stage 3 artifacts.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for Stage 3 artifacts.")
    parser.add_argument("--config", help="Optional JSON config file, flat or ResearchClaw-like.")
    parser.add_argument("--topic", help="Research topic. Overrides --config.")
    parser.add_argument("--problem-tree-file", help="Stage 2 problem_tree.md input.")
    parser.add_argument("--plan-json-file", help="Optional JSON search plan mapping.")
    parser.add_argument("--plan-yaml-file", help="Optional YAML text to preserve as search_plan.yaml.")
    parser.add_argument("--sources-json-file", help="Optional source list JSON or {'sources': [...]} JSON.")
    parser.add_argument("--min-year", type=int, help="Minimum publication year.")
    parser.add_argument("--verify-sources", action="store_true", help="Verify source URLs with HTTP HEAD.")
    parser.add_argument("--stage-ref", default="stage-03", help="Evidence ref prefix.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_config: dict[str, Any] = _load_json(args.config) if args.config else {}
    problem_tree = (
        Path(args.problem_tree_file).read_text(encoding="utf-8")
        if args.problem_tree_file
        else ""
    )

    inferred_topic = infer_topic_from_problem_tree(problem_tree) if problem_tree else ""
    overrides = {
        "topic": args.topic or inferred_topic,
        "min_year": args.min_year,
        "stage_ref": args.stage_ref,
        "use_web_fetch": args.verify_sources,
    }
    raw_config.update({k: v for k, v in overrides.items() if v is not None and v != ""})

    plan = _load_json(args.plan_json_file) if args.plan_json_file else None
    plan_yaml_text = (
        Path(args.plan_yaml_file).read_text(encoding="utf-8")
        if args.plan_yaml_file
        else None
    )
    sources = None
    if args.sources_json_file:
        source_payload = _load_json(args.sources_json_file)
        raw_sources = source_payload.get("sources", source_payload)
        if isinstance(raw_sources, list):
            sources = [item for item in raw_sources if isinstance(item, Mapping)]

    result = generate_stage3_artifacts(
        args.output_dir,
        raw_config,
        problem_tree=problem_tree,
        plan=plan,
        plan_yaml_text=plan_yaml_text,
        sources=sources,
        verify_sources=args.verify_sources,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
