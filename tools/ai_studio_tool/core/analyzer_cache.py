"""Persistent cache for deterministic analyzer evidence.

The source snapshot cache prevents repeated target-file reads. This layer sits
above it and prevents all registered analyzers from recomputing evidence when
both the graph content and analyzer implementation are unchanged.
"""

import datetime
import hashlib
import json
import os
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from core.analyzer_registry import (
        get_analyzer_engine_signature,
        get_available_analyzers,
        run_analyzers,
    )
    from core.graph_cache import CACHE_MODES, DEFAULT_GRAPH_CACHE_DIR
    from core.shared_graph import graph_content_signature
except ImportError:
    from analyzer_registry import (  # type: ignore
        get_analyzer_engine_signature,
        get_available_analyzers,
        run_analyzers,
    )
    from graph_cache import CACHE_MODES, DEFAULT_GRAPH_CACHE_DIR  # type: ignore
    from shared_graph import graph_content_signature  # type: ignore


ANALYZER_CACHE_SCHEMA_VERSION = "analyzer-evidence-cache-v1"
DEFAULT_ANALYZER_CACHE_DIR = os.path.join(DEFAULT_GRAPH_CACHE_DIR, "analyzers")


def _utc_now() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _unique_names(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        name = str(value)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _source_cache_key(shared_graph: Dict[str, Any]) -> str:
    key = shared_graph.get("cache", {}).get("cache_key")
    if isinstance(key, str) and key:
        return key
    scan_root = str(shared_graph.get("scan_root", ""))
    fallback = "\0".join([
        "analyzer-root-v1",
        os.path.abspath(scan_root) if scan_root else "in-memory-graph",
    ])
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]


def _cache_path(source_cache_key: str, cache_dir: Optional[str]) -> str:
    if (
        len(source_cache_key) != 24
        or any(char not in "0123456789abcdef" for char in source_cache_key)
    ):
        raise ValueError("Invalid source cache key")
    directory = os.path.abspath(cache_dir or DEFAULT_ANALYZER_CACHE_DIR)
    return os.path.join(directory, f"analyzers_{source_cache_key}.json")


def _display_path(path: str) -> str:
    tool_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    absolute = os.path.abspath(path)
    try:
        relative = os.path.relpath(absolute, tool_root)
    except ValueError:
        return absolute.replace("\\", "/")
    if relative != ".." and not relative.startswith(f"..{os.sep}"):
        return relative.replace("\\", "/")
    return absolute.replace("\\", "/")


def _results_digest(results: Dict[str, Any]) -> str:
    encoded = json.dumps(
        results,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _load_cache(
    path: str,
    source_cache_key: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        return None, f"analyzer_cache_read_error:{type(exc).__name__}"

    if not isinstance(payload, dict):
        return None, "analyzer_cache_payload_not_object"
    if payload.get("schema_version") != ANALYZER_CACHE_SCHEMA_VERSION:
        return None, "analyzer_cache_schema_mismatch"
    if payload.get("source_cache_key") != source_cache_key:
        return None, "analyzer_cache_identity_mismatch"
    if not isinstance(payload.get("graph_content_signature"), str):
        return None, "analyzer_cache_graph_signature_missing"
    if not isinstance(payload.get("engine_signature"), str):
        return None, "analyzer_cache_engine_signature_missing"
    results = payload.get("results")
    if not isinstance(results, dict):
        return None, "analyzer_cache_results_not_object"
    if any(
        not isinstance(name, str)
        or not isinstance(result, dict)
        or bool(result.get("error"))
        for name, result in results.items()
    ):
        return None, "analyzer_cache_result_invalid"
    if payload.get("results_sha256") != _results_digest(results):
        return None, "analyzer_cache_checksum_mismatch"
    return payload, None


def _write_cache(
    path: str,
    source_cache_key: str,
    graph_signature: str,
    engine_signature: str,
    results: Dict[str, Any],
    created_at: Optional[str],
) -> Optional[str]:
    directory = os.path.dirname(path)
    temporary_path: Optional[str] = None
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        payload = {
            "schema_version": ANALYZER_CACHE_SCHEMA_VERSION,
            "source_cache_key": source_cache_key,
            "graph_content_signature": graph_signature,
            "engine_signature": engine_signature,
            "created_at": created_at or _utc_now(),
            "updated_at": _utc_now(),
            "contains_full_source_content": False,
            "contains_derived_source_evidence": True,
            "results": dict(sorted(results.items())),
        }
        payload["results_sha256"] = _results_digest(payload["results"])
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".analyzers_",
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
        os.replace(temporary_path, path)
        temporary_path = None
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return None
    except Exception as exc:
        return f"analyzer_cache_write_error:{type(exc).__name__}"
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def _base_metrics(
    mode: str,
    path: str,
    source_cache_key: str,
    graph_signature: str,
    engine_signature: str,
    requested: List[str],
) -> Dict[str, Any]:
    return {
        "mode": mode,
        "status": "miss",
        "cache_path": _display_path(path),
        "source_cache_key": source_cache_key,
        "graph_content_signature": graph_signature,
        "engine_signature": engine_signature,
        "analyzers_requested": requested,
        "analyzers_reused": [],
        "analyzers_executed": [],
        "reused_count": 0,
        "executed_count": 0,
        "hit_ratio": 0.0,
        "contains_full_source_content": False,
        "contains_derived_source_evidence": True,
    }


def run_cached_analyzers(
    shared_graph: Dict[str, Any],
    analyzer_names: Optional[List[str]] = None,
    cache_dir: Optional[str] = None,
    mode: str = "auto",
) -> Dict[str, Any]:
    """Run or reuse analyzer outputs under exact graph and code signatures."""
    normalized_mode = str(mode).strip().lower()
    if normalized_mode not in CACHE_MODES:
        raise ValueError(
            f"Unsupported analyzer cache mode: {mode}. "
            f"Expected one of: {', '.join(CACHE_MODES)}"
        )
    requested = _unique_names(
        analyzer_names if analyzer_names is not None else get_available_analyzers()
    )
    source_key = _source_cache_key(shared_graph)
    graph_signature = graph_content_signature(shared_graph)
    engine_signature = get_analyzer_engine_signature()
    path = _cache_path(source_key, cache_dir)
    metrics = _base_metrics(
        normalized_mode,
        path,
        source_key,
        graph_signature,
        engine_signature,
        requested,
    )

    if normalized_mode == "off":
        output = run_analyzers(shared_graph, requested)
        metrics.update({
            "status": "disabled",
            "analyzers_executed": requested,
            "executed_count": len(requested),
        })
        output["cache"] = metrics
        return output

    payload, load_error = _load_cache(path, source_key)
    compatible = bool(
        payload
        and payload.get("graph_content_signature") == graph_signature
        and payload.get("engine_signature") == engine_signature
    )
    if load_error:
        metrics["recovery_reason"] = load_error
    elif payload and not compatible:
        reasons = []
        if payload.get("graph_content_signature") != graph_signature:
            reasons.append("graph_content_changed")
        if payload.get("engine_signature") != engine_signature:
            reasons.append("analyzer_engine_changed")
        metrics["invalidation_reasons"] = reasons

    cached_results = payload.get("results", {}) if compatible and payload else {}
    reused_names = (
        [name for name in requested if name in cached_results]
        if normalized_mode == "auto"
        else []
    )
    execute_names = [name for name in requested if name not in reused_names]
    fresh = (
        run_analyzers(shared_graph, execute_names)
        if execute_names
        else {
            "analyzers_run": [],
            "analyzers_succeeded": [],
            "analyzers_failed": 0,
            "errors": {},
            "results": {},
        }
    )

    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    succeeded: List[str] = []
    for name in requested:
        result = (
            cached_results[name]
            if name in reused_names
            else fresh.get("results", {}).get(name, {})
        )
        results[name] = result
        if isinstance(result, dict) and result.get("error"):
            errors[name] = str(result.get("error"))
        else:
            succeeded.append(name)

    if normalized_mode == "refresh":
        status = "refreshed"
    elif load_error:
        status = "recovered"
    elif payload and not compatible:
        status = "invalidated"
    elif payload is None:
        status = "miss"
    elif not execute_names:
        status = "hit"
    elif reused_names:
        status = "partial"
    else:
        status = "miss"

    metrics.update({
        "status": status,
        "analyzers_reused": reused_names,
        "analyzers_executed": execute_names,
        "reused_count": len(reused_names),
        "executed_count": len(execute_names),
        "hit_ratio": round(len(reused_names) / max(1, len(requested)), 4),
    })

    stored_results = dict(cached_results) if compatible else {}
    for name in execute_names:
        result = fresh.get("results", {}).get(name, {})
        if isinstance(result, dict) and not result.get("error"):
            stored_results[name] = result
        else:
            stored_results.pop(name, None)

    should_write = status != "hit"
    if should_write:
        write_error = _write_cache(
            path,
            source_key,
            graph_signature,
            engine_signature,
            stored_results,
            payload.get("created_at") if compatible and payload else None,
        )
        if write_error:
            metrics["status_before_write"] = metrics["status"]
            metrics["status"] = "write_failed"
            metrics["write_error"] = write_error

    return {
        "analyzers_run": requested,
        "analyzers_succeeded": succeeded,
        "analyzers_failed": len(errors),
        "errors": errors,
        "results": results,
        "cache": metrics,
    }


def get_analyzer_cache_status(
    source_cache_key: str,
    graph_signature: Optional[str] = None,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Inspect one analyzer cache entry without executing analyzers."""
    path = _cache_path(source_cache_key, cache_dir)
    payload, load_error = _load_cache(path, source_cache_key)
    result: Dict[str, Any] = {
        "cache_path": _display_path(path),
        "source_cache_key": source_cache_key,
        "contains_full_source_content": False,
        "contains_derived_source_evidence": True,
    }
    if load_error:
        return {**result, "status": "corrupt", "reason": load_error}
    if payload is None:
        return {**result, "status": "missing", "analyzer_count": 0}

    engine_signature = get_analyzer_engine_signature()
    reasons = []
    if payload.get("engine_signature") != engine_signature:
        reasons.append("analyzer_engine_changed")
    if graph_signature and payload.get("graph_content_signature") != graph_signature:
        reasons.append("graph_content_changed")
    return {
        **result,
        "status": "stale" if reasons else "valid",
        "stale_reasons": reasons,
        "analyzer_count": len(payload.get("results", {})),
        "graph_content_signature": payload.get("graph_content_signature"),
        "engine_signature": payload.get("engine_signature"),
        "created_at": payload.get("created_at"),
        "updated_at": payload.get("updated_at"),
    }


def clear_analyzer_cache(
    source_cache_key: str,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove the analyzer cache paired with one source-cache identity."""
    path = _cache_path(source_cache_key, cache_dir)
    existed = os.path.exists(path)
    if existed:
        try:
            os.unlink(path)
        except OSError as exc:
            return {
                "status": "clear_failed",
                "cache_path": _display_path(path),
                "removed": False,
                "error": f"analyzer_cache_clear_error:{type(exc).__name__}",
            }
    return {
        "status": "cleared" if existed else "already_missing",
        "cache_path": _display_path(path),
        "removed": existed,
    }


__all__ = [
    "ANALYZER_CACHE_SCHEMA_VERSION",
    "DEFAULT_ANALYZER_CACHE_DIR",
    "clear_analyzer_cache",
    "get_analyzer_cache_status",
    "run_cached_analyzers",
]
