"""Content-addressed persistent cells for deterministic memory recall.

The canonical memory store is the authority. This module persists only a
derived reference machine: one compact predicate manifest plus immutable packs
partitioned by a stable hash of memory id. A one-record mutation rewrites one
pack and the manifest instead of a monolithic full-record projection.

Warm directed queries use manifest indexes to load only candidate packs. Pack
hashes detect accidental/stale local state; they are not an external
tamper-proof trust anchor. Any cache failure falls back to one validated
canonical snapshot and can never restore the canonical store.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from memory.retrieval import (
    RECALL_PROJECTION_SCHEMA_VERSION,
    build_recall_projection,
    normalize_recall_path,
    normalize_recall_text,
    projection_signature_from_records,
    recall_index_record,
    recall_terms,
)
from memory.runtime import (
    memory_runtime_lock,
    write_bytes_unlocked,
    write_json_unlocked,
)


RECALL_CACHE_SCHEMA_VERSION = "content-addressed-memory-recall-cache-v2"
RECALL_CELL_SCHEMA_VERSION = "memory-recall-cell-pack-v1"
RECALL_STORAGE_MODEL = "content_addressed_memory_recall_cells_v1"
RECALL_CACHE_MODES = ("auto", "refresh", "off")
RECALL_CELL_PARTITION_COUNT = 64
ABSENT_EMPTY_STORE_SIGNATURE = "sha256:" + hashlib.sha256(
    b"canonical-memory-store-absent-empty-v1"
).hexdigest()
RECALL_CACHE_INTEGRITY_BOUNDARY = (
    "SHA-256 detects accidental/stale local cache state; it is not an external "
    "tamper-proof trust anchor"
)
_INDEX_FIELDS = (
    "term_index",
    "tag_index",
    "type_index",
    "file_index",
    "basename_index",
)
_OPTIONAL_INDEX_FIELDS = (
    "related_file_index",
)


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    digest = value[7:]
    return len(digest) == 64 and all(
        character in "0123456789abcdef" for character in digest
    )


def _compact_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _engine_signature() -> str:
    digest = hashlib.sha256()
    digest.update(
        f"python:{sys.version_info.major}.{sys.version_info.minor}".encode(
            "utf-8"
        )
    )
    digest.update(b"\0")
    for path in (
        Path(__file__),
        Path(__file__).with_name("retrieval.py"),
        Path(__file__).with_name("runtime.py"),
        Path(__file__).with_name("store.py"),
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _store_fingerprint(store_path: str) -> Dict[str, Any]:
    path = Path(store_path)
    backup_present = Path(f"{path}.bak").is_file()
    if not path.is_file():
        return {
            "content_sha256": ABSENT_EMPTY_STORE_SIGNATURE,
            "bytes_hashed": 0,
            "present": False,
            "backup_present": backup_present,
            "recovery_pending": backup_present,
        }
    payload = path.read_bytes()
    return {
        "content_sha256": _sha256_bytes(payload),
        "bytes_hashed": len(payload),
        "present": True,
        "backup_present": backup_present,
        "recovery_pending": False,
    }


def _integrity_path(cache_path: str) -> Path:
    return Path(f"{cache_path}.sha256")


def _partition_for_id(memory_id: str) -> int:
    digest = hashlib.sha256(memory_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % RECALL_CELL_PARTITION_COUNT


def _cell_path(paths: Dict[str, Any], content_sha256: str) -> Path:
    if not _is_sha256(content_sha256):
        raise ValueError("invalid recall cell content hash")
    digest = content_sha256[7:]
    return Path(paths["recall_cells_dir"]) / f"{digest}.json"


def _append_ordinal(
    index: Dict[str, List[int]], key: str, ordinal: int
) -> None:
    if key:
        index.setdefault(key, []).append(ordinal)


def _build_indexes(memories: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    indexes: Dict[str, Dict[str, List[int]]] = {
        field: {} for field in _INDEX_FIELDS
    }
    indexes["related_file_index"] = {}
    record_signatures: List[str] = []
    order: List[str] = []
    for ordinal, memory in enumerate(memories):
        indexed = recall_index_record(memory)
        memory_id = indexed["memory_id"]
        order.append(memory_id)
        record_signatures.append(indexed["record_signature"])
        for term in indexed["terms"]:
            _append_ordinal(indexes["term_index"], term, ordinal)
        for tag in indexed["tags"]:
            _append_ordinal(indexes["tag_index"], tag, ordinal)
        _append_ordinal(indexes["type_index"], indexed["type"], ordinal)
        _append_ordinal(indexes["file_index"], indexed["file"], ordinal)
        _append_ordinal(
            indexes["basename_index"], indexed["basename"], ordinal
        )
        for rf in indexed.get("related_files", []):
            _append_ordinal(indexes["related_file_index"], rf, ordinal)
    return {
        "order": order,
        "record_signatures": record_signatures,
        **indexes,
    }


def _pack_payload(partition: int, memories: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "schema_version": RECALL_CELL_SCHEMA_VERSION,
        "partition": partition,
        "memories": sorted(
            memories,
            key=lambda memory: str(memory.get("id", "")),
        ),
    }


def _write_pack_unlocked(
    paths: Dict[str, Any],
    partition: int,
    memories: List[Dict[str, Any]],
) -> Tuple[str, bool, int]:
    raw_payload = _compact_json_bytes(_pack_payload(partition, memories))
    content_hash = _sha256_bytes(raw_payload)
    path = _cell_path(paths, content_hash)
    if path.is_file():
        try:
            if _sha256_bytes(path.read_bytes()) == content_hash:
                return content_hash, False, 0
        except OSError:
            pass
    write_bytes_unlocked(str(path), raw_payload)
    return content_hash, True, len(raw_payload)


def _read_pack(
    paths: Dict[str, Any],
    partition: int,
    content_hash: str,
) -> List[Dict[str, Any]]:
    path = _cell_path(paths, content_hash)
    raw_payload = path.read_bytes()
    if _sha256_bytes(raw_payload) != content_hash:
        raise ValueError("recall cell content hash mismatch")
    payload = json.loads(raw_payload)
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != RECALL_CELL_SCHEMA_VERSION
        or payload.get("partition") != partition
        or not isinstance(payload.get("memories"), list)
    ):
        raise ValueError("recall cell payload is invalid")
    memories = payload["memories"]
    seen: Set[str] = set()
    for memory in memories:
        if not isinstance(memory, dict) or not memory.get("id"):
            raise ValueError("recall cell memory is invalid")
        memory_id = str(memory["id"])
        if memory_id in seen or _partition_for_id(memory_id) != partition:
            raise ValueError("recall cell partition invariant failed")
        seen.add(memory_id)
    return memories


def _manifest_refs_exist(
    paths: Dict[str, Any], manifest: Dict[str, Any]
) -> Optional[str]:
    for content_hash in manifest.get("packs", {}).values():
        if not _cell_path(paths, content_hash).is_file():
            return "recall_cell_missing"
    return None


def _validate_manifest_shape(payload: Any, scope_id: str) -> None:
    if not isinstance(payload, dict):
        raise ValueError("recall cache manifest must be an object")
    if payload.get("schema_version") != RECALL_CACHE_SCHEMA_VERSION:
        raise ValueError("recall cache manifest schema mismatch")
    if payload.get("projection_schema_version") != RECALL_PROJECTION_SCHEMA_VERSION:
        raise ValueError("recall projection schema mismatch")
    if payload.get("cell_schema_version") != RECALL_CELL_SCHEMA_VERSION:
        raise ValueError("recall cell schema mismatch")
    if payload.get("storage_model") != RECALL_STORAGE_MODEL:
        raise ValueError("recall cache storage model mismatch")
    if payload.get("scope_id") != scope_id:
        raise ValueError("recall cache scope mismatch")
    if payload.get("partition_count") != RECALL_CELL_PARTITION_COUNT:
        raise ValueError("recall cell partition count mismatch")
    order = payload.get("order")
    signatures = payload.get("record_signatures")
    packs = payload.get("packs")
    if (
        not isinstance(order, list)
        or not all(isinstance(memory_id, str) and memory_id for memory_id in order)
        or len(order) != len(set(order))
        or not isinstance(signatures, list)
        or len(signatures) != len(order)
        or not all(_is_sha256(value) for value in signatures)
        or not isinstance(packs, dict)
    ):
        raise ValueError("recall cache manifest records are invalid")
    expected_partitions = {str(_partition_for_id(memory_id)) for memory_id in order}
    if set(packs) != expected_partitions:
        raise ValueError("recall cache manifest pack coverage mismatch")
    for raw_partition, content_hash in packs.items():
        partition = int(raw_partition)
        if (
            partition < 0
            or partition >= RECALL_CELL_PARTITION_COUNT
            or not _is_sha256(content_hash)
        ):
            raise ValueError("recall cache manifest pack reference is invalid")
    for field in _INDEX_FIELDS + _OPTIONAL_INDEX_FIELDS:
        index = payload.get(field)
        if index is None and field in _OPTIONAL_INDEX_FIELDS:
            continue
        if not isinstance(index, dict):
            raise ValueError(f"recall cache {field} is invalid")
        for key, postings in index.items():
            if (
                not isinstance(key, str)
                or not isinstance(postings, list)
                or len(postings) != len(set(postings))
                or any(
                    not isinstance(ordinal, int)
                    or isinstance(ordinal, bool)
                    or ordinal < 0
                    or ordinal >= len(order)
                    for ordinal in postings
                )
            ):
                raise ValueError(f"recall cache {field} postings are invalid")
    expected_signature = projection_signature_from_records(
        order, dict(zip(order, signatures))
    )
    if (
        payload.get("snapshot_memory_count") != len(order)
        or payload.get("snapshot_signature") != expected_signature
        or payload.get("indexed_term_count") != len(payload["term_index"])
        or not isinstance(payload.get("engine_signature"), str)
        or not isinstance(payload.get("store_content_sha256"), str)
    ):
        raise ValueError("recall cache manifest snapshot proof is invalid")


def _load_manifest_unlocked(
    paths: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    path = Path(paths["recall_cache_path"])
    integrity_path = _integrity_path(str(path))
    if not path.is_file():
        if integrity_path.exists():
            return None, "recall_cache_manifest_missing"
        return None, None
    try:
        raw_payload = path.read_bytes()
        with integrity_path.open("r", encoding="utf-8") as handle:
            integrity = json.load(handle)
    except Exception as exc:
        return None, f"recall_cache_read_error:{type(exc).__name__}"
    if (
        not isinstance(integrity, dict)
        or integrity.get("schema_version") != RECALL_CACHE_SCHEMA_VERSION
        or integrity.get("cache_sha256") != _sha256_bytes(raw_payload)
    ):
        return None, "recall_cache_checksum_mismatch"
    try:
        payload = json.loads(raw_payload)
        _validate_manifest_shape(payload, paths["scope_id"])
    except Exception as exc:
        return None, f"recall_cache_manifest_invalid:{type(exc).__name__}"
    missing = _manifest_refs_exist(paths, payload)
    if missing:
        return None, missing
    return payload, None


def _manifest_payload(
    paths: Dict[str, Any],
    fingerprint: Dict[str, Any],
    engine_signature: str,
    indexed: Dict[str, Any],
    pack_refs: Dict[str, str],
    created_at: Optional[str],
) -> Dict[str, Any]:
    order = indexed["order"]
    signatures = indexed["record_signatures"]
    return {
        "schema_version": RECALL_CACHE_SCHEMA_VERSION,
        "projection_schema_version": RECALL_PROJECTION_SCHEMA_VERSION,
        "cell_schema_version": RECALL_CELL_SCHEMA_VERSION,
        "storage_model": RECALL_STORAGE_MODEL,
        "scope_id": paths["scope_id"],
        "engine_signature": engine_signature,
        "store_content_sha256": fingerprint["content_sha256"],
        "canonical_store_present": bool(fingerprint["present"]),
        "canonical_backup_present": bool(fingerprint.get("backup_present", False)),
        "canonical_recovery_pending": bool(fingerprint.get("recovery_pending", False)),
        "canonical_store_bytes": int(fingerprint["bytes_hashed"]),
        "created_at": created_at or _utc_now(),
        "updated_at": _utc_now(),
        "contains_full_memory_content": True,
        "canonical_store_authoritative": True,
        "cache_can_restore_canonical_store": False,
        "integrity_boundary": RECALL_CACHE_INTEGRITY_BOUNDARY,
        "partition_count": RECALL_CELL_PARTITION_COUNT,
        "order": order,
        "record_signatures": signatures,
        "packs": dict(sorted(pack_refs.items(), key=lambda item: int(item[0]))),
        "term_index": indexed["term_index"],
        "tag_index": indexed["tag_index"],
        "type_index": indexed["type_index"],
        "file_index": indexed["file_index"],
        "basename_index": indexed["basename_index"],
        "related_file_index": indexed.get("related_file_index", {}),
        "snapshot_signature": projection_signature_from_records(
            order, dict(zip(order, signatures))
        ),
        "snapshot_memory_count": len(order),
        "indexed_term_count": len(indexed["term_index"]),
        "built_from_single_snapshot": True,
    }


def _write_manifest_unlocked(
    paths: Dict[str, Any], manifest: Dict[str, Any]
) -> Tuple[Optional[str], int]:
    try:
        write_json_unlocked(
            paths["recall_cache_path"],
            manifest,
            retain_backup=False,
            compact=True,
        )
        raw_payload = Path(paths["recall_cache_path"]).read_bytes()
        write_json_unlocked(
            str(_integrity_path(paths["recall_cache_path"])),
            {
                "schema_version": RECALL_CACHE_SCHEMA_VERSION,
                "cache_sha256": _sha256_bytes(raw_payload),
            },
            retain_backup=False,
            compact=True,
        )
        return None, len(raw_payload)
    except Exception as exc:
        return f"recall_cache_write_error:{type(exc).__name__}", 0


def _gc_unreferenced_packs_unlocked(
    paths: Dict[str, Any], referenced_hashes: Set[str]
) -> Dict[str, int]:
    cells_dir = Path(paths["recall_cells_dir"])
    removed = 0
    removed_bytes = 0
    failures = 0
    if not cells_dir.is_dir():
        return {
            "cell_packs_removed": 0,
            "cell_bytes_removed": 0,
            "cell_gc_failures": 0,
        }
    referenced_names = {
        f"{value.removeprefix('sha256:')}.json" for value in referenced_hashes
    }
    for candidate in cells_dir.glob("*.json"):
        if candidate.name in referenced_names or not candidate.is_file():
            continue
        try:
            removed_bytes += candidate.stat().st_size
            candidate.unlink()
            removed += 1
        except OSError:
            failures += 1
            continue
    try:
        if not any(cells_dir.iterdir()):
            cells_dir.rmdir()
    except OSError:
        pass
    return {
        "cell_packs_removed": removed,
        "cell_bytes_removed": removed_bytes,
        "cell_gc_failures": failures,
    }


def _base_metrics(
    mode: str,
    paths: Dict[str, Any],
    fingerprint: Dict[str, Any],
    engine_signature: str,
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "status": "miss",
        "storage_model": RECALL_STORAGE_MODEL,
        "cache_path": paths["recall_cache_path"],
        "cells_dir": paths["recall_cells_dir"],
        "integrity_path": str(_integrity_path(paths["recall_cache_path"])),
        "cache_schema_version": RECALL_CACHE_SCHEMA_VERSION,
        "cell_schema_version": RECALL_CELL_SCHEMA_VERSION,
        "projection_schema_version": RECALL_PROJECTION_SCHEMA_VERSION,
        "scope_id": paths["scope_id"],
        "engine_signature": engine_signature,
        "store_content_sha256": fingerprint["content_sha256"],
        "canonical_store_present": bool(fingerprint["present"]),
        "canonical_backup_present": bool(fingerprint.get("backup_present", False)),
        "canonical_recovery_pending": bool(fingerprint.get("recovery_pending", False)),
        "canonical_store_bytes_hashed": int(fingerprint["bytes_hashed"]),
        "canonical_store_load_count": 0,
        "entries_reused": 0,
        "entries_rebuilt": 0,
        "entries_removed": 0,
        "hit_ratio": 0.0,
        "cell_partition_count": RECALL_CELL_PARTITION_COUNT,
        "cell_pack_count": 0,
        "cell_packs_written": 0,
        "cell_packs_reused": 0,
        "cell_packs_removed": 0,
        "cell_gc_failures": 0,
        "cell_bytes_written": 0,
        "manifest_bytes_written": 0,
        "full_projection_rewrite_avoided": False,
        "contains_full_memory_content": True,
        "canonical_store_authoritative": True,
        "cache_can_restore_canonical_store": False,
        "integrity_boundary": RECALL_CACHE_INTEGRITY_BOUNDARY,
    }


def _posting_union(index: Dict[str, List[int]], keys: Iterable[str]) -> Set[int]:
    result: Set[int] = set()
    for key in keys:
        result.update(index.get(key, []))
    return result


def _phrase_ordinals(manifest: Dict[str, Any], phrase: str) -> Set[int]:
    terms = sorted(recall_terms(phrase))
    if not terms:
        return set(range(len(manifest["order"])))
    postings = [set(manifest["term_index"].get(term, [])) for term in terms]
    if not postings or any(not values for values in postings):
        return set()
    result = postings[0]
    for values in postings[1:]:
        result.intersection_update(values)
    return result


def _candidate_ids(
    manifest: Dict[str, Any],
    query: Optional[str],
    target_files: List[str],
    memory_type: Optional[str],
    tags: List[str],
    target_hops: Optional[Dict[str, int]] = None,
) -> Tuple[List[str], List[str]]:
    directed: Set[int] = set()
    has_directed_signal = bool(query)
    if query:
        query_terms = recall_terms(
            normalize_recall_text(query), minimum_length=2
        )
        directed.update(
            _posting_union(manifest["term_index"], query_terms)
            if query_terms else range(len(manifest["order"]))
        )

    normalized_targets: List[str] = []
    related_file_index = manifest.get("related_file_index", {})
    for raw_path in target_files:
        file_path = normalize_recall_path(raw_path)
        if not file_path or file_path in normalized_targets:
            continue
        normalized_targets.append(file_path)
        has_directed_signal = True
        basename = os.path.basename(file_path)
        file_dir = os.path.dirname(file_path)
        directory_tag = file_dir.replace("/", ".") if file_dir else ""
        directed.update(manifest["file_index"].get(file_path, []))
        directed.update(related_file_index.get(file_path, []))
        directed.update(_phrase_ordinals(manifest, file_path))
        if basename:
            directed.update(manifest["basename_index"].get(basename, []))
        if directory_tag:
            directed.update(manifest["tag_index"].get(directory_tag, []))

    if target_hops:
        has_directed_signal = True
        for hop_path, dist in sorted(target_hops.items(), key=lambda x: (x[1], str(x[0]))):
            norm_hop = normalize_recall_path(hop_path)
            if not norm_hop or norm_hop in normalized_targets:
                continue
            if dist <= 2:
                directed.update(manifest["file_index"].get(norm_hop, []))
                directed.update(related_file_index.get(norm_hop, []))

    candidates = (
        directed
        if has_directed_signal
        else set(range(len(manifest["order"])))
    )
    if memory_type:
        candidates.intersection_update(
            manifest["type_index"].get(memory_type, [])
        )
    if tags:
        candidates.intersection_update(
            _posting_union(manifest["tag_index"], tags)
        )
    return (
        [manifest["order"][ordinal] for ordinal in sorted(candidates)],
        normalized_targets,
    )


def _invalidate_manifest_after_query_error(
    paths: Dict[str, Any], expected_snapshot_signature: str
) -> bool:
    manifest_path = Path(paths["recall_cache_path"])
    if manifest_path.is_file():
        try:
            current = json.loads(manifest_path.read_bytes())
            if current.get("snapshot_signature") != expected_snapshot_signature:
                return False
        except Exception:
            pass
    for candidate in (
        manifest_path,
        _integrity_path(paths["recall_cache_path"]),
    ):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
    return True


def _lazy_projection(
    manifest: Dict[str, Any],
    paths: Dict[str, Any],
    metrics: Dict[str, Any],
    load_store_unlocked: Callable[[], Dict[str, Any]],
) -> Dict[str, Any]:
    shell: Dict[str, Any] = {
        "schema_version": RECALL_PROJECTION_SCHEMA_VERSION,
        "snapshot_signature": manifest["snapshot_signature"],
        "snapshot_memory_count": manifest["snapshot_memory_count"],
        "indexed_term_count": manifest["indexed_term_count"],
        "built_from_single_snapshot": True,
        "storage_model": RECALL_STORAGE_MODEL,
        "cache": metrics,
    }

    def provide(
        *,
        query: Optional[str],
        target_files: List[str],
        target_hops: Optional[Dict[str, int]] = None,
        memory_type: Optional[str],
        tags: List[str],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        active_manifest = manifest
        candidate_ids: List[str] = []
        normalized_targets: List[str] = []
        partitions: List[int] = []
        pack_reads = 0
        memories_by_id: Dict[str, Dict[str, Any]] = {}
        fallback_store: Optional[Dict[str, Any]] = None
        read_error: Optional[Exception] = None
        # Keep candidate reads under the same project lock used by GC. The
        # captured content-addressed manifest is an immutable snapshot; if a
        # newer generation already retired one required pack, canonical
        # fallback below supplies one current consistent snapshot.
        with memory_runtime_lock(paths):
            try:
                candidate_ids, normalized_targets = _candidate_ids(
                    active_manifest,
                    query,
                    target_files,
                    memory_type,
                    tags,
                    target_hops=target_hops,
                )
                wanted = set(candidate_ids)
                partitions = sorted({
                    _partition_for_id(memory_id) for memory_id in wanted
                })
                for partition in partitions:
                    content_hash = active_manifest["packs"][str(partition)]
                    pack_reads += 1
                    for memory in _read_pack(paths, partition, content_hash):
                        memory_id = str(memory.get("id", ""))
                        if memory_id in wanted:
                            memories_by_id[memory_id] = memory
                if set(memories_by_id) != wanted:
                    raise ValueError(
                        "recall candidate cells do not cover manifest ids"
                    )
            except Exception as exc:
                read_error = exc
                store = load_store_unlocked()
                manifest_invalidated = _invalidate_manifest_after_query_error(
                    paths, active_manifest["snapshot_signature"]
                )
                fallback_store = store

        if fallback_store is not None:
            fallback = build_recall_projection(
                fallback_store.get("memories", [])
            )
            metrics.update({
                "status": "read_failed",
                "canonical_store_load_count": 1,
                "query_pack_reads": pack_reads,
                "query_memory_materialized": len(fallback.get("entries", [])),
                "query_fallback_to_canonical": True,
                "query_manifest_invalidated": manifest_invalidated,
                "read_error": (
                    f"recall_cell_read_error:{type(read_error).__name__}"
                ),
            })
            shell.update({
                "snapshot_signature": fallback["snapshot_signature"],
                "snapshot_memory_count": fallback["snapshot_memory_count"],
                "indexed_term_count": fallback["indexed_term_count"],
            })
            return fallback, {
                "candidate_materialized_count": fallback["snapshot_memory_count"],
                "query_pack_reads": pack_reads,
                "query_pack_read_ratio": round(
                    pack_reads / max(1, len(active_manifest["packs"])), 6
                ),
                "query_fallback_to_canonical": True,
            }

        ordered_memories = [memories_by_id[memory_id] for memory_id in candidate_ids]
        materialized = build_recall_projection(ordered_memories)
        shell.update({
            "snapshot_signature": active_manifest["snapshot_signature"],
            "snapshot_memory_count": active_manifest["snapshot_memory_count"],
            "indexed_term_count": active_manifest["indexed_term_count"],
        })
        metrics.update({
            "query_pack_reads": pack_reads,
            "query_memory_materialized": len(ordered_memories),
            "query_fallback_to_canonical": False,
        })
        return materialized, {
            "candidate_materialized_count": len(ordered_memories),
            "query_pack_reads": pack_reads,
            "query_pack_count": len(active_manifest["packs"]),
            "query_pack_read_ratio": round(
                pack_reads / max(1, len(active_manifest["packs"])), 6
            ),
            "manifest_predicate_selection": True,
            "normalized_target_files": normalized_targets,
        }

    shell["_candidate_provider"] = provide
    return shell


def _current_pack_groups(
    memories: Iterable[Dict[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    groups: Dict[int, List[Dict[str, Any]]] = {}
    for memory in memories:
        partition = _partition_for_id(str(memory.get("id", "")))
        groups.setdefault(partition, []).append(memory)
    return groups


def load_or_build_recall_projection_unlocked(
    paths: Dict[str, Any],
    load_store_unlocked: Callable[[], Dict[str, Any]],
    mode: str = "auto",
) -> Dict[str, Any]:
    """Return a lazy content-addressed projection while caller holds the lock."""
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in RECALL_CACHE_MODES:
        raise ValueError(
            f"Unsupported memory recall cache mode: {mode}. Expected one of: "
            f"{', '.join(RECALL_CACHE_MODES)}"
        )

    engine_signature = _engine_signature()
    fingerprint = _store_fingerprint(paths["store_path"])
    metrics = _base_metrics(normalized_mode, paths, fingerprint, engine_signature)
    manifest: Optional[Dict[str, Any]] = None
    load_error: Optional[str] = None
    if normalized_mode == "auto":
        manifest, load_error = _load_manifest_unlocked(paths)
        if load_error:
            metrics["recovery_reason"] = load_error

    engine_compatible = bool(
        manifest and manifest.get("engine_signature") == engine_signature
    )
    store_compatible = bool(
        manifest
        and not fingerprint.get("recovery_pending", False)
        and manifest.get("store_content_sha256") == fingerprint["content_sha256"]
        and bool(manifest.get("canonical_store_present")) == bool(fingerprint["present"])
    )
    if manifest and engine_compatible and store_compatible:
        total = int(manifest["snapshot_memory_count"])
        metrics.update({
            "status": "hit",
            "entries_reused": total,
            "hit_ratio": 1.0,
            "cell_pack_count": len(manifest["packs"]),
            "cell_packs_reused": len(manifest["packs"]),
            "projection_signature": manifest["snapshot_signature"],
        })
        return _lazy_projection(manifest, paths, metrics, load_store_unlocked)

    invalidation_reasons: List[str] = []
    if manifest and not engine_compatible:
        invalidation_reasons.append("projection_engine_changed")
    if manifest and not store_compatible:
        invalidation_reasons.append(
            "canonical_recovery_pending"
            if fingerprint.get("recovery_pending", False)
            else "canonical_store_changed"
        )
    if invalidation_reasons:
        metrics["invalidation_reasons"] = invalidation_reasons

    store = load_store_unlocked()
    memories = store.get("memories", [])
    metrics["canonical_store_load_count"] = 1
    fingerprint = _store_fingerprint(paths["store_path"])
    metrics.update({
        "store_content_sha256": fingerprint["content_sha256"],
        "canonical_store_present": bool(fingerprint["present"]),
        "canonical_backup_present": bool(fingerprint.get("backup_present", False)),
        "canonical_recovery_pending": bool(fingerprint.get("recovery_pending", False)),
        "canonical_store_bytes_hashed": int(fingerprint["bytes_hashed"]),
    })
    indexed = _build_indexes(memories)
    current_signatures = dict(zip(
        indexed["order"], indexed["record_signatures"]
    ))
    previous_signatures = (
        dict(zip(manifest.get("order", []), manifest.get("record_signatures", [])))
        if manifest and engine_compatible and normalized_mode == "auto"
        else {}
    )
    current_ids = set(current_signatures)
    previous_ids = set(previous_signatures)
    reused_ids = {
        memory_id for memory_id in current_ids.intersection(previous_ids)
        if current_signatures[memory_id] == previous_signatures[memory_id]
    }
    rebuilt_ids = current_ids - reused_ids
    removed_ids = previous_ids - current_ids
    metrics.update({
        "entries_reused": len(reused_ids),
        "entries_rebuilt": len(rebuilt_ids),
        "entries_removed": len(removed_ids),
        "hit_ratio": round(
            len(reused_ids)
            / max(1, len(reused_ids) + len(rebuilt_ids) + len(removed_ids)),
            6,
        ),
    })

    if normalized_mode == "off":
        projection = build_recall_projection(memories)
        metrics["status"] = "disabled"
        projection["cache"] = metrics
        return projection

    groups = _current_pack_groups(memories)
    full_rebuild = not (
        manifest and engine_compatible and normalized_mode == "auto"
    )
    pack_refs = dict(manifest.get("packs", {})) if not full_rebuild else {}
    if full_rebuild:
        affected_partitions = set(groups)
    else:
        affected_partitions = {
            _partition_for_id(memory_id)
            for memory_id in rebuilt_ids.union(removed_ids)
        }
    pack_write_error: Optional[str] = None
    for partition in sorted(affected_partitions):
        partition_memories = groups.get(partition, [])
        key = str(partition)
        if not partition_memories:
            pack_refs.pop(key, None)
            continue
        try:
            content_hash, written, byte_count = _write_pack_unlocked(
                paths, partition, partition_memories
            )
        except Exception as exc:
            pack_write_error = f"recall_cell_write_error:{type(exc).__name__}"
            break
        pack_refs[key] = content_hash
        if written:
            metrics["cell_packs_written"] += 1
            metrics["cell_bytes_written"] += byte_count

    metrics["cell_pack_count"] = len(pack_refs)
    metrics["cell_packs_reused"] = max(
        0, len(pack_refs) - int(metrics["cell_packs_written"])
    )
    metrics["full_projection_rewrite_avoided"] = bool(
        not full_rebuild and len(reused_ids) > 0
    )
    if pack_write_error:
        projection = build_recall_projection(memories)
        metrics.update({
            "status": "write_failed",
            "build_status": "partial" if not full_rebuild else "miss",
            "write_error": pack_write_error,
        })
        projection["cache"] = metrics
        return projection

    next_manifest = _manifest_payload(
        paths,
        fingerprint,
        engine_signature,
        indexed,
        pack_refs,
        manifest.get("created_at") if manifest else None,
    )
    write_error, manifest_bytes = _write_manifest_unlocked(paths, next_manifest)
    metrics["manifest_bytes_written"] = manifest_bytes
    metrics["projection_signature"] = next_manifest["snapshot_signature"]

    if normalized_mode == "refresh":
        build_status = "refreshed"
    elif load_error:
        build_status = "recovered"
    elif manifest and engine_compatible and reused_ids:
        build_status = "partial"
    elif manifest:
        build_status = "invalidated"
    else:
        build_status = "miss"

    if write_error:
        projection = build_recall_projection(memories)
        metrics.update({
            "status": "write_failed",
            "build_status": build_status,
            "write_error": write_error,
        })
        projection["cache"] = metrics
        return projection

    metrics.update(_gc_unreferenced_packs_unlocked(paths, set(pack_refs.values())))
    metrics["status"] = build_status
    return _lazy_projection(next_manifest, paths, metrics, load_store_unlocked)


def get_recall_cache_status_unlocked(paths: Dict[str, Any]) -> Dict[str, Any]:
    """Validate manifest and every referenced pack for an explicit audit."""
    fingerprint = _store_fingerprint(paths["store_path"])
    engine_signature = _engine_signature()
    metrics = _base_metrics("status", paths, fingerprint, engine_signature)
    manifest, load_error = _load_manifest_unlocked(paths)
    if load_error:
        metrics.update({"status": "corrupt", "recovery_reason": load_error})
        return metrics
    if not manifest:
        metrics["status"] = "missing"
        return metrics
    try:
        validated_bytes = 0
        validated_records = 0
        memories_by_id: Dict[str, Dict[str, Any]] = {}
        for raw_partition, content_hash in manifest["packs"].items():
            path = _cell_path(paths, content_hash)
            validated_bytes += path.stat().st_size
            pack_memories = _read_pack(
                paths, int(raw_partition), content_hash
            )
            validated_records += len(pack_memories)
            for memory in pack_memories:
                memory_id = str(memory["id"])
                if memory_id in memories_by_id:
                    raise ValueError("duplicate memory across recall cells")
                memories_by_id[memory_id] = memory
        if (
            validated_records != manifest["snapshot_memory_count"]
            or set(memories_by_id) != set(manifest["order"])
        ):
            raise ValueError("recall cell record coverage mismatch")
        reconstructed = _build_indexes(
            memories_by_id[memory_id] for memory_id in manifest["order"]
        )
        for field in ("order", "record_signatures", *_INDEX_FIELDS):
            if reconstructed[field] != manifest[field]:
                raise ValueError(
                    f"recall manifest {field} does not match cell content"
                )
    except Exception as exc:
        metrics.update({
            "status": "corrupt",
            "recovery_reason": f"recall_cell_invalid:{type(exc).__name__}",
        })
        return metrics
    stale_reasons: List[str] = []
    if manifest["engine_signature"] != engine_signature:
        stale_reasons.append("projection_engine_changed")
    if (
        manifest["store_content_sha256"] != fingerprint["content_sha256"]
        or bool(manifest["canonical_store_present"]) != bool(fingerprint["present"])
    ):
        stale_reasons.append("canonical_store_changed")
    if fingerprint.get("recovery_pending", False):
        stale_reasons.append("canonical_recovery_pending")
    total = int(manifest["snapshot_memory_count"])
    metrics.update({
        "status": "stale" if stale_reasons else "valid",
        "stale_reasons": stale_reasons,
        "entries_reused": total if not stale_reasons else 0,
        "hit_ratio": 1.0 if not stale_reasons else 0.0,
        "cell_pack_count": len(manifest["packs"]),
        "cell_packs_reused": len(manifest["packs"]) if not stale_reasons else 0,
        "cell_packs_validated": len(manifest["packs"]),
        "cell_bytes_validated": validated_bytes,
        "projection_signature": manifest["snapshot_signature"],
        "cached_store_content_sha256": manifest["store_content_sha256"],
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
    })
    return metrics


def clear_recall_cache_unlocked(paths: Dict[str, Any]) -> Dict[str, Any]:
    manifest_path = Path(paths["recall_cache_path"])
    integrity_path = _integrity_path(paths["recall_cache_path"])
    cells_dir = Path(paths["recall_cells_dir"])
    existing = [path for path in (manifest_path, integrity_path) if path.exists()]
    cell_files = list(cells_dir.glob("*.json")) if cells_dir.is_dir() else []
    if not existing and not cell_files:
        return {
            "status": "missing",
            "cache_path": str(manifest_path),
            "integrity_path": str(integrity_path),
            "cells_dir": str(cells_dir),
            "scope_id": paths["scope_id"],
        }
    try:
        for candidate in existing + cell_files:
            candidate.unlink()
        try:
            if cells_dir.is_dir() and not any(cells_dir.iterdir()):
                cells_dir.rmdir()
        except OSError:
            pass
        return {
            "status": "cleared",
            "cache_path": str(manifest_path),
            "integrity_path": str(integrity_path),
            "cells_dir": str(cells_dir),
            "cell_packs_removed": len(cell_files),
            "scope_id": paths["scope_id"],
        }
    except OSError as exc:
        return {
            "status": "clear_failed",
            "cache_path": str(manifest_path),
            "integrity_path": str(integrity_path),
            "cells_dir": str(cells_dir),
            "scope_id": paths["scope_id"],
            "error": f"{type(exc).__name__}: {exc}",
        }


__all__ = [
    "ABSENT_EMPTY_STORE_SIGNATURE",
    "RECALL_CACHE_INTEGRITY_BOUNDARY",
    "RECALL_CACHE_MODES",
    "RECALL_CACHE_SCHEMA_VERSION",
    "RECALL_CELL_PARTITION_COUNT",
    "RECALL_CELL_SCHEMA_VERSION",
    "RECALL_STORAGE_MODEL",
    "clear_recall_cache_unlocked",
    "get_recall_cache_status_unlocked",
    "load_or_build_recall_projection_unlocked",
]
