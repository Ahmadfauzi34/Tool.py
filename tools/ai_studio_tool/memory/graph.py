"""
Memory Graph Builder — HoTT Kernel Memory Domain
Schema Version: 4.1.0-memory

Membangun graph dari memory store.
Setara dengan shared_graph.py untuk codebase.
"""

from typing import Any, Dict, List, Set, Tuple

try:
    from memory.store import load_store
except ImportError:
    from memory_store import load_store


MEMORY_GRAPH_MODEL = "memory_association_multigraph_1_complex"
INACTIVE_EVIDENCE_STATUSES = {"resolved", "stale", "orphaned", "superseded"}


def _association_layer(association: Dict[str, Any]) -> str:
    metadata = association.get("metadata", {})
    if (
        metadata.get("layer") == "provenance"
        or metadata.get("reason") == "observation_batch_order"
    ):
        return "provenance"
    return "semantic"


def _is_current_memory(memory: Dict[str, Any]) -> bool:
    context = memory.get("context", {})
    evidence_status = str(context.get("evidence_status", "active"))
    return evidence_status not in INACTIVE_EVIDENCE_STATUSES


def _count_evidence_statuses(
    memories: List[Dict[str, Any]],
) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for memory in memories:
        status = str(memory.get("context", {}).get("evidence_status", "unverified"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _build_association_views(
    memory_map: Dict[str, Dict[str, Any]],
    associations: List[Dict[str, Any]],
) -> Tuple[
    List[Tuple[str, str]],
    List[Dict[str, Any]],
    Dict[Tuple[str, str], str],
    Dict[Tuple[str, str], List[str]],
    Dict[str, Dict[str, Any]],
    Dict[str, Set[str]],
]:
    """Preserve every association as a distinct 1-cell."""
    edges: List[Tuple[str, str]] = []
    edge_records: List[Dict[str, Any]] = []
    edge_types: Dict[Tuple[str, str], str] = {}
    edge_types_by_pair: Dict[Tuple[str, str], List[str]] = {}
    association_map: Dict[str, Dict[str, Any]] = {}
    adjacency: Dict[str, Set[str]] = {}

    for association in associations:
        from_id = association.get("from", "")
        to_id = association.get("to", "")
        if from_id not in memory_map or to_id not in memory_map:
            continue
        association_id = str(association.get("id", ""))
        association_type = str(association.get("type", "semantic"))
        pair = (from_id, to_id)
        edges.append(pair)
        edge_records.append({
            "association_id": association_id,
            "from": from_id,
            "to": to_id,
            "type": association_type,
        })
        # Compatibility view; use edge_types_by_pair/edge_records for exact math.
        edge_types[pair] = association_type
        edge_types_by_pair.setdefault(pair, []).append(association_type)
        adjacency.setdefault(from_id, set()).add(to_id)
        adjacency.setdefault(to_id, set()).add(from_id)
        if association_id:
            association_map[association_id] = association

    edge_records.sort(
        key=lambda item: (
            item["from"], item["to"], item["type"], item["association_id"]
        )
    )
    for pair in edge_types_by_pair:
        edge_types_by_pair[pair].sort()
    return (
        sorted(edges),
        edge_records,
        edge_types,
        edge_types_by_pair,
        association_map,
        adjacency,
    )


def build_memory_graph(
    include_archived: bool = False,
    include_historical: bool = False,
    include_provenance: bool = False,
) -> Dict[str, Any]:
    """
    Bangun memory graph dari memory store.

    Args:
        include_archived: Jika True, include archived memories di graph.
                          Default False (hanya active memories).

    Returns:
        Dict dengan:
        - vertices: list of memory IDs
        - edges: list of (from_id, to_id) tuples
        - memory_map: dict of memory_id -> memory data
        - association_map: dict of association_id -> association data
        - adjacency: dict of memory_id -> list of connected memory IDs
        - node_metadata: dict of memory_id -> metadata
        - summary: statistics
    """
    store = load_store()
    memories = store.get("memories", [])
    associations = store.get("associations", [])

    store_lifecycle_counts = _count_evidence_statuses(memories)

    provenance_total = sum(
        1 for association in associations
        if _association_layer(association) == "provenance"
    )

    # Filter archived and non-current analyzer evidence.
    if not include_archived:
        active_ids = {
            m["id"] for m in memories
            if m.get("status", "active") == "active"
            and (include_historical or _is_current_memory(m))
        }
        memories = [m for m in memories if m["id"] in active_ids]
        associations = [
            a for a in associations
            if a.get("from") in active_ids and a.get("to") in active_ids
        ]
    elif not include_historical:
        current_ids = {m["id"] for m in memories if _is_current_memory(m)}
        memories = [m for m in memories if m["id"] in current_ids]
        associations = [
            association for association in associations
            if association.get("from") in current_ids
            and association.get("to") in current_ids
        ]

    if not include_provenance:
        associations = [
            association for association in associations
            if _association_layer(association) != "provenance"
        ]

    included_lifecycle_counts = _count_evidence_statuses(memories)

    # Build vertices and memory_map
    vertices: List[str] = []
    memory_map: Dict[str, Dict[str, Any]] = {}
    node_metadata: Dict[str, Dict[str, Any]] = {}

    for memory in memories:
        mid = memory["id"]
        vertices.append(mid)
        memory_map[mid] = memory
        node_metadata[mid] = {
            "type": memory.get("type", "unknown"),
            "importance": memory.get("importance", 0.0),
            "access_count": memory.get("access_count", 0),
            "tags": memory.get("tags", []),
            "is_consolidated": memory.get("consolidated_into") is not None,
            "evidence_status": memory.get("context", {}).get(
                "evidence_status", "unverified"
            ),
        }

    (
        edges,
        edge_records,
        edge_types,
        edge_types_by_pair,
        association_map,
        adjacency,
    ) = _build_association_views(memory_map, associations)

    # Convert sets to sorted lists
    adjacency_list = {k: sorted(v) for k, v in adjacency.items()}

    # Compute fan_in / fan_out
    fan_in: Dict[str, int] = {}
    fan_out: Dict[str, int] = {}
    for src, tgt in edges:
        fan_out[src] = fan_out.get(src, 0) + 1
        fan_in[tgt] = fan_in.get(tgt, 0) + 1

    for mid in vertices:
        node_metadata[mid]["fan_in"] = fan_in.get(mid, 0)
        node_metadata[mid]["fan_out"] = fan_out.get(mid, 0)

    # Summary
    by_type = {}
    for m in memories:
        t = m.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    return {
        "schema_version": "4.1.0-memory",
        "model": {
            "name": MEMORY_GRAPH_MODEL,
            "vertices": "memory records",
            "one_cells": "association records with multiplicity preserved",
            "betti_semantics": "underlying undirected multigraph cycle rank",
            "not_directed_cycle_count": True,
            "filtration": "semantic_associations",
            "provenance_batch_order_excluded": not include_provenance,
            "historical_evidence_excluded": not include_historical,
        },
        "vertices": sorted(vertices),
        "edges": edges,
        "edge_records": edge_records,
        "edge_types": edge_types,
        "edge_types_by_pair": edge_types_by_pair,
        "memory_map": memory_map,
        "association_map": association_map,
        "adjacency": adjacency_list,
        "node_metadata": node_metadata,
        "summary": {
            "total_memories": len(vertices),
            "total_associations": len(edges),
            "by_type": by_type,
            "by_edge_type": _count_edge_types(edge_records),
            "by_evidence_status": included_lifecycle_counts,
            "store_by_evidence_status": store_lifecycle_counts,
            "historical_memories_excluded": sum(
                count for status, count in store_lifecycle_counts.items()
                if status in INACTIVE_EVIDENCE_STATUSES
            ) if not include_historical else 0,
            "provenance_associations_total": provenance_total,
            "provenance_associations_excluded": (
                provenance_total if not include_provenance else 0
            ),
            "isolated_memories": sum(
                1 for mid in vertices
                if fan_in.get(mid, 0) == 0 and fan_out.get(mid, 0) == 0
            ),
        },
    }


def _count_edge_types(edge_records: List[Dict[str, Any]]) -> Dict[str, int]:
    """Hitung jumlah edges per type."""
    counts: Dict[str, int] = {}
    for record in edge_records:
        etype = str(record.get("type", "semantic"))
        counts[etype] = counts.get(etype, 0) + 1
    return counts


def build_memory_graph_from_data(
    memories: List[Dict[str, Any]],
    associations: List[Dict[str, Any]],
    include_archived: bool = False,
    include_historical: bool = False,
    include_provenance: bool = False,
) -> Dict[str, Any]:
    """
    Bangun memory graph dari data langsung (tanpa file).
    Berguna untuk testing dan inline operations.
    """
    store_lifecycle_counts = _count_evidence_statuses(memories)
    provenance_total = sum(
        1 for association in associations
        if _association_layer(association) == "provenance"
    )

    if not include_archived:
        active_ids = {
            m["id"] for m in memories
            if m.get("status", "active") == "active"
            and (include_historical or _is_current_memory(m))
        }
        memories = [m for m in memories if m["id"] in active_ids]
        associations = [
            a for a in associations
            if a.get("from") in active_ids and a.get("to") in active_ids
        ]
    elif not include_historical:
        current_ids = {m["id"] for m in memories if _is_current_memory(m)}
        memories = [m for m in memories if m["id"] in current_ids]
        associations = [
            association for association in associations
            if association.get("from") in current_ids
            and association.get("to") in current_ids
        ]

    if not include_provenance:
        associations = [
            association for association in associations
            if _association_layer(association) != "provenance"
        ]

    included_lifecycle_counts = _count_evidence_statuses(memories)

    vertices: List[str] = []
    memory_map: Dict[str, Dict[str, Any]] = {}
    node_metadata: Dict[str, Dict[str, Any]] = {}

    for memory in memories:
        mid = memory["id"]
        vertices.append(mid)
        memory_map[mid] = memory
        node_metadata[mid] = {
            "type": memory.get("type", "unknown"),
            "importance": memory.get("importance", 0.0),
            "access_count": memory.get("access_count", 0),
            "tags": memory.get("tags", []),
            "is_consolidated": memory.get("consolidated_into") is not None,
            "evidence_status": memory.get("context", {}).get(
                "evidence_status", "unverified"
            ),
        }

    (
        edges,
        edge_records,
        edge_types,
        edge_types_by_pair,
        association_map,
        adjacency,
    ) = _build_association_views(memory_map, associations)

    adjacency_list = {k: sorted(v) for k, v in adjacency.items()}

    fan_in: Dict[str, int] = {}
    fan_out: Dict[str, int] = {}
    for src, tgt in edges:
        fan_out[src] = fan_out.get(src, 0) + 1
        fan_in[tgt] = fan_in.get(tgt, 0) + 1

    for mid in vertices:
        node_metadata[mid]["fan_in"] = fan_in.get(mid, 0)
        node_metadata[mid]["fan_out"] = fan_out.get(mid, 0)

    return {
        "schema_version": "4.1.0-memory",
        "model": {
            "name": MEMORY_GRAPH_MODEL,
            "vertices": "memory records",
            "one_cells": "association records with multiplicity preserved",
            "betti_semantics": "underlying undirected multigraph cycle rank",
            "not_directed_cycle_count": True,
            "filtration": "semantic_associations",
            "provenance_batch_order_excluded": not include_provenance,
            "historical_evidence_excluded": not include_historical,
        },
        "vertices": sorted(vertices),
        "edges": edges,
        "edge_records": edge_records,
        "edge_types": edge_types,
        "edge_types_by_pair": edge_types_by_pair,
        "memory_map": memory_map,
        "association_map": association_map,
        "adjacency": adjacency_list,
        "node_metadata": node_metadata,
        "summary": {
            "total_memories": len(vertices),
            "total_associations": len(edges),
            "by_edge_type": _count_edge_types(edge_records),
            "by_evidence_status": included_lifecycle_counts,
            "store_by_evidence_status": store_lifecycle_counts,
            "historical_memories_excluded": sum(
                count for status, count in store_lifecycle_counts.items()
                if status in INACTIVE_EVIDENCE_STATUSES
            ) if not include_historical else 0,
            "provenance_associations_total": provenance_total,
            "provenance_associations_excluded": (
                provenance_total if not include_provenance else 0
            ),
        },
    }
