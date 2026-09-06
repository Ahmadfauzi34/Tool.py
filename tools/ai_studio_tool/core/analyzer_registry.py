"""
Analyzer Registry — HoTT Kernel
Schema Version: 3.0.0-kernel

Setiap analyzer adalah fungsi yang menerima SharedGraph
dan mengembalikan findings. Tidak ada analyzer yang boleh
melakukan filesystem scan sendiri.
"""

import hashlib
import inspect
import marshal
import os
import sys
from typing import Any, Dict, List, Optional

# Import topology analyzers
try:
    from codebase.topology_analyzers import (
        analyze_circular,
        analyze_risk,
        analyze_test_reachability,
    )
    TOPO_ANALYZERS_AVAILABLE = True
except ImportError:
    try:
        from topology_analyzers import (
            analyze_circular,
            analyze_risk,
            analyze_test_reachability,
        )
        TOPO_ANALYZERS_AVAILABLE = True
    except ImportError:
        TOPO_ANALYZERS_AVAILABLE = False


# Import performance analyzers
try:
    from codebase.performance_analyzers import (
        analyze_async_waterfall,
        analyze_deopt,
        analyze_gc_pressure,
        analyze_cache,
    )
    PERF_ANALYZERS_AVAILABLE = True
except ImportError:
    try:
        from performance_analyzers import (
            analyze_async_waterfall,
            analyze_deopt,
            analyze_gc_pressure,
            analyze_cache,
        )
        PERF_ANALYZERS_AVAILABLE = True
    except ImportError:
        PERF_ANALYZERS_AVAILABLE = False


# Import HoTT analyzers
try:
    from codebase.hott_analyzers import (
        analyze_isomorphism,
        analyze_sheaf,
        analyze_homotopy,
        analyze_manifold,
    )
    HOTT_ANALYZERS_AVAILABLE = True
except ImportError:
    try:
        from hott_analyzers import (
            analyze_isomorphism,
            analyze_sheaf,
            analyze_homotopy,
            analyze_manifold,
        )
        HOTT_ANALYZERS_AVAILABLE = True
    except ImportError:
        HOTT_ANALYZERS_AVAILABLE = False


ANALYZER_REGISTRY: Dict[str, Dict[str, Any]] = {}
ANALYZER_ENGINE_SCHEMA_VERSION = "analyzer-engine-v1"


def register_analyzer(name: str, fn: Any, description: str, category: str, available: bool = True) -> None:
    """Mendaftarkan analyzer ke registry."""
    ANALYZER_REGISTRY[name] = {
        "fn": fn,
        "description": description,
        "category": category,
        "available": available,
    }


def analyze_orphan(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter untuk unreferenced_files detection."""
    findings = []
    metadata = shared_graph.get("node_metadata", {})

    for fp, meta in metadata.items():
        fan_in = meta.get("fan_in", 0)
        is_entrypoint = meta.get("is_entrypoint", False)
        is_test = meta.get("is_test", False)

        if fan_in == 0 and not is_entrypoint and not is_test:
            findings.append({
                "type": "unreferenced_file",
                "severity": "low",
                "file": fp,
                "node_type": meta.get("type", "Other"),
                "observation": (
                    f"File '{fp}' has fan_in=0 and is not an entrypoint "
                    f"or test file. Potentially unreferenced."
                ),
            })

    findings.sort(key=lambda f: f["file"])

    return {
        "analyzer": "topo.orphan",
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
        },
    }


def analyze_entrypoint_impact(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter untuk entrypoint impact analysis."""
    findings = []
    metadata = shared_graph.get("node_metadata", {})

    for fp, meta in metadata.items():
        if meta.get("is_entrypoint"):
            findings.append({
                "type": "entrypoint",
                "severity": "info",
                "file": fp,
                "entrypoint_kind": meta.get("entrypoint_kind", "none"),
                "confidence": meta.get("entrypoint_confidence", 0.0),
                "fan_in": meta.get("fan_in", 0),
                "fan_out": meta.get("fan_out", 0),
            })

    return {
        "analyzer": "topo.entrypoint",
        "findings": findings,
        "summary": {
            "total_entrypoints": len(findings),
        },
    }


# Register all 13 analyzers
register_analyzer("topo.orphan", analyze_orphan, "Deteksi unreferenced/orphan source files", "topology")
register_analyzer("topo.entrypoint", analyze_entrypoint_impact, "Deteksi entry points dan transitively reachable files", "topology")

if TOPO_ANALYZERS_AVAILABLE:
    register_analyzer("topo.circular", analyze_circular, "Deteksi circular import dependencies (cycle basis)", "topology")
    register_analyzer("topo.risk", analyze_risk, "Evaluasi change risk per file (fan-in, boundary, entrypoint)", "topology")
    register_analyzer(
        "topo.test_reachability",
        analyze_test_reachability,
        "Petakan static import reachability dari test ke source (bukan runtime coverage)",
        "topology",
    )

if PERF_ANALYZERS_AVAILABLE:
    register_analyzer("perf.async", analyze_async_waterfall, "Deteksi sequential await di loop dan waterfall async", "performance")
    register_analyzer("perf.deopt", analyze_deopt, "Deteksi V8 deoptimization triggers (eval, delete, polymorphic)", "performance")
    register_analyzer("perf.gc", analyze_gc_pressure, "Deteksi GC pressure patterns (large allocations in loops)", "performance")
    register_analyzer("perf.cache", analyze_cache, "Audit implementasi in-memory cache (TTL, eviction, collision)", "performance")

if HOTT_ANALYZERS_AVAILABLE:
    register_analyzer("hott.isomorphism", analyze_isomorphism, "Observasi type shape equivalence (Univalence)", "hott")
    register_analyzer("hott.sheaf", analyze_sheaf, "Verifikasi boundary gluing across architectural layers", "hott")
    register_analyzer("hott.homotopy", analyze_homotopy, "Analisis import path contractibility dan cycle topology", "hott")
    register_analyzer("hott.manifold", analyze_manifold, "Konstruksi topological manifold dan Betti numbers (beta_0, beta_1, beta_2)", "hott")


def get_available_analyzers() -> List[str]:
    """Mengembalikan daftar nama analyzer yang terdaftar dan available."""
    return [k for k, v in ANALYZER_REGISTRY.items() if v.get("available", True)]


def get_analyzer_engine_signature(
    analyzer_names: Optional[List[str]] = None,
) -> str:
    """Hash analyzer source modules so code changes invalidate cached evidence."""
    names = analyzer_names if analyzer_names is not None else get_available_analyzers()
    digest = hashlib.sha256()
    digest.update(ANALYZER_ENGINE_SCHEMA_VERSION.encode("utf-8"))
    digest.update(repr(tuple(sys.version_info[:3])).encode("utf-8"))
    module_payloads: Dict[str, bytes] = {}

    for name in sorted(set(names)):
        entry = ANALYZER_REGISTRY.get(name, {})
        fn = entry.get("fn")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry.get("category", "")).encode("utf-8"))
        digest.update(b"\0")
        if not callable(fn):
            digest.update(b"unavailable\0")
            continue

        module_name = getattr(fn, "__module__", "")
        digest.update(module_name.encode("utf-8"))
        digest.update(b"\0")
        source_path = inspect.getsourcefile(fn)
        if source_path and os.path.isfile(source_path):
            normalized_path = os.path.abspath(source_path)
            if normalized_path not in module_payloads:
                with open(normalized_path, "rb") as handle:
                    module_payloads[normalized_path] = handle.read()
            payload = module_payloads[normalized_path]
        else:
            code = getattr(fn, "__code__", None)
            payload = marshal.dumps(code) if code is not None else repr(fn).encode("utf-8")
        digest.update(hashlib.sha256(payload).digest())

    return f"sha256:{digest.hexdigest()}"


def run_analyzers(
    shared_graph: Dict[str, Any],
    analyzer_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Menjalankan kumpulan analyzer terhadap satu SharedGraph.
    
    Args:
        shared_graph: Dict SharedGraph yang dibangun oleh build_shared_graph()
        analyzer_names: List nama analyzer yang ingin dijalankan (None = semua)
    
    Returns:
        Dict dengan structure { "results": { analyzer_name: output }, ... }
    """
    to_run = analyzer_names if analyzer_names is not None else get_available_analyzers()
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    succeeded: List[str] = []
    
    for name in to_run:
        entry = ANALYZER_REGISTRY.get(name)
        if not entry:
            message = f"Analyzer '{name}' not found in registry"
            results[name] = {"error": message, "analyzer": name}
            errors[name] = message
            continue
        
        fn = entry.get("fn")
        if not callable(fn):
            message = f"Analyzer function for '{name}' is not callable"
            results[name] = {"error": message, "analyzer": name}
            errors[name] = message
            continue
        
        try:
            results[name] = fn(shared_graph)
            succeeded.append(name)
        except Exception as exc:
            message = str(exc)
            results[name] = {"error": message, "analyzer": name}
            errors[name] = message
            
    return {
        "analyzers_run": list(results.keys()),
        "analyzers_succeeded": succeeded,
        "analyzers_failed": len(errors),
        "errors": errors,
        "results": results,
    }
