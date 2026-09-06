"""
Persistent SharedGraph snapshot cache.

The cache avoids reopening unchanged source files and repeating their import
parsing across CLI invocations. Filesystem discovery still runs once so
additions, mutations, and deletions can be invalidated at file granularity.

Security note: cache records contain source text. The default cache lives under
the portable tool directory and is written with owner-only permissions where
the platform supports chmod.
"""

import datetime
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

try:
    from core.shared_graph import (
        DEFAULT_IGNORE_DIRS,
        IMPORT_REGEX,
        SCHEMA_VERSION as SHARED_GRAPH_SCHEMA_VERSION,
        _read_file,
        _strip_comments,
        build_shared_graph,
        discover_source_files,
        graph_content_signature,
    )
except ImportError:
    from shared_graph import (  # type: ignore
        DEFAULT_IGNORE_DIRS,
        IMPORT_REGEX,
        SCHEMA_VERSION as SHARED_GRAPH_SCHEMA_VERSION,
        _read_file,
        _strip_comments,
        build_shared_graph,
        discover_source_files,
        graph_content_signature,
    )


CACHE_SCHEMA_VERSION = "shared-graph-cache-v2"
LEGACY_CACHE_SCHEMA_VERSIONS = ("shared-graph-cache-v1",)
PARSER_VERSION = f"imports-v1+shared-graph-{SHARED_GRAPH_SCHEMA_VERSION}"
CACHE_MODES = ("auto", "refresh", "off")

_TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_GRAPH_CACHE_DIR = os.path.join(_TOOL_ROOT, "data", "codebase", "cache")
STAT_TRUST_BOUNDARY = (
    "Unchanged means size, mtime_ns, and ctime_ns are identical. Filesystems "
    "that preserve all three values after a content mutation require "
    "--cache-mode refresh."
)


def _utc_now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _normalize_path(value: str) -> str:
    normalized = os.path.normpath(value).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _normalized_ignore_dirs(ignore_dirs: Optional[Iterable[str]]) -> List[str]:
    values = DEFAULT_IGNORE_DIRS if ignore_dirs is None else ignore_dirs
    return sorted({str(value) for value in values})


def _cache_identity(
    scan_root: str,
    ignore_dirs: Optional[Iterable[str]],
    cache_schema_version: str = CACHE_SCHEMA_VERSION,
) -> Dict[str, Any]:
    return {
        "root_absolute": _normalize_path(os.path.abspath(scan_root)),
        "graph_scan_root": _normalize_path(scan_root),
        "ignore_dirs": _normalized_ignore_dirs(ignore_dirs),
        "parser_version": PARSER_VERSION,
        "cache_schema_version": cache_schema_version,
    }


def _cache_key(identity: Dict[str, Any]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _cache_location(
    scan_root: str,
    ignore_dirs: Optional[Iterable[str]],
    cache_dir: Optional[str],
) -> Tuple[Dict[str, Any], str, str]:
    identity = _cache_identity(scan_root, ignore_dirs)
    key = _cache_key(identity)
    directory = os.path.abspath(cache_dir or DEFAULT_GRAPH_CACHE_DIR)
    return identity, key, os.path.join(directory, f"shared_graph_{key}.json")


def _legacy_cache_paths(
    scan_root: str,
    ignore_dirs: Optional[Iterable[str]],
    cache_dir: Optional[str],
) -> List[str]:
    directory = os.path.abspath(cache_dir or DEFAULT_GRAPH_CACHE_DIR)
    paths = []
    for schema_version in LEGACY_CACHE_SCHEMA_VERSIONS:
        identity = _cache_identity(
            scan_root,
            ignore_dirs,
            cache_schema_version=schema_version,
        )
        paths.append(
            os.path.join(directory, f"shared_graph_{_cache_key(identity)}.json")
        )
    return paths


def _remove_legacy_entries(
    scan_root: str,
    ignore_dirs: Optional[Iterable[str]],
    cache_dir: Optional[str],
) -> List[str]:
    removed = []
    for path in _legacy_cache_paths(scan_root, ignore_dirs, cache_dir):
        if not os.path.exists(path):
            continue
        try:
            os.unlink(path)
            removed.append(_display_cache_path(path))
        except OSError:
            pass
    return removed


def _display_cache_path(cache_path: str) -> str:
    absolute = os.path.abspath(cache_path)
    try:
        relative = os.path.relpath(absolute, _TOOL_ROOT)
    except ValueError:
        return _normalize_path(absolute)
    if relative != ".." and not relative.startswith(f"..{os.sep}"):
        return _normalize_path(relative)
    return _normalize_path(absolute)


def _content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def _valid_stat(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and all(
            isinstance(value.get(key), int)
            for key in ("size", "mtime_ns", "ctime_ns")
        )
    )


def _validate_record(record: Any) -> bool:
    if not isinstance(record, dict):
        return False
    content = record.get("content")
    imports = record.get("imports")
    if not isinstance(content, str) or not isinstance(imports, list):
        return False
    if not all(isinstance(value, str) for value in imports):
        return False
    if not _valid_stat(record.get("stat")):
        return False
    return record.get("content_sha256") == _content_hash(content)


def _load_cache(
    cache_path: str,
    identity: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not os.path.exists(cache_path):
        return None, None
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        return None, f"cache_read_error:{type(exc).__name__}"

    if not isinstance(payload, dict):
        return None, "cache_payload_not_object"
    if payload.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        return None, "cache_schema_mismatch"
    if payload.get("parser_version") != PARSER_VERSION:
        return None, "parser_version_mismatch"
    if payload.get("identity") != identity:
        return None, "cache_identity_mismatch"
    records = payload.get("files")
    if not isinstance(records, dict):
        return None, "cache_files_not_object"
    if not isinstance(payload.get("graph_content_signature"), str):
        return None, "cache_graph_signature_missing"
    if not all(
        isinstance(path, str) and _validate_record(record)
        for path, record in records.items()
    ):
        return None, "cache_record_invalid"
    return payload, None


def _stat_fingerprint(path: str) -> Optional[Dict[str, int]]:
    try:
        value = os.stat(path)
    except OSError:
        return None
    return {
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
        "ctime_ns": int(value.st_ctime_ns),
    }


def _read_record(
    path: str,
    discovered_stat: Dict[str, int],
) -> Optional[Dict[str, Any]]:
    """Read a stable-enough file snapshot, retrying once if stat changes."""
    expected_stat = discovered_stat
    content: Optional[str] = None
    final_stat: Optional[Dict[str, int]] = None
    for _ in range(2):
        content = _read_file(path)
        if content is None:
            return None
        final_stat = _stat_fingerprint(path)
        if final_stat is None:
            return None
        if final_stat == expected_stat:
            break
        expected_stat = final_stat

    if content is None or final_stat is None:
        return None
    imports = IMPORT_REGEX.findall(_strip_comments(content))
    return {
        "stat": final_stat,
        "content": content,
        "imports": imports,
        "content_sha256": _content_hash(content),
    }


def _write_cache(
    cache_path: str,
    identity: Dict[str, Any],
    records: Dict[str, Dict[str, Any]],
    created_at: Optional[str],
    graph_signature: str,
) -> Optional[str]:
    directory = os.path.dirname(cache_path)
    temporary_path: Optional[str] = None
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        payload = {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "identity": identity,
            "created_at": created_at or _utc_now(),
            "updated_at": _utc_now(),
            "contains_source_content": True,
            "stat_trust_boundary": STAT_TRUST_BOUNDARY,
            "graph_content_signature": graph_signature,
            "files": dict(sorted(records.items())),
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".shared_graph_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, cache_path)
        temporary_path = None
        try:
            os.chmod(cache_path, 0o600)
        except OSError:
            pass
        return None
    except Exception as exc:
        return f"cache_write_error:{type(exc).__name__}"
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def _metrics_base(
    mode: str,
    key: str,
    cache_path: str,
    discovered_count: int,
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "status": "miss",
        "cache_key": key,
        "cache_path": _display_cache_path(cache_path),
        "files_discovered": discovered_count,
        "files_reused": 0,
        "files_read": 0,
        "files_added": 0,
        "files_changed": 0,
        "files_deleted": 0,
        "read_failures": [],
        "hit_ratio": 0.0,
        "contains_source_content": True,
        "stat_trust_boundary": STAT_TRUST_BOUNDARY,
    }


def build_cached_shared_graph(
    scan_root: str = ".",
    ignore_dirs: Optional[Iterable[str]] = None,
    cache_dir: Optional[str] = None,
    mode: str = "auto",
) -> Dict[str, Any]:
    """Build SharedGraph with persistent file-level snapshot reuse."""
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in CACHE_MODES:
        raise ValueError(
            f"Unsupported graph cache mode: {mode}. Expected one of: {', '.join(CACHE_MODES)}"
        )

    ignored: Set[str] = set(_normalized_ignore_dirs(ignore_dirs))
    identity, key, cache_path = _cache_location(scan_root, ignored, cache_dir)

    if normalized_mode == "off":
        graph = build_shared_graph(scan_root, ignore_dirs=ignored)
        metrics = _metrics_base(
            normalized_mode,
            key,
            cache_path,
            graph.get("summary", {}).get("total_files", 0),
        )
        metrics.update({
            "status": "disabled",
            "files_read": graph.get("summary", {}).get("total_files", 0),
            "graph_content_signature": graph_content_signature(graph),
        })
        graph["cache"] = metrics
        return graph

    discovered = discover_source_files(scan_root, ignored)
    cached_payload, load_error = _load_cache(cache_path, identity)
    cached_records: Dict[str, Dict[str, Any]] = (
        cached_payload.get("files", {}) if cached_payload else {}
    )
    metrics = _metrics_base(normalized_mode, key, cache_path, len(discovered))
    if load_error:
        metrics["recovery_reason"] = load_error

    records: Dict[str, Dict[str, Any]] = {}
    for path, stat in discovered.items():
        cached_record = cached_records.get(path)
        may_reuse = (
            normalized_mode == "auto"
            and cached_record is not None
            and cached_record.get("stat") == stat
        )
        if may_reuse:
            records[path] = cached_record
            metrics["files_reused"] += 1
            continue

        record = _read_record(path, stat)
        if record is None:
            metrics["read_failures"].append(path)
            continue
        records[path] = record
        metrics["files_read"] += 1
        if path in cached_records:
            metrics["files_changed"] += 1
        else:
            metrics["files_added"] += 1

    deleted = sorted(set(cached_records) - set(discovered))
    metrics["files_deleted"] = len(deleted)
    if deleted:
        metrics["deleted_paths"] = deleted

    if normalized_mode == "refresh":
        status = "refreshed"
    elif load_error:
        status = "recovered"
    elif cached_payload is None:
        status = "miss"
    elif metrics["files_read"] == 0 and metrics["files_deleted"] == 0:
        status = "hit"
    else:
        status = "partial"
    metrics["status"] = status
    if not discovered and status == "hit":
        metrics["hit_ratio"] = 1.0
    else:
        metrics["hit_ratio"] = round(
            metrics["files_reused"] / max(1, len(discovered)),
            4,
        )

    snapshot = {
        path: {"content": record["content"], "imports": record["imports"]}
        for path, record in records.items()
    }
    graph = build_shared_graph(
        scan_root,
        ignore_dirs=ignored,
        _file_snapshot=snapshot,
    )
    signature = graph_content_signature(graph)
    metrics["graph_content_signature"] = signature
    if (
        status == "hit"
        and cached_payload is not None
        and cached_payload.get("graph_content_signature") != signature
    ):
        status = "recovered"
        metrics["status"] = status
        metrics["recovery_reason"] = "cache_graph_signature_mismatch"

    should_write = status != "hit" or bool(metrics["read_failures"])
    if should_write:
        write_error = _write_cache(
            cache_path,
            identity,
            records,
            cached_payload.get("created_at") if cached_payload else None,
            signature,
        )
        if write_error:
            metrics["status_before_write"] = metrics["status"]
            metrics["status"] = "write_failed"
            metrics["write_error"] = write_error
        else:
            legacy_removed = _remove_legacy_entries(
                scan_root,
                ignored,
                cache_dir,
            )
            if legacy_removed:
                metrics["legacy_entries_removed"] = legacy_removed

    graph["cache"] = metrics
    return graph


def get_graph_cache_status(
    scan_root: str = ".",
    ignore_dirs: Optional[Iterable[str]] = None,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspect cache freshness using stat metadata without reading sources."""
    ignored: Set[str] = set(_normalized_ignore_dirs(ignore_dirs))
    identity, key, cache_path = _cache_location(scan_root, ignored, cache_dir)
    discovered = discover_source_files(scan_root, ignored)
    cached_payload, load_error = _load_cache(cache_path, identity)
    result: Dict[str, Any] = {
        "cache_key": key,
        "cache_path": _display_cache_path(cache_path),
        "files_discovered": len(discovered),
        "contains_source_content": True,
        "stat_trust_boundary": STAT_TRUST_BOUNDARY,
    }
    if load_error:
        result.update({"status": "corrupt", "reason": load_error})
        return result
    if cached_payload is None:
        legacy_paths = [
            _display_cache_path(path)
            for path in _legacy_cache_paths(scan_root, ignored, cache_dir)
            if os.path.exists(path)
        ]
        result.update({
            "status": "missing",
            "files_reusable": 0,
            "files_added": len(discovered),
            "files_changed": 0,
            "files_deleted": 0,
        })
        if legacy_paths:
            result["legacy_entries_found"] = legacy_paths
        return result

    records = cached_payload.get("files", {})
    reusable = sum(
        1
        for path, stat in discovered.items()
        if path in records and records[path].get("stat") == stat
    )
    added = sum(1 for path in discovered if path not in records)
    changed = sum(
        1
        for path, stat in discovered.items()
        if path in records and records[path].get("stat") != stat
    )
    deleted = len(set(records) - set(discovered))
    status = "valid" if not (added or changed or deleted) else "stale"
    result.update({
        "status": status,
        "files_reusable": reusable,
        "files_added": added,
        "files_changed": changed,
        "files_deleted": deleted,
        "created_at": cached_payload.get("created_at"),
        "updated_at": cached_payload.get("updated_at"),
        "graph_content_signature": cached_payload.get("graph_content_signature"),
    })
    return result


def clear_graph_cache(
    scan_root: str = ".",
    ignore_dirs: Optional[Iterable[str]] = None,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Delete only the cache entry associated with one root/configuration."""
    ignored: Set[str] = set(_normalized_ignore_dirs(ignore_dirs))
    identity, key, cache_path = _cache_location(scan_root, ignored, cache_dir)
    del identity  # Key calculation is the only identity use needed here.
    paths = [cache_path, *_legacy_cache_paths(scan_root, ignored, cache_dir)]
    existing_paths = [path for path in paths if os.path.exists(path)]
    removed_paths = []
    for path in existing_paths:
        try:
            os.unlink(path)
            removed_paths.append(_display_cache_path(path))
        except OSError as exc:
            return {
                "status": "clear_failed",
                "cache_key": key,
                "cache_path": _display_cache_path(path),
                "removed": bool(removed_paths),
                "removed_paths": removed_paths,
                "error": f"cache_clear_error:{type(exc).__name__}",
            }
    return {
        "status": "cleared" if removed_paths else "already_missing",
        "cache_key": key,
        "cache_path": _display_cache_path(cache_path),
        "removed": bool(removed_paths),
        "removed_paths": removed_paths,
    }


__all__ = [
    "CACHE_MODES",
    "CACHE_SCHEMA_VERSION",
    "LEGACY_CACHE_SCHEMA_VERSIONS",
    "DEFAULT_GRAPH_CACHE_DIR",
    "PARSER_VERSION",
    "STAT_TRUST_BOUNDARY",
    "build_cached_shared_graph",
    "clear_graph_cache",
    "get_graph_cache_status",
]
