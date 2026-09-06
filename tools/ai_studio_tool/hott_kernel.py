"""
HoTT Kernel — Unified Entry Point
Schema Version: 3.0.0-kernel

Single entry point untuk seluruh analisis codebase.
Menggantikan 13 tool calls terpisah menjadi 1.

Usage:
    python3 hott_kernel.py analyze src
    python3 hott_kernel.py analyze src --analyzers topo.orphan,topo.entrypoint
    python3 hott_kernel.py analyzers
"""

import os
import sys
import json
import hashlib
import datetime
from typing import Any, Dict, List, Optional

# Import kernel components
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    from core.shared_graph import (
        SOURCE_EXTENSIONS,
        build_shared_graph,
        graph_content_signature,
    )
    SHARED_GRAPH_AVAILABLE = True
except ImportError:
    try:
        from shared_graph import (
            SOURCE_EXTENSIONS,
            build_shared_graph,
            graph_content_signature,
        )
        SHARED_GRAPH_AVAILABLE = True
    except ImportError:
        SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
        graph_content_signature = None
        SHARED_GRAPH_AVAILABLE = False

try:
    from core.graph_cache import (
        CACHE_MODES,
        build_cached_shared_graph,
        clear_graph_cache,
        get_graph_cache_status,
    )
    GRAPH_CACHE_AVAILABLE = True
except ImportError:
    CACHE_MODES = ("auto", "refresh", "off")
    GRAPH_CACHE_AVAILABLE = False

try:
    from core.analyzer_registry import run_analyzers, get_available_analyzers
    REGISTRY_AVAILABLE = True
except ImportError:
    try:
        from analyzer_registry import run_analyzers, get_available_analyzers
        REGISTRY_AVAILABLE = True
    except ImportError:
        REGISTRY_AVAILABLE = False

try:
    from core.analyzer_cache import (
        clear_analyzer_cache,
        get_analyzer_cache_status,
        run_cached_analyzers,
    )
    ANALYZER_CACHE_AVAILABLE = True
except ImportError:
    ANALYZER_CACHE_AVAILABLE = False

try:
    from core.context_optimizer import (
        DEFAULT_BUDGET_TOKENS,
        DEFAULT_MAX_HOPS,
        MAX_BUDGET_TOKENS,
        MAX_HOPS,
        MIN_BUDGET_TOKENS,
        build_context_pack,
    )
    CONTEXT_OPTIMIZER_AVAILABLE = True
except ImportError:
    CONTEXT_OPTIMIZER_AVAILABLE = False

try:
    from codebase.targeted_queries import query_impact, query_outline, query_brief
    TOPO_QUERIES_AVAILABLE = True
except ImportError:
    try:
        from topology_analyzers import query_impact, query_outline, query_brief
        TOPO_QUERIES_AVAILABLE = True
    except ImportError:
        TOPO_QUERIES_AVAILABLE = False

try:
    from core.synthesizer import encode_topological_invariants
    ENCODER_AVAILABLE = True
except ImportError:
    try:
        from invariant_encoder import encode_topological_invariants
        ENCODER_AVAILABLE = True
    except ImportError:
        ENCODER_AVAILABLE = False

try:
    from core.synthesizer import establish_baseline, steer_decoder
    STEERING_AVAILABLE = True
except ImportError:
    try:
        from decoder_steering import establish_baseline, steer_decoder
        STEERING_AVAILABLE = True
    except ImportError:
        STEERING_AVAILABLE = False

try:
    from memory.store import (
        store_memory, recall_memories, get_memory_stats,
        store_association, consolidate_memories,
    )
    from memory.graph import build_memory_graph
    from memory.analyzers import run_memory_analyzers
    MEMORY_AVAILABLE = True
except ImportError:
    try:
        from memory_store import (
            store_memory, recall_memories, get_memory_stats,
            store_association, consolidate_memories,
        )
        from memory_graph import build_memory_graph
        from memory_analyzers import run_memory_analyzers
        MEMORY_AVAILABLE = True
    except ImportError:
        MEMORY_AVAILABLE = False

try:
    from memory.store import (
        clear_memory_recall_cache,
        get_memory_recall_cache_status,
        refresh_memory_recall_cache,
    )
    MEMORY_RECALL_CACHE_AVAILABLE = True
except ImportError:
    try:
        from memory_store import (
            clear_memory_recall_cache,
            get_memory_recall_cache_status,
            refresh_memory_recall_cache,
        )
        MEMORY_RECALL_CACHE_AVAILABLE = True
    except ImportError:
        MEMORY_RECALL_CACHE_AVAILABLE = False

try:
    from memory.synthesizer import (
        compute_memory_fingerprint,
        establish_memory_baseline,
        load_memory_baseline,
        detect_memory_drift,
        generate_memory_steering_signals,
        assemble_memory_prompt_block,
    )
    MEMORY_SYNTH_AVAILABLE = True
except ImportError:
    try:
        from memory_synthesizer import (
            compute_memory_fingerprint,
            establish_memory_baseline,
            load_memory_baseline,
            detect_memory_drift,
            generate_memory_steering_signals,
            assemble_memory_prompt_block,
        )
        MEMORY_SYNTH_AVAILABLE = True
    except ImportError:
        MEMORY_SYNTH_AVAILABLE = False

try:
    from bridge.xanalyze import (
        filter_findings_for_memory,
        auto_store_findings,
        check_consolidation_trigger,
    )
    from bridge.xsteer import cross_domain_steer
    from bridge.xcontext import get_memory_context_for_file, get_memory_evidence
    CROSS_DOMAIN_AVAILABLE = True
except ImportError:
    try:
        from cross_domain_bridge import (
            filter_findings_for_memory,
            auto_store_findings,
            check_consolidation_trigger,
            cross_domain_steer,
            get_memory_context_for_file,
            get_memory_evidence,
        )
        CROSS_DOMAIN_AVAILABLE = True
    except ImportError:
        CROSS_DOMAIN_AVAILABLE = False

try:
    from memory.runtime import (
        MemoryStateError,
        configure_memory_runtime,
        memory_runtime_provenance,
    )
    MEMORY_RUNTIME_AVAILABLE = True
except ImportError:
    MEMORY_RUNTIME_AVAILABLE = False

    class MemoryStateError(RuntimeError):
        """Fallback exception type when the optional memory runtime is absent."""

        error_code = "memory_state_error"
        details: Dict[str, Any] = {}

try:
    from context.fibration import (
        init_fiber, lift_to_fiber, descend_from_fiber,
        start_section, add_to_section, get_section_status,
        fiber_status, switch_base,
        transport_from_archive, list_archived_fibers,
    )
    FIBRATION_AVAILABLE = True
except ImportError:
    try:
        from memory_fibration import (
            init_fiber, lift_to_fiber, descend_from_fiber,
            start_section, add_to_section, get_section_status,
            fiber_status, switch_base,
            transport_from_archive, list_archived_fibers,
        )
        FIBRATION_AVAILABLE = True
    except ImportError:
        FIBRATION_AVAILABLE = False

try:
    from memory.kan_extension import kan_retrieve
    KAN_EXTENSION_AVAILABLE = True
except ImportError:
    try:
        from memory_kan_extension import kan_retrieve
        KAN_EXTENSION_AVAILABLE = True
    except ImportError:
        KAN_EXTENSION_AVAILABLE = False


CODEBASE_SCHEMA_VERSION = "3.0.0-kernel"
_ACTIVE_GRAPH_CACHE_MODE = os.environ.get(
    "AI_STUDIO_GRAPH_CACHE",
    "auto",
).strip().lower()
_MEMORY_SCOPE_EXPLICIT = any(
    os.environ.get(name)
    for name in (
        "AI_STUDIO_PROJECT_ROOT",
        "AI_STUDIO_MEMORY_SCOPE",
    )
)


def _utc_timestamp() -> str:
    """Return an explicit UTC timestamp without deprecated naive datetime APIs."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _kernel_error(error_code: str, message: str, **details: Any) -> Dict[str, Any]:
    """Build a stable machine-readable error payload for CLI and API callers."""
    return {
        "schema_version": CODEBASE_SCHEMA_VERSION,
        "error": message,
        "error_code": error_code,
        **details,
    }


def _infer_project_root(scan_root: str) -> str:
    """Infer the nearest project boundary without coupling to Angular names."""
    scan_path = os.path.abspath(scan_root)
    candidate = scan_path if os.path.isdir(scan_path) else os.path.dirname(scan_path)
    markers = ("package.json", "tsconfig.json", "pyproject.toml", ".git")
    current = candidate
    for _ in range(6):
        if any(os.path.exists(os.path.join(current, marker)) for marker in markers):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    if os.path.basename(candidate).lower() in ("src", "source"):
        return os.path.dirname(candidate)
    return candidate


def _bind_memory_scope_to_scan(scan_root: str) -> None:
    """Keep scan-backed memory isolated even when the CLI runs outside a project."""
    if not MEMORY_RUNTIME_AVAILABLE or _MEMORY_SCOPE_EXPLICIT:
        return
    configure_memory_runtime(project_root=_infer_project_root(scan_root))


def _validate_scan_root(scan_root: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(scan_root):
        return _kernel_error(
            "scan_root_not_found",
            f"Scan root does not exist: {scan_root}",
            scan_root=scan_root,
        )
    if not os.path.isdir(scan_root):
        return _kernel_error(
            "scan_root_not_directory",
            f"Scan root is not a directory: {scan_root}",
            scan_root=scan_root,
        )
    return None


def _validate_output_mode(
    output_mode: str,
    allowed: tuple[str, ...],
) -> Optional[Dict[str, Any]]:
    if output_mode in allowed:
        return None
    return _kernel_error(
        "invalid_output_mode",
        f"Invalid output mode: {output_mode}",
        output_mode=output_mode,
        supported_output_modes=list(allowed),
    )


def _set_graph_cache_mode(mode: str) -> Optional[Dict[str, Any]]:
    """Validate and activate one cache policy for this kernel process."""
    global _ACTIVE_GRAPH_CACHE_MODE
    normalized = str(mode).strip().lower()
    if normalized not in CACHE_MODES:
        return _kernel_error(
            "invalid_graph_cache_mode",
            f"Invalid graph cache mode: {mode}",
            cache_mode=mode,
            supported_cache_modes=list(CACHE_MODES),
        )
    _ACTIVE_GRAPH_CACHE_MODE = normalized
    return None


def _build_kernel_graph(scan_root: str) -> Dict[str, Any]:
    """Build the canonical graph using the active cross-invocation cache policy."""
    if GRAPH_CACHE_AVAILABLE:
        return build_cached_shared_graph(
            scan_root,
            mode=_ACTIVE_GRAPH_CACHE_MODE,
        )
    graph = build_shared_graph(scan_root)
    graph["cache"] = {
        "mode": "off",
        "status": "unavailable",
        "files_discovered": graph.get("summary", {}).get("total_files", 0),
        "files_reused": 0,
        "files_read": graph.get("summary", {}).get("total_files", 0),
        "hit_ratio": 0.0,
    }
    return graph


def _run_kernel_analyzers(
    graph: Dict[str, Any],
    analyzer_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run analyzers under the same cache policy as the canonical graph."""
    if not REGISTRY_AVAILABLE:
        return {
            "analyzers_run": [],
            "analyzers_succeeded": [],
            "analyzers_failed": 0,
            "errors": {},
            "results": {},
            "cache": {
                "mode": "off",
                "status": "unavailable",
                "analyzers_requested": analyzer_names or [],
                "analyzers_reused": [],
                "analyzers_executed": [],
                "reused_count": 0,
                "executed_count": 0,
                "hit_ratio": 0.0,
            },
        }
    if ANALYZER_CACHE_AVAILABLE:
        return run_cached_analyzers(
            graph,
            analyzer_names,
            mode=_ACTIVE_GRAPH_CACHE_MODE,
        )

    output = run_analyzers(graph, analyzer_names)
    executed = list(output.get("analyzers_run", []))
    output["cache"] = {
        "mode": "off",
        "status": "unavailable",
        "analyzers_requested": executed,
        "analyzers_reused": [],
        "analyzers_executed": executed,
        "reused_count": 0,
        "executed_count": len(executed),
        "hit_ratio": 0.0,
    }
    return output


def kernel_cache(action: str, scan_root: str = ".") -> Dict[str, Any]:
    """Manage source, analyzer, and scoped memory-recall derived caches."""
    if not GRAPH_CACHE_AVAILABLE:
        return _kernel_error(
            "graph_cache_unavailable",
            "persistent graph cache module is not available",
        )
    if action not in ("status", "refresh", "clear"):
        return _kernel_error(
            "invalid_cache_action",
            f"Invalid cache action: {action}",
            action=action,
            supported_actions=["status", "refresh", "clear"],
        )
    if action != "clear":
        root_error = _validate_scan_root(scan_root)
        if root_error:
            return root_error
    _bind_memory_scope_to_scan(scan_root)
    if action == "status":
        cache_result = get_graph_cache_status(scan_root)
        if ANALYZER_CACHE_AVAILABLE:
            analyzer_cache_result = get_analyzer_cache_status(
                cache_result.get("cache_key", ""),
                cache_result.get("graph_content_signature"),
            )
            source_status = cache_result.get("status")
            if (
                source_status != "valid"
                and analyzer_cache_result.get("status") not in ("missing", "corrupt")
            ):
                stale_reasons = list(analyzer_cache_result.get("stale_reasons", []))
                reason = f"source_snapshot_{source_status}"
                if reason not in stale_reasons:
                    stale_reasons.append(reason)
                analyzer_cache_result.update({
                    "status": "stale",
                    "stale_reasons": stale_reasons,
                })
            cache_result["analyzer_cache"] = analyzer_cache_result
        else:
            cache_result["analyzer_cache"] = {"status": "unavailable"}
        cache_result["memory_recall_cache"] = (
            get_memory_recall_cache_status()
            if MEMORY_RECALL_CACHE_AVAILABLE
            else {"status": "unavailable"}
        )
    elif action == "clear":
        cache_result = clear_graph_cache(scan_root)
        if cache_result.get("status") == "clear_failed":
            return _kernel_error(
                "graph_cache_clear_failed",
                "persistent graph cache entry could not be removed",
                scan_root=scan_root,
                cache=cache_result,
            )
        if ANALYZER_CACHE_AVAILABLE:
            analyzer_cache_result = clear_analyzer_cache(
                cache_result.get("cache_key", ""),
            )
            cache_result["analyzer_cache"] = analyzer_cache_result
            if analyzer_cache_result.get("status") == "clear_failed":
                return _kernel_error(
                    "analyzer_cache_clear_failed",
                    "persistent analyzer cache entry could not be removed",
                    scan_root=scan_root,
                    cache=cache_result,
                )
        else:
            cache_result["analyzer_cache"] = {"status": "unavailable"}
        memory_cache_result = (
            clear_memory_recall_cache()
            if MEMORY_RECALL_CACHE_AVAILABLE
            else {"status": "unavailable"}
        )
        cache_result["memory_recall_cache"] = memory_cache_result
        if memory_cache_result.get("status") == "clear_failed":
            return _kernel_error(
                "memory_recall_cache_clear_failed",
                "derived memory recall cache could not be removed",
                scan_root=scan_root,
                cache=cache_result,
            )
    else:
        graph = build_cached_shared_graph(scan_root, mode="refresh")
        analyzer_output = (
            run_cached_analyzers(graph, mode="refresh")
            if ANALYZER_CACHE_AVAILABLE and REGISTRY_AVAILABLE
            else _run_kernel_analyzers(graph)
        )
        cache_result = graph.get("cache", {})
        cache_result = {
            **cache_result,
            "analyzer_cache": analyzer_output.get("cache", {}),
            "memory_recall_cache": (
                refresh_memory_recall_cache()
                if MEMORY_RECALL_CACHE_AVAILABLE
                else {"status": "unavailable"}
            ),
            "graph_summary": graph.get("summary", {}),
        }
        if cache_result["memory_recall_cache"].get("status") == "write_failed":
            return _kernel_error(
                "memory_recall_cache_refresh_failed",
                "derived memory recall cache could not be refreshed",
                scan_root=scan_root,
                cache=cache_result,
            )
    return {
        "schema_version": CODEBASE_SCHEMA_VERSION,
        "mode": "cache",
        "action": action,
        "scan_root": scan_root,
        "cache": cache_result,
    }


def _analysis_status(total_files: int, analyzers_failed: int = 0) -> Dict[str, Any]:
    """Describe whether a supported TS/JS analysis domain was discovered."""
    if total_files <= 0:
        state = "empty"
    elif analyzers_failed > 0:
        state = "partial"
    else:
        state = "complete"
    status = {
        "analysis_status": state,
        "supported_source_extensions": list(SOURCE_EXTENSIONS),
    }
    if total_files == 0:
        status["analysis_warning"] = (
            "No supported TypeScript/JavaScript source files were found in scan_root."
        )
    return status


def _emit_cli_result(result: Dict[str, Any]) -> None:
    """Print one JSON result and expose a reliable status to Bash callers."""
    print(json.dumps(result, indent=2))
    if result.get("error"):
        raise SystemExit(2)
    if result.get("unified_summary", {}).get("analyzers_failed", 0) > 0:
        raise SystemExit(3)


def _exception_result(exc: Exception) -> Dict[str, Any]:
    """Preserve typed durable-state failures for the top-level CLI boundary."""
    if isinstance(exc, MemoryStateError):
        raise exc
    error_code = getattr(exc, "error_code", None)
    if error_code:
        return _kernel_error(
            str(error_code),
            str(exc),
            **getattr(exc, "details", {}),
        )
    return {"error": str(exc)}


def kernel_memory_store(
    memory_type: str,
    content: str,
    source: str = "manual",
    importance: float = 0.5,
    tags: Optional[str] = None,
) -> Dict[str, Any]:
    """Simpan memori baru."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    try:
        memory = store_memory(
            memory_type=memory_type,
            content=content,
            source=source,
            importance=importance,
            tags=tag_list,
        )
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_store",
            "status": "stored",
            "memory": memory,
            "memory_scope": memory_runtime_provenance() if MEMORY_RUNTIME_AVAILABLE else {},
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_recall(
    query: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Recall memori berdasarkan filter."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    results = recall_memories(
        query=query,
        memory_type=memory_type,
        tags=tag_list,
        limit=limit,
        cache_mode=_ACTIVE_GRAPH_CACHE_MODE,
    )

    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_recall",
        "query": query,
        "memory_type": memory_type,
        "results": results,
        "count": len(results),
        "memory_scope": memory_runtime_provenance() if MEMORY_RUNTIME_AVAILABLE else {},
    }


def kernel_memory_analyze(
    analyzer_names: Optional[List[str]] = None,
    output_mode: str = "full",
    include_historical: bool = False,
    include_provenance: bool = False,
) -> Dict[str, Any]:
    """Analisis topologi memori."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    memory_graph = build_memory_graph(
        include_historical=include_historical,
        include_provenance=include_provenance,
    )
    analyzer_output = run_memory_analyzers(memory_graph, analyzer_names)

    total_findings = sum(
        len(r.get("findings", []))
        for r in analyzer_output.get("results", {}).values()
    )
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for r in analyzer_output.get("results", {}).values():
        for f in r.get("findings", []):
            sev = f.get("severity", "low")
            if sev in severity_counts:
                severity_counts[sev] += 1

    total_memories = memory_graph["summary"]["total_memories"]
    weighted_sum = (
        severity_counts["high"] * 3
        + severity_counts["medium"] * 2
        + severity_counts["low"] * 1
    )
    pressure = weighted_sum / max(1, total_memories)
    health_score = round(1.0 / (1.0 + pressure), 3)
    health_model = {
        "name": "severity_weighted_structural_pressure_v1",
        "formula": "1 / (1 + weighted_finding_count / max(1, current_vertices))",
        "weighted_finding_count": weighted_sum,
        "structural_pressure": round(pressure, 6),
        "not_correctness_or_truth_score": True,
        "healthy_fragmentation_possible": True,
        "bridge_requires_relation_witness": True,
    }
    betti_breakdown = analyzer_output.get("results", {}).get(
        "mem.betti_breakdown", {}
    )
    betti_data = betti_breakdown.get("betti_numbers", {})
    betti_numbers = {
        "beta_0": int(betti_data.get("beta_0", 0)),
        "beta_1": int(betti_data.get("beta_1_total", 0)),
        "beta_2": 0,
    }
    memory_archetype = analyzer_output.get("results", {}).get(
        "mem.manifold", {}
    ).get("summary", {}).get("memory_archetype", "unknown")
    circular_summary = analyzer_output.get("results", {}).get(
        "mem.circular", {}
    ).get("summary", {})
    cycle_semantics = {
        "beta_1_is_not_directed_cycle_count": True,
        "directed_reasoning_cycle_witness_count": (
            betti_breakdown.get("summary", {}).get(
                "directed_reasoning_cycle_witness_count", 0
            )
        ),
        "directed_cycle_witness_semantics": circular_summary.get(
            "directed_cycle_witness_semantics",
            "deduplicated DFS back-edge witnesses; not all elementary cycles",
        ),
    }

    if output_mode == "summary":
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_analyze",
            "topological_model": memory_graph.get("model", {}),
            "cycle_semantics": cycle_semantics,
            "betti_numbers": betti_numbers,
            "memory_archetype": memory_archetype,
            "memory_stats": memory_graph["summary"],
            "memory_health_score": health_score,
            "memory_health_model": health_model,
            "findings_by_severity": severity_counts,
            "total_findings": total_findings,
            "analyzers_run": analyzer_output["analyzers_run"],
            "analyzers_failed": analyzer_output.get("analyzers_failed", 0),
            "analyzer_errors": analyzer_output.get("errors", {}),
        }

    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_analyze",
        "topological_model": memory_graph.get("model", {}),
        "cycle_semantics": cycle_semantics,
        "betti_numbers": betti_numbers,
        "memory_archetype": memory_archetype,
        "memory_graph_summary": memory_graph["summary"],
        "analyzers": analyzer_output,
        "memory_health_score": health_score,
        "memory_health_model": health_model,
        "unified_summary": {
            "total_memories": total_memories,
            "total_associations": memory_graph["summary"]["total_associations"],
            "total_findings": total_findings,
            "findings_by_severity": severity_counts,
            "memory_health_score": health_score,
            "memory_health_model": health_model,
            "betti_numbers": betti_numbers,
            "memory_archetype": memory_archetype,
        },
    }


def kernel_memory_stats() -> Dict[str, Any]:
    """Statistik memory store."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    stats = get_memory_stats()
    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_stats",
        **stats,
    }


def kernel_memory_associate(
    from_id: str,
    to_id: str,
    assoc_type: str,
    strength: float = 0.5,
) -> Dict[str, Any]:
    """Buat asosiasi antara dua memori."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    try:
        assoc = store_association(
            from_id=from_id,
            to_id=to_id,
            assoc_type=assoc_type,
            strength=strength,
        )
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_associate",
            "status": "associated",
            "association": assoc,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_consolidate(
    source_ids: List[str],
    content: str,
    tags: Optional[str] = None,
    importance: float = 0.9,
) -> Dict[str, Any]:
    """Konsolidasi memori (colimit operation)."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    try:
        result = consolidate_memories(
            source_ids=source_ids,
            content=content,
            tags=tag_list,
            importance=importance,
        )
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_consolidate",
            "status": "consolidated",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_steer(output_mode: str = "full") -> Dict[str, Any]:
    """Memory steering: topology → reasoning strategy."""
    if not MEMORY_AVAILABLE or not MEMORY_SYNTH_AVAILABLE:
        return {"error": "memory modules not available"}

    # Build memory graph
    memory_graph = build_memory_graph()

    # Run manifold analyzer untuk Betti numbers
    from memory.analyzers import analyze_manifold
    manifold_result = analyze_manifold(memory_graph)
    manifold_data = manifold_result.get("manifold", {})

    # Compute health score
    from memory.analyzers import run_memory_analyzers
    analyzer_output = run_memory_analyzers(memory_graph)
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for r in analyzer_output.get("results", {}).values():
        for f in r.get("findings", []):
            sev = f.get("severity", "low")
            if sev in severity_counts:
                severity_counts[sev] += 1

    total_memories = memory_graph["summary"]["total_memories"]
    weighted_sum = (
        severity_counts["high"] * 3
        + severity_counts["medium"] * 2
        + severity_counts["low"] * 1
    )
    pressure = weighted_sum / max(1, total_memories)
    health_score = round(1.0 / (1.0 + pressure), 3)

    # Compute fingerprint
    memory_stats = memory_graph["summary"]
    fingerprint = compute_memory_fingerprint(manifold_data, memory_stats)

    # Load baseline & detect drift
    baseline = load_memory_baseline()
    drift = detect_memory_drift(fingerprint, baseline)

    # Generate steering signals
    directed_reasoning_count = (
        analyzer_output.get("results", {})
        .get("mem.betti_breakdown", {})
        .get("summary", {})
        .get("directed_reasoning_cycle_witness_count", 0)
    )
    signals = generate_memory_steering_signals(
        fingerprint,
        drift,
        health_score,
        directed_reasoning_cycle_witness_count=directed_reasoning_count,
    )

    # Assemble prompt block
    prompt_block = assemble_memory_prompt_block(fingerprint, drift, signals, health_score)

    if output_mode == "summary":
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_steer",
            "summary": {
                "has_baseline": drift.get("has_baseline", False),
                "drift_interpretation": drift.get("interpretation", "no_baseline"),
                "reasoning_strategy": signals["reasoning_strategy"],
                "reasoning_budget": signals["reasoning_budget"],
                "regrounding_needed": signals["regrounding_needed"],
                "health_score": health_score,
            },
            "steering_signals": signals,
        }

    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_steer",
        "fingerprint": fingerprint,
        "health_score": health_score,
        "drift_analysis": drift,
        "steering_signals": signals,
        "steering_prompt_block": prompt_block,
    }


def kernel_memory_establish() -> Dict[str, Any]:
    """Establish memory baseline."""
    if not MEMORY_AVAILABLE or not MEMORY_SYNTH_AVAILABLE:
        return {"error": "memory modules not available"}

    # Build graph & compute fingerprint
    memory_graph = build_memory_graph()
    from memory.analyzers import analyze_manifold, run_memory_analyzers
    manifold_result = analyze_manifold(memory_graph)
    manifold_data = manifold_result.get("manifold", {})

    # Compute health score
    analyzer_output = run_memory_analyzers(memory_graph)
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for r in analyzer_output.get("results", {}).values():
        for f in r.get("findings", []):
            sev = f.get("severity", "low")
            if sev in severity_counts:
                severity_counts[sev] += 1

    total_memories = memory_graph["summary"]["total_memories"]
    weighted_sum = (
        severity_counts["high"] * 3
        + severity_counts["medium"] * 2
        + severity_counts["low"] * 1
    )
    pressure = weighted_sum / max(1, total_memories)
    health_score = round(1.0 / (1.0 + pressure), 3)

    # Compute fingerprint
    fingerprint = compute_memory_fingerprint(manifold_data, memory_graph["summary"])

    # Establish baseline
    result = establish_memory_baseline(fingerprint, health_score)

    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_establish",
        **result,
    }


def kernel_memory_drift() -> Dict[str, Any]:
    """Detect memory drift against baseline."""
    if not MEMORY_AVAILABLE or not MEMORY_SYNTH_AVAILABLE:
        return {"error": "memory modules not available"}

    # Build graph & compute fingerprint
    memory_graph = build_memory_graph()
    from memory.analyzers import analyze_manifold
    manifold_result = analyze_manifold(memory_graph)
    manifold_data = manifold_result.get("manifold", {})

    fingerprint = compute_memory_fingerprint(manifold_data, memory_graph["summary"])

    # Load baseline & detect drift
    baseline = load_memory_baseline()
    drift = detect_memory_drift(fingerprint, baseline)

    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_drift",
        "fingerprint": fingerprint,
        "drift_analysis": drift,
    }


def kernel_memory_consolidate_by_tag(
    tag: str,
    content: Optional[str] = None,
    importance: float = 0.9,
) -> Dict[str, Any]:
    """Konsolidasi memori berdasarkan tag."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.store import consolidate_by_tag
        result = consolidate_by_tag(tag=tag, content=content, importance=importance)
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_consolidate_by_tag",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_consolidate_auto(
    min_group_size: int = 3,
    importance: float = 0.9,
) -> Dict[str, Any]:
    """Otomatis konsolidasi semua tag groups yang memenuhi threshold."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.store import consolidate_by_tag_auto
        result = consolidate_by_tag_auto(
            min_group_size=min_group_size,
            importance=importance,
        )
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_consolidate_auto",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_unconsolidated_tags() -> Dict[str, Any]:
    """Lihat ringkasan unconsolidated memories by tag."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.store import get_unconsolidated_by_tag
        result = get_unconsolidated_by_tag()
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_unconsolidated_tags",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_betti_breakdown() -> Dict[str, Any]:
    """Hitung β₁ breakdown per kategori edge type."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.graph import build_memory_graph
        from memory.analyzers import analyze_betti_breakdown
        memory_graph = build_memory_graph()
        result = analyze_betti_breakdown(memory_graph)
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_betti_breakdown",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_compact(
    only_consolidated: bool = True,
    memory_type: str = "episodic",
    dry_run: bool = False,
    restore: bool = False,
    restore_all: bool = False,
    restore_id: Optional[str] = None,
    stats: bool = False,
) -> Dict[str, Any]:
    """Memory compact: quotient forgetting untuk archived memories."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}

    try:
        from memory.store import (
            compact_memories, get_archive_stats,
            restore_memory, restore_all_archived,
        )
        from memory.graph import build_memory_graph
        from memory.analyzers import analyze_manifold
    except ImportError as exc:
        return {"error": f"import failed: {exc}"}

    # Mode: stats
    if stats:
        archive_stats = get_archive_stats()
        # Hitung Betti untuk active graph
        active_graph = build_memory_graph(include_archived=False)
        active_manifold = analyze_manifold(active_graph)
        # Hitung Betti untuk full graph (termasuk archived)
        full_graph = build_memory_graph(include_archived=True)
        full_manifold = analyze_manifold(full_graph)

        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_compact_stats",
            "archive_stats": archive_stats,
            "active_graph_betti": active_manifold["manifold"]["betti_numbers"],
            "full_graph_betti": full_manifold["manifold"]["betti_numbers"],
        }

    # Mode: restore
    if restore_all:
        result = restore_all_archived()
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_compact_restore",
            **result,
        }

    if restore_id:
        result = restore_memory(restore_id)
        if result is None:
            return {"error": f"Memory not found: {restore_id}"}
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_compact_restore",
            "restored": result,
        }

    # Mode: compact (dengan Betti impact analysis)
    # Hitung Betti SEBELUM compact
    graph_before = build_memory_graph(include_archived=False)
    manifold_before = analyze_manifold(graph_before)
    betti_before = manifold_before["manifold"]["betti_numbers"]

    # Execute compact
    compact_result = compact_memories(
        only_consolidated=only_consolidated,
        memory_type=memory_type,
        dry_run=dry_run,
    )

    if dry_run:
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_compact",
            **compact_result,
            "betti_before": betti_before,
        }

    # Hitung Betti SESUDAH compact
    graph_after = build_memory_graph(include_archived=False)
    manifold_after = analyze_manifold(graph_after)
    betti_after = manifold_after["manifold"]["betti_numbers"]

    # Hitung Betti impact
    betti_impact = {
        "beta_0": {"before": betti_before["beta_0"], "after": betti_after["beta_0"],
                    "delta": betti_after["beta_0"] - betti_before["beta_0"]},
        "beta_1": {"before": betti_before["beta_1"], "after": betti_after["beta_1"],
                    "delta": betti_after["beta_1"] - betti_before["beta_1"]},
        "beta_2": {"before": betti_before["beta_2"], "after": betti_after["beta_2"],
                    "delta": betti_after["beta_2"] - betti_before["beta_2"]},
    }

    return {
        "schema_version": "4.1.0-memory",
        "mode": "memory_compact",
        **compact_result,
        "betti_before": betti_before,
        "betti_after": betti_after,
        "betti_impact": betti_impact,
    }


def kernel_memory_bridge(
    from_id: str,
    to_id: str,
    assoc_type: str = "semantic",
    strength: float = 0.7,
    safe_mode: bool = True,
) -> Dict[str, Any]:
    """Manual bridge antara dua memories."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.store import bridge_memories
        result = bridge_memories(
            from_id=from_id,
            to_id=to_id,
            assoc_type=assoc_type,
            strength=strength,
            safe_mode=safe_mode,
        )
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_bridge",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_bridge_auto(
    min_shared_tags: int = 1,
    assoc_type: str = "semantic",
    safe_mode: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Auto bridge: hubungkan semantic memories yang share tags."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.store import bridge_auto
        result = bridge_auto(
            min_shared_tags=min_shared_tags,
            assoc_type=assoc_type,
            safe_mode=safe_mode,
            dry_run=dry_run,
        )
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_bridge_auto",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_bridge_candidates(
    min_shared_tags: int = 1,
) -> Dict[str, Any]:
    """Lihat kandidat bridge sebelum eksekusi."""
    if not MEMORY_AVAILABLE:
        return {"error": "memory modules not available"}
    try:
        from memory.store import get_bridge_candidates
        result = get_bridge_candidates(min_shared_tags=min_shared_tags)
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_bridge_candidates",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_memory_kan(
    query: str,
    mode: str = "both",
    max_depth: int = 2,
) -> Dict[str, Any]:
    """Kan Extension retrieval: structured completion."""
    if not KAN_EXTENSION_AVAILABLE:
        return {"error": "memory_kan_extension not available"}

    try:
        result = kan_retrieve(query, mode=mode, max_depth=max_depth)
        return {
            "schema_version": "4.1.0-memory",
            "mode": "memory_kan",
            **result,
        }
    except Exception as exc:
        return _exception_result(exc)


def kernel_xanalyze(
    scan_root: str = ".",
    analyzer_names: Optional[List[str]] = None,
    output_mode: str = "summary",
    auto_store: bool = True,
) -> Dict[str, Any]:
    """
    Cross-Domain Analyze: analisis codebase + auto-store findings ke memory.
    """
    if not SHARED_GRAPH_AVAILABLE or not REGISTRY_AVAILABLE:
        return {"error": "required modules not available"}

    _bind_memory_scope_to_scan(scan_root)

    # Step 1: Build graph + run analyzers
    graph = _build_kernel_graph(scan_root)
    analyzer_output = _run_kernel_analyzers(graph, analyzer_names)
    analyzer_results = analyzer_output.get("results", {})

    # Step 2: Synthesize (untuk correlations & fingerprint)
    total_files = graph.get("summary", {}).get("total_files", 0)
    health_score = _compute_topological_health_score(analyzer_output, total_files)
    correlations = _detect_cross_analyzer_correlations(graph, analyzer_output)
    fingerprint = {}
    if ENCODER_AVAILABLE:
        enc_res = encode_topological_invariants(
            scan_root,
            shared_graph=graph,
            analyzer_output=analyzer_output,
        )
        if enc_res.get("available"):
            fingerprint = enc_res.get("topological_fingerprint", {})
    if not fingerprint and "hott.manifold" in analyzer_results:
        manifold_data = analyzer_results["hott.manifold"].get("manifold", {})
        fingerprint = {
            "signature_hash": "sha256:unknown",
            "complexity_score": manifold_data.get("complexity_score", 0.0),
            "structural_archetype": manifold_data.get("structural_archetype", "unknown"),
        }

    # Step 3: Selective filter + auto-store
    store_result = {"stored_count": 0, "skipped": True}
    if auto_store and CROSS_DOMAIN_AVAILABLE:
        storeable = filter_findings_for_memory(analyzer_results, correlations)
        full_graph_signature = graph.get("cache", {}).get(
            "graph_content_signature"
        )
        if not full_graph_signature and graph_content_signature is not None:
            full_graph_signature = graph_content_signature(graph)
        file_content_hashes = {
            path: f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
            for path, content in graph.get("file_map", {}).items()
        }
        store_result = auto_store_findings(
            storeable,
            scan_root,
            evidence_signature=fingerprint.get("signature_hash"),
            graph_content_signature=full_graph_signature,
            active_files=graph.get("vertices", []),
            file_content_hashes=file_content_hashes,
            analyzers_observed=analyzer_output.get(
                "analyzers_succeeded", analyzer_results.keys()
            ),
            analyzers_failed=analyzer_output.get("errors", {}).keys(),
        )

    # Step 4: Check consolidation trigger
    consolidation_signal = {"trigger": False}
    reconciled_activity = sum(
        int(store_result.get(key, 0))
        for key in (
            "stored_count", "reused_count", "revised_count",
            "resolved_count", "orphaned_count", "stale_count",
        )
    )
    if CROSS_DOMAIN_AVAILABLE and reconciled_activity > 0:
        consolidation_signal = check_consolidation_trigger()

    # Step 5: Format output
    total_findings = sum(
        len(r.get("findings", [])) for r in analyzer_results.values()
    )
    severity_counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for r in analyzer_results.values():
        for f in r.get("findings", []):
            sev = f.get("severity", "info")
            if sev in severity_counts:
                severity_counts[sev] += 1

    if output_mode == "summary":
        return {
            "schema_version": "4.1.0-memory",
            "mode": "xanalyze",
            "scan_root": scan_root,
            "graph_cache": graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "analysis_summary": {
                "total_findings": total_findings,
                "findings_by_severity": severity_counts,
                "correlation_count": len(correlations),
                "health_score": health_score,
                "archetype": fingerprint.get("structural_archetype", "unknown"),
            },
            "memory_store_result": store_result,
            "consolidation_signal": {
                "consolidation_candidate": consolidation_signal.get("trigger", False),
                "reasons": consolidation_signal.get("reasons", []),
            },
        }

    return {
        "schema_version": "4.1.0-memory",
        "mode": "xanalyze",
        "scan_root": scan_root,
        "graph_cache": graph.get("cache", {}),
        "analyzer_cache": analyzer_output.get("cache", {}),
        "analyzers": analyzer_output,
        "synthesis": {
            "fingerprint": fingerprint,
            "topological_health_score": health_score,
            "correlations": correlations,
        },
        "memory_store_result": store_result,
        "consolidation_signal": consolidation_signal,
    }


def kernel_xsteer(scan_root: str = ".", output_mode: str = "full") -> Dict[str, Any]:
    """Cross-Domain Steer: unified codebase + memory steering."""
    if not CROSS_DOMAIN_AVAILABLE:
        return {"error": "cross_domain_bridge not available"}

    _bind_memory_scope_to_scan(scan_root)

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    graph = _build_kernel_graph(scan_root)
    analyzer_output = _run_kernel_analyzers(graph)
    result = cross_domain_steer(
        scan_root,
        shared_graph=graph,
        analyzer_output=analyzer_output,
    )

    if output_mode == "summary":
        return {
            "schema_version": "4.1.0-memory",
            "mode": "xsteer",
            "graph_cache": graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "codebase": result.get("codebase_steering", {}),
            "memory": result.get("memory_steering", {}),
            "memory_scope": result.get("memory_scope", {}),
            "consolidation_candidate": result.get("consolidation_signal", {}).get("consolidation_candidate", False),
        }

    return result


def kernel_xcontext(file_path: str) -> Dict[str, Any]:
    """Cross-Domain Context: recall relevant memories untuk file."""
    if not CROSS_DOMAIN_AVAILABLE:
        return {"error": "cross_domain_bridge not available"}

    return get_memory_context_for_file(file_path)


def kernel_fiber(subcommand: str, args: List[str]) -> Dict[str, Any]:
    """Router untuk fiber operations."""
    if not FIBRATION_AVAILABLE:
        return {"error": "memory_fibration not available"}

    if subcommand == "init":
        task = args[0] if len(args) > 0 else "general"
        focus = args[1] if len(args) > 1 else "general"
        return {"schema_version": "4.1.0-memory", "mode": "fiber_init", **init_fiber(task, focus)}

    elif subcommand == "lift":
        query = None
        mem_type = None
        tags = None
        max_lift = 10
        i = 0
        while i < len(args):
            if args[i] == "--query" and i + 1 < len(args):
                query = args[i + 1]
                i += 2
            elif args[i] == "--type" and i + 1 < len(args):
                mem_type = args[i + 1]
                i += 2
            elif args[i] == "--tags" and i + 1 < len(args):
                tags = args[i + 1].split(",")
                i += 2
            elif args[i] == "--max" and i + 1 < len(args):
                try:
                    max_lift = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            else:
                i += 1
        result = lift_to_fiber(query=query, memory_type=mem_type, tags=tags, max_lift=max_lift)
        return {"schema_version": "4.1.0-memory", "mode": "fiber_lift", **result}

    elif subcommand == "descend":
        memory_id = args[0] if args and not args[0].startswith("--") else None
        descend_all = "--all" in args
        reason = "task_completed"
        for i, arg in enumerate(args):
            if arg == "--reason" and i + 1 < len(args):
                reason = args[i + 1]
        result = descend_from_fiber(memory_id=memory_id, descend_all=descend_all, reason=reason)
        return {"schema_version": "4.1.0-memory", "mode": "fiber_descend", **result}

    elif subcommand == "status":
        return {"schema_version": "4.1.0-memory", "mode": "fiber_status", **fiber_status()}

    elif subcommand == "section_start":
        name = args[0] if len(args) > 0 else "unnamed"
        narrative = args[1] if len(args) > 1 else ""
        result = start_section(name, narrative)
        return {"schema_version": "4.1.0-memory", "mode": "fiber_section_start", **result}

    elif subcommand == "section_add":
        if not args:
            return {"error": "Usage: fiber section_add <memory_id>"}
        result = add_to_section(args[0])
        return {"schema_version": "4.1.0-memory", "mode": "fiber_section_add", **result}

    elif subcommand == "section_status":
        return {"schema_version": "4.1.0-memory", "mode": "fiber_section_status", **get_section_status()}

    elif subcommand == "switch":
        task = args[0] if len(args) > 0 else "new_task"
        focus = args[1] if len(args) > 1 else "new_focus"
        result = switch_base(task, focus)
        return {"schema_version": "4.1.0-memory", "mode": "fiber_switch", **result}

    elif subcommand == "list_archives":
        return kernel_fiber_list_archives()

    elif subcommand == "transport":
        if len(args) < 3:
            return {"error": "Usage: fiber transport <source_fiber_id> <new_task> <new_focus> [--threshold 0.6] [--max 10] [--dry-run]"}
        source_id = args[0]
        new_task = args[1]
        new_focus = args[2]
        threshold = 0.6
        max_transport = 10
        dry_run = False
        i = 3
        while i < len(args):
            if args[i] == "--threshold" and i + 1 < len(args):
                try:
                    threshold = float(args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif args[i] == "--max" and i + 1 < len(args):
                try:
                    max_transport = int(args[i + 1])
                except ValueError:
                    pass
                i += 2
            elif args[i] == "--dry-run":
                dry_run = True
                i += 1
            else:
                i += 1
        return kernel_fiber_transport(source_id, new_task, new_focus, threshold, max_transport, dry_run)

    else:
        return {"error": f"Unknown fiber subcommand: {subcommand}"}


def kernel_fiber_transport(
    source_fiber_id: str,
    new_task: str,
    new_focus: str,
    threshold: float = 0.6,
    max_transport: int = 10,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Parallel transport dari fiber lama ke fiber baru."""
    if not FIBRATION_AVAILABLE:
        return {"error": "memory_fibration not available"}
    
    try:
        result = transport_from_archive(
            source_fiber_id=source_fiber_id,
            new_task=new_task,
            new_focus=new_focus,
            threshold=threshold,
            max_transport=max_transport,
            dry_run=dry_run,
        )
        return {"schema_version": "4.1.0-memory", "mode": "fiber_transport", **result}
    except Exception as exc:
        return _exception_result(exc)


def kernel_fiber_list_archives() -> Dict[str, Any]:
    """List archived fibers."""
    if not FIBRATION_AVAILABLE:
        return {"error": "memory_fibration not available"}
    
    try:
        result = list_archived_fibers()
        return {"schema_version": "4.1.0-memory", "mode": "fiber_list_archives", **result}
    except Exception as exc:
        return _exception_result(exc)




def kernel_analyze(
    scan_root: str = ".",
    analyzer_names: Optional[List[str]] = None,
    output_mode: str = "full",
) -> Dict[str, Any]:
    """
    Orkestrasi penuh: build SharedGraph + run analyzers + synthesize.

    Output modes:
    - "full"     : semua data termasuk shared_graph (default)
    - "summary"  : hanya unified_summary + counts
    - "findings" : findings analyzers + summary, tanpa shared_graph
    - "graph"    : hanya shared_graph (tanpa file_map), tanpa analyzers
    """
    if not SHARED_GRAPH_AVAILABLE:
        return {"error": "shared_graph module not found", "available": False}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    output_error = _validate_output_mode(
        output_mode,
        ("full", "summary", "findings", "graph"),
    )
    if output_error:
        return output_error

    # Step 1: Build SharedGraph (1x scan, 1x graph build)
    shared_graph = _build_kernel_graph(scan_root)

    # Mode graph: langsung return tanpa jalankan analyzers
    if output_mode == "graph":
        graph_output = {k: v for k, v in shared_graph.items() if k != "file_map"}
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "graph",
            "scan_root": scan_root,
            "graph_cache": shared_graph.get("cache", {}),
            "shared_graph": graph_output,
        }

    # Step 2: Run analyzers
    if REGISTRY_AVAILABLE:
        analyzer_output = _run_kernel_analyzers(shared_graph, analyzer_names)
    else:
        analyzer_output = {"results": {}, "errors": {}, "analyzers_run": 0}

    # Step 3: Build unified summary
    unified_summary = {
        "total_files": shared_graph["summary"]["total_files"],
        "total_edges": shared_graph["summary"]["total_edges"],
        "total_boundaries": shared_graph["summary"]["total_boundaries"],
        "total_type_shapes": shared_graph["summary"]["total_type_shapes"],
        "entrypoint_count": shared_graph["summary"]["entrypoint_count"],
        "test_file_count": shared_graph["summary"]["test_file_count"],
        "total_findings": sum(
            len(r.get("findings", []))
            for r in analyzer_output.get("results", {}).values()
        ),
        "findings_by_severity": _count_findings_by_severity(analyzer_output),
        "analyzers_run": analyzer_output.get("analyzers_run", 0),
        "analyzers_failed": analyzer_output.get("analyzers_failed", 0),
        "analyzer_errors": analyzer_output.get("errors", {}),
        **_analysis_status(
            shared_graph["summary"]["total_files"],
            analyzer_output.get("analyzers_failed", 0),
        ),
    }

    base = {
        "schema_version": "3.0.0-kernel",
        "mode": "analyze",
        "output_mode": output_mode,
        "scan_root": scan_root,
        "timestamp": _utc_timestamp(),
        "graph_cache": shared_graph.get("cache", {}),
        "analyzer_cache": analyzer_output.get("cache", {}),
    }

    # Step 4: Filter output berdasarkan mode
    if output_mode == "summary":
        base["unified_summary"] = unified_summary
        return base

    elif output_mode == "findings":
        base["analyzers"] = analyzer_output
        base["unified_summary"] = unified_summary
        return base

    else:  # "full"
        graph_output = {k: v for k, v in shared_graph.items() if k != "file_map"}
        base["shared_graph"] = graph_output
        base["analyzers"] = analyzer_output
        base["unified_summary"] = unified_summary
        return base


def _count_findings_by_severity(analyzer_output: Dict[str, Any]) -> Dict[str, int]:
    """Hitung total findings per severity level dari semua analyzer."""
    counts = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for result in analyzer_output.get("results", {}).values():
        for finding in result.get("findings", []):
            sev = finding.get("severity", "info")
            if sev in counts:
                counts[sev] += 1
    return counts


def kernel_impact(
    scan_root: str,
    target_file: str,
    output_mode: str = "full",
) -> Dict[str, Any]:
    """Targeted impact analysis via SharedGraph."""
    if not SHARED_GRAPH_AVAILABLE or not TOPO_QUERIES_AVAILABLE:
        return {"error": "required modules not available"}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    output_error = _validate_output_mode(output_mode, ("full", "summary"))
    if output_error:
        return output_error

    graph = _build_kernel_graph(scan_root)
    result = query_impact(graph, target_file)

    if output_mode == "summary":
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "impact",
            "graph_cache": graph.get("cache", {}),
            "target": result.get("target"),
            "exists": result.get("exists"),
            "change_risk_level": result.get("change_risk_level"),
            "affected_entrypoints": result.get("affected_entrypoints", []),
            "downstream_count": result.get("downstream_count", 0),
            "upstream_count": result.get("upstream_count", 0),
            "target_fan_in": result.get("target_fan_in", 0),
        }

    return {
        "schema_version": "3.0.0-kernel",
        "mode": "impact",
        "graph_cache": graph.get("cache", {}),
        **result,
    }


def kernel_outline(
    scan_root: str,
    target_file: str,
) -> Dict[str, Any]:
    """Targeted outline extraction via SharedGraph."""
    if not SHARED_GRAPH_AVAILABLE or not TOPO_QUERIES_AVAILABLE:
        return {"error": "required modules not available"}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error

    graph = _build_kernel_graph(scan_root)
    result = query_outline(graph, target_file)

    return {
        "schema_version": "3.0.0-kernel",
        "mode": "outline",
        "graph_cache": graph.get("cache", {}),
        **result,
    }


def kernel_brief(
    scan_root: str,
    target_file: str,
    output_mode: str = "full",
) -> Dict[str, Any]:
    """Targeted brief (outline + impact) via SharedGraph."""
    if not SHARED_GRAPH_AVAILABLE or not TOPO_QUERIES_AVAILABLE:
        return {"error": "required modules not available"}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    output_error = _validate_output_mode(output_mode, ("full", "summary"))
    if output_error:
        return output_error

    graph = _build_kernel_graph(scan_root)
    result = query_brief(graph, target_file)

    if output_mode == "summary":
        impact_data = result.get("impact", {})
        outline_data = result.get("outline", {})
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "brief",
            "graph_cache": graph.get("cache", {}),
            "file": result.get("file"),
            "exists": result.get("exists"),
            "export_count": outline_data.get("stats", {}).get("export_count", 0),
            "import_count": outline_data.get("stats", {}).get("import_count", 0),
            "change_risk_level": impact_data.get("change_risk_level"),
            "affected_entrypoints": impact_data.get("affected_entrypoints", []),
            "downstream_count": impact_data.get("downstream_count", 0),
        }

    return {
        "schema_version": "3.0.0-kernel",
        "mode": "brief",
        "graph_cache": graph.get("cache", {}),
        **result,
    }


def kernel_cycle_break(
    scan_root: str,
    target_file: Optional[str] = None,
    output_mode: str = "full",
) -> Dict[str, Any]:
    """Targeted cycle-break advisor and Feedback Arc Set plan via SharedGraph."""
    if not SHARED_GRAPH_AVAILABLE:
        return {"error": "required modules not available"}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    output_error = _validate_output_mode(output_mode, ("full", "summary"))
    if output_error:
        return output_error

    graph = _build_kernel_graph(scan_root)
    from codebase.cycle_break import analyze_cycle_breaks
    advisor_result = analyze_cycle_breaks(graph)

    plan = advisor_result.get("summary", {})
    advisories = advisor_result.get("advisories", [])

    if target_file:
        target_norm = os.path.normpath(target_file).replace("\\", "/")
        if target_norm.startswith("./"):
            target_norm = target_norm[2:]
        # Filter advisories and cuts affecting target_file
        advisories = [
            adv for adv in advisories
            if any(target_norm in node for node in adv.get("cycle", []))
        ]
        recommended_cuts = [
            cut for cut in plan.get("recommended_cuts", [])
            if target_norm in cut.get("source", "") or target_norm in cut.get("target", "")
        ]
        plan = {
            **plan,
            "target_filtered": True,
            "target_file": target_norm,
            "cycles_affecting_target": len(advisories),
            "cuts_affecting_target": len(recommended_cuts),
            "recommended_cuts": recommended_cuts,
        }

    if output_mode == "summary":
        return {
            "schema_version": CODEBASE_SCHEMA_VERSION,
            "mode": "cycle_break",
            "scan_root": scan_root,
            "graph_cache": graph.get("cache", {}),
            "summary": plan,
        }

    return {
        "schema_version": CODEBASE_SCHEMA_VERSION,
        "mode": "cycle_break",
        "scan_root": scan_root,
        "graph_cache": graph.get("cache", {}),
        "summary": plan,
        "advisories": advisories,
    }


def _memory_context_metadata(memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """Expose memory provenance without duplicating prompt content outside its budget."""
    return {
        "selected_count": memory_context.get("selected_count", 0),
        "retrieved_count": memory_context.get("retrieved_count", 0),
        "selected": [
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "file": item.get("file"),
                "evidence_status": item.get("evidence_status"),
                "freshness": item.get("freshness"),
                "source_content_sha256": item.get("source_content_sha256"),
                "content_sha256": item.get("content_sha256"),
                "content_truncated": item.get("content_truncated", False),
                "retrieval_match": item.get("retrieval_match", {}),
            }
            for item in memory_context.get("memories", [])
        ],
        "memory_scope": memory_context.get("memory_scope", {}),
        "retrieval": memory_context.get("retrieval", {}),
    }


def kernel_context(
    scan_root: str,
    query: str,
    target_files: Optional[List[str]] = None,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
    max_hops: int = DEFAULT_MAX_HOPS,
    detail: str = "source",
    output_mode: str = "prompt",
) -> Dict[str, Any]:
    """Build a query-directed, budget-bounded context projection for an LLM."""
    if not SHARED_GRAPH_AVAILABLE or not REGISTRY_AVAILABLE or not CONTEXT_OPTIMIZER_AVAILABLE:
        return _kernel_error(
            "context_optimizer_unavailable",
            "context optimizer dependencies are not available",
        )

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    if not query or not query.strip():
        return _kernel_error(
            "empty_context_query",
            "Context query must contain non-whitespace text.",
        )
    output_error = _validate_output_mode(output_mode, ("prompt", "summary", "full"))
    if output_error:
        return output_error
    if detail not in ("outline", "source"):
        return _kernel_error(
            "invalid_context_detail",
            f"Invalid context detail: {detail}",
            detail=detail,
            supported_details=["outline", "source"],
        )
    if not isinstance(budget_tokens, int) or not MIN_BUDGET_TOKENS <= budget_tokens <= MAX_BUDGET_TOKENS:
        return _kernel_error(
            "invalid_context_budget",
            (
                f"Context budget must be an integer between {MIN_BUDGET_TOKENS} "
                f"and {MAX_BUDGET_TOKENS} estimated tokens."
            ),
            budget_tokens=budget_tokens,
            minimum=MIN_BUDGET_TOKENS,
            maximum=MAX_BUDGET_TOKENS,
        )
    if not isinstance(max_hops, int) or not 0 <= max_hops <= MAX_HOPS:
        return _kernel_error(
            "invalid_context_hops",
            f"Context max_hops must be an integer between 0 and {MAX_HOPS}.",
            max_hops=max_hops,
            minimum=0,
            maximum=MAX_HOPS,
        )

    _bind_memory_scope_to_scan(scan_root)

    # One canonical scan; all analyzers and the optimizer reuse this snapshot.
    graph = _build_kernel_graph(scan_root)
    analyzer_output = _run_kernel_analyzers(graph)
    memory_context: Dict[str, Any] = {}
    if CROSS_DOMAIN_AVAILABLE:
        current_graph_signature = graph.get("cache", {}).get(
            "graph_content_signature"
        )
        if not current_graph_signature and graph_content_signature is not None:
            current_graph_signature = graph_content_signature(graph)
        current_file_hashes = {
            path: f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
            for path, content in graph.get("file_map", {}).items()
        }
        memory_context = get_memory_evidence(
            query=query,
            target_files=target_files,
            max_memories=5,
            current_graph_signature=current_graph_signature,
            current_file_hashes=current_file_hashes,
            cache_mode=_ACTIVE_GRAPH_CACHE_MODE,
        )
    pack = build_context_pack(
        graph,
        query,
        target_files=target_files,
        budget_tokens=budget_tokens,
        max_hops=max_hops,
        detail=detail,
        analyzer_output=analyzer_output,
        memory_context=memory_context,
    )
    unresolved_targets = pack.get("selection", {}).get("unresolved_targets", [])
    if unresolved_targets:
        return _kernel_error(
            "context_target_not_found",
            "One or more explicit context targets could not be resolved uniquely.",
            unresolved_targets=unresolved_targets,
            scan_root=scan_root,
        )

    base = {
        "schema_version": "3.0.0-kernel",
        "mode": "context",
        "output_mode": output_mode,
        "scan_root": scan_root,
        "query": query,
        "graph_cache": graph.get("cache", {}),
        "analyzer_cache": analyzer_output.get("cache", {}),
    }
    if output_mode == "prompt":
        selection = pack.get("selection", {})
        memory_metadata = _memory_context_metadata(pack.get("memory_context", {}))
        return {
            **base,
            "model": pack.get("model", {}),
            "selection": {
                "mode": selection.get("mode"),
                "confidence": selection.get("confidence"),
                "selected_paths": selection.get("selected_paths", []),
                "resolved_targets": selection.get("resolved_targets", []),
                "max_hops": selection.get("max_hops"),
            },
            "budget": pack.get("budget", {}),
            "provenance": pack.get("provenance", {}),
            "memory_context": memory_metadata,
            "context_block": pack.get("context_block", ""),
        }
    if output_mode == "summary":
        memory_metadata = _memory_context_metadata(pack.get("memory_context", {}))
        return {
            **base,
            "model": pack.get("model", {}),
            "selection": pack.get("selection", {}),
            "budget": pack.get("budget", {}),
            "provenance": pack.get("provenance", {}),
            "memory_context": memory_metadata,
            "quotient_summary": pack.get("quotient_graph", {}).get("summary", {}),
            "selected_files": [
                {
                    "file": item.get("file"),
                    "score": item.get("score"),
                    "graph_distance": item.get("graph_distance"),
                    "selection_signals": item.get("selection_signals", []),
                }
                for item in pack.get("selected_files", [])
            ],
        }
    return {**base, **pack}


def kernel_establish(
    scan_root: str = ".",
    baseline_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Establish topological baseline via decoder_steering."""
    if not STEERING_AVAILABLE:
        return {"error": "steering module not available"}
    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    graph = _build_kernel_graph(scan_root)
    analyzer_output = _run_kernel_analyzers(
        graph,
        ["hott.manifold", "topo.test_reachability"],
    )
    result = establish_baseline(
        scan_root,
        baseline_path,
        shared_graph=graph,
        analyzer_output=analyzer_output,
    )
    return {
        "schema_version": "3.0.0-kernel",
        "graph_cache": graph.get("cache", {}),
        "analyzer_cache": analyzer_output.get("cache", {}),
        **result,
    }


def _compute_topological_health_score(analyzer_output: Dict[str, Any], total_files: int) -> float:
    """Hitung health score (0.0 to 1.0] dari seluruh 13 analyzer."""
    if total_files <= 0:
        return 1.0
    weights = {"high": 3, "medium": 2, "low": 1, "info": 0}
    weighted_sum = 0
    results = analyzer_output.get("results", {})
    for res in results.values():
        for finding in res.get("findings", []):
            sev = finding.get("severity", "info")
            weighted_sum += weights.get(sev, 0)

    pressure = weighted_sum / max(1, total_files)
    return round(1.0 / (1.0 + pressure), 3)


def _detect_cross_analyzer_correlations(
    graph: Dict[str, Any],
    analyzer_output: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Deteksi korelasi lintas analyzer (gluing synthesis)."""
    correlations: List[Dict[str, Any]] = []
    results = analyzer_output.get("results", {})

    # 1. Isomorphic types across boundaries
    iso_res = results.get("hott.isomorphism", {}).get("findings", [])
    if iso_res:
        for finding in iso_res:
            if finding.get("type") == "structural_isomorphism":
                file_a = finding.get("file", "")
                file_b = finding.get("file_b", "")
                space_a = finding.get("space_a", {})
                space_b = finding.get("space_b", {})
                correlations.append({
                    "type": "boundary_isomorphism",
                    "severity": "low",
                    "file": file_a,
                    "file_b": file_b,
                    "type_name_a": space_a.get("name", "unknown"),
                    "type_name_b": space_b.get("name", "unknown"),
                    "isomorphism_confidence": finding.get("isomorphism_confidence", 0.0),
                    "observation": (
                        f"Isomorphic types '{space_a.get('name')}' ({file_a}) and "
                        f"'{space_b.get('name')}' ({file_b}) reside in a boundary structure. "
                        f"Type duplication correlates with boundary surface."
                    ),
                })

    # 2. Orphan files with performance issues
    orphan_res = results.get("topo.orphan", {}).get("findings", [])
    orphan_files = {f.get("file") for f in orphan_res if f.get("file")}
    if orphan_files:
        for analyzer_name in ("perf.async", "perf.cache", "perf.deopt", "perf.gc", "topo.risk"):
            for finding in results.get(analyzer_name, {}).get("findings", []):
                f_path = finding.get("file")
                if f_path and f_path in orphan_files and finding.get("severity") in ("high", "medium"):
                    correlations.append({
                        "type": "orphan_with_issues",
                        "severity": finding.get("severity", "medium"),
                        "file": f_path,
                        "analyzer": analyzer_name,
                        "issue_type": finding.get("type"),
                        "observation": f"Orphan file '{f_path}' has high/medium finding ({finding.get('type')}) from '{analyzer_name}'.",
                    })

    # 3. Entrypoints with high risk or perf issues
    risk_res = results.get("topo.risk", {}).get("findings", [])
    for finding in risk_res:
        if finding.get("risk_level") == "high":
            f_path = finding.get("file")
            correlations.append({
                "type": "entrypoint_high_risk",
                "severity": "high",
                "file": f_path,
                "reasons": finding.get("reasons", []),
                "observation": f"High change risk detected on '{f_path}' affecting entrypoints.",
            })

    # 4. Change risk without a static test-import witness
    test_reachability = results.get("topo.test_reachability", {})
    unreachable_from_tests = set(test_reachability.get("unreachable_sources", []))
    for finding in risk_res:
        f_path = finding.get("file")
        risk_level = finding.get("risk_level")
        if f_path in unreachable_from_tests and risk_level in ("high", "medium"):
            correlations.append({
                "type": "change_risk_without_test_path",
                "severity": risk_level,
                "file": f_path,
                "risk_score": finding.get("risk_score", 0),
                "risk_reasons": finding.get("reasons", []),
                "test_model": "static_test_import_reachability",
                "observation": (
                    f"'{f_path}' has {risk_level} change risk but no static import "
                    "path from a supported test file. This is not runtime coverage evidence."
                ),
            })

    correlations.sort(key=lambda c: (c.get("severity", ""), c.get("type", ""), c.get("file", "")))
    return correlations


def kernel_synthesize(
    scan_root: str = ".",
    output_mode: str = "full",
    analyzer_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Synthesis: SEMUA 13 analyzer + fingerprint + health + correlations.
    Menggunakan analyzer_registry.
    """
    if not SHARED_GRAPH_AVAILABLE or not REGISTRY_AVAILABLE:
        return {"error": "required modules not available", "available": False}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    output_error = _validate_output_mode(
        output_mode,
        ("full", "summary", "findings"),
    )
    if output_error:
        return output_error

    # Step 1: Build SharedGraph (1x scan)
    graph = _build_kernel_graph(scan_root)

    # Step 2: Run ALL 13 analyzers
    analyzer_output = _run_kernel_analyzers(graph, analyzer_names)
    results = analyzer_output.get("results", {})

    # Step 3: Fingerprint via invariant_encoder
    fingerprint = None
    if ENCODER_AVAILABLE:
        enc_res = encode_topological_invariants(
            scan_root,
            shared_graph=graph,
            analyzer_output=analyzer_output,
        )
        if enc_res.get("available"):
            fingerprint = enc_res.get("topological_fingerprint")

    if not fingerprint and "hott.manifold" in results:
        manifold_data = results["hott.manifold"].get("manifold", {})
        fingerprint = {
            "signature_hash": "sha256:unknown",
            "complexity_score": manifold_data.get("complexity_score", 0.0),
            "structural_archetype": manifold_data.get("structural_archetype", "unknown"),
        }

    # Step 4: Compute health score & correlations
    total_files = graph.get("summary", {}).get("total_files", 0)
    health_score = _compute_topological_health_score(analyzer_output, total_files)
    correlations = _detect_cross_analyzer_correlations(graph, analyzer_output)

    # Step 5: Unified summary
    unified_summary = {
        "total_files": total_files,
        "total_edges": graph.get("summary", {}).get("total_edges", 0),
        "total_boundaries": graph.get("summary", {}).get("total_boundaries", 0),
        "total_type_shapes": graph.get("summary", {}).get("total_type_shapes", 0),
        "entrypoint_count": graph.get("summary", {}).get("entrypoint_count", 0),
        "test_file_count": graph.get("summary", {}).get("test_file_count", 0),
        "total_findings": sum(len(r.get("findings", [])) for r in results.values()),
        "findings_by_severity": _count_findings_by_severity(analyzer_output),
        "correlation_count": len(correlations),
        "analyzers_run": analyzer_output.get("analyzers_run", 0),
        "analyzers_failed": analyzer_output.get("analyzers_failed", 0),
        "topological_health_score": health_score,
        "analyzer_errors": analyzer_output.get("errors", {}),
        **_analysis_status(
            total_files,
            analyzer_output.get("analyzers_failed", 0),
        ),
    }

    if output_mode == "summary":
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "synthesize",
            "scan_root": scan_root,
            "graph_cache": graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "fingerprint": fingerprint,
            "topological_health_score": health_score,
            "correlations": correlations,
            "unified_summary": unified_summary,
        }
    elif output_mode == "findings":
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "synthesize",
            "scan_root": scan_root,
            "graph_cache": graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "fingerprint": fingerprint,
            "topological_health_score": health_score,
            "correlations": correlations,
            "unified_summary": unified_summary,
            "analyzers": analyzer_output,
        }
    else:  # "full"
        graph_output = {k: v for k, v in graph.items() if k != "file_map"}
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "synthesize",
            "scan_root": scan_root,
            "graph_cache": graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "shared_graph": graph_output,
            "fingerprint": fingerprint,
            "topological_health_score": health_score,
            "correlations": correlations,
            "unified_summary": unified_summary,
            "analyzers": analyzer_output,
        }


def kernel_steer(
    scan_root: str = ".",
    baseline_path: Optional[str] = None,
    output_mode: str = "full",
) -> Dict[str, Any]:
    """Topological decoder steering via decoder_steering."""
    if not STEERING_AVAILABLE:
        return {"error": "steering module not available"}

    root_error = _validate_scan_root(scan_root)
    if root_error:
        return root_error
    output_error = _validate_output_mode(output_mode, ("full", "summary"))
    if output_error:
        return output_error

    graph = _build_kernel_graph(scan_root)
    analyzer_output = _run_kernel_analyzers(
        graph,
        ["hott.manifold", "topo.test_reachability"],
    )
    result = steer_decoder(
        scan_root,
        baseline_path,
        shared_graph=graph,
        analyzer_output=analyzer_output,
    )

    if output_mode == "summary":
        return {
            "schema_version": "3.0.0-kernel",
            "mode": "steer",
            "scan_root": scan_root,
            "graph_cache": graph.get("cache", {}),
            "analyzer_cache": analyzer_output.get("cache", {}),
            "baseline": result.get("baseline"),
            "summary": result.get("summary"),
            "steering_signals": result.get("steering_signals"),
            "cycle_semantics": result.get("cycle_semantics"),
            "test_topology": result.get("test_topology"),
            "steering_prompt_block": result.get("steering_prompt_block"),
        }

    return {
        "schema_version": "3.0.0-kernel",
        "mode": "steer",
        "graph_cache": graph.get("cache", {}),
        "analyzer_cache": analyzer_output.get("cache", {}),
        **result,
    }


def main():
    global _MEMORY_SCOPE_EXPLICIT

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h", "help"):
        print(json.dumps({
            "tool": "hott_kernel",
            "schema_version": "4.0.0-kernel",
            "global_options": {
                "cache_mode": "--cache-mode auto|refresh|off (or AI_STUDIO_GRAPH_CACHE)",
                "memory_project_root": "--memory-project-root PATH (or AI_STUDIO_PROJECT_ROOT)",
                "memory_scope": "--memory-scope NAME (or AI_STUDIO_MEMORY_SCOPE)",
                "memory_state_dir": "--memory-state-dir PATH (or AI_STUDIO_STATE_DIR)",
            },
            "usage": {
                "analyze": "python3 hott_kernel.py analyze [root] [--analyzers a,b] [--output full|summary|findings|graph]",
                "analyzers": "python3 hott_kernel.py analyzers",
                "cache": "python3 hott_kernel.py cache status|refresh|clear [root]",
                "impact": "python3 hott_kernel.py impact <file> [root] [--output full|summary]",
                "outline": "python3 hott_kernel.py outline <file> [root]",
                "brief": "python3 hott_kernel.py brief <file> [root] [--output full|summary]",
                "context": "python3 hott_kernel.py context <query> [root] [--target file[,file]] [--budget-tokens 1200] [--max-hops 2] [--detail outline|source] [--output prompt|summary|full]",
                "establish": "python3 hott_kernel.py establish [root] [--baseline path]",
                "synthesize": "python3 hott_kernel.py synthesize [root] [--output full|summary]",
                "steer": "python3 hott_kernel.py steer [root] [--output full|summary] [--baseline path]",
                "memory_store": "python3 hott_kernel.py memory_store <type> <content> [--source src] [--importance 0.5] [--tags t1,t2]",
                "memory_recall": "python3 hott_kernel.py memory_recall [query] [--type t] [--tags t1,t2] [--limit 20]",
                "memory_analyze": "python3 hott_kernel.py memory_analyze [--analyzers a,b] [--output full|summary] [--include-historical] [--include-provenance]",
                "memory_stats": "python3 hott_kernel.py memory_stats",
                "memory_associate": "python3 hott_kernel.py memory_associate <from_id> <to_id> <type> [--strength 0.7]",
                "memory_consolidate": "python3 hott_kernel.py memory_consolidate <id1,id2,...> --content '...' [--tags t1,t2]",
                "memory_steer": "python3 hott_kernel.py memory_steer [--output full|summary]",
                "memory_establish": "python3 hott_kernel.py memory_establish",
                "memory_drift": "python3 hott_kernel.py memory_drift",
                "memory_compact": "python3 hott_kernel.py memory compact [--consolidated|--all] [--type episodic] [--dry-run|--stats|--restore <id>|--restore-all]",
                "memory_bridge": "python3 hott_kernel.py memory bridge <from_id> <to_id> [type] [--strength 0.7] [--unsafe]",
                "memory_bridge_auto": "python3 hott_kernel.py memory bridge_auto [--min-shared-tags 1] [--type semantic] [--dry-run]",
                "memory_bridge_candidates": "python3 hott_kernel.py memory bridge_candidates [--min-shared-tags 1]",
                "memory_kan": "python3 hott_kernel.py memory kan <query> [--mode lan|ran|both] [--max-depth 2]",
                "fiber_init": "python3 hott_kernel.py fiber init <task> <focus>",
                "fiber_lift": "python3 hott_kernel.py fiber lift [--query q] [--type t] [--tags t1,t2] [--max 10]",
                "fiber_descend": "python3 hott_kernel.py fiber descend <memory_id> | --all [--reason r]",
                "fiber_status": "python3 hott_kernel.py fiber status",
                "fiber_section_start": "python3 hott_kernel.py fiber section_start <name> <narrative>",
                "fiber_section_add": "python3 hott_kernel.py fiber section_add <memory_id>",
                "fiber_section_status": "python3 hott_kernel.py fiber section_status",
                "fiber_switch": "python3 hott_kernel.py fiber switch <new_task> <new_focus>",
                "fiber_transport": "python3 hott_kernel.py fiber transport <source_fiber_id> <new_task> <new_focus> [--threshold 0.6] [--max 10] [--dry-run]",
                "fiber_list_archives": "python3 hott_kernel.py fiber list_archives",
                "xanalyze": "python3 hott_kernel.py xanalyze [root] [--output summary|full] [--no-store] [--analyzers a,b]",
                "xsteer": "python3 hott_kernel.py xsteer [root] [--output full|summary]",
                "xcontext": "python3 hott_kernel.py xcontext <file_path>",
            },
        }, indent=2))
        return

    runtime_options = {
        "project_root": None,
        "scope": None,
        "state_dir": None,
    }
    runtime_flags = {
        "--memory-project-root": "project_root",
        "--memory-scope": "scope",
        "--memory-state-dir": "state_dir",
    }
    for index, argument in enumerate(sys.argv):
        option_name = runtime_flags.get(argument)
        if option_name is None:
            continue
        if index + 1 >= len(sys.argv) or sys.argv[index + 1].startswith("--"):
            _emit_cli_result(_kernel_error(
                "missing_memory_runtime_option",
                f"{argument} requires a non-empty value.",
                option=argument,
            ))
        runtime_options[option_name] = sys.argv[index + 1]
    if any(value is not None for value in runtime_options.values()):
        if not MEMORY_RUNTIME_AVAILABLE:
            _emit_cli_result(_kernel_error(
                "memory_runtime_unavailable",
                "Memory runtime configuration is not available.",
            ))
        configure_memory_runtime(**runtime_options)
        if runtime_options["project_root"] is not None or runtime_options["scope"] is not None:
            _MEMORY_SCOPE_EXPLICIT = True

    requested_cache_mode = _ACTIVE_GRAPH_CACHE_MODE
    for index, argument in enumerate(sys.argv):
        if argument == "--cache-mode":
            if index + 1 >= len(sys.argv):
                _emit_cli_result(_kernel_error(
                    "missing_graph_cache_mode",
                    "--cache-mode requires auto, refresh, or off.",
                    supported_cache_modes=list(CACHE_MODES),
                ))
            requested_cache_mode = sys.argv[index + 1]
    cache_mode_error = _set_graph_cache_mode(requested_cache_mode)
    if cache_mode_error:
        _emit_cli_result(cache_mode_error)

    mode = sys.argv[1]

    # Valid modes contract and self-healing guidance for AI tools
    VALID_MODES = {
        "analyze", "analyzers", "cache", "impact", "outline", "brief", "cycle_break", "context",
        "establish", "synthesize", "steer", "memory_store", "memory_recall",
        "memory_analyze", "memory_stats", "memory_associate", "memory_consolidate",
        "memory_steer", "memory_establish", "memory_drift", "memory_compact",
        "memory_bridge", "memory_bridge_auto", "memory_bridge_candidates",
        "memory_kan", "memory", "fiber", "xanalyze", "xsteer", "xcontext",
    }

    if mode not in VALID_MODES:
        _emit_cli_result(_kernel_error(
            "unknown_mode",
            f"Unknown mode: '{mode}'.",
            valid_modes=sorted(list(VALID_MODES)),
            suggested_fix=(
                "Choose one of the supported modes: analyze, context, synthesize, "
                "steer, impact, outline, brief, cache, memory_recall, memory_store, xanalyze, xsteer, xcontext."
            ),
        ))
        return

    if mode == "analyze":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."

        # Parse flags
        analyzers = None
        output_mode = "full"

        for i, arg in enumerate(sys.argv):
            if arg == "--analyzers" and i + 1 < len(sys.argv):
                analyzers = sys.argv[i + 1].split(",")
            elif arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]

        if output_mode not in ("full", "summary", "findings", "graph"):
            _emit_cli_result(_kernel_error(
                "invalid_output_mode",
                f"Invalid output mode: {output_mode}",
                output_mode=output_mode,
                supported_output_modes=["full", "summary", "findings", "graph"],
            ))

        result = kernel_analyze(root, analyzers, output_mode)
        _emit_cli_result(result)

    elif mode == "analyzers":
        if REGISTRY_AVAILABLE:
            _emit_cli_result({
                "available_analyzers": get_available_analyzers(),
            })
        else:
            _emit_cli_result(_kernel_error(
                "registry_unavailable",
                "registry not available",
            ))

    elif mode == "cache":
        if len(sys.argv) < 3 or sys.argv[2].startswith("--"):
            _emit_cli_result(_kernel_error(
                "missing_cache_action",
                "Usage: hott_kernel.py cache status|refresh|clear [root]",
                supported_actions=["status", "refresh", "clear"],
            ))
        action = sys.argv[2]
        root = (
            sys.argv[3]
            if len(sys.argv) > 3 and not sys.argv[3].startswith("--")
            else "."
        )
        _emit_cli_result(kernel_cache(action, root))

    elif mode == "impact":
        if len(sys.argv) < 3:
            _emit_cli_result(_kernel_error(
                "missing_argument",
                "Usage: hott_kernel.py impact <file> [root]",
            ))
        target = sys.argv[2]
        root = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "."
        output_mode = "full"
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        result = kernel_impact(root, target, output_mode)
        _emit_cli_result(result)

    elif mode == "outline":
        if len(sys.argv) < 3:
            _emit_cli_result(_kernel_error(
                "missing_argument",
                "Usage: hott_kernel.py outline <file> [root]",
            ))
        target = sys.argv[2]
        root = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "."
        result = kernel_outline(root, target)
        _emit_cli_result(result)

    elif mode == "brief":
        if len(sys.argv) < 3:
            _emit_cli_result(_kernel_error(
                "missing_argument",
                "Usage: hott_kernel.py brief <file> [root]",
            ))
        target = sys.argv[2]
        root = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "."
        output_mode = "full"
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        result = kernel_brief(root, target, output_mode)
        _emit_cli_result(result)

    elif mode == "cycle_break":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."
        target_file = None
        output_mode = "full"
        for i, arg in enumerate(sys.argv):
            if arg in ("--target", "--target-file", "--file") and i + 1 < len(sys.argv):
                target_file = sys.argv[i + 1]
            elif arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        result = kernel_cycle_break(root, target_file, output_mode)
        _emit_cli_result(result)

    elif mode == "context":
        if len(sys.argv) < 3 or sys.argv[2].startswith("--"):
            _emit_cli_result(_kernel_error(
                "missing_argument",
                "Usage: hott_kernel.py context <query> [root] [--target file[,file]] [--budget-tokens N] [--max-hops N] [--detail outline|source] [--output prompt|summary|full]",
            ))
        query = sys.argv[2]
        root = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else "."
        target_files: List[str] = []
        budget_tokens = DEFAULT_BUDGET_TOKENS
        max_hops = DEFAULT_MAX_HOPS
        detail = "source"
        output_mode = "prompt"
        parse_error = None
        for i, arg in enumerate(sys.argv):
            if arg in ("--target", "--targets", "--target-file", "--target-files") and i + 1 < len(sys.argv):
                target_files.extend(
                    value.strip()
                    for value in sys.argv[i + 1].split(",")
                    if value.strip()
                )
            elif arg in ("--budget-tokens", "--budget_tokens") and i + 1 < len(sys.argv):
                try:
                    budget_tokens = int(sys.argv[i + 1])
                except ValueError:
                    parse_error = _kernel_error(
                        "invalid_context_budget",
                        "--budget-tokens must be an integer.",
                        budget_tokens=sys.argv[i + 1],
                    )
            elif arg in ("--max-hops", "--max_hops") and i + 1 < len(sys.argv):
                try:
                    max_hops = int(sys.argv[i + 1])
                except ValueError:
                    parse_error = _kernel_error(
                        "invalid_context_hops",
                        "--max-hops must be an integer.",
                        max_hops=sys.argv[i + 1],
                    )
            elif arg == "--detail" and i + 1 < len(sys.argv):
                detail = sys.argv[i + 1]
            elif arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        if parse_error:
            _emit_cli_result(parse_error)
        result = kernel_context(
            root,
            query,
            target_files=target_files,
            budget_tokens=budget_tokens,
            max_hops=max_hops,
            detail=detail,
            output_mode=output_mode,
        )
        _emit_cli_result(result)

    elif mode == "establish":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."
        baseline_path = None
        for i, arg in enumerate(sys.argv):
            if arg == "--baseline" and i + 1 < len(sys.argv):
                baseline_path = sys.argv[i + 1]
        result = kernel_establish(root, baseline_path)
        _emit_cli_result(result)

    elif mode == "synthesize":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."
        output_mode = "full"
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        result = kernel_synthesize(root, output_mode)
        _emit_cli_result(result)

    elif mode == "steer":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."
        output_mode = "full"
        baseline_path = None
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
            elif arg == "--baseline" and i + 1 < len(sys.argv):
                baseline_path = sys.argv[i + 1]
        result = kernel_steer(root, baseline_path, output_mode)
        _emit_cli_result(result)

    elif mode == "memory_store":
        if len(sys.argv) < 4:
            _emit_cli_result({"error": "Usage: hott_kernel.py memory_store <type> <content> [--source src] [--importance 0.5] [--tags t1,t2]"})
            return
        m_type = sys.argv[2]
        m_content = sys.argv[3]
        m_source = "manual"
        m_importance = 0.5
        m_tags = None
        for i, arg in enumerate(sys.argv):
            if arg == "--source" and i + 1 < len(sys.argv):
                m_source = sys.argv[i + 1]
            elif arg == "--importance" and i + 1 < len(sys.argv):
                try:
                    m_importance = float(sys.argv[i + 1])
                except ValueError:
                    pass
            elif arg == "--tags" and i + 1 < len(sys.argv):
                m_tags = sys.argv[i + 1]
        result = kernel_memory_store(m_type, m_content, m_source, m_importance, m_tags)
        _emit_cli_result(result)

    elif mode == "memory_recall":
        m_query = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
        m_type = None
        m_tags = None
        m_limit = 20
        for i, arg in enumerate(sys.argv):
            if arg == "--type" and i + 1 < len(sys.argv):
                m_type = sys.argv[i + 1]
            elif arg == "--tags" and i + 1 < len(sys.argv):
                m_tags = sys.argv[i + 1]
            elif arg == "--limit" and i + 1 < len(sys.argv):
                try:
                    m_limit = int(sys.argv[i + 1])
                except ValueError:
                    pass
        result = kernel_memory_recall(m_query, m_type, m_tags, m_limit)
        _emit_cli_result(result)

    elif mode == "memory_analyze":
        m_analyzers = None
        m_output = "full"
        m_include_historical = "--include-historical" in sys.argv
        m_include_provenance = "--include-provenance" in sys.argv
        for i, arg in enumerate(sys.argv):
            if arg == "--analyzers" and i + 1 < len(sys.argv):
                m_analyzers = sys.argv[i + 1].split(",")
            elif arg == "--output" and i + 1 < len(sys.argv):
                m_output = sys.argv[i + 1]
        result = kernel_memory_analyze(
            m_analyzers,
            m_output,
            include_historical=m_include_historical,
            include_provenance=m_include_provenance,
        )
        _emit_cli_result(result)

    elif mode == "memory_stats":
        result = kernel_memory_stats()
        _emit_cli_result(result)

    elif mode in ("memory_associate", "associate"):
        if len(sys.argv) < 5:
            _emit_cli_result({"error": "Usage: hott_kernel.py memory_associate <from_id> <to_id> <type> [--strength 0.7]"})
            return
        from_id = sys.argv[2]
        to_id = sys.argv[3]
        assoc_type = sys.argv[4]
        strength = 0.5
        for i, arg in enumerate(sys.argv):
            if arg == "--strength" and i + 1 < len(sys.argv):
                try:
                    strength = float(sys.argv[i + 1])
                except ValueError:
                    pass
        result = kernel_memory_associate(from_id, to_id, assoc_type, strength)
        _emit_cli_result(result)

    elif mode in ("memory_consolidate", "consolidate"):
        if len(sys.argv) < 3:
            _emit_cli_result({"error": "Usage: hott_kernel.py memory_consolidate <id1,id2,...> --content '...'"})
            return
        source_ids = sys.argv[2].split(",")
        content = ""
        tags = None
        importance = 0.9
        for i, arg in enumerate(sys.argv):
            if arg == "--content" and i + 1 < len(sys.argv):
                content = sys.argv[i + 1]
            elif arg == "--tags" and i + 1 < len(sys.argv):
                tags = sys.argv[i + 1]
            elif arg == "--importance" and i + 1 < len(sys.argv):
                try:
                    importance = float(sys.argv[i + 1])
                except ValueError:
                    pass
        if not content:
            _emit_cli_result({"error": "--content is required"})
            return
        result = kernel_memory_consolidate(source_ids, content, tags, importance)
        _emit_cli_result(result)

    elif mode in ("memory_steer",):
        output_mode = "full"
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        result = kernel_memory_steer(output_mode)
        _emit_cli_result(result)

    elif mode in ("memory_establish",):
        result = kernel_memory_establish()
        _emit_cli_result(result)

    elif mode in ("memory_drift",):
        result = kernel_memory_drift()
        _emit_cli_result(result)

    elif mode == "memory":
        if len(sys.argv) < 3:
            _emit_cli_result({"error": "Usage: hott_kernel.py memory <submode> ..."})
            return
        submode = sys.argv[2]
        if submode == "store":
            if len(sys.argv) < 5:
                _emit_cli_result({"error": "Usage: memory store <type> <content> [--source src] [--importance 0.5] [--tags t1,t2]"})
                return
            m_type = sys.argv[3]
            m_content = sys.argv[4]
            m_source = "manual"
            m_importance = 0.5
            m_tags = None
            for i, arg in enumerate(sys.argv):
                if arg == "--source" and i + 1 < len(sys.argv):
                    m_source = sys.argv[i + 1]
                elif arg == "--importance" and i + 1 < len(sys.argv):
                    try:
                        m_importance = float(sys.argv[i + 1])
                    except ValueError:
                        pass
                elif arg == "--tags" and i + 1 < len(sys.argv):
                    m_tags = sys.argv[i + 1]
            result = kernel_memory_store(m_type, m_content, m_source, m_importance, m_tags)
            _emit_cli_result(result)
        elif submode == "recall":
            m_query = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else None
            m_type = None
            m_tags = None
            m_limit = 20
            for i, arg in enumerate(sys.argv):
                if arg == "--type" and i + 1 < len(sys.argv):
                    m_type = sys.argv[i + 1]
                elif arg == "--tags" and i + 1 < len(sys.argv):
                    m_tags = sys.argv[i + 1]
                elif arg == "--limit" and i + 1 < len(sys.argv):
                    try:
                        m_limit = int(sys.argv[i + 1])
                    except ValueError:
                        pass
            result = kernel_memory_recall(m_query, m_type, m_tags, m_limit)
            _emit_cli_result(result)
        elif submode == "analyze":
            m_analyzers = None
            m_output = "full"
            m_include_historical = "--include-historical" in sys.argv
            m_include_provenance = "--include-provenance" in sys.argv
            for i, arg in enumerate(sys.argv):
                if arg == "--analyzers" and i + 1 < len(sys.argv):
                    m_analyzers = sys.argv[i + 1].split(",")
                elif arg == "--output" and i + 1 < len(sys.argv):
                    m_output = sys.argv[i + 1]
            result = kernel_memory_analyze(
                m_analyzers,
                m_output,
                include_historical=m_include_historical,
                include_provenance=m_include_provenance,
            )
            _emit_cli_result(result)
        elif submode == "stats":
            result = kernel_memory_stats()
            _emit_cli_result(result)
        elif submode == "associate":
            if len(sys.argv) < 6:
                _emit_cli_result({"error": "Usage: memory associate <from_id> <to_id> <type> [--strength 0.7]"})
                return
            from_id = sys.argv[3]
            to_id = sys.argv[4]
            assoc_type = sys.argv[5]
            strength = 0.5
            for i, arg in enumerate(sys.argv):
                if arg == "--strength" and i + 1 < len(sys.argv):
                    try:
                        strength = float(sys.argv[i + 1])
                    except ValueError:
                        pass
            result = kernel_memory_associate(from_id, to_id, assoc_type, strength)
            _emit_cli_result(result)
        elif submode == "consolidate":
            if len(sys.argv) < 5:
                _emit_cli_result({"error": "Usage: memory consolidate <id1,id2,...> --content '...'"})
                return
            source_ids = sys.argv[3].split(",")
            content = ""
            tags = None
            importance = 0.9
            for i, arg in enumerate(sys.argv):
                if arg == "--content" and i + 1 < len(sys.argv):
                    content = sys.argv[i + 1]
                elif arg == "--tags" and i + 1 < len(sys.argv):
                    tags = sys.argv[i + 1]
                elif arg == "--importance" and i + 1 < len(sys.argv):
                    try:
                        importance = float(sys.argv[i + 1])
                    except ValueError:
                        pass
            if not content:
                _emit_cli_result({"error": "--content is required"})
                return
            result = kernel_memory_consolidate(source_ids, content, tags, importance)
            _emit_cli_result(result)
        elif submode == "steer":
            output_mode = "full"
            for i, arg in enumerate(sys.argv):
                if arg == "--output" and i + 1 < len(sys.argv):
                    output_mode = sys.argv[i + 1]
            result = kernel_memory_steer(output_mode)
            _emit_cli_result(result)
        elif submode == "establish":
            result = kernel_memory_establish()
            _emit_cli_result(result)
        elif submode == "drift":
            result = kernel_memory_drift()
            _emit_cli_result(result)
        elif submode == "betti_breakdown":
            result = kernel_memory_betti_breakdown()
            _emit_cli_result(result)
        elif submode == "consolidate_by_tag":
            if len(sys.argv) < 4:
                _emit_cli_result({"error": "Usage: memory consolidate_by_tag <tag> [--content '...'] [--importance 0.9]"})
                return
            m_tag = sys.argv[3]
            m_content = None
            m_importance = 0.9
            for i, arg in enumerate(sys.argv):
                if arg == "--content" and i + 1 < len(sys.argv):
                    m_content = sys.argv[i + 1]
                elif arg == "--importance" and i + 1 < len(sys.argv):
                    try:
                        m_importance = float(sys.argv[i + 1])
                    except ValueError:
                        pass
            result = kernel_memory_consolidate_by_tag(m_tag, m_content, m_importance)
            _emit_cli_result(result)
        elif submode == "consolidate_auto":
            min_size = 3
            m_importance = 0.9
            for i, arg in enumerate(sys.argv):
                if arg == "--min-size" and i + 1 < len(sys.argv):
                    try:
                        min_size = int(sys.argv[i + 1])
                    except ValueError:
                        pass
                elif arg == "--importance" and i + 1 < len(sys.argv):
                    try:
                        m_importance = float(sys.argv[i + 1])
                    except ValueError:
                        pass
            result = kernel_memory_consolidate_auto(min_size, m_importance)
            _emit_cli_result(result)
        elif submode == "unconsolidated_tags":
            result = kernel_memory_unconsolidated_tags()
            _emit_cli_result(result)
        elif submode == "compact":
            # Parse flags
            only_consolidated = True
            memory_type = "episodic"
            dry_run = False
            restore_all = False
            restore_id = None
            stats = False

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--consolidated":
                    only_consolidated = True
                elif arg == "--all":
                    only_consolidated = False
                elif arg == "--type" and i + 1 < len(sys.argv):
                    memory_type = sys.argv[i + 1]
                    i += 1
                elif arg == "--dry-run":
                    dry_run = True
                elif arg == "--restore-all":
                    restore_all = True
                elif arg == "--restore" and i + 1 < len(sys.argv):
                    restore_id = sys.argv[i + 1]
                    i += 1
                elif arg == "--stats":
                    stats = True
                i += 1

            result = kernel_memory_compact(
                only_consolidated=only_consolidated,
                memory_type=memory_type,
                dry_run=dry_run,
                restore_id=restore_id,
                restore_all=restore_all,
                stats=stats,
            )
            _emit_cli_result(result)
        elif submode == "bridge":
            # memory bridge <from_id> <to_id> [type] [--strength 0.7] [--unsafe]
            if len(sys.argv) < 5:
                _emit_cli_result({"error": "Usage: memory bridge <from_id> <to_id> [type] [--strength 0.7]"})
                return
            from_id = sys.argv[3]
            to_id = sys.argv[4]
            assoc_type = sys.argv[5] if len(sys.argv) > 5 and not sys.argv[5].startswith("--") else "semantic"
            strength = 0.7
            safe_mode = True
            for i, arg in enumerate(sys.argv):
                if arg == "--strength" and i + 1 < len(sys.argv):
                    try:
                        strength = float(sys.argv[i + 1])
                    except ValueError:
                        pass
                elif arg == "--unsafe":
                    safe_mode = False
            result = kernel_memory_bridge(from_id, to_id, assoc_type, strength, safe_mode)
            _emit_cli_result(result)

        elif submode == "bridge_auto":
            # memory bridge_auto [--min-shared-tags 1] [--type semantic] [--dry-run] [--unsafe]
            min_shared_tags = 1
            assoc_type = "semantic"
            dry_run = False
            safe_mode = True
            for i, arg in enumerate(sys.argv):
                if arg == "--min-shared-tags" and i + 1 < len(sys.argv):
                    try:
                        min_shared_tags = int(sys.argv[i + 1])
                    except ValueError:
                        pass
                elif arg == "--type" and i + 1 < len(sys.argv):
                    assoc_type = sys.argv[i + 1]
                elif arg == "--dry-run":
                    dry_run = True
                elif arg == "--unsafe":
                    safe_mode = False
            result = kernel_memory_bridge_auto(min_shared_tags, assoc_type, safe_mode, dry_run)
            _emit_cli_result(result)

        elif submode == "bridge_candidates":
            # memory bridge_candidates [--min-shared-tags 1]
            min_shared_tags = 1
            for i, arg in enumerate(sys.argv):
                if arg == "--min-shared-tags" and i + 1 < len(sys.argv):
                    try:
                        min_shared_tags = int(sys.argv[i + 1])
                    except ValueError:
                        pass
            result = kernel_memory_bridge_candidates(min_shared_tags)
            _emit_cli_result(result)
        elif submode == "kan":
            # memory kan <query> [--mode lan|ran|both] [--max-depth 2]
            if len(sys.argv) < 4:
                _emit_cli_result({"error": "Usage: memory kan <query> [--mode lan|ran|both] [--max-depth 2]"})
                return
            query = sys.argv[3]
            kan_mode = "both"
            max_depth = 2
            for i, arg in enumerate(sys.argv):
                if arg == "--mode" and i + 1 < len(sys.argv):
                    kan_mode = sys.argv[i + 1]
                elif arg == "--max-depth" and i + 1 < len(sys.argv):
                    try:
                        max_depth = int(sys.argv[i + 1])
                    except ValueError:
                        pass
            if kan_mode not in ("lan", "ran", "both"):
                _emit_cli_result({"error": f"Invalid mode: {kan_mode}. Use lan, ran, or both."})
                return
            result = kernel_memory_kan(query, kan_mode, max_depth)
            _emit_cli_result(result)
        else:
            _emit_cli_result({"error": f"Unknown memory submode: {submode}"})

    elif mode == "xanalyze":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."
        output_mode = "summary"
        auto_store = True
        analyzers = None
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
            elif arg == "--no-store":
                auto_store = False
            elif arg == "--analyzers" and i + 1 < len(sys.argv):
                analyzers = sys.argv[i + 1].split(",")
        result = kernel_xanalyze(root, analyzers, output_mode, auto_store)
        _emit_cli_result(result)

    elif mode == "xsteer":
        root = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "."
        output_mode = "full"
        for i, arg in enumerate(sys.argv):
            if arg == "--output" and i + 1 < len(sys.argv):
                output_mode = sys.argv[i + 1]
        result = kernel_xsteer(root, output_mode)
        _emit_cli_result(result)

    elif mode == "xcontext":
        if len(sys.argv) < 3:
            _emit_cli_result({"error": "Usage: hott_kernel.py xcontext <file_path>"})
            return
        file_path = sys.argv[2]
        result = kernel_xcontext(file_path)
        _emit_cli_result(result)

    elif mode == "fiber":
        if len(sys.argv) < 3:
            _emit_cli_result({
                "error": "Usage: hott_kernel.py fiber <init|lift|descend|status|section_start|section_add|section_status|switch|transport|list_archives> [args]"
            })
            return
        subcommand = sys.argv[2]
        
        if subcommand == "transport":
            # fiber transport <source_fiber_id> <new_task> <new_focus> [--threshold 0.6] [--max 10] [--dry-run]
            if len(sys.argv) < 6:
                _emit_cli_result({
                    "error": "Usage: fiber transport <source_fiber_id> <new_task> <new_focus> [--threshold 0.6] [--max 10] [--dry-run]"
                })
                return
            source_id = sys.argv[3]
            new_task = sys.argv[4]
            new_focus = sys.argv[5]
            threshold = 0.6
            max_transport = 10
            dry_run = False
            i = 6
            while i < len(sys.argv):
                if sys.argv[i] == "--threshold" and i + 1 < len(sys.argv):
                    try:
                        threshold = float(sys.argv[i + 1])
                    except ValueError:
                        pass
                    i += 2
                elif sys.argv[i] == "--max" and i + 1 < len(sys.argv):
                    try:
                        max_transport = int(sys.argv[i + 1])
                    except ValueError:
                        pass
                    i += 2
                elif sys.argv[i] == "--dry-run":
                    dry_run = True
                    i += 1
                else:
                    i += 1
            result = kernel_fiber_transport(source_id, new_task, new_focus, threshold, max_transport, dry_run)
            _emit_cli_result(result)
        
        elif subcommand == "list_archives":
            result = kernel_fiber_list_archives()
            _emit_cli_result(result)
        
        else:
            args = sys.argv[3:]
            result = kernel_fiber(subcommand, args)
            _emit_cli_result(result)

    else:
        _emit_cli_result(_kernel_error(
            "unknown_mode",
            f"Unknown mode: {mode}",
            mode=mode,
        ))



if __name__ == "__main__":
    try:
        main()
    except MemoryStateError as exc:
        _emit_cli_result(_kernel_error(
            getattr(exc, "error_code", "memory_state_error"),
            str(exc),
            **getattr(exc, "details", {}),
        ))
