"""Project-scoped Memory-Augmented Context — HoTT Kernel Bridge Domain."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Optional


RETRIEVAL_CLAIM_BOUNDARY = (
    "deterministic lexical/path projection over one canonical snapshot with "
    "freshness gating; exact for declared predicates, not semantic relevance proof"
)


def _memory_modules():
    try:
        from memory.store import (
            build_memory_recall_projection,
            rank_memory_recall_projection,
        )
        from memory.runtime import memory_runtime_provenance
    except ImportError:
        from memory_store import (
            build_memory_recall_projection,
            rank_memory_recall_projection,
        )
        from memory_runtime import memory_runtime_provenance
    return (
        build_memory_recall_projection,
        rank_memory_recall_projection,
        memory_runtime_provenance,
    )


def _evidence_freshness(
    memory: Dict[str, Any],
    current_graph_signature: Optional[str],
    current_file_hashes: Dict[str, str],
) -> str:
    context = memory.get("context", {})
    if not context.get("dedup_key"):
        return "unverified"
    persisted = str(context.get("evidence_status", "active"))
    if persisted != "active":
        return persisted
    file_path = str(context.get("file", "")).replace("\\", "/")
    if file_path and current_file_hashes and file_path not in current_file_hashes:
        return "orphaned"
    stored_file_hash = context.get("source_content_sha256")
    if (
        file_path
        and stored_file_hash
        and current_file_hashes.get(file_path)
        and current_file_hashes[file_path] != stored_file_hash
    ):
        return "stale"
    stored_graph_signature = context.get("graph_content_signature")
    if current_graph_signature and stored_graph_signature:
        return "fresh" if current_graph_signature == stored_graph_signature else "stale"
    return "unverified"


def _memory_view(
    memory: Dict[str, Any],
    current_graph_signature: Optional[str] = None,
    current_file_hashes: Optional[Dict[str, str]] = None,
    retrieval_match: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    content = str(memory.get("content", ""))
    context = memory.get("context", {})
    normalized_hashes = {
        str(path).replace("\\", "/"): str(value)
        for path, value in (current_file_hashes or {}).items()
    }
    freshness = _evidence_freshness(
        memory, current_graph_signature, normalized_hashes
    )
    return {
        "id": memory["id"],
        "type": memory.get("type", "unknown"),
        "content": content,
        "importance": float(memory.get("importance", 0.0)),
        "tags": list(memory.get("tags", [])),
        "source": memory.get("source", "unknown"),
        "finding_type": context.get("finding_type"),
        "file": context.get("file"),
        "observation_count": int(context.get("observation_count", 1)),
        "last_observed_at": context.get("last_observed_at"),
        "first_evidence_signature": context.get("first_evidence_signature"),
        "last_evidence_signature": context.get("last_evidence_signature"),
        "graph_content_signature": context.get("graph_content_signature"),
        "source_content_sha256": context.get("source_content_sha256"),
        "evidence_status": context.get(
            "evidence_status", "unverified" if not context.get("dedup_key") else "active"
        ),
        "freshness": freshness,
        "revision_count": int(context.get("revision_count", 1)),
        "retrieval_match": retrieval_match or memory.get("retrieval_match", {}),
        "content_sha256": f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
    }


def _compute_graph_hops(
    normalized_targets: List[str],
    graph: Optional[Dict[str, Any]],
    max_hops: int = 2,
) -> Dict[str, int]:
    if not graph or not normalized_targets:
        return {}
    edges = graph.get("edges", [])
    adj: Dict[str, set[str]] = {}
    for edge in edges:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            u = str(edge[0]).replace("\\", "/")
            v = str(edge[1]).replace("\\", "/")
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
    distances: Dict[str, int] = {}
    queue: List[str] = []
    for target in normalized_targets:
        distances[target] = 0
        queue.append(target)
    while queue:
        current = queue.pop(0)
        dist = distances[current]
        if dist >= max_hops:
            continue
        for neighbor in sorted(adj.get(current, set())):
            if neighbor not in distances:
                distances[neighbor] = dist + 1
                queue.append(neighbor)
    return {node: dist for node, dist in distances.items() if dist > 0}


def get_memory_evidence(
    query: Optional[str] = None,
    target_files: Optional[Iterable[str]] = None,
    max_memories: int = 5,
    current_graph_signature: Optional[str] = None,
    current_file_hashes: Optional[Dict[str, str]] = None,
    include_stale: bool = False,
    cache_mode: str = "auto",
    target_hops: Optional[Dict[str, int]] = None,
    graph: Optional[Dict[str, Any]] = None,
    max_hops: int = 2,
) -> Dict[str, Any]:
    """Recall scoped evidence for a developer query and optional file targets with graph-hop neighborhood."""
    try:
        (
            build_projection,
            rank_projection,
            runtime_provenance,
        ) = _memory_modules()
    except ImportError:
        return {
            "error": "memory_store not available",
            "selected_count": 0,
            "memories": [],
        }

    normalized_targets = [str(path).replace("\\", "/") for path in (target_files or [])]
    computed_hops = dict(target_hops or {})
    if graph and normalized_targets:
        graph_hops = _compute_graph_hops(normalized_targets, graph, max_hops=max_hops)
        for node, dist in graph_hops.items():
            if node not in computed_hops or dist < computed_hops[node]:
                computed_hops[node] = dist

    projection = build_projection(cache_mode=cache_mode)
    ranked = rank_projection(
        projection,
        query=query,
        target_files=normalized_targets,
        target_hops=computed_hops if computed_hops else None,
        include_historical_evidence=include_stale,
    )

    selected: List[Dict[str, Any]] = []
    excluded_by_freshness: Dict[str, int] = {}
    freshness_evaluated_count = 0
    target_witness_required = bool(normalized_targets and max_memories >= 2)
    target_witness_satisfied = False
    for candidate in ranked.get("candidates", []):
        memory = candidate.get("memory", {})
        if not memory.get("id"):
            continue
        retrieval_match = candidate.get("retrieval_match", {})
        is_primary_target = bool(
            retrieval_match.get("rank_vector", {}).get("target_primary", False)
        )
        if len(selected) >= max_memories:
            if not target_witness_required or target_witness_satisfied:
                break
            if not is_primary_target:
                continue
        freshness_evaluated_count += 1
        view = _memory_view(
            memory,
            current_graph_signature=current_graph_signature,
            current_file_hashes=current_file_hashes,
            retrieval_match=retrieval_match,
        )
        freshness = str(view.get("freshness", "unverified"))
        if freshness in {"resolved", "stale", "orphaned", "superseded"} and not include_stale:
            excluded_by_freshness[freshness] = (
                excluded_by_freshness.get(freshness, 0) + 1
            )
            continue
        if len(selected) < max_memories:
            selected.append(view)
        elif is_primary_target:
            # Query relevance orders the prompt, but an explicit target owns one
            # witness slot when the context projection has at least two slots.
            selected[-1] = view
        target_witness_satisfied = target_witness_satisfied or is_primary_target

    runtime = runtime_provenance()
    trace = dict(ranked.get("trace", {}))
    recall_cache = trace.get("cache", {})
    trace.update({
        "source_store_loads": int(
            recall_cache.get("canonical_store_load_count", 1)
        ),
        "freshness_evaluated_count": freshness_evaluated_count,
        "selected_count": len(selected),
        "target_witness_required": target_witness_required,
        "target_witness_satisfied": target_witness_satisfied,
        "graph_hops_evaluated": len(computed_hops),
        "graph_hops": computed_hops,
    })

    kan_imputations = []
    try:
        from memory.kan_extension import impute_module_relations
        for tf in normalized_targets[:3]:
            imp = impute_module_relations(
                tf,
                shared_graph=graph,
                memory_store={"memories": selected},
            )
            kan_imputations.append(imp)
    except Exception:
        kan_imputations = []

    res = {
        "query": query,
        "target_files": normalized_targets,
        "retrieved_count": int(trace.get("ranked_count", 0)),
        "selected_count": len(selected),
        "memories": selected,
        "memory_scope": runtime,
        "retrieval": {
            "model": "scoped_memory_recall_projection_v3_freshness",
            "claim_boundary": RETRIEVAL_CLAIM_BOUNDARY,
            "archived_included": False,
            "stale_included": include_stale,
            "current_graph_signature": current_graph_signature,
            "excluded_by_freshness": excluded_by_freshness,
            "max_memories": max_memories,
            "projection": trace,
        },
    }
    if kan_imputations:
        res["kan_imputation"] = kan_imputations
    return res


def get_memory_context_for_file(
    file_path: str,
    max_memories: int = 5,
    graph: Optional[Dict[str, Any]] = None,
    target_hops: Optional[Dict[str, int]] = None,
    max_hops: int = 2,
) -> Dict[str, Any]:
    """Compatibility wrapper for file-oriented scoped recall with graph-hop neighborhood and Kan Extension imputation."""
    result = get_memory_evidence(
        query=file_path,
        target_files=[file_path],
        max_memories=max_memories,
        graph=graph,
        target_hops=target_hops,
        max_hops=max_hops,
    )
    res = {
        "file": file_path,
        "memory_count": result.get("selected_count", 0),
        "memories": result.get("memories", []),
        "memory_scope": result.get("memory_scope", {}),
        "retrieval": result.get("retrieval", {}),
        **({"error": result["error"]} if result.get("error") else {}),
    }
    try:
        from memory.kan_extension import impute_module_relations
        kan_extension = impute_module_relations(
            file_path,
            shared_graph=graph,
            memory_store={"memories": result.get("memories", [])},
        )
        res["kan_extension"] = kan_extension
    except Exception:
        pass
    return res


__all__ = [
    "get_memory_context_for_file",
    "get_memory_evidence",
    "RETRIEVAL_CLAIM_BOUNDARY",
]
