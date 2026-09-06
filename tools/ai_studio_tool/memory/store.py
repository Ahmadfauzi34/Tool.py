"""
Memory Store — HoTT Kernel Memory Domain
Schema Version: 4.1.0-memory

Project-scoped durable memory storage engine.
Supports episodic, semantic, and procedural memory types.
"""

import copy
import os
import uuid
import datetime
from typing import Any, Callable, Dict, List, Optional

from memory.runtime import (
    get_memory_runtime_paths,
    memory_runtime_lock,
    memory_runtime_provenance,
    read_json_unlocked,
    write_json_unlocked,
)
from memory.provenance import (
    DEFAULT_PROVENANCE_EVENT_LIMIT,
    apply_provenance_retention,
    default_provenance_retention,
    normalize_observation_event,
    provenance_retention_snapshot,
    validate_provenance_event_limit,
)
from memory.retrieval import (
    rank_recall_projection,
    recall_from_projection,
)
from memory.retrieval_cache import (
    clear_recall_cache_unlocked,
    get_recall_cache_status_unlocked,
    load_or_build_recall_projection_unlocked,
)

SCHEMA_VERSION = "4.1.0-memory"

# Compatibility constants are snapshots of the initial process scope. Runtime
# operations resolve paths dynamically so CLI configuration can select a scope.
_INITIAL_PATHS = get_memory_runtime_paths(create=False)
MEMORY_STORE_PATH = _INITIAL_PATHS["store_path"]
BASELINE_PATH = _INITIAL_PATHS["baseline_path"]
CONSOLIDATION_LOG_PATH = _INITIAL_PATHS["consolidation_log_path"]

MEMORY_TYPES = ("episodic", "semantic", "procedural")
ASSOCIATION_TYPES = (
    "temporal", "causal", "semantic", "inferential",
    "consolidation", "derivation", "contradiction", "redundancy"
)
REASONING_EDGE_TYPES = {"inferential", "causal"}

# Status memory untuk quotient forgetting
MEMORY_STATUS_ACTIVE = "active"
MEMORY_STATUS_ARCHIVED = "archived"

EVIDENCE_STATUS_ACTIVE = "active"
EVIDENCE_STATUS_RESOLVED = "resolved"
EVIDENCE_STATUS_STALE = "stale"
EVIDENCE_STATUS_ORPHANED = "orphaned"
EVIDENCE_STATUS_SUPERSEDED = "superseded"
EVIDENCE_STATUS_UNVERIFIED = "unverified"
INACTIVE_EVIDENCE_STATUSES = {
    EVIDENCE_STATUS_RESOLVED,
    EVIDENCE_STATUS_STALE,
    EVIDENCE_STATUS_ORPHANED,
    EVIDENCE_STATUS_SUPERSEDED,
}


class ReasoningCycleRejectedError(ValueError):
    """A reasoning association would close a directed path."""

    error_code = "would_create_reasoning_cycle"

    def __init__(self, from_id: str, to_id: str, assoc_type: str) -> None:
        super().__init__(
            f"Association {from_id} --{assoc_type}--> {to_id} would create "
            "a directed reasoning cycle"
        )
        self.details = {
            "from_id": from_id,
            "to_id": to_id,
            "association_type": assoc_type,
            "safe_mode": True,
        }


def _get_status(memory: Dict[str, Any]) -> str:
    """Ambil status memory dengan backward compatibility."""
    return memory.get("status", MEMORY_STATUS_ACTIVE)


def _get_evidence_status(memory: Dict[str, Any]) -> str:
    """Return analyzer-evidence lifecycle without changing manual memories."""
    context = memory.get("context", {})
    if not context.get("dedup_key"):
        return EVIDENCE_STATUS_UNVERIFIED
    return str(context.get("evidence_status", EVIDENCE_STATUS_ACTIVE))


def is_semantically_current_memory(memory: Dict[str, Any]) -> bool:
    """Return whether a memory may participate in current semantic automation.

    Manual memories have the ``unverified`` evidence status and remain eligible.
    Analyzer evidence that is historical stays in the store for audit, but must
    not silently influence consolidation or semantic graph decisions.
    """
    return (
        _get_status(memory) == MEMORY_STATUS_ACTIVE
        and _get_evidence_status(memory) not in INACTIVE_EVIDENCE_STATUSES
    )


def _generate_id(memory_type: str) -> str:
    """Generate unique ID dengan prefix tipe."""
    prefix_map = {"episodic": "ep", "semantic": "sem", "procedural": "proc"}
    prefix = prefix_map.get(memory_type, "mem")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{short_uuid}"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _legacy_scan_scope(scan_root: Any, project_root: Any) -> str:
    """Map pre-lifecycle scan roots to the stable relative namespace."""
    raw = str(scan_root or ".").replace("\\", "/").rstrip("/") or "."
    project = os.path.abspath(str(project_root or os.getcwd()))
    if raw == ".":
        return "project"
    if os.path.isabs(raw):
        try:
            relative = os.path.relpath(os.path.abspath(raw), project).replace("\\", "/")
        except ValueError:
            return raw
        if relative == ".":
            return "project"
        if relative != ".." and not relative.startswith("../"):
            return relative
        return raw
    normalized = os.path.normpath(raw).replace("\\", "/")
    if normalized == os.path.basename(project):
        return "project"
    return normalized


def _default_store() -> Dict[str, Any]:
    now = _now_iso()
    paths = get_memory_runtime_paths(create=True)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "scope": {
            "scope_id": paths["scope_id"],
            "scope_kind": paths["scope_kind"],
            "scope_name": paths["scope_name"],
        },
        "memories": [],
        "associations": [],
        "events": [],
        "provenance_retention": default_provenance_retention(),
    }


def _validate_store(store: Any) -> None:
    if not isinstance(store, dict):
        raise ValueError("memory store root must be an object")
    if not isinstance(store.get("memories"), list):
        raise ValueError("memory store 'memories' must be a list")
    if not isinstance(store.get("associations"), list):
        raise ValueError("memory store 'associations' must be a list")
    memory_ids = [item.get("id") for item in store["memories"] if isinstance(item, dict)]
    if len(memory_ids) != len(store["memories"]) or any(not mid for mid in memory_ids):
        raise ValueError("every memory must be an object with a non-empty id")
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError("memory ids must be unique")
    dedup_keys = [
        item.get("context", {}).get("dedup_key")
        for item in store["memories"]
        if item.get("context", {}).get("dedup_key")
    ]
    if len(dedup_keys) != len(set(dedup_keys)):
        raise ValueError("memory observation dedup keys must be unique")
    known_ids = set(memory_ids)
    association_ids: List[str] = []
    for association in store["associations"]:
        if not isinstance(association, dict) or not association.get("id"):
            raise ValueError("every association must have an id")
        association_ids.append(str(association["id"]))
        if association.get("from") not in known_ids or association.get("to") not in known_ids:
            raise ValueError("association endpoints must reference existing memories")
    if len(association_ids) != len(set(association_ids)):
        raise ValueError("association ids must be unique")
    if "events" in store and not isinstance(store["events"], list):
        raise ValueError("memory store 'events' must be a list")
    for event in store.get("events", []):
        if not isinstance(event, dict) or not event.get("type"):
            raise ValueError("every memory event must be an object with a type")
        if "occurrence_count" in event and (
            isinstance(event["occurrence_count"], bool)
            or not isinstance(event["occurrence_count"], int)
            or event["occurrence_count"] < 1
        ):
            raise ValueError("memory event occurrence_count must be a positive integer")
    retention = store.get("provenance_retention")
    if retention is not None:
        if not isinstance(retention, dict):
            raise ValueError("memory store 'provenance_retention' must be an object")
        validate_provenance_event_limit(
            retention.get("observation_event_limit", DEFAULT_PROVENANCE_EVENT_LIMIT)
        )
        for field in (
            "coalesced_batch_occurrences",
            "archived_event_records",
            "archived_batch_occurrences",
        ):
            value = retention.get(field, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(
                    f"memory provenance retention '{field}' must be a non-negative integer"
                )


def _normalize_store(store: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate older valid stores in memory without treating migration as learning."""
    store.setdefault("created_at", _now_iso())
    store.setdefault("updated_at", store["created_at"])
    store.setdefault("events", [])
    paths = get_memory_runtime_paths(create=True)
    for memory in store.get("memories", []):
        context = memory.setdefault("context", {})
        if not context.get("dedup_key"):
            continue
        if not context.get("evidence_status"):
            if context.get("graph_content_signature"):
                context["evidence_status"] = EVIDENCE_STATUS_ACTIVE
            else:
                # Pre-lifecycle analyzer records cannot be proven to describe
                # the current full source snapshot. Preserve them for audit,
                # but keep them out of semantic automation until re-observed.
                context["evidence_status"] = EVIDENCE_STATUS_STALE
                context.setdefault(
                    "migration_reason",
                    "legacy_evidence_missing_graph_content_signature",
                )
        context.setdefault("revision_count", 1)
        if not context.get("observation_namespace"):
            analyzer = str(context.get("source_analyzer", "unknown"))
            scan_scope = _legacy_scan_scope(
                context.get("scan_root", "."), paths.get("project_root")
            )
            context.setdefault("scan_scope", scan_scope)
            context["observation_namespace"] = f"xanalyze:{scan_scope}:{analyzer}"
    store["scope"] = {
        "scope_id": paths["scope_id"],
        "scope_kind": paths["scope_kind"],
        "scope_name": paths["scope_name"],
    }
    apply_provenance_retention(store)
    store["schema_version"] = SCHEMA_VERSION
    return store


def _load_store_unlocked(paths: Dict[str, Any]) -> Dict[str, Any]:
    store = read_json_unlocked(paths["store_path"], _default_store, _validate_store)
    return _normalize_store(store)


def _mutate_store(mutator: Callable[[Dict[str, Any]], Any]) -> Any:
    """Run one read-modify-write transaction under the project-scope lock."""
    with memory_runtime_lock() as paths:
        store = _load_store_unlocked(paths)
        result = mutator(store)
        store["updated_at"] = _now_iso()
        _validate_store(store)
        write_json_unlocked(paths["store_path"], store)
        return result


def load_store() -> Dict[str, Any]:
    """Load the current project-scoped store with corruption recovery."""
    with memory_runtime_lock() as paths:
        return _load_store_unlocked(paths)


def save_store(store: Dict[str, Any]) -> None:
    """Atomically replace the scoped store (compatibility API)."""
    replacement = copy.deepcopy(store)
    replacement["updated_at"] = _now_iso()
    _normalize_store(replacement)
    _validate_store(replacement)
    with memory_runtime_lock() as paths:
        write_json_unlocked(paths["store_path"], replacement)


def _new_memory_record(
    memory_type: str,
    content: str,
    source: str,
    importance: float,
    tags: Optional[List[str]],
    context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    now = _now_iso()
    return {
        "id": _generate_id(memory_type),
        "type": memory_type,
        "content": content,
        "source": source,
        "timestamp": now,
        "importance": max(0.0, min(1.0, importance)),
        "access_count": 0,
        "last_accessed": now,
        "tags": sorted(set(tags or [])),
        "context": context or {},
        "consolidated_into": None,
    }


def store_memory(
    memory_type: str,
    content: str,
    source: str = "manual",
    importance: float = 0.5,
    tags: Optional[List[str]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Simpan memori baru."""
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"Invalid memory type: {memory_type}. Must be one of {MEMORY_TYPES}")

    memory = _new_memory_record(memory_type, content, source, importance, tags, context)

    def append(store: Dict[str, Any]) -> Dict[str, Any]:
        store["memories"].append(memory)
        return copy.deepcopy(memory)

    return _mutate_store(append)


def upsert_memory_observations(
    observations: List[Dict[str, Any]],
    *,
    link_type: str = "temporal",
    link_strength: float = 0.6,
    reconcile_namespaces: Optional[List[str]] = None,
    stale_namespaces: Optional[List[str]] = None,
    current_graph_signature: Optional[str] = None,
    active_files: Optional[List[str]] = None,
    create_batch_links: bool = False,
    provenance_event_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Atomically reconcile one analyzer-evidence snapshot.

    ``dedup_key`` identifies the logical finding, while content/severity/hash
    changes create revisions on that same node. Findings absent from a fully
    observed namespace become resolved (or orphaned when their file vanished).
    Batch ordering is provenance and is recorded as an event; it is not a
    semantic association unless the compatibility flag ``create_batch_links``
    is explicitly enabled.
    """
    if link_type not in ASSOCIATION_TYPES:
        raise ValueError(f"Invalid association type: {link_type}")
    if provenance_event_limit is not None:
        validate_provenance_event_limit(provenance_event_limit)
    for observation in observations:
        if not observation.get("dedup_key"):
            raise ValueError("Every observation requires a dedup_key")
        if observation.get("memory_type", "episodic") not in MEMORY_TYPES:
            raise ValueError(f"Invalid memory type: {observation.get('memory_type')}")

    input_count = len(observations)
    normalized_active_files = (
        {str(path).replace("\\", "/") for path in active_files}
        if active_files is not None
        else None
    )
    namespace_set = {str(value) for value in (reconcile_namespaces or []) if value}
    stale_namespace_set = {
        str(value) for value in (stale_namespaces or []) if value
    } - namespace_set
    unique_by_key: Dict[str, Dict[str, Any]] = {}
    for observation in observations:
        dedup_key = str(observation["dedup_key"])
        if dedup_key not in unique_by_key:
            unique_by_key[dedup_key] = copy.deepcopy(observation)
            continue
        existing = unique_by_key[dedup_key]
        existing["tags"] = sorted(
            set(existing.get("tags", [])) | set(observation.get("tags", []))
        )
        existing["importance"] = max(
            float(existing.get("importance", 0.5)),
            float(observation.get("importance", 0.5)),
        )
        existing_context = existing.setdefault("context", {})
        existing_context.update(copy.deepcopy(observation.get("context") or {}))
    unique_observations = list(unique_by_key.values())

    def upsert(store: Dict[str, Any]) -> Dict[str, Any]:
        now = _now_iso()
        by_key = {
            memory.get("context", {}).get("dedup_key"): memory
            for memory in store["memories"]
            if memory.get("context", {}).get("dedup_key")
        }
        stored_ids: List[str] = []
        reused_ids: List[str] = []
        revised_ids: List[str] = []
        observed_ids: List[str] = []
        active_keys_by_namespace: Dict[str, set] = {
            namespace: set() for namespace in namespace_set
        }

        for observation in unique_observations:
            dedup_key = str(observation["dedup_key"])
            context = copy.deepcopy(observation.get("context") or {})
            context["dedup_key"] = dedup_key
            namespace = str(context.get("observation_namespace", ""))
            if namespace:
                active_keys_by_namespace.setdefault(namespace, set()).add(dedup_key)
            context["evidence_status"] = EVIDENCE_STATUS_ACTIVE
            if current_graph_signature:
                context["graph_content_signature"] = current_graph_signature
            existing = by_key.get(dedup_key)
            if existing is not None:
                existing_context = existing.setdefault("context", {})
                previous_revision = (
                    str(existing.get("content", "")),
                    str(existing_context.get("severity", "")),
                    str(existing_context.get("source_content_sha256", "")),
                    str(existing_context.get("graph_content_signature", "")),
                )
                previous_signature = existing_context.get("evidence_signature")
                if previous_signature:
                    existing_context.setdefault("first_evidence_signature", previous_signature)
                existing_context.update(context)
                current_signature = context.get("evidence_signature")
                if current_signature:
                    existing_context.setdefault("first_evidence_signature", current_signature)
                    existing_context["last_evidence_signature"] = current_signature
                existing_context.setdefault("first_observed_at", existing.get("timestamp", now))
                existing_context["last_observed_at"] = now
                existing_context["observation_count"] = int(
                    existing_context.get("observation_count", 1)
                ) + 1
                next_content = str(observation.get("content", existing.get("content", "")))
                next_revision = (
                    next_content,
                    str(context.get("severity", "")),
                    str(context.get("source_content_sha256", "")),
                    str(context.get("graph_content_signature", "")),
                )
                revision_count = int(existing_context.get("revision_count", 1))
                if next_revision != previous_revision:
                    revision_count += 1
                    revised_ids.append(existing["id"])
                existing_context["revision_count"] = revision_count
                existing_context["evidence_status"] = EVIDENCE_STATUS_ACTIVE
                existing_context.pop("resolved_at", None)
                existing_context.pop("resolved_graph_content_signature", None)
                existing_context.pop("resolution_reason", None)
                existing_context.pop("stale_at", None)
                existing_context.pop("stale_reason", None)
                existing_context.pop("stale_graph_content_signature", None)
                existing_context.pop("migration_reason", None)
                existing["content"] = next_content
                existing["source"] = str(observation.get("source", existing.get("source", "manual")))
                existing["importance"] = max(
                    float(existing.get("importance", 0.0)),
                    max(0.0, min(1.0, float(observation.get("importance", 0.5)))),
                )
                existing["tags"] = sorted(set(existing.get("tags", [])) | set(observation.get("tags", [])))
                if _get_status(existing) == MEMORY_STATUS_ARCHIVED:
                    existing["status"] = MEMORY_STATUS_ACTIVE
                    existing.pop("archived_at", None)
                    existing.pop("archive_reason", None)
                reused_ids.append(existing["id"])
                observed_ids.append(existing["id"])
                continue

            context.setdefault("first_observed_at", now)
            context["last_observed_at"] = now
            context["observation_count"] = 1
            context["revision_count"] = 1
            if context.get("evidence_signature"):
                context["first_evidence_signature"] = context["evidence_signature"]
                context["last_evidence_signature"] = context["evidence_signature"]
            memory = _new_memory_record(
                observation.get("memory_type", "episodic"),
                str(observation.get("content", "")),
                str(observation.get("source", "observation")),
                float(observation.get("importance", 0.5)),
                list(observation.get("tags", [])),
                context,
            )
            store["memories"].append(memory)
            by_key[dedup_key] = memory
            stored_ids.append(memory["id"])
            observed_ids.append(memory["id"])

        resolved_ids: List[str] = []
        orphaned_ids: List[str] = []
        for memory in store["memories"]:
            context = memory.get("context", {})
            namespace = str(context.get("observation_namespace", ""))
            if namespace not in namespace_set:
                continue
            dedup_key = str(context.get("dedup_key", ""))
            if dedup_key in active_keys_by_namespace.get(namespace, set()):
                continue
            if _get_evidence_status(memory) not in {
                EVIDENCE_STATUS_ACTIVE,
                EVIDENCE_STATUS_STALE,
            }:
                continue
            file_path = str(context.get("file", "")).replace("\\", "/")
            if (
                file_path
                and normalized_active_files is not None
                and file_path not in normalized_active_files
            ):
                evidence_status = EVIDENCE_STATUS_ORPHANED
                orphaned_ids.append(memory["id"])
                reason = "source_file_absent_from_current_snapshot"
            else:
                evidence_status = EVIDENCE_STATUS_RESOLVED
                resolved_ids.append(memory["id"])
                reason = "finding_absent_from_current_analyzer_snapshot"
            context["evidence_status"] = evidence_status
            context["resolved_at"] = now
            context["resolution_reason"] = reason
            if current_graph_signature:
                context["resolved_graph_content_signature"] = current_graph_signature

        stale_ids: List[str] = []
        for memory in store["memories"]:
            context = memory.get("context", {})
            namespace = str(context.get("observation_namespace", ""))
            if namespace not in stale_namespace_set:
                continue
            if _get_evidence_status(memory) != EVIDENCE_STATUS_ACTIVE:
                continue
            file_path = str(context.get("file", "")).replace("\\", "/")
            if (
                file_path
                and normalized_active_files is not None
                and file_path not in normalized_active_files
            ):
                context["evidence_status"] = EVIDENCE_STATUS_ORPHANED
                context["resolved_at"] = now
                context["resolution_reason"] = (
                    "source_file_absent_from_current_snapshot"
                )
                orphaned_ids.append(memory["id"])
                continue
            context["evidence_status"] = EVIDENCE_STATUS_STALE
            context["stale_at"] = now
            context["stale_reason"] = "analyzer_failed_on_current_snapshot"
            if current_graph_signature:
                context["stale_graph_content_signature"] = current_graph_signature
            stale_ids.append(memory["id"])

        existing_links = {
            (item.get("from"), item.get("to"), item.get("type"))
            for item in store["associations"]
        }
        associations_created = 0
        for from_id, to_id in (
            zip(observed_ids, observed_ids[1:]) if create_batch_links else []
        ):
            key = (from_id, to_id, link_type)
            if from_id == to_id or key in existing_links:
                continue
            store["associations"].append({
                "id": f"assoc_{uuid.uuid4().hex[:8]}",
                "from": from_id,
                "to": to_id,
                "type": link_type,
                "strength": max(0.0, min(1.0, link_strength)),
                "created_at": now,
                "metadata": {
                    "reason": "observation_batch_order",
                    "layer": "provenance",
                },
            })
            existing_links.add(key)
            associations_created += 1

        event = {
            "type": "observation_batch",
            "timestamp": now,
            "namespaces": sorted(namespace_set),
            "stale_namespaces": sorted(stale_namespace_set),
            "graph_content_signature": current_graph_signature,
            "observed_ids": list(observed_ids),
            "stored_ids": list(stored_ids),
            "reused_ids": list(reused_ids),
            "revised_ids": list(revised_ids),
            "resolved_ids": list(resolved_ids),
            "orphaned_ids": list(orphaned_ids),
            "stale_ids": list(stale_ids),
            "provenance_not_semantic_edge": not create_batch_links,
        }
        previous_event = store.get("events", [])[-1] if store.get("events") else None
        normalized_event = normalize_observation_event(event)
        event_will_coalesce = (
            isinstance(previous_event, dict)
            and previous_event.get("type") == "observation_batch"
            and normalize_observation_event(previous_event).get("event_signature")
            == normalized_event.get("event_signature")
        )
        store.setdefault("events", []).append(normalized_event)
        retention_transition = apply_provenance_retention(
            store, provenance_event_limit
        )
        retention_snapshot = provenance_retention_snapshot(store)

        return {
            "status": "reconciled",
            "stored_count": len(stored_ids),
            "reused_count": len(reused_ids),
            "updated_count": len(reused_ids),
            "revised_count": len(revised_ids),
            "resolved_count": len(resolved_ids),
            "orphaned_count": len(orphaned_ids),
            "stale_count": len(stale_ids),
            "stored_ids": stored_ids,
            "reused_ids": reused_ids,
            "revised_ids": revised_ids,
            "resolved_ids": resolved_ids,
            "orphaned_ids": orphaned_ids,
            "stale_ids": stale_ids,
            "observed_ids": observed_ids,
            "associations_created": associations_created,
            "provenance_events_recorded": 1,
            "provenance_event_records_added": 0 if event_will_coalesce else 1,
            "provenance_event_coalesced": event_will_coalesce,
            "provenance_event_records_compacted": retention_transition[
                "compacted_event_records"
            ],
            "provenance_batch_occurrences_compacted": retention_transition[
                "compacted_batch_occurrences"
            ],
            "provenance_retention": retention_snapshot,
            "batch_order_is_semantic_edge": create_batch_links,
            "input_observation_count": input_count,
            "unique_observation_count": len(unique_observations),
            "duplicate_input_count": input_count - len(unique_observations),
        }

    return _mutate_store(upsert)


def store_association(
    from_id: str,
    to_id: str,
    assoc_type: str,
    strength: float = 0.5,
    metadata: Optional[Dict[str, Any]] = None,
    safe_mode: bool = True,
) -> Dict[str, Any]:
    """Simpan asosiasi antara dua memori."""
    if assoc_type not in ASSOCIATION_TYPES:
        raise ValueError(f"Invalid association type: {assoc_type}")

    association = {
        "id": f"assoc_{uuid.uuid4().hex[:8]}",
        "from": from_id,
        "to": to_id,
        "type": assoc_type,
        "strength": max(0.0, min(1.0, strength)),
        "created_at": _now_iso(),
        "metadata": metadata or {},
    }

    def append(store: Dict[str, Any]) -> Dict[str, Any]:
        memory_ids = {m["id"] for m in store["memories"]}
        if from_id not in memory_ids:
            raise ValueError(f"Memory not found: {from_id}")
        if to_id not in memory_ids:
            raise ValueError(f"Memory not found: {to_id}")
        if (
            safe_mode
            and assoc_type in REASONING_EDGE_TYPES
            and would_create_reasoning_cycle(from_id, to_id, store)
        ):
            raise ReasoningCycleRejectedError(from_id, to_id, assoc_type)
        store["associations"].append(association)
        return copy.deepcopy(association)

    return _mutate_store(append)


def consolidate_memories(
    source_ids: List[str],
    content: str,
    tags: Optional[List[str]] = None,
    importance: float = 0.9,
    pattern_type: str = "correlation",
    confidence: float = 0.8,
) -> Dict[str, Any]:
    """
    Konsolidasi beberapa memori menjadi satu memori semantik baru.
    Ini adalah operasi COLIMIT dalam istilah HoTT.

    Args:
        source_ids: List of memory IDs to consolidate
        content: Consolidated content (the abstraction)
        tags: Tags for the new semantic memory
        importance: Importance of the consolidated memory
        pattern_type: Type of pattern detected
        confidence: Confidence in the consolidation

    Returns:
        Dict with new semantic memory and consolidation info
    """
    if not source_ids:
        raise ValueError("At least one source memory is required")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Source memory IDs must be unique")

    batch_id = f"batch_{uuid.uuid4().hex[:6]}"
    new_semantic = _new_memory_record(
        "semantic",
        content,
        f"consolidation:{','.join(source_ids)}",
        importance,
        (tags or []) + ["consolidated"],
        {
            "consolidated_from": source_ids,
            "pattern_type": pattern_type,
            "confidence": confidence,
            "consolidation_batch": batch_id,
        },
    )

    def consolidate(store: Dict[str, Any]) -> Dict[str, Any]:
        memory_ids = {m["id"] for m in store["memories"]}
        for source_id in source_ids:
            if source_id not in memory_ids:
                raise ValueError(f"Memory not found: {source_id}")
        store["memories"].append(new_semantic)
        for source_id in source_ids:
            store["associations"].append({
                "id": f"assoc_{uuid.uuid4().hex[:8]}",
                "from": source_id,
                "to": new_semantic["id"],
                "type": "consolidation",
                "strength": max(0.0, min(1.0, confidence)),
                "created_at": _now_iso(),
                "metadata": {
                    "reason": "colimit_construction",
                    "consolidation_batch": batch_id,
                },
            })
        for memory in store["memories"]:
            if memory["id"] in source_ids:
                memory["consolidated_into"] = new_semantic["id"]
        store.setdefault("events", []).append({
            "type": "consolidation",
            "batch_id": batch_id,
            "timestamp": _now_iso(),
            "source_ids": list(source_ids),
            "target_id": new_semantic["id"],
            "content_summary": content[:200],
        })
        return {
            "new_semantic_memory": copy.deepcopy(new_semantic),
            "consolidated_from": list(source_ids),
            "associations_created": len(source_ids),
            "consolidation_batch": batch_id,
            "transactional": True,
        }

    result = _mutate_store(consolidate)
    try:
        _log_consolidation(batch_id, source_ids, new_semantic["id"], content)
        result["external_audit_log"] = "written"
    except Exception as exc:
        # The authoritative event is already inside the atomic store transaction.
        result["external_audit_log"] = "write_failed"
        result["external_audit_error"] = str(exc)
    return result


def _log_consolidation(
    batch_id: str,
    source_ids: List[str],
    target_id: str,
    content: str,
) -> None:
    """Write a derived audit view; authoritative event remains in the store."""
    def validate_log(value: Any) -> None:
        if not isinstance(value, list):
            raise ValueError("consolidation log must be a list")

    with memory_runtime_lock() as paths:
        log = read_json_unlocked(paths["consolidation_log_path"], list, validate_log)
        log.append({
            "batch_id": batch_id,
            "timestamp": _now_iso(),
            "source_ids": source_ids,
            "target_id": target_id,
            "content_summary": content[:200],
        })
        write_json_unlocked(paths["consolidation_log_path"], log)


def recall_memories(
    query: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    min_importance: float = 0.0,
    limit: int = 20,
    include_archived: bool = False,
    include_historical_evidence: bool = False,
    cache_mode: str = "auto",
) -> List[Dict[str, Any]]:
    """
    Recall memori berdasarkan filter.
    Default: hanya active memories (exclude archived).
    Ini adalah operasi READ — tidak mengubah access_count.
    Untuk access tracking, gunakan access_memory().
    """
    projection = build_memory_recall_projection(cache_mode=cache_mode)
    return recall_from_projection(
        projection,
        query=query,
        memory_type=memory_type,
        tags=tags,
        min_importance=min_importance,
        limit=limit,
        include_archived=include_archived,
        include_historical_evidence=include_historical_evidence,
    )


def build_memory_recall_projection(cache_mode: str = "auto") -> Dict[str, Any]:
    """Load or reuse one deterministic projection of the canonical store."""
    with memory_runtime_lock() as paths:
        return load_or_build_recall_projection_unlocked(
            paths,
            lambda: _load_store_unlocked(paths),
            mode=cache_mode,
        )


def get_memory_recall_cache_status() -> Dict[str, Any]:
    """Inspect whether the derived recall cache matches canonical state."""
    with memory_runtime_lock() as paths:
        return get_recall_cache_status_unlocked(paths)


def clear_memory_recall_cache() -> Dict[str, Any]:
    """Remove only derived recall state; canonical memory is untouched."""
    with memory_runtime_lock() as paths:
        return clear_recall_cache_unlocked(paths)


def refresh_memory_recall_cache() -> Dict[str, Any]:
    """Rebuild the recall cache from one validated canonical snapshot."""
    return build_memory_recall_projection(cache_mode="refresh").get("cache", {})


def rank_memory_recall_projection(
    projection: Dict[str, Any],
    query: Optional[str] = None,
    target_files: Optional[List[str]] = None,
    target_hops: Optional[Dict[str, int]] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    min_importance: float = 0.0,
    include_archived: bool = False,
    include_historical_evidence: bool = False,
) -> Dict[str, Any]:
    """Expose multi-signal ranking over an already loaded memory snapshot."""
    return rank_recall_projection(
        projection,
        query=query,
        target_files=target_files,
        target_hops=target_hops,
        memory_type=memory_type,
        tags=tags,
        min_importance=min_importance,
        include_archived=include_archived,
        include_historical_evidence=include_historical_evidence,
    )


def access_memory(memory_id: str) -> Optional[Dict[str, Any]]:
    """Tandai memori sebagai diakses (update access_count dan last_accessed)."""
    def access(store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for memory in store["memories"]:
            if memory["id"] == memory_id:
                memory["access_count"] = memory.get("access_count", 0) + 1
                memory["last_accessed"] = _now_iso()
                return copy.deepcopy(memory)
        return None

    return _mutate_store(access)


def get_memory(memory_id: str) -> Optional[Dict[str, Any]]:
    """Ambil satu memori by ID."""
    store = load_store()
    for memory in store["memories"]:
        if memory["id"] == memory_id:
            return memory
    return None


def get_associations_for(memory_id: str) -> List[Dict[str, Any]]:
    """Ambil semua asosiasi yang melibatkan memori tertentu."""
    store = load_store()
    return [
        a for a in store["associations"]
        if a.get("from") == memory_id or a.get("to") == memory_id
    ]


def get_memory_stats() -> Dict[str, Any]:
    """Statistik memory store."""
    store = load_store()
    memories = store.get("memories", [])
    associations = store.get("associations", [])

    by_type = {}
    for m in memories:
        t = m.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    by_assoc_type = {}
    for a in associations:
        t = a.get("type", "unknown")
        by_assoc_type[t] = by_assoc_type.get(t, 0) + 1

    active_count = sum(1 for memory in memories if _get_status(memory) == MEMORY_STATUS_ACTIVE)
    archived_count = len(memories) - active_count
    by_evidence_status: Dict[str, int] = {}
    analyzer_evidence_count = 0
    for memory in memories:
        if memory.get("context", {}).get("dedup_key"):
            analyzer_evidence_count += 1
        status = _get_evidence_status(memory)
        by_evidence_status[status] = by_evidence_status.get(status, 0) + 1
    provenance_association_count = sum(
        1 for association in associations
        if association.get("metadata", {}).get("layer") == "provenance"
        or association.get("metadata", {}).get("reason") == "observation_batch_order"
    )
    return {
        "total_memories": len(memories),
        "active_memories": active_count,
        "archived_memories": archived_count,
        "total_associations": len(associations),
        "by_type": by_type,
        "by_association_type": by_assoc_type,
        "analyzer_evidence_memories": analyzer_evidence_count,
        "by_evidence_status": by_evidence_status,
        "provenance_associations": provenance_association_count,
        "semantic_associations": len(associations) - provenance_association_count,
        "provenance_retention": provenance_retention_snapshot(store),
        "schema_version": store.get("schema_version", "unknown"),
        "updated_at": store.get("updated_at", "unknown"),
        "runtime": memory_runtime_provenance(),
    }


def consolidate_by_tag(
    tag: str,
    content: Optional[str] = None,
    importance: float = 0.9,
    memory_type: str = "episodic",
    only_unconsolidated: bool = True,
) -> Dict[str, Any]:
    """
    Konsolidasi semua memori dengan tag tertentu menjadi satu semantic memory.
    
    Args:
        tag: Tag untuk filter memories
        content: Content untuk semantic memory baru. Jika None, auto-generate.
        importance: Importance score
        memory_type: Type memori yang di-filter (default: episodic)
        only_unconsolidated: Hanya proses yang belum di-consolidate
    """
    store = load_store()

    # Filter memories by tag
    candidates = [
        m for m in store["memories"]
        if m.get("type") == memory_type
        and is_semantically_current_memory(m)
        and tag in m.get("tags", [])
        and (not only_unconsolidated or m.get("consolidated_into") is None)
    ]

    if not candidates:
        return {
            "status": "no_candidates",
            "tag": tag,
            "message": f"No {memory_type} memories with tag '{tag}' found",
        }

    # Auto-generate content jika tidak disediakan
    if content is None:
        finding_types = set()
        files = set()
        content_previews = []
        for m in candidates:
            ctx = m.get("context", {})
            if ctx.get("finding_type"):
                finding_types.add(ctx["finding_type"])
            if ctx.get("file"):
                files.add(ctx["file"])
            # Fallback: ambil preview dari content jika context kosong
            if not ctx.get("finding_type") and not ctx.get("file"):
                content_previews.append(m.get("content", "")[:80])

        details = []
        if finding_types:
            details.append(f"Finding types: {', '.join(sorted(finding_types))}")
        if files:
            details.append(f"Files: {', '.join(sorted(files))}")
        if content_previews:
            details.append(f"Items: {'; '.join(content_previews[:3])}")

        detail_str = f" ({'. '.join(details)}.)" if details else ""
        content = (
            f"Consolidated pattern from {len(candidates)} memories tagged '{tag}'.{detail_str}"
        )

    # Consolidate
    source_ids = [m["id"] for m in candidates]
    result = consolidate_memories(
        source_ids=source_ids,
        content=content,
        tags=[tag, "auto_consolidated"],
        importance=importance,
    )
    result["status"] = "consolidated"
    result["tag"] = tag
    result["candidates_found"] = len(candidates)
    return result


def consolidate_by_tag_auto(
    min_group_size: int = 3,
    importance: float = 0.9,
) -> Dict[str, Any]:
    """
    Otomatis detect semua tag groups dan consolidate yang memenuhi threshold.
    
    Args:
        min_group_size: Minimum jumlah memories per tag untuk trigger consolidation
        importance: Importance score untuk semantic memories baru
    """
    store = load_store()

    # Group unconsolidated episodic by tag
    tag_groups: Dict[str, List[str]] = {}
    for m in store["memories"]:
        if m.get("type") != "episodic":
            continue
        if not is_semantically_current_memory(m):
            continue
        if m.get("consolidated_into") is not None:
            continue
        for tag in m.get("tags", []):
            # Skip generic tags
            if tag in ("consolidated", "auto_consolidated"):
                continue
            if tag not in tag_groups:
                tag_groups[tag] = []
            tag_groups[tag].append(m["id"])

    # Filter groups by threshold
    eligible_groups = {
        tag: ids for tag, ids in tag_groups.items()
        if len(ids) >= min_group_size
    }

    if not eligible_groups:
        return {
            "status": "no_eligible_groups",
            "message": f"No tag groups with >= {min_group_size} unconsolidated memories",
            "tag_groups_found": {tag: len(ids) for tag, ids in tag_groups.items()},
        }

    # Consolidate each eligible group
    results = []
    for tag, ids in sorted(eligible_groups.items()):
        result = consolidate_by_tag(
            tag=tag,
            importance=importance,
        )
        if result.get("status") == "consolidated" or "new_semantic_memory" in result:
            results.append({
                "tag": tag,
                "memories_consolidated": len(ids),
                "new_semantic_id": result.get("new_semantic_memory", {}).get("id"),
            })

    return {
        "status": "consolidated",
        "groups_consolidated": len(results),
        "results": results,
        "skipped_groups": {
            tag: len(ids) for tag, ids in tag_groups.items()
            if tag not in eligible_groups
        },
    }


def get_unconsolidated_by_tag() -> Dict[str, Any]:
    """
    Dapatkan ringkasan unconsolidated episodic memories grouped by tag.
    Berguna untuk exploration sebelum consolidation.
    """
    store = load_store()

    tag_groups: Dict[str, List[Dict[str, Any]]] = {}
    unconsolidated_count = 0

    for m in store["memories"]:
        if m.get("type") != "episodic":
            continue
        if not is_semantically_current_memory(m):
            continue
        if m.get("consolidated_into") is not None:
            continue
        unconsolidated_count += 1
        for tag in m.get("tags", []):
            if tag not in tag_groups:
                tag_groups[tag] = []
            tag_groups[tag].append({
                "id": m["id"],
                "content_preview": m.get("content", "")[:100],
                "importance": m.get("importance", 0.5),
            })

    return {
        "unconsolidated_count": unconsolidated_count,
        "tag_groups": {
            tag: {
                "count": len(mems),
                "memories": mems,
            }
            for tag, mems in sorted(tag_groups.items())
        },
    }


def archive_memory(memory_id: str, reason: str = "consolidated") -> Optional[Dict[str, Any]]:
    """
    Archive satu memory (quotient forgetting).
    Memory tidak dihapus, hanya ditandai sebagai archived.
    """
    def archive(store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for memory in store["memories"]:
            if memory["id"] == memory_id:
                memory["status"] = MEMORY_STATUS_ARCHIVED
                memory["archived_at"] = _now_iso()
                memory["archive_reason"] = reason
                return copy.deepcopy(memory)
        return None

    return _mutate_store(archive)


def restore_memory(memory_id: str) -> Optional[Dict[str, Any]]:
    """Restore satu archived memory kembali aktif."""
    def restore(store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for memory in store["memories"]:
            if memory["id"] == memory_id:
                memory["status"] = MEMORY_STATUS_ACTIVE
                memory.pop("archived_at", None)
                memory.pop("archive_reason", None)
                return copy.deepcopy(memory)
        return None

    return _mutate_store(restore)


def restore_all_archived() -> Dict[str, Any]:
    """Restore semua archived memories."""
    def restore(store: Dict[str, Any]) -> Dict[str, Any]:
        restored_count = 0
        for memory in store["memories"]:
            if _get_status(memory) == MEMORY_STATUS_ARCHIVED:
                memory["status"] = MEMORY_STATUS_ACTIVE
                memory.pop("archived_at", None)
                memory.pop("archive_reason", None)
                restored_count += 1
        return {"restored_count": restored_count}

    return _mutate_store(restore)


def get_compact_candidates(
    only_consolidated: bool = True,
    memory_type: str = "episodic",
) -> List[Dict[str, Any]]:
    """
    Dapatkan kandidat untuk compact:
    - Memory yang sudah consolidated (consolidated_into != null)
    - Memory dengan status aktif
    - Memory dengan tipe tertentu (default: episodic)
    """
    store = load_store()
    candidates = []

    for memory in store["memories"]:
        if _get_status(memory) != MEMORY_STATUS_ACTIVE:
            continue
        if memory.get("type") != memory_type:
            continue
        if only_consolidated and memory.get("consolidated_into") is None:
            continue
        candidates.append(memory)

    return candidates


def compact_memories(
    only_consolidated: bool = True,
    memory_type: str = "episodic",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Compact memories: archive yang sudah consolidated.
    
    Args:
        only_consolidated: Hanya archive yang sudah di-consolidate
        memory_type: Tipe memory yang di-compact
        dry_run: Jika True, hanya preview tanpa eksekusi
    """
    if dry_run:
        candidates = get_compact_candidates(only_consolidated, memory_type)
        return {
            "status": "dry_run",
            "candidates_count": len(candidates),
            "candidates": [
                {
                    "id": m["id"],
                    "type": m.get("type"),
                    "content_preview": m.get("content", "")[:80],
                    "consolidated_into": m.get("consolidated_into"),
                }
                for m in candidates
            ],
        }

    def compact(store: Dict[str, Any]) -> Dict[str, Any]:
        archived_ids: List[str] = []
        now = _now_iso()
        for memory in store["memories"]:
            if _get_status(memory) != MEMORY_STATUS_ACTIVE:
                continue
            if memory.get("type") != memory_type:
                continue
            if only_consolidated and memory.get("consolidated_into") is None:
                continue
            memory["status"] = MEMORY_STATUS_ARCHIVED
            memory["archived_at"] = now
            memory["archive_reason"] = "quotient_forgetting"
            archived_ids.append(memory["id"])
        return {
            "status": "compacted",
            "archived_count": len(archived_ids),
            "archived_ids": archived_ids,
            "memory_type": memory_type,
            "transactional": True,
        }

    return _mutate_store(compact)


def get_archive_stats() -> Dict[str, Any]:
    """Statistik archived vs active memories."""
    store = load_store()
    active_count = 0
    archived_count = 0
    archived_by_type: Dict[str, int] = {}

    for memory in store["memories"]:
        status = _get_status(memory)
        if status == MEMORY_STATUS_ACTIVE:
            active_count += 1
        elif status == MEMORY_STATUS_ARCHIVED:
            archived_count += 1
            mtype = memory.get("type", "unknown")
            archived_by_type[mtype] = archived_by_type.get(mtype, 0) + 1

    return {
        "total_memories": active_count + archived_count,
        "active_count": active_count,
        "archived_count": archived_count,
        "archived_by_type": archived_by_type,
    }


def _build_reasoning_adjacency(store: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build adjacency hanya untuk reasoning edges (inferential, causal)."""
    adj: Dict[str, List[str]] = {}
    active_ids = {
        m["id"] for m in store.get("memories", [])
        if _get_status(m) == MEMORY_STATUS_ACTIVE
    }
    for assoc in store.get("associations", []):
        if assoc.get("type") in REASONING_EDGE_TYPES:
            src, tgt = assoc.get("from"), assoc.get("to")
            if src in active_ids and tgt in active_ids and src and tgt:
                adj.setdefault(src, []).append(tgt)
    return adj


def would_create_reasoning_cycle(
    from_id: str,
    to_id: str,
    store: Dict[str, Any],
) -> bool:
    """
    Cek apakah menambah edge from_id -> to_id akan membuat reasoning cycle.
    Menggunakan DFS: jika sudah ada path dari to_id ke from_id via reasoning edges,
    maka menambah from_id -> to_id akan membentuk cycle.
    """
    adj = _build_reasoning_adjacency(store)

    # DFS dari to_id, cek apakah bisa reach from_id
    visited = set()
    stack = [to_id]
    while stack:
        node = stack.pop()
        if node == from_id:
            return True  # Cycle akan terbentuk
        if node in visited:
            continue
        visited.add(node)
        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                stack.append(neighbor)
    return False


def bridge_memories(
    from_id: str,
    to_id: str,
    assoc_type: str = "semantic",
    strength: float = 0.7,
    metadata: Optional[Dict[str, Any]] = None,
    safe_mode: bool = True,
) -> Dict[str, Any]:
    """
    Buat asosiasi tingkat tinggi antara dua memories (biasanya semantic).
    Ini adalah "lem level-2" yang menghubungkan pulau-pulau pengetahuan.
    """
    if assoc_type not in ASSOCIATION_TYPES:
        return {"status": "error", "error": f"Invalid association type: {assoc_type}"}

    def bridge(store: Dict[str, Any]) -> Dict[str, Any]:
        memory_ids = {m["id"] for m in store.get("memories", [])}
        if from_id not in memory_ids:
            return {"status": "error", "error": f"Memory not found: {from_id}"}
        if to_id not in memory_ids:
            return {"status": "error", "error": f"Memory not found: {to_id}"}
        if from_id == to_id:
            return {"status": "error", "error": "Cannot bridge memory to itself"}
        if safe_mode and assoc_type in REASONING_EDGE_TYPES and would_create_reasoning_cycle(
            from_id, to_id, store
        ):
            return {
                "status": "rejected",
                "reason": "would_create_reasoning_cycle",
                "from_id": from_id,
                "to_id": to_id,
                "assoc_type": assoc_type,
                "message": (
                    f"Bridge {from_id} --{assoc_type}--> {to_id} would create "
                    f"a directed reasoning cycle. Use assoc_type='semantic' or "
                    f"reverse the direction. β₁_reasoning is reported separately "
                    f"as an undirected multigraph cycle rank."
                ),
            }
        association = {
            "id": f"assoc_{uuid.uuid4().hex[:8]}",
            "from": from_id,
            "to": to_id,
            "type": assoc_type,
            "strength": max(0.0, min(1.0, strength)),
            "created_at": _now_iso(),
            "metadata": metadata or {"reason": "semantic_bridging"},
        }
        store["associations"].append(association)
        return {
            "status": "bridged",
            "association": copy.deepcopy(association),
            "from_id": from_id,
            "to_id": to_id,
            "assoc_type": assoc_type,
            "safe_mode": safe_mode,
            "transactional": True,
        }

    return _mutate_store(bridge)


def get_bridge_candidates(
    memory_type: str = "semantic",
    min_shared_tags: int = 1,
) -> Dict[str, Any]:
    """
    Lihat kandidat bridge: pairs of memories yang share tags.
    Berguna untuk exploration sebelum bridge_auto.
    """
    store = load_store()

    candidates = [
        m for m in store.get("memories", [])
        if m.get("type") == memory_type
        and _get_status(m) == MEMORY_STATUS_ACTIVE
    ]

    # Existing pairs (untuk avoid duplicate)
    existing_pairs = set()
    for a in store.get("associations", []):
        existing_pairs.add((a.get("from"), a.get("to")))
        existing_pairs.add((a.get("to"), a.get("from")))

    # Find pairs with shared tags
    bridge_candidates = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            m1, m2 = candidates[i], candidates[j]
            shared_tags = set(m1.get("tags", [])) & set(m2.get("tags", []))
            # Exclude generic tags
            shared_tags -= {"consolidated", "auto_consolidated", "pattern"}

            if len(shared_tags) >= min_shared_tags:
                pair = (m1["id"], m2["id"])
                already_bridged = pair in existing_pairs
                bridge_candidates.append({
                    "from_id": m1["id"],
                    "to_id": m2["id"],
                    "from_content_preview": m1.get("content", "")[:60],
                    "to_content_preview": m2.get("content", "")[:60],
                    "shared_tags": sorted(shared_tags),
                    "already_bridged": already_bridged,
                })

    return {
        "candidates_count": len(bridge_candidates),
        "new_bridges_possible": sum(1 for c in bridge_candidates if not c["already_bridged"]),
        "candidates": bridge_candidates,
    }


def bridge_auto(
    min_shared_tags: int = 1,
    memory_type: str = "semantic",
    assoc_type: str = "semantic",
    safe_mode: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Otomatis hubungkan memories yang share tags.
    Membangun "knowledge graph" tingkat tinggi.
    """
    store = load_store()

    candidates = [
        m for m in store.get("memories", [])
        if m.get("type") == memory_type
        and _get_status(m) == MEMORY_STATUS_ACTIVE
    ]

    # Existing pairs
    existing_pairs = set()
    for a in store.get("associations", []):
        existing_pairs.add((a.get("from"), a.get("to")))
        existing_pairs.add((a.get("to"), a.get("from")))

    # Find eligible pairs
    bridges_to_create = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            m1, m2 = candidates[i], candidates[j]
            shared_tags = set(m1.get("tags", [])) & set(m2.get("tags", []))
            shared_tags -= {"consolidated", "auto_consolidated", "pattern"}

            if len(shared_tags) >= min_shared_tags:
                if (m1["id"], m2["id"]) in existing_pairs:
                    continue

                # Tentukan arah: dari importance rendah ke tinggi (spesifik → umum)
                if m1.get("importance", 0.5) <= m2.get("importance", 0.5):
                    from_m, to_m = m1, m2
                else:
                    from_m, to_m = m2, m1

                bridges_to_create.append({
                    "from_id": from_m["id"],
                    "to_id": to_m["id"],
                    "shared_tags": sorted(shared_tags),
                    "from_importance": from_m.get("importance", 0.5),
                    "to_importance": to_m.get("importance", 0.5),
                })

    if dry_run:
        return {
            "status": "dry_run",
            "bridges_count": len(bridges_to_create),
            "bridges": bridges_to_create,
            "assoc_type": assoc_type,
            "safe_mode": safe_mode,
        }

    # Execute bridges dengan safety check
    created = []
    rejected = []
    for bridge in bridges_to_create:
        result = bridge_memories(
            from_id=bridge["from_id"],
            to_id=bridge["to_id"],
            assoc_type=assoc_type,
            strength=0.7,
            metadata={
                "shared_tags": bridge["shared_tags"],
                "reason": "auto_bridging",
                "direction": "specific_to_general",
            },
            safe_mode=safe_mode,
        )
        if result.get("status") == "bridged":
            created.append(result)
        elif result.get("status") == "rejected":
            rejected.append(result)

    return {
        "status": "bridged",
        "bridges_created": len(created),
        "bridges_rejected": len(rejected),
        "rejected_reasons": [r.get("reason") for r in rejected],
        "created_bridges": [
            {"from": c["from_id"], "to": c["to_id"], "type": c["assoc_type"]}
            for c in created
        ],
    }
