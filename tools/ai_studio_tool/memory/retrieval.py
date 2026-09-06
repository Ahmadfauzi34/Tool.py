"""Snapshot-consistent reference projection for deterministic memory recall.

The durable store remains canonical and unbounded by this module.  A projection
indexes retrieval-relevant fields from one loaded snapshot, then ranks only the
candidate subspace for one or more developer signals.  The index is a reference
machine for the declared lexical/path predicate; it is not a proof that omitted
records are semantically irrelevant.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple


RECALL_PROJECTION_SCHEMA_VERSION = "memory-recall-projection-v2"
LEXICAL_MATCH_MODEL = "lexical_overlap_v1"
MULTI_SIGNAL_MATCH_MODEL = "multi_signal_memory_projection_v1"
INACTIVE_EVIDENCE_STATUSES = {
    "resolved",
    "stale",
    "orphaned",
    "superseded",
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _normalize_path(value: Any) -> str:
    return _normalize_text(str(value or "").replace("\\", "/"))


def _terms(value: Any, minimum_length: int = 1) -> Set[str]:
    return {
        token
        for token in _TOKEN_PATTERN.findall(_normalize_text(value))
        if len(token) >= minimum_length
    }


def normalize_recall_text(value: Any) -> str:
    """Public normalization contract shared by persistent predicate indexes."""
    return _normalize_text(value)


def normalize_recall_path(value: Any) -> str:
    """Public path normalization used by target-file retrieval."""
    return _normalize_path(value)


def recall_terms(value: Any, minimum_length: int = 1) -> Set[str]:
    """Public tokenizer used by both in-memory and persistent projections."""
    return _terms(value, minimum_length=minimum_length)


def _memory_status(memory: Dict[str, Any]) -> str:
    return str(memory.get("status", "active"))


def _evidence_status(memory: Dict[str, Any]) -> str:
    context = memory.get("context", {})
    if not context.get("dedup_key"):
        return "unverified"
    return str(context.get("evidence_status", "active"))


def _searchable_text(memory: Dict[str, Any]) -> str:
    context = memory.get("context", {})
    return _normalize_text(" ".join([
        str(memory.get("content", "")),
        str(memory.get("source", "")),
        " ".join(str(tag) for tag in memory.get("tags", [])),
        str(context.get("file", "")),
        str(context.get("finding_type", "")),
        str(context.get("source_analyzer", "")),
    ]))


def memory_record_signature(memory: Dict[str, Any]) -> str:
    """Hash one complete canonical memory record deterministically."""
    payload = json.dumps(
        memory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def recall_index_record(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Return stable fields used by the declared lexical/path predicates."""
    context = memory.get("context", {})
    searchable = _searchable_text(memory)
    file_path = _normalize_path(
        context.get("file", "") or context.get("target_file", "") or memory.get("file", "")
    )
    raw_related = context.get("related_files", []) or memory.get("related_files", [])
    if isinstance(raw_related, str):
        raw_related = [raw_related]
    related_files = sorted({
        _normalize_path(rf)
        for rf in raw_related
        if _normalize_path(rf)
    })
    return {
        "memory_id": str(memory.get("id", "")),
        "record_signature": memory_record_signature(memory),
        "searchable": searchable,
        "terms": sorted(_terms(searchable)),
        "tags": sorted({str(tag) for tag in memory.get("tags", [])}),
        "type": str(memory.get("type", "")),
        "file": file_path,
        "basename": os.path.basename(file_path),
        "related_files": related_files,
    }


def projection_signature_from_records(
    ordered_memory_ids: Iterable[str],
    record_signatures: Dict[str, str],
) -> str:
    """Compose an exact snapshot signature without materializing all entries."""
    digest = hashlib.sha256()
    for memory_id in ordered_memory_ids:
        digest.update(str(memory_id).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record_signatures[memory_id]).encode("ascii"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _append_index(index: Dict[str, List[int]], key: str, ordinal: int) -> None:
    if key:
        index.setdefault(key, []).append(ordinal)


def _build_recall_entry(memory: Dict[str, Any], ordinal: int) -> Dict[str, Any]:
    indexed = recall_index_record(memory)
    return {
        "ordinal": ordinal,
        "memory": memory,
        "record_signature": indexed["record_signature"],
        "searchable": indexed["searchable"],
        "terms": set(indexed["terms"]),
        "tags": set(indexed["tags"]),
        "file": indexed["file"],
        "basename": indexed["basename"],
        "related_files": indexed.get("related_files", []),
        "status": _memory_status(memory),
        "evidence_status": _evidence_status(memory),
    }


def _projection_signature(entries: List[Dict[str, Any]]) -> str:
    ordered_ids = [str(entry["memory"].get("id", "")) for entry in entries]
    signatures = {
        str(entry["memory"].get("id", "")): str(entry["record_signature"])
        for entry in entries
    }
    return projection_signature_from_records(ordered_ids, signatures)


def _assemble_recall_projection(
    entries: List[Dict[str, Any]],
    build_stats: Dict[str, int],
) -> Dict[str, Any]:
    term_index: Dict[str, List[int]] = {}
    tag_index: Dict[str, List[int]] = {}
    type_index: Dict[str, List[int]] = {}
    file_index: Dict[str, List[int]] = {}
    basename_index: Dict[str, List[int]] = {}
    related_file_index: Dict[str, List[int]] = {}

    for ordinal, entry in enumerate(entries):
        memory = entry["memory"]
        entry["ordinal"] = ordinal
        for term in sorted(entry["terms"]):
            _append_index(term_index, term, ordinal)
        for tag in sorted(entry["tags"]):
            _append_index(tag_index, tag, ordinal)
        _append_index(type_index, str(memory.get("type", "")), ordinal)
        _append_index(file_index, entry["file"], ordinal)
        _append_index(basename_index, entry["basename"], ordinal)
        for rf in entry.get("related_files", []):
            _append_index(related_file_index, rf, ordinal)

    return {
        "schema_version": RECALL_PROJECTION_SCHEMA_VERSION,
        "entries": entries,
        "term_index": term_index,
        "tag_index": tag_index,
        "type_index": type_index,
        "file_index": file_index,
        "basename_index": basename_index,
        "related_file_index": related_file_index,
        "snapshot_signature": _projection_signature(entries),
        "snapshot_memory_count": len(entries),
        "indexed_term_count": len(term_index),
        "built_from_single_snapshot": True,
        "build": build_stats,
    }


def build_recall_projection(
    memories: Iterable[Dict[str, Any]],
    previous_projection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build or incrementally update an inverted canonical-snapshot projection."""
    prior_by_id: Dict[str, Dict[str, Any]] = {}
    if (
        isinstance(previous_projection, dict)
        and previous_projection.get("schema_version")
        == RECALL_PROJECTION_SCHEMA_VERSION
    ):
        for entry in previous_projection.get("entries", []):
            memory = entry.get("memory", {}) if isinstance(entry, dict) else {}
            memory_id = str(memory.get("id", ""))
            if memory_id:
                prior_by_id[memory_id] = entry

    entries: List[Dict[str, Any]] = []
    current_ids: Set[str] = set()
    reused = 0
    rebuilt = 0
    for ordinal, memory in enumerate(memories):
        memory_id = str(memory.get("id", ""))
        current_ids.add(memory_id)
        prior = prior_by_id.get(memory_id)
        signature = memory_record_signature(memory)
        if prior and prior.get("record_signature") == signature:
            entry = dict(prior)
            entry["ordinal"] = ordinal
            entry["memory"] = memory
            entries.append(entry)
            reused += 1
            continue
        entries.append(_build_recall_entry(memory, ordinal))
        rebuilt += 1

    removed = len(set(prior_by_id) - current_ids)
    return _assemble_recall_projection(
        entries,
        {
            "entries_reused": reused,
            "entries_rebuilt": rebuilt,
            "entries_removed": removed,
        },
    )


def serialize_recall_projection(projection: Dict[str, Any]) -> Dict[str, Any]:
    """Convert the in-process sets into a safe JSON cache representation."""
    entries = []
    for entry in projection.get("entries", []):
        entries.append({
            "memory": entry.get("memory", {}),
            "record_signature": entry.get("record_signature"),
            "searchable": entry.get("searchable", ""),
            "terms": sorted(entry.get("terms", [])),
        })
    return {
        "schema_version": projection.get("schema_version"),
        "entries": entries,
        "term_index": projection.get("term_index", {}),
        "tag_index": projection.get("tag_index", {}),
        "type_index": projection.get("type_index", {}),
        "file_index": projection.get("file_index", {}),
        "basename_index": projection.get("basename_index", {}),
        "snapshot_signature": projection.get("snapshot_signature"),
        "snapshot_memory_count": projection.get("snapshot_memory_count", 0),
        "indexed_term_count": projection.get("indexed_term_count", 0),
        "built_from_single_snapshot": projection.get(
            "built_from_single_snapshot", False
        ),
    }


def deserialize_recall_projection(payload: Any) -> Dict[str, Any]:
    """Validate and restore a JSON projection without executing cached data."""
    if not isinstance(payload, dict):
        raise ValueError("recall projection cache payload must be an object")
    if payload.get("schema_version") != RECALL_PROJECTION_SCHEMA_VERSION:
        raise ValueError("recall projection cache schema mismatch")
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("recall projection entries must be a list")
    entries: List[Dict[str, Any]] = []
    for ordinal, raw in enumerate(raw_entries):
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("memory"), dict)
            or not isinstance(raw.get("record_signature"), str)
            or not isinstance(raw.get("searchable"), str)
            or not isinstance(raw.get("terms"), list)
            or not all(isinstance(term, str) for term in raw.get("terms", []))
        ):
            raise ValueError("recall projection entry is invalid")
        memory = raw["memory"]
        context = memory.get("context", {})
        file_path = _normalize_path(context.get("file", ""))
        entries.append({
            "ordinal": ordinal,
            "memory": memory,
            "record_signature": raw["record_signature"],
            "searchable": raw["searchable"],
            "terms": raw["terms"],
            "tags": [str(tag) for tag in memory.get("tags", [])],
            "file": file_path,
            "basename": os.path.basename(file_path),
            "status": _memory_status(memory),
            "evidence_status": _evidence_status(memory),
        })

    indexes: Dict[str, Dict[str, List[int]]] = {}
    for field in (
        "term_index",
        "tag_index",
        "type_index",
        "file_index",
        "basename_index",
    ):
        index = payload.get(field)
        if not isinstance(index, dict) or any(
            not isinstance(key, str)
            or not isinstance(postings, list)
            or not all(
                isinstance(value, int) and 0 <= value < len(entries)
                for value in postings
            )
            for key, postings in index.items()
        ):
            raise ValueError(f"recall projection {field} is invalid")
        indexes[field] = index

    if payload.get("snapshot_memory_count") != len(entries):
        raise ValueError("recall projection memory count mismatch")
    if not isinstance(payload.get("snapshot_signature"), str):
        raise ValueError("recall projection signature missing")
    return {
        "schema_version": payload["schema_version"],
        "entries": entries,
        **indexes,
        "snapshot_signature": payload["snapshot_signature"],
        "snapshot_memory_count": len(entries),
        "indexed_term_count": int(payload.get("indexed_term_count", 0)),
        "built_from_single_snapshot": True,
        "build": {
            "entries_reused": len(entries),
            "entries_rebuilt": 0,
            "entries_removed": 0,
        },
    }


def projection_metadata(projection: Dict[str, Any]) -> Dict[str, Any]:
    """Return the serializable proof surface, excluding in-process indexes."""
    metadata = {
        "schema_version": projection.get("schema_version"),
        "snapshot_signature": projection.get("snapshot_signature"),
        "snapshot_memory_count": int(projection.get("snapshot_memory_count", 0)),
        "indexed_term_count": int(projection.get("indexed_term_count", 0)),
        "built_from_single_snapshot": bool(
            projection.get("built_from_single_snapshot", False)
        ),
    }
    if isinstance(projection.get("cache"), dict):
        metadata["cache"] = copy.deepcopy(projection["cache"])
    if projection.get("storage_model"):
        metadata["storage_model"] = projection["storage_model"]
    return metadata


def _posting_union(index: Dict[str, List[int]], keys: Iterable[str]) -> Set[int]:
    result: Set[int] = set()
    for key in keys:
        result.update(index.get(key, []))
    return result


def _phrase_candidates(projection: Dict[str, Any], phrase: str) -> Set[int]:
    terms = sorted(_terms(phrase))
    if not terms:
        return set(range(len(projection["entries"])))
    postings = [set(projection["term_index"].get(term, [])) for term in terms]
    if not postings or any(not values for values in postings):
        return set()
    candidates = postings[0]
    for values in postings[1:]:
        candidates.intersection_update(values)
    return candidates


def _query_signals(
    projection: Dict[str, Any],
    query: Optional[str],
    signals: Dict[int, Dict[str, Any]],
) -> None:
    if not query:
        return
    normalized_query = _normalize_text(query)
    query_terms = _terms(normalized_query, minimum_length=2)
    candidates = (
        _posting_union(projection["term_index"], query_terms)
        if query_terms
        else set(range(len(projection["entries"])))
    )
    for ordinal in candidates:
        entry = projection["entries"][ordinal]
        matched_terms = query_terms.intersection(entry["terms"])
        exact = normalized_query in entry["searchable"]
        if not exact and query_terms and not matched_terms:
            continue
        if not exact and not query_terms:
            continue
        overlap = len(matched_terms) / max(1, len(query_terms))
        importance = float(entry["memory"].get("importance", 0.0))
        score = (4.0 if exact else 0.0) + 2.0 * overlap + importance
        signals.setdefault(ordinal, {})["query"] = {
            "model": LEXICAL_MATCH_MODEL,
            "score": round(score, 6),
            "exact_substring": exact,
            "matched_terms": sorted(matched_terms),
            "query_term_count": len(query_terms),
        }


def _target_signals(
    projection: Dict[str, Any],
    target_files: Iterable[str],
    signals: Dict[int, Dict[str, Any]],
    target_hops: Optional[Dict[str, int]] = None,
) -> List[str]:
    normalized_targets: List[str] = []
    related_file_index = projection.get("related_file_index", {})
    for raw_path in target_files:
        file_path = _normalize_path(raw_path)
        if not file_path or file_path in normalized_targets:
            continue
        normalized_targets.append(file_path)
        basename = os.path.basename(file_path)
        file_dir = os.path.dirname(file_path)
        directory_tag = file_dir.replace("/", ".") if file_dir else ""

        for ordinal in projection["file_index"].get(file_path, []):
            target = signals.setdefault(ordinal, {}).setdefault("target", {})
            target.setdefault("exact_files", set()).add(file_path)

        for ordinal in related_file_index.get(file_path, []):
            target = signals.setdefault(ordinal, {}).setdefault("target", {})
            target.setdefault("related_files", set()).add(file_path)

        for ordinal in _phrase_candidates(projection, file_path):
            if file_path not in projection["entries"][ordinal]["searchable"]:
                continue
            target = signals.setdefault(ordinal, {}).setdefault("target", {})
            target.setdefault("path_phrases", set()).add(file_path)

        if basename:
            for ordinal in projection["basename_index"].get(basename, []):
                target = signals.setdefault(ordinal, {}).setdefault("target", {})
                target.setdefault("basenames", set()).add(basename)

        if directory_tag:
            for ordinal in projection["tag_index"].get(directory_tag, []):
                target = signals.setdefault(ordinal, {}).setdefault("target", {})
                target.setdefault("directory_tags", set()).add(directory_tag)

    if target_hops:
        for hop_path, dist in sorted(target_hops.items(), key=lambda x: (x[1], str(x[0]))):
            norm_hop = _normalize_path(hop_path)
            if not norm_hop or norm_hop in normalized_targets:
                continue
            if dist == 1:
                for ordinal in projection["file_index"].get(norm_hop, []):
                    target = signals.setdefault(ordinal, {}).setdefault("target", {})
                    target.setdefault("graph_hop_1", set()).add(norm_hop)
                for ordinal in related_file_index.get(norm_hop, []):
                    target = signals.setdefault(ordinal, {}).setdefault("target", {})
                    target.setdefault("graph_hop_1", set()).add(norm_hop)
            elif dist == 2:
                for ordinal in projection["file_index"].get(norm_hop, []):
                    target = signals.setdefault(ordinal, {}).setdefault("target", {})
                    target.setdefault("graph_hop_2", set()).add(norm_hop)
                for ordinal in related_file_index.get(norm_hop, []):
                    target = signals.setdefault(ordinal, {}).setdefault("target", {})
                    target.setdefault("graph_hop_2", set()).add(norm_hop)

    return normalized_targets


def _target_strength(target: Dict[str, Any]) -> int:
    if target.get("exact_files"):
        return 5
    if target.get("related_files"):
        return 4
    if target.get("graph_hop_1"):
        return 4
    if target.get("path_phrases"):
        return 3
    if target.get("graph_hop_2"):
        return 2
    if target.get("basenames"):
        return 2
    if target.get("directory_tags"):
        return 1
    return 0


def _serializable_match(
    signal: Dict[str, Any],
    importance: float,
) -> Dict[str, Any]:
    query_match = signal.get("query", {})
    target = signal.get("target", {})
    strength = _target_strength(target)
    selection_signals: List[str] = []
    if query_match:
        selection_signals.append(
            "query_exact" if query_match.get("exact_substring") else "query_terms"
        )
    if target.get("exact_files"):
        selection_signals.append("target_file_exact")
    if target.get("related_files"):
        selection_signals.append("target_related_file")
    if target.get("graph_hop_1"):
        selection_signals.append("target_graph_hop_1")
    if target.get("graph_hop_2"):
        selection_signals.append("target_graph_hop_2")
    if target.get("path_phrases"):
        selection_signals.append("target_path_phrase")
    if target.get("basenames"):
        selection_signals.append("target_basename")
    if target.get("directory_tags"):
        selection_signals.append("target_directory_tag")

    hop_distance: Optional[int] = None
    if target.get("exact_files"):
        hop_distance = 0
    elif target.get("related_files") or target.get("graph_hop_1"):
        hop_distance = 1
    elif target.get("graph_hop_2"):
        hop_distance = 2

    return {
        "model": MULTI_SIGNAL_MATCH_MODEL,
        "query": copy.deepcopy(query_match),
        "target": {
            key: sorted(value)
            for key, value in target.items()
            if value
        },
        "selection_signals": selection_signals,
        "rank_vector": {
            "target_strength": strength,
            "target_primary": strength >= 3,
            "query_score": float(query_match.get("score", 0.0)),
            "importance": importance,
            "hop_distance": hop_distance,
            "target_hop_1": bool(target.get("graph_hop_1")),
            "target_hop_2": bool(target.get("graph_hop_2")),
            "target_hop_distance": hop_distance if hop_distance is not None else 3,
        },
    }


def rank_recall_projection(
    projection: Dict[str, Any],
    query: Optional[str] = None,
    target_files: Optional[Iterable[str]] = None,
    target_hops: Optional[Dict[str, int]] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    min_importance: float = 0.0,
    include_archived: bool = False,
    include_historical_evidence: bool = False,
) -> Dict[str, Any]:
    """Rank candidate references without copying the canonical memory records."""
    provider: Optional[Callable[..., Tuple[Dict[str, Any], Dict[str, Any]]]] = (
        projection.get("_candidate_provider")
    )
    if callable(provider):
        lazy_target_files = list(target_files or [])
        materialized, provider_trace = provider(
            query=query,
            target_files=lazy_target_files,
            target_hops=target_hops,
            memory_type=memory_type,
            tags=list(tags or []),
        )
        ranked = rank_recall_projection(
            materialized,
            query=query,
            target_files=lazy_target_files,
            target_hops=target_hops,
            memory_type=memory_type,
            tags=tags,
            min_importance=min_importance,
            include_archived=include_archived,
            include_historical_evidence=include_historical_evidence,
        )
        trace = ranked["trace"]
        global_total = int(projection.get("snapshot_memory_count", 0))
        exact_candidates = int(trace.get("candidate_count", 0))
        trace.update(projection_metadata(projection))
        trace.update(provider_trace)
        trace.update({
            "candidate_count": exact_candidates,
            "projection_pruned_count": max(0, global_total - exact_candidates),
            "candidate_ratio": round(
                exact_candidates / max(1, global_total), 6
            ),
            "snapshot_consistent": True,
        })
        return ranked

    signals: Dict[int, Dict[str, Any]] = {}
    _query_signals(projection, query, signals)
    normalized_targets = _target_signals(
        projection, target_files or [], signals, target_hops=target_hops
    )
    has_directed_signal = bool(query or normalized_targets or target_hops)
    candidate_ordinals = (
        set(signals)
        if has_directed_signal
        else set(range(len(projection["entries"])))
    )

    if memory_type:
        candidate_ordinals.intersection_update(
            projection["type_index"].get(memory_type, [])
        )
    if tags:
        candidate_ordinals.intersection_update(
            _posting_union(projection["tag_index"], tags)
        )

    ranked: List[Dict[str, Any]] = []
    filtered_counts: Dict[str, int] = {}
    for ordinal in candidate_ordinals:
        entry = projection["entries"][ordinal]
        memory = entry["memory"]
        exclusion: Optional[str] = None
        if not include_archived and entry["status"] != "active":
            exclusion = "archived"
        elif (
            not include_historical_evidence
            and entry["evidence_status"] in INACTIVE_EVIDENCE_STATUSES
        ):
            exclusion = entry["evidence_status"]
        elif float(memory.get("importance", 0.0)) < min_importance:
            exclusion = "below_min_importance"
        if exclusion:
            filtered_counts[exclusion] = filtered_counts.get(exclusion, 0) + 1
            continue

        importance = float(memory.get("importance", 0.0))
        signal = signals.get(ordinal, {})
        match = _serializable_match(signal, importance)
        rank_vector = match["rank_vector"]
        hop_order = (
            rank_vector["hop_distance"]
            if rank_vector.get("hop_distance") is not None
            else 99
        )
        ranked.append({
            "ordinal": ordinal,
            "memory": memory,
            "retrieval_match": match,
            "sort_key": (
                -float(rank_vector["query_score"]),
                -int(bool(rank_vector["target_primary"])),
                -int(rank_vector["target_strength"]),
                hop_order,
                -importance,
                str(memory.get("timestamp", "")),
                str(memory.get("id", "")),
            ),
        })

    if not has_directed_signal:
        ranked.sort(key=lambda item: int(item["ordinal"]))
        ranked.sort(
            key=lambda item: str(item["memory"].get("timestamp", "")),
            reverse=True,
        )
        ranked.sort(
            key=lambda item: float(item["memory"].get("importance", 0.0)),
            reverse=True,
        )
    else:
        ranked.sort(key=lambda item: item["sort_key"])

    total = len(projection["entries"])
    candidate_count = len(candidate_ordinals)
    return {
        "candidates": ranked,
        "trace": {
            **projection_metadata(projection),
            "query": query,
            "target_files": normalized_targets,
            "candidate_count": candidate_count,
            "ranked_count": len(ranked),
            "filtered_counts": filtered_counts,
            "projection_pruned_count": max(0, total - candidate_count),
            "candidate_ratio": round(candidate_count / max(1, total), 6),
            "snapshot_consistent": True,
            "predicate_completeness": (
                "exact_for_declared_lexical_and_path_predicates"
            ),
            "omitted_semantic_relevance_proven": False,
            "graph_hops_active": bool(target_hops),
            "graph_hop_count": len(target_hops) if target_hops else 0,
        },
    }


def recall_from_projection(
    projection: Dict[str, Any],
    query: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    min_importance: float = 0.0,
    limit: int = 20,
    include_archived: bool = False,
    include_historical_evidence: bool = False,
) -> List[Dict[str, Any]]:
    """Compatibility recall over a prebuilt projection."""
    ranked = rank_recall_projection(
        projection,
        query=query,
        memory_type=memory_type,
        tags=tags,
        min_importance=min_importance,
        include_archived=include_archived,
        include_historical_evidence=include_historical_evidence,
    )
    results: List[Dict[str, Any]] = []
    for candidate in ranked["candidates"][:limit]:
        memory = copy.deepcopy(candidate["memory"])
        if query:
            memory["retrieval_match"] = copy.deepcopy(
                candidate["retrieval_match"].get("query", {})
            )
        results.append(memory)
    return results


__all__ = [
    "LEXICAL_MATCH_MODEL",
    "MULTI_SIGNAL_MATCH_MODEL",
    "RECALL_PROJECTION_SCHEMA_VERSION",
    "build_recall_projection",
    "deserialize_recall_projection",
    "memory_record_signature",
    "normalize_recall_path",
    "normalize_recall_text",
    "projection_metadata",
    "projection_signature_from_records",
    "rank_recall_projection",
    "recall_index_record",
    "recall_from_projection",
    "recall_terms",
    "serialize_recall_projection",
]
