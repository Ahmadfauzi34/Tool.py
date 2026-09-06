"""Bounded observation provenance for the project-scoped memory store.

The hot journal retains exact recent observation-batch records. Consecutive
identical batches are run-length encoded, while records older than the policy
limit become aggregate counters plus a chained digest. The checkpoint preserves
counts and a sequence commitment, not reconstructable detail or external
tamper-proof storage.
"""

import copy
import datetime
import hashlib
import json
from typing import Any, Dict, List, Optional


PROVENANCE_RETENTION_SCHEMA_VERSION = "bounded-observation-provenance-v1"
DEFAULT_PROVENANCE_EVENT_LIMIT = 128
DEFAULT_ARCHIVED_NAMESPACE_LIMIT = 256
PROVENANCE_NAMESPACE_OVERFLOW_KEY = "__other__"
PROVENANCE_LIFECYCLE_ID_FIELDS = (
    "observed_ids",
    "stored_ids",
    "reused_ids",
    "revised_ids",
    "resolved_ids",
    "orphaned_ids",
    "stale_ids",
)
_SIGNATURE_EXCLUDED_FIELDS = {
    "timestamp",
    "first_timestamp",
    "last_timestamp",
    "occurrence_count",
    "event_signature",
}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def default_provenance_retention(
    event_limit: int = DEFAULT_PROVENANCE_EVENT_LIMIT,
) -> Dict[str, Any]:
    return {
        "schema_version": PROVENANCE_RETENTION_SCHEMA_VERSION,
        "observation_event_limit": event_limit,
        "archived_namespace_limit": DEFAULT_ARCHIVED_NAMESPACE_LIMIT,
        "coalesced_batch_occurrences": 0,
        "archived_event_records": 0,
        "archived_batch_occurrences": 0,
        "archived_namespace_overflow_occurrences": 0,
        "archived_by_namespace": {},
        "archived_lifecycle_totals": {
            field.removesuffix("_ids"): 0
            for field in PROVENANCE_LIFECYCLE_ID_FIELDS
        },
        "checkpoint_digest": None,
        "digest_algorithm": "sha256-chain-v1",
        "counts_preserved": True,
        "archived_detail_recoverable": False,
    }


def validate_provenance_event_limit(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("provenance observation event limit must be an integer")
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "provenance observation event limit must be an integer"
        ) from exc
    if limit < 1:
        raise ValueError("provenance observation event limit must be at least 1")
    return limit


def _non_negative_integer(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _event_occurrence_count(event: Dict[str, Any]) -> int:
    return max(1, _non_negative_integer(event.get("occurrence_count", 1), 1))


def _observation_event_signature(event: Dict[str, Any]) -> str:
    semantic_payload = {
        key: value
        for key, value in event.items()
        if key not in _SIGNATURE_EXCLUDED_FIELDS
    }
    canonical = json.dumps(
        semantic_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_observation_event(event: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(event)
    timestamp = str(
        normalized.get("timestamp")
        or normalized.get("first_timestamp")
        or normalized.get("last_timestamp")
        or _now_iso()
    )
    normalized["timestamp"] = str(normalized.get("first_timestamp") or timestamp)
    normalized["first_timestamp"] = str(
        normalized.get("first_timestamp") or timestamp
    )
    normalized["last_timestamp"] = str(normalized.get("last_timestamp") or timestamp)
    normalized["occurrence_count"] = _event_occurrence_count(normalized)
    normalized["event_signature"] = _observation_event_signature(normalized)
    return normalized


def _normalize_provenance_retention(store: Dict[str, Any]) -> Dict[str, Any]:
    raw = store.get("provenance_retention")
    retention = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    limit = validate_provenance_event_limit(
        retention.get("observation_event_limit", DEFAULT_PROVENANCE_EVENT_LIMIT)
    )
    namespace_limit = max(
        1,
        _non_negative_integer(
            retention.get(
                "archived_namespace_limit", DEFAULT_ARCHIVED_NAMESPACE_LIMIT
            ),
            DEFAULT_ARCHIVED_NAMESPACE_LIMIT,
        ),
    )
    defaults = default_provenance_retention(limit)
    for key, value in defaults.items():
        retention.setdefault(key, copy.deepcopy(value))
    retention["schema_version"] = PROVENANCE_RETENTION_SCHEMA_VERSION
    retention["observation_event_limit"] = limit
    retention["archived_namespace_limit"] = namespace_limit
    for field in (
        "coalesced_batch_occurrences",
        "archived_event_records",
        "archived_batch_occurrences",
        "archived_namespace_overflow_occurrences",
    ):
        retention[field] = _non_negative_integer(retention.get(field, 0))

    archived_by_namespace = retention.get("archived_by_namespace")
    normalized_by_namespace: Dict[str, int] = {}
    overflow = retention["archived_namespace_overflow_occurrences"]
    items = sorted(
        (
            archived_by_namespace.items()
            if isinstance(archived_by_namespace, dict)
            else []
        ),
        key=lambda item: str(item[0]),
    )
    for namespace, count in items:
        normalized_count = _non_negative_integer(count)
        key = str(namespace)
        if key == PROVENANCE_NAMESPACE_OVERFLOW_KEY:
            overflow += normalized_count
        elif len(normalized_by_namespace) < namespace_limit:
            normalized_by_namespace[key] = normalized_count
        else:
            overflow += normalized_count
    retention["archived_by_namespace"] = normalized_by_namespace
    retention["archived_namespace_overflow_occurrences"] = overflow

    lifecycle = retention.get("archived_lifecycle_totals")
    normalized_lifecycle: Dict[str, int] = {}
    for field in PROVENANCE_LIFECYCLE_ID_FIELDS:
        key = field.removesuffix("_ids")
        value = lifecycle.get(key, 0) if isinstance(lifecycle, dict) else 0
        normalized_lifecycle[key] = _non_negative_integer(value)
    retention["archived_lifecycle_totals"] = normalized_lifecycle
    retention["counts_preserved"] = True
    retention["archived_detail_recoverable"] = False
    store["provenance_retention"] = retention
    return retention


def _chain_archived_event_digest(
    previous_digest: Optional[str], event: Dict[str, Any]
) -> str:
    canonical = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    previous = str(previous_digest or "")
    digest = hashlib.sha256(f"{previous}\n{canonical}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _increment_archived_namespace(
    retention: Dict[str, Any], namespace: str, occurrences: int
) -> None:
    counts = retention["archived_by_namespace"]
    key = str(namespace)
    if key in counts:
        counts[key] += occurrences
        return
    if len(counts) < int(retention["archived_namespace_limit"]):
        counts[key] = occurrences
        return
    retention["archived_namespace_overflow_occurrences"] += occurrences


def _archive_observation_event(
    retention: Dict[str, Any], event: Dict[str, Any]
) -> None:
    occurrences = _event_occurrence_count(event)
    retention["archived_event_records"] += 1
    retention["archived_batch_occurrences"] += occurrences
    namespaces = {
        str(namespace)
        for field in ("namespaces", "stale_namespaces")
        for namespace in (
            event.get(field, []) if isinstance(event.get(field, []), list) else []
        )
    }
    for namespace in sorted(namespaces):
        _increment_archived_namespace(retention, namespace, occurrences)
    for field in PROVENANCE_LIFECYCLE_ID_FIELDS:
        lifecycle_key = field.removesuffix("_ids")
        identifiers = event.get(field, [])
        if not isinstance(identifiers, list):
            continue
        retention["archived_lifecycle_totals"][lifecycle_key] += (
            len(identifiers) * occurrences
        )
    first = str(event.get("first_timestamp") or event.get("timestamp") or "")
    last = str(event.get("last_timestamp") or event.get("timestamp") or "")
    if first and not retention.get("first_archived_at"):
        retention["first_archived_at"] = first
    if last:
        retention["last_archived_at"] = last
    if event.get("graph_content_signature"):
        retention["last_archived_graph_content_signature"] = event[
            "graph_content_signature"
        ]
    retention["checkpoint_digest"] = _chain_archived_event_digest(
        retention.get("checkpoint_digest"), event
    )


def apply_provenance_retention(
    store: Dict[str, Any], event_limit: Optional[int] = None
) -> Dict[str, Any]:
    retention = _normalize_provenance_retention(store)
    limit = validate_provenance_event_limit(
        event_limit
        if event_limit is not None
        else retention["observation_event_limit"]
    )
    retention["observation_event_limit"] = limit

    normalized_events: List[Dict[str, Any]] = []
    coalesced_occurrences = 0
    for raw_event in store.setdefault("events", []):
        event = copy.deepcopy(raw_event)
        if event.get("type") != "observation_batch":
            normalized_events.append(event)
            continue
        event = normalize_observation_event(event)
        previous = normalized_events[-1] if normalized_events else None
        if (
            isinstance(previous, dict)
            and previous.get("type") == "observation_batch"
            and previous.get("event_signature") == event.get("event_signature")
        ):
            occurrences = _event_occurrence_count(event)
            previous["occurrence_count"] = (
                _event_occurrence_count(previous) + occurrences
            )
            previous["first_timestamp"] = min(
                str(previous.get("first_timestamp", "")),
                str(event.get("first_timestamp", "")),
            )
            previous["last_timestamp"] = max(
                str(previous.get("last_timestamp", "")),
                str(event.get("last_timestamp", "")),
            )
            coalesced_occurrences += occurrences
            continue
        normalized_events.append(event)
    retention["coalesced_batch_occurrences"] += coalesced_occurrences

    observation_indices = [
        index
        for index, event in enumerate(normalized_events)
        if event.get("type") == "observation_batch"
    ]
    excess = max(0, len(observation_indices) - limit)
    removed_indices = set(observation_indices[:excess])
    removed = [normalized_events[index] for index in observation_indices[:excess]]
    for event in removed:
        _archive_observation_event(retention, event)
    if removed_indices:
        normalized_events = [
            event
            for index, event in enumerate(normalized_events)
            if index not in removed_indices
        ]
    store["events"] = normalized_events
    return {
        "coalesced_batch_occurrences": coalesced_occurrences,
        "compacted_event_records": len(removed),
        "compacted_batch_occurrences": sum(
            _event_occurrence_count(event) for event in removed
        ),
    }


def provenance_retention_snapshot(store: Dict[str, Any]) -> Dict[str, Any]:
    retention = _normalize_provenance_retention(store)
    retained = [
        event
        for event in store.get("events", [])
        if event.get("type") == "observation_batch"
    ]
    retained_occurrences = sum(_event_occurrence_count(event) for event in retained)
    archived_occurrences = int(retention.get("archived_batch_occurrences", 0))
    return {
        "schema_version": retention["schema_version"],
        "observation_event_limit": retention["observation_event_limit"],
        "retained_event_records": len(retained),
        "retained_batch_occurrences": retained_occurrences,
        "archived_event_records": int(retention.get("archived_event_records", 0)),
        "archived_batch_occurrences": archived_occurrences,
        "total_batch_occurrences": retained_occurrences + archived_occurrences,
        "coalesced_batch_occurrences": int(
            retention.get("coalesced_batch_occurrences", 0)
        ),
        "archived_namespace_limit": retention["archived_namespace_limit"],
        "archived_namespace_overflow_occurrences": int(
            retention.get("archived_namespace_overflow_occurrences", 0)
        ),
        "archived_by_namespace": copy.deepcopy(
            retention.get("archived_by_namespace", {})
        ),
        "archived_lifecycle_totals": copy.deepcopy(
            retention.get("archived_lifecycle_totals", {})
        ),
        "checkpoint_digest": retention.get("checkpoint_digest"),
        "digest_algorithm": retention.get("digest_algorithm", "sha256-chain-v1"),
        "counts_preserved": True,
        "archived_detail_recoverable": False,
        "hot_history_bounded": len(retained)
        <= int(retention["observation_event_limit"]),
    }


__all__ = [
    "DEFAULT_PROVENANCE_EVENT_LIMIT",
    "PROVENANCE_RETENTION_SCHEMA_VERSION",
    "apply_provenance_retention",
    "default_provenance_retention",
    "normalize_observation_event",
    "provenance_retention_snapshot",
    "validate_provenance_event_limit",
]
