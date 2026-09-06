"""
Query-Directed Context Optimizer — HoTT Kernel
Schema Version: 3.0.0-kernel

Builds a deterministic, budget-bounded context projection from one SharedGraph.
The optimizer never scans or reads source files itself; it consumes file_map and
analyzer evidence already produced from the canonical graph snapshot.

This is context selection, not a correctness proof or a model-specific tokenizer.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    from core.shared_graph import graph_content_signature
except ImportError:
    from shared_graph import graph_content_signature


CONTEXT_MODEL = "query_directed_quotient_context_v2_memory"
CHARS_PER_TOKEN_ESTIMATE = 4
CHARS_PER_TOKEN_CODE = 3.0
CHARS_PER_TOKEN_NARRATIVE = 4.0
DEFAULT_BUDGET_TOKENS = 1200
MIN_BUDGET_TOKENS = 256
MAX_BUDGET_TOKENS = 32000
DEFAULT_MAX_HOPS = 2
MAX_HOPS = 5
MAX_SEMANTIC_SEEDS = 8
MAX_EXCERPT_LINES = 12
MAX_MEMORY_CONTEXT_CHARS = 1200
MAX_MEMORY_CONTENT_CHARS = 480
MIN_SOURCE_CARD_CHARS = 420
MAX_MEMORY_BUDGET_FRACTION = 0.35

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_STOPWORDS = {
    "a", "an", "and", "atau", "cek", "check", "code", "codebase",
    "dalam", "dan", "dari", "developer", "di", "file", "fix", "ini",
    "itu", "ke", "llm", "of", "pada", "periksa", "project", "proyek",
    "source", "the", "this", "to", "untuk", "yang",
    "ts", "js", "tsx", "jsx",
}
_SEVERITY_SIGNAL = {"high": 1.0, "medium": 2.0 / 3.0, "low": 1.0 / 3.0, "info": 0.0}

# Atomic identifier preservation patterns
_ATOMIC_EXT_RE = re.compile(
    r"(?i)\b(?:[\w\-]+/)*([\w\-]+(?:\.[\w\-]+)*\.(?:ts|tsx|js|jsx|json|html|css|scss|py|md|yml|yaml|sql))\b"
)
_ATOMIC_DOTTED_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]+)+\b"
)
_ATOMIC_CODE_RE = re.compile(
    r"\b[A-Z]{2,}\d+\b|\b[A-Z][A-Z0-9_]{3,}\b"
)


def estimate_tokens(text: str, content_type: str = "auto") -> int:
    """
    Menghitung estimasi konsumsi token adaptif.
    - 'code', 'source', 'diff': ~2.8 karakter per token
      (karena indentasi, bracket, camelCase identifier, operator)
    - 'narrative', 'text': ~3.8 karakter per token
    - 'auto': mendeteksi secara heuristik apakah teks dominan blok kode
    """
    if not text:
        return 0
    if content_type == "auto":
        code_indicators = ("{", "}", "();", "const ", "function ", "import ", "export ", "class ")
        is_code = any(ind in text for ind in code_indicators)
        ratio = CHARS_PER_TOKEN_CODE if is_code else CHARS_PER_TOKEN_NARRATIVE
    elif content_type in ("code", "source", "diff"):
        ratio = CHARS_PER_TOKEN_CODE
    else:
        ratio = CHARS_PER_TOKEN_NARRATIVE
    return max(1, math.ceil(len(text) / ratio))


def _normalize_path(value: str) -> str:
    normalized = os.path.normpath(value).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _terms(value: str) -> Set[str]:
    """
    Mengekstrak token dengan strategi Multi-Pass Preserve-First:
    1. Melindungi entitas atomik (nama file berekstensi, dotted identifiers, error codes)
       agar tidak terpecah menjadi kata generik atau terbuang oleh stopwords.
    2. Mengekstrak sub-token leksikal (camelCase/snake_case) untuk pencocokan parsial kata dasar.
    """
    if not value:
        return set()

    terms: Set[str] = set()

    # 1. Preserved Atomic Tokens
    for ext_match in _ATOMIC_EXT_RE.findall(value):
        clean_ext = ext_match.lower()
        if len(clean_ext) >= 3:
            terms.add(clean_ext)

    for dotted_match in _ATOMIC_DOTTED_RE.findall(value):
        clean_dotted = dotted_match.lower()
        if len(clean_dotted) >= 3:
            terms.add(clean_dotted)

    for code_match in _ATOMIC_CODE_RE.findall(value):
        clean_code = code_match.lower()
        if len(clean_code) >= 3:
            terms.add(clean_code)

    # 2. Standard Sub-tokens
    expanded = _CAMEL_RE.sub(r"\1 \2", value)
    for raw_token in _TOKEN_RE.findall(expanded.replace("_", " ").replace(".", " ").replace("/", " ")):
        lowered = raw_token.lower()
        if lowered not in _STOPWORDS and len(lowered) >= 2:
            terms.add(lowered)

    return terms


def _overlap(query_terms: Set[str], field_terms: Set[str]) -> Tuple[float, List[str]]:
    matched = sorted(query_terms & field_terms)
    if not query_terms:
        return 0.0, matched
    return len(matched) / len(query_terms), matched


def _content_signature(shared_graph: Dict[str, Any]) -> str:
    return graph_content_signature(shared_graph)


def _build_adjacency(
    vertices: Iterable[str],
    edges: Iterable[Tuple[str, str]],
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, List[str]]]:
    forward: Dict[str, Set[str]] = defaultdict(set)
    reverse: Dict[str, Set[str]] = defaultdict(set)
    undirected: Dict[str, Set[str]] = defaultdict(set)
    for source, target in edges:
        forward[source].add(target)
        reverse[target].add(source)
        undirected[source].add(target)
        undirected[target].add(source)
    for vertex in vertices:
        forward.setdefault(vertex, set())
        reverse.setdefault(vertex, set())
        undirected.setdefault(vertex, set())
    return (
        {key: sorted(value) for key, value in forward.items()},
        {key: sorted(value) for key, value in reverse.items()},
        {key: sorted(value) for key, value in undirected.items()},
    )


def _resolve_target(target: str, vertices: Set[str]) -> Tuple[Optional[str], List[str]]:
    normalized = _normalize_path(target)
    if normalized in vertices:
        return normalized, []
    suffix = f"/{normalized}"
    matches = sorted(path for path in vertices if path.endswith(suffix))
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def _finding_files(value: Any, vertices: Set[str], found: Set[str]) -> None:
    if isinstance(value, str):
        normalized = _normalize_path(value)
        if normalized in vertices:
            found.add(normalized)
    elif isinstance(value, dict):
        for nested in value.values():
            _finding_files(nested, vertices, found)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            _finding_files(nested, vertices, found)


def _collect_evidence(
    analyzer_output: Dict[str, Any],
    vertices: Set[str],
) -> Dict[str, List[Dict[str, Any]]]:
    evidence: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for analyzer_name, result in sorted(analyzer_output.get("results", {}).items()):
        for finding in result.get("findings", []):
            files: Set[str] = set()
            _finding_files(finding, vertices, files)
            if not files:
                continue
            reasons = finding.get("reasons", finding.get("risk_reasons", []))
            if not isinstance(reasons, list):
                reasons = [str(reasons)]
            item = {
                "analyzer": analyzer_name,
                "type": finding.get("type", "finding"),
                "severity": finding.get("severity", "info"),
                "reasons": [str(reason) for reason in reasons],
                "observation": str(finding.get("observation", ""))[:320],
            }
            for path in sorted(files):
                evidence[path].append(item)
    for path in evidence:
        evidence[path].sort(
            key=lambda item: (
                -_SEVERITY_SIGNAL.get(item["severity"], 0.0),
                item["analyzer"],
                item["type"],
            )
        )
    return evidence


def _outline(shared_graph: Dict[str, Any], path: str) -> Dict[str, Any]:
    try:
        from codebase.topology_analyzers import query_outline
    except ImportError:
        from topology_analyzers import query_outline
    result = query_outline(shared_graph, path)
    if not result.get("exists"):
        return {"exports": [], "declarations": [], "stats": {}}
    return {
        "exports": result.get("exports", []),
        "declarations": [
            {
                "line": item.get("line"),
                "kind": item.get("kind"),
                "name": item.get("name"),
            }
            for item in result.get("declarations", [])
        ],
        "stats": result.get("stats", {}),
    }


def _multi_source_distances(
    seeds: Iterable[str],
    adjacency: Dict[str, List[str]],
    max_hops: int,
) -> Dict[str, int]:
    distances: Dict[str, int] = {}
    queue: deque[str] = deque()
    for seed in sorted(set(seeds)):
        distances[seed] = 0
        queue.append(seed)
    while queue:
        current = queue.popleft()
        distance = distances[current]
        if distance >= max_hops:
            continue
        for neighbor in adjacency.get(current, []):
            if neighbor in distances:
                continue
            distances[neighbor] = distance + 1
            queue.append(neighbor)
    return distances


def _source_excerpt(content: str, query_terms: Set[str]) -> Dict[str, Any]:
    lines = content.splitlines()
    matched_indices = [
        index
        for index, line in enumerate(lines)
        if query_terms and query_terms & _terms(line)
    ]
    strategy = "query_window"
    selected_indices: Set[int] = set()
    for index in matched_indices:
        selected_indices.update(
            candidate
            for candidate in (index - 1, index, index + 1)
            if 0 <= candidate < len(lines)
        )
    if not selected_indices:
        strategy = "structural_head"
        structural = [
            index
            for index, line in enumerate(lines)
            if line.strip().startswith(("import ", "export ", "@"))
        ]
        selected_indices.update(structural[:MAX_EXCERPT_LINES])
        if not selected_indices:
            selected_indices.update(
                index for index, line in enumerate(lines) if line.strip()
            )
    ordered = sorted(selected_indices)[:MAX_EXCERPT_LINES]
    return {
        "strategy": strategy,
        "matched_line_count": len(matched_indices),
        "truncated": len(selected_indices) > len(ordered) or len(ordered) < len(lines),
        "lines": [
            {"line": index + 1, "text": lines[index][:240]}
            for index in ordered
        ],
    }


def _build_quotient(
    shared_graph: Dict[str, Any],
    selected_paths: List[str],
) -> Dict[str, Any]:
    boundaries = shared_graph.get("boundaries", {})
    file_to_boundary = shared_graph.get("file_to_boundary", {})
    internal_edges: Dict[str, int] = defaultdict(int)
    cross_edges: Dict[Tuple[str, str], int] = defaultdict(int)
    cross_witnesses: Dict[Tuple[str, str], List[List[str]]] = defaultdict(list)
    for source, target in shared_graph.get("edges", []):
        source_boundary = file_to_boundary.get(source, shared_graph.get("scan_root", "."))
        target_boundary = file_to_boundary.get(target, shared_graph.get("scan_root", "."))
        if source_boundary == target_boundary:
            internal_edges[source_boundary] += 1
        else:
            edge = (source_boundary, target_boundary)
            cross_edges[edge] += 1
            if len(cross_witnesses[edge]) < 2:
                cross_witnesses[edge].append([source, target])

    relevant = sorted({file_to_boundary.get(path) for path in selected_paths if file_to_boundary.get(path)})
    relevant_set = set(relevant)
    relevant_nodes = []
    for boundary in relevant:
        data = boundaries.get(boundary, {})
        relevant_nodes.append({
            "boundary": boundary,
            "file_count": len(data.get("files", [])),
            "selected_file_count": sum(
                1 for path in selected_paths if file_to_boundary.get(path) == boundary
            ),
            "internal_edge_count": internal_edges.get(boundary, 0),
            "has_barrel": bool(data.get("barrel")),
        })

    relevant_edges = []
    for (source, target), count in sorted(cross_edges.items()):
        if source not in relevant_set and target not in relevant_set:
            continue
        relevant_edges.append({
            "source_boundary": source,
            "target_boundary": target,
            "edge_count": count,
            "witnesses": cross_witnesses[(source, target)],
        })
        if len(relevant_edges) >= 12:
            break

    return {
        "model": {
            "name": "boundary_quotient_graph",
            "definition": "G/P where P partitions files by SharedGraph boundary",
            "edge_semantics": "resolved relative imports aggregated by boundary pair",
        },
        "summary": {
            "original_vertex_count": len(shared_graph.get("vertices", [])),
            "original_edge_count": len(shared_graph.get("edges", [])),
            "quotient_vertex_count": len(boundaries),
            "quotient_cross_edge_count": len(cross_edges),
            "quotient_cross_edge_multiplicity": sum(cross_edges.values()),
            "relevant_boundary_count": len(relevant_nodes),
            "omitted_boundary_count": max(0, len(boundaries) - len(relevant_nodes)),
        },
        "relevant_boundaries": relevant_nodes,
        "relevant_cross_edges": relevant_edges,
    }


def _compact_list(values: List[str], limit: int = 3) -> str:
    if not values:
        return "-"
    shown = values[:limit]
    suffix = f" (+{len(values) - limit})" if len(values) > limit else ""
    return ", ".join(shown) + suffix


def _render_card(profile: Dict[str, Any], detail: str, char_cap: int) -> str:
    distance = profile.get("graph_distance")
    distance_text = "-" if distance is None else str(distance)
    path = str(profile["file"])
    if len(path) > 180:
        path = f"...{path[-177:]}"
    lines = [
        f"FILE {path} | score={profile['score']:.4f} | d={distance_text}",
    ]

    def joined(candidate: List[str]) -> str:
        return "\n".join(candidate) + "\n"

    excerpt_lines = profile.get("source_excerpt", {}).get("lines", [])
    if detail == "source" and excerpt_lines:
        source_prefix = f"  L{excerpt_lines[0]['line']}: "
        source_text = str(excerpt_lines[0]["text"])
        source_base = joined(lines + ["source_excerpt:", source_prefix])
        available_source_chars = max(0, char_cap - len(source_base))
        first_source = source_prefix + source_text[:available_source_chars]
        if available_source_chars and len(
            joined(lines + ["source_excerpt:", first_source])
        ) <= char_cap:
            lines.extend(["source_excerpt:", first_source])
            for item in excerpt_lines[1:]:
                rendered_line = f"  L{item['line']}: {item['text']}"
                if len(joined(lines + [rendered_line])) > char_cap:
                    break
                lines.append(rendered_line)

    optional_lines = [
        f"why={_compact_list(profile['selection_signals'], 3)}",
        (
            f"topology=boundary:{profile['topology']['boundary']}; "
            f"type:{profile['topology']['node_type']}; "
            f"fan_in:{profile['topology']['fan_in']}; fan_out:{profile['topology']['fan_out']}"
        ),
        f"imports={_compact_list(profile['topology']['direct_imports'])}",
        f"imported_by={_compact_list(profile['topology']['direct_importers'])}",
    ]
    symbols = [
        f"{item.get('kind')}:{item.get('name')}@L{item.get('line')}"
        for item in profile.get("outline", {}).get("declarations", [])
    ]
    if symbols:
        optional_lines.append(f"symbols={_compact_list(symbols, 5)}")
    findings = [
        f"{item['analyzer']}:{item['type']}:{item['severity']}"
        for item in profile.get("findings", [])
    ]
    if findings:
        optional_lines.append(f"evidence={_compact_list(findings, 4)}")
    for optional in optional_lines:
        if len(joined(lines + [optional])) <= char_cap:
            lines.append(optional)
    rendered = joined(lines)
    if len(rendered) > char_cap:
        rendered = rendered[: max(0, char_cap - 1)].rstrip() + "\n"
    return rendered


def _render_memory_block(
    memory_context: Optional[Dict[str, Any]],
    char_cap: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Render scoped memory as bounded, explicitly non-authoritative evidence."""
    if not memory_context or not memory_context.get("memories") or char_cap <= 0:
        return "", []

    scope = memory_context.get("memory_scope", {})
    retrieval = memory_context.get("retrieval", {})
    lines = [
        "[PROJECT MEMORY EVIDENCE]",
        (
            f"scope={scope.get('scope_id', 'unknown')}; "
            f"retrieval={retrieval.get('model', 'unknown')}"
        ),
        "trust=historical observation; freshness-gated when grounded; verify current source.",
    ]
    included: List[Dict[str, Any]] = []

    for memory in memory_context.get("memories", []):
        raw_content = " ".join(str(memory.get("content", "")).split())
        source = " ".join(str(memory.get("source", "unknown")).split())[:160]
        record_prefix = (
            f"MEMORY {memory.get('id', 'unknown')} | type={memory.get('type', 'unknown')} | "
            f"observations={int(memory.get('observation_count', 1))} | "
            f"status={memory.get('evidence_status', 'unverified')}; "
            f"freshness={memory.get('freshness', 'unverified')}\n"
            f"source={source}; file={memory.get('file') or '-'}; "
            f"hash={memory.get('content_sha256', 'unknown')}\n"
            "content="
        )
        base_candidate = "\n".join(lines + [record_prefix]) + "\n"
        available_content_chars = min(
            MAX_MEMORY_CONTENT_CHARS,
            max(0, char_cap - len(base_candidate)),
        )
        if available_content_chars <= 3:
            break
        content_truncated = len(raw_content) > available_content_chars
        content = (
            raw_content[: available_content_chars - 3].rstrip() + "..."
            if content_truncated
            else raw_content
        )
        record = record_prefix + content
        candidate = "\n".join(lines + [record]) + "\n"
        if len(candidate) > char_cap:
            break
        lines.append(record)
        included_view = dict(memory)
        included_view["content"] = content
        included_view["content_truncated"] = content_truncated
        included.append(included_view)

    if not included:
        return "", []
    return "\n".join(lines) + "\n", included


def _render_kan_imputation_block(
    kan_imputations: List[Dict[str, Any]],
    char_cap: int,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Render Kan Extension imputed context for zero-context or new modules."""
    if not kan_imputations or char_cap <= 0:
        return "", []

    lines = [
        "[KAN EXTENSION IMPUTED CONTEXT]",
        "model=Lan_colimit+Ran_limit; guidance=architectural_imputation_for_new_modules",
    ]
    included: List[Dict[str, Any]] = []

    for imp in kan_imputations:
        target = imp.get("target_file", "")
        role = imp.get("inferred_role", "module")
        lan = imp.get("left_kan_extension", {})
        ran = imp.get("right_kan_extension", {})
        iso_refs = imp.get("kan_synthesis", {}).get("isomorphic_references", [])
        short_iso = [Path(r).name for r in iso_refs[:2]]
        iso_text = ", ".join(short_iso) if short_iso else "none"

        dep_roles = [d.get("role") for d in lan.get("imputed_dependencies", []) if d.get("role")]
        caller_roles = [c.get("role") for c in lan.get("imputed_dependents", []) if c.get("role")]
        hints = ran.get("guided_hints", [])

        block_lines = [
            f"TARGET {target} | role={role} | isomorphs={iso_text}",
            f"colimit_imputed_dependencies={', '.join(dep_roles) if dep_roles else 'none'}",
            f"colimit_imputed_dependents={', '.join(caller_roles) if caller_roles else 'none'}",
        ]
        test_file = lan.get("expected_companion_test")
        if test_file:
            block_lines.append(f"expected_companion_test={Path(test_file).name}")
        if hints:
            block_lines.append("limit_guided_hints:")
            for h in hints[:3]:
                block_lines.append(f"  * {h}")

        rendered_entry = "\n".join(block_lines)
        candidate = "\n".join(lines + [rendered_entry]) + "\n"
        if len(candidate) <= char_cap:
            lines.append(rendered_entry)
            included.append(imp)
            continue

        # Compacting fallback: reduce hints if this is the first entry
        if not included:
            compact_lines = block_lines[:3]
            if test_file:
                compact_lines.append(f"expected_companion_test={Path(test_file).name}")
            if hints:
                compact_lines.append(f"hint: {hints[0][:120]}")
            compact_entry = "\n".join(compact_lines)
            if len("\n".join(lines + [compact_entry]) + "\n") <= char_cap:
                lines.append(compact_entry)
                included.append(imp)
        break

    if not included:
        return "", []
    return "\n".join(lines) + "\n", included


def build_context_pack(
    shared_graph: Dict[str, Any],
    query: str,
    target_files: Optional[List[str]] = None,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    max_hops: int = DEFAULT_MAX_HOPS,
    detail: str = "source",
    analyzer_output: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Project measured graph evidence into a deterministic prompt-sized pack."""
    vertices = sorted(shared_graph.get("vertices", []))
    vertex_set = set(vertices)
    file_map = shared_graph.get("file_map", {})
    node_metadata = shared_graph.get("node_metadata", {})
    file_to_boundary = shared_graph.get("file_to_boundary", {})
    query_terms = _terms(query)
    requested_targets = target_files or []

    if analyzer_output is None:
        try:
            from core.analyzer_registry import run_analyzers
        except ImportError:
            from analyzer_registry import run_analyzers
        analyzer_output = run_analyzers(shared_graph)

    resolved_targets: List[str] = []
    unresolved_targets: List[Dict[str, Any]] = []
    for requested in requested_targets:
        resolved, ambiguous = _resolve_target(requested, vertex_set)
        if resolved:
            resolved_targets.append(resolved)
        else:
            unresolved_targets.append({
                "requested": requested,
                "ambiguous_matches": ambiguous,
            })
    resolved_targets = sorted(set(resolved_targets))

    forward, reverse, undirected = _build_adjacency(
        vertices,
        shared_graph.get("edges", []),
    )
    evidence_by_file = _collect_evidence(analyzer_output, vertex_set)
    outlines: Dict[str, Dict[str, Any]] = {}
    lexical_data: Dict[str, Dict[str, Any]] = {}

    for path in vertices:
        outline = _outline(shared_graph, path)
        outlines[path] = outline
        path_score, path_matches = _overlap(query_terms, _terms(path))
        symbol_text = " ".join(
            list(outline.get("exports", []))
            + [item.get("name", "") for item in outline.get("declarations", [])]
        )
        symbol_score, symbol_matches = _overlap(query_terms, _terms(symbol_text))
        evidence_text = " ".join(
            " ".join([
                item.get("analyzer", ""),
                item.get("type", ""),
                item.get("observation", ""),
                " ".join(item.get("reasons", [])),
            ])
            for item in evidence_by_file.get(path, [])
        )
        evidence_score, evidence_matches = _overlap(query_terms, _terms(evidence_text))
        lexical = max(path_score, 0.9 * symbol_score, 0.8 * evidence_score)
        lexical_data[path] = {
            "score": lexical,
            "path_score": path_score,
            "symbol_score": symbol_score,
            "evidence_score": evidence_score,
            "path_matches": path_matches,
            "symbol_matches": symbol_matches,
            "evidence_matches": evidence_matches,
        }

    semantic_rank = sorted(
        (path for path in vertices if lexical_data[path]["score"] > 0.0),
        key=lambda path: (-lexical_data[path]["score"], path),
    )
    semantic_seeds = semantic_rank[:MAX_SEMANTIC_SEEDS]
    # Explicit targets define the projection base. Query matches still affect
    # ranking, but unrelated lexical matches must not pull in another subgraph.
    seeds = resolved_targets if resolved_targets else semantic_seeds
    distances = _multi_source_distances(seeds, undirected, max_hops) if seeds else {}

    if resolved_targets:
        selection_mode = "explicit_target_graph"
    elif semantic_seeds:
        selection_mode = "query_graph"
    else:
        selection_mode = "structural_fallback"

    candidates = set(distances)
    if not resolved_targets:
        candidates.update(semantic_rank)
    if not candidates:
        candidates.update(vertices)

    max_degree = max(
        (int(node_metadata.get(path, {}).get("fan_in", 0))
         + int(node_metadata.get(path, {}).get("fan_out", 0)) for path in vertices),
        default=0,
    )
    profiles: List[Dict[str, Any]] = []
    for path in sorted(candidates):
        metadata = node_metadata.get(path, {})
        lexical = lexical_data[path]
        distance = distances.get(path)
        proximity = 1.0 / (1.0 + distance) if distance is not None else 0.0
        degree = int(metadata.get("fan_in", 0)) + int(metadata.get("fan_out", 0))
        centrality = degree / max_degree if max_degree else 0.0
        findings = evidence_by_file.get(path, [])
        evidence_signal = max(
            (_SEVERITY_SIGNAL.get(item.get("severity", "info"), 0.0) for item in findings),
            default=0.0,
        )
        base_score = (
            0.45 * lexical["score"]
            + 0.25 * proximity
            + 0.20 * centrality
            + 0.10 * evidence_signal
        )
        mandatory = path in resolved_targets
        score = base_score + (1.0 if mandatory else 0.0)
        signals: List[str] = []
        if mandatory:
            signals.append("explicit_target")
        for label, matches in (
            ("query_path", lexical["path_matches"]),
            ("query_symbol", lexical["symbol_matches"]),
            ("query_finding", lexical["evidence_matches"]),
        ):
            if matches:
                signals.append(f"{label}:{','.join(matches)}")
        if distance is not None:
            signals.append(f"graph_distance:{distance}")
        if centrality >= 0.5:
            signals.append("structural_centrality")
        if evidence_signal > 0:
            signals.append(f"finding_severity:{findings[0].get('severity', 'info')}")
        if not signals:
            signals.append("structural_fallback")

        content = file_map.get(path, "")
        profiles.append({
            "file": path,
            "score": round(score, 6),
            "mandatory": mandatory,
            "graph_distance": distance,
            "selection_signals": signals,
            "matched_query_terms": {
                "path": lexical["path_matches"],
                "symbols": lexical["symbol_matches"],
                "findings": lexical["evidence_matches"],
            },
            "score_components": {
                "lexical": round(lexical["score"], 6),
                "proximity": round(proximity, 6),
                "degree_centrality": round(centrality, 6),
                "finding_severity": round(evidence_signal, 6),
                "explicit_target_bonus": 1.0 if mandatory else 0.0,
            },
            "topology": {
                "boundary": file_to_boundary.get(path, shared_graph.get("scan_root", ".")),
                "node_type": metadata.get("type", "Other"),
                "is_entrypoint": bool(metadata.get("is_entrypoint")),
                "is_test": bool(metadata.get("is_test")),
                "fan_in": int(metadata.get("fan_in", 0)),
                "fan_out": int(metadata.get("fan_out", 0)),
                "direct_imports": forward.get(path, []),
                "direct_importers": reverse.get(path, []),
            },
            "outline": outlines[path],
            "findings": findings[:6],
            "source_excerpt": _source_excerpt(content, query_terms),
            "content_sha256": f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
        })

    profiles.sort(key=lambda item: (-int(item["mandatory"]), -item["score"], item["file"]))
    char_budget = budget_tokens * CHARS_PER_TOKEN_ESTIMATE
    signature = _content_signature(shared_graph)
    query_display = " ".join(query.strip().split())[:240]
    header = (
        "[QUERY-DIRECTED CODE CONTEXT]\n"
        f"query={query_display}\n"
        f"model={CONTEXT_MODEL}; graph={signature}; "
        f"V={len(vertices)}; E={len(shared_graph.get('edges', []))}\n"
        f"selection={selection_mode}; hops<={max_hops}; "
        "score=target_bonus+0.45L+0.25P+0.20C+0.10F\n"
        "scope=static TS/JS graph plus project-scoped historical observations; "
        "excerpts may be partial; findings and memories are observations.\n"
    )
    footer_reserve = 120
    available_content_chars = max(
        0, char_budget - len(header) - footer_reserve
    )
    source_floor_chars = min(MIN_SOURCE_CARD_CHARS, available_content_chars)
    memory_cap = min(
        MAX_MEMORY_CONTEXT_CHARS,
        int(char_budget * MAX_MEMORY_BUDGET_FRACTION),
        max(0, available_content_chars - source_floor_chars),
    )
    memory_block, included_memories = _render_memory_block(memory_context, memory_cap)

    # Kan Extension Imputation for Zero-Context / Target Modules
    kan_imputations: List[Dict[str, Any]] = []
    kan_block = ""
    try:
        from memory.kan_extension import impute_module_relations
        kan_targets: List[str] = []
        if target_files:
            kan_targets.extend(target_files)
        else:
            for item in profiles:
                topo = item.get("topology", {})
                if topo.get("fan_in", 0) == 0 and topo.get("fan_out", 0) == 0 and not topo.get("is_entrypoint"):
                    kan_targets.append(item.get("file"))

        for kt in kan_targets[:3]:
            imp = impute_module_relations(
                kt,
                shared_graph=shared_graph,
                memory_store=memory_context,
            )
            kan_imputations.append(imp)

        zero_context_targets = [
            imp for imp in kan_imputations
            if imp.get("is_new_or_zero_context") or (target_files and len(included_memories) == 0)
        ]
        if zero_context_targets:
            kan_cap = min(800, max(0, available_content_chars - source_floor_chars - len(memory_block)))
            if kan_cap > 100:
                kan_block, _ = _render_kan_imputation_block(zero_context_targets, kan_cap)
    except Exception:
        pass

    parts = [header]
    selected: List[Dict[str, Any]] = []
    rendered_cards: List[str] = []
    allocation_divisor = max(1, min(len(profiles), 4))
    card_budget = max(
        0,
        available_content_chars - len(memory_block) - len(kan_block),
    )
    per_card_cap = max(
        MIN_SOURCE_CARD_CHARS,
        min(1200, card_budget // allocation_divisor if card_budget else 0),
    )
    for profile in profiles:
        card = _render_card(profile, detail, per_card_cap)
        cards_length = sum(len(item) for item in rendered_cards)
        if cards_length + len(card) <= card_budget:
            rendered_cards.append(card)
            selected.append(profile)
            continue
        if profile["mandatory"]:
            compact = _render_card(profile, detail, MIN_SOURCE_CARD_CHARS)
            if cards_length + len(compact) <= card_budget:
                rendered_cards.append(compact)
                selected.append(profile)

    # Current source is the grounding floor. If memory prevented every source
    # card from fitting, omit memory and retry the highest-ranked source.
    if not selected and profiles:
        memory_block = ""
        included_memories = []
        kan_block = ""
        card_budget = available_content_chars
        fallback_cap = min(1200, max(MIN_SOURCE_CARD_CHARS, card_budget))
        fallback = _render_card(profiles[0], detail, fallback_cap)
        if len(fallback) <= card_budget:
            rendered_cards.append(fallback)
            selected.append(profiles[0])

    parts.extend(rendered_cards)
    if memory_block:
        parts.append(memory_block)
    if kan_block:
        parts.append(kan_block)

    selected_paths = [item["file"] for item in selected]
    footer = (
        f"SELECTED={len(selected)}/{len(vertices)}; "
        f"FILES_OMITTED={max(0, len(vertices) - len(selected))}; "
        f"CANDIDATES_OMITTED={max(0, len(profiles) - len(selected))}; "
        "request targeted source only when evidence is insufficient.\n"
    )
    context_block = "\n".join(parts) + footer
    if len(context_block) > char_budget:
        context_block = context_block[:char_budget].rstrip()
    used_chars = len(context_block)
    source_excerpt_line_count = sum(
        1
        for card in rendered_cards
        for line in card.splitlines()
        if line.startswith("  L")
    )
    source_grounding_satisfied = (
        detail != "source"
        or not selected
        or source_excerpt_line_count > 0
    )
    code_chars = sum(
        len(line)
        for card in rendered_cards
        for line in card.splitlines()
        if line.startswith("  L")
    )
    narrative_chars = max(0, used_chars - code_chars)
    estimated_tokens = math.ceil(
        (code_chars / CHARS_PER_TOKEN_CODE) + (narrative_chars / CHARS_PER_TOKEN_NARRATIVE)
    ) if used_chars > 0 else 0
    max_lexical = max((item["score"] for item in lexical_data.values()), default=0.0)
    if resolved_targets:
        confidence = "high"
    elif max_lexical >= 0.5:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "schema_version": "3.0.0-kernel",
        "available": True,
        "model": {
            "name": CONTEXT_MODEL,
            "purpose": (
                "deterministic query-directed projection of measured codebase evidence "
                "and scoped historical observations"
            ),
            "score_formula": "explicit_target_bonus + 0.45*L + 0.25*P + 0.20*C + 0.10*F",
            "terms": {
                "L": "max(path overlap, 0.9*symbol overlap, 0.8*finding overlap)",
                "P": "1/(1+undirected graph distance from a semantic seed)",
                "C": "normalized total degree (fan_in + fan_out)",
                "F": "maximum mapped analyzer-finding severity",
            },
            "claim_boundary": (
                "Ranking is deterministic context selection, not a proof that omitted files "
                "are irrelevant and not a model-specific token count. Memory evidence is "
                "non-authoritative until verified against current source."
            ),
        },
        "query": query,
        "selection": {
            "mode": selection_mode,
            "confidence": confidence,
            "query_terms": sorted(query_terms),
            "semantic_seeds": semantic_seeds,
            "graph_seeds": seeds,
            "requested_targets": requested_targets,
            "resolved_targets": resolved_targets,
            "unresolved_targets": unresolved_targets,
            "max_hops": max_hops,
            "selected_paths": selected_paths,
        },
        "budget": {
            "requested_estimated_tokens": budget_tokens,
            "char_budget": char_budget,
            "chars_per_token_estimate": CHARS_PER_TOKEN_ESTIMATE,
            "chars_per_token_code": CHARS_PER_TOKEN_CODE,
            "chars_per_token_narrative": CHARS_PER_TOKEN_NARRATIVE,
            "used_chars": used_chars,
            "code_chars": code_chars,
            "narrative_chars": narrative_chars,
            "estimated_tokens": estimated_tokens,
            "utilization": round(used_chars / char_budget, 4) if char_budget else 0.0,
            "within_budget": used_chars <= char_budget,
            "token_count_is_estimate": True,
            "adaptive_token_estimation": True,
            "allocation": {
                "source_floor_chars": source_floor_chars,
                "source_card_chars": sum(len(item) for item in rendered_cards),
                "source_excerpt_line_count": source_excerpt_line_count,
                "source_grounding_satisfied": source_grounding_satisfied,
                "memory_cap_chars": memory_cap,
                "memory_chars": len(memory_block),
                "memory_max_fraction": MAX_MEMORY_BUDGET_FRACTION,
                "current_source_precedes_memory": bool(memory_block),
            },
        },
        "provenance": {
            "graph_content_signature": signature,
            "scan_root": shared_graph.get("scan_root"),
            "graph_cache": shared_graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "shared_graph_scan_passes": 1,
            "optimizer_additional_filesystem_scans": 0,
            "analyzers_share_same_graph": True,
            "selected_file_count": len(selected),
            "omitted_file_count": max(0, len(vertices) - len(selected)),
            "analyzers_failed": analyzer_output.get("analyzers_failed", 0),
            "analyzer_errors": analyzer_output.get("errors", {}),
            "memory_scope": (memory_context or {}).get("memory_scope", {}),
            "memory_retrieval": (memory_context or {}).get("retrieval", {}),
            "memory_evidence_retrieved": int(
                (memory_context or {}).get("selected_count", 0)
            ),
            "memory_evidence_included": len(included_memories),
            "kan_extension_active": bool(kan_imputations),
            "kan_imputed_modules": [item.get("target_file") for item in kan_imputations],
        },
        "quotient_graph": _build_quotient(shared_graph, selected_paths),
        "selected_files": selected,
        "kan_imputation": kan_imputations,
        "memory_context": {
            "selected_count": len(included_memories),
            "retrieved_count": int((memory_context or {}).get("selected_count", 0)),
            "memories": included_memories,
            "memory_scope": (memory_context or {}).get("memory_scope", {}),
            "retrieval": (memory_context or {}).get("retrieval", {}),
        },
        "context_block": context_block,
    }


__all__ = [
    "build_context_pack",
    "CONTEXT_MODEL",
    "CHARS_PER_TOKEN_ESTIMATE",
    "CHARS_PER_TOKEN_CODE",
    "CHARS_PER_TOKEN_NARRATIVE",
    "DEFAULT_BUDGET_TOKENS",
    "DEFAULT_MAX_HOPS",
    "MIN_BUDGET_TOKENS",
    "MAX_BUDGET_TOKENS",
    "MAX_HOPS",
    "MAX_MEMORY_CONTEXT_CHARS",
    "estimate_tokens",
]
