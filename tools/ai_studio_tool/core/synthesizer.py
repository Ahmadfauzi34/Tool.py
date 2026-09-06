"""
Synthesizer — HoTT Kernel Core
Schema Version: 3.0.0-kernel

Unifies:
- Topological integrity synthesis
- Invariant encoding (fingerprint)
- Baseline management & drift detection
- Decoder steering context generation
"""

import os
import json
import math
import hashlib
import datetime
from typing import Any, Dict, List, Optional

_TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CODEBASE_BASELINE_DIR = os.path.join(_TOOL_ROOT, "data", "codebase", "baseline")
DEFAULT_BASELINE_PATH = os.path.join(DEFAULT_CODEBASE_BASELINE_DIR, "topological_baseline.json")


def _ensure_baseline_dir(path: str = DEFAULT_BASELINE_PATH) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def _saturate(x: float, half_point: float) -> float:
    if x <= 0:
        return 0.0
    if half_point <= 0:
        return 1.0
    return x / (x + half_point)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def synthesize_topological_integrity(
    scan_root: str,
    ignore_dirs: Optional[List[str]] = None,
    output_mode: str = "full",
    shared_graph: Optional[Dict[str, Any]] = None,
    analyzer_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Menjalankan sintesis integritas topologis menggunakan shared graph dan registry."""
    try:
        from core.shared_graph import build_shared_graph
        from core.analyzer_registry import run_analyzers
    except ImportError:
        from shared_graph import build_shared_graph
        from analyzer_registry import run_analyzers

    if shared_graph is None:
        shared_graph = build_shared_graph(scan_root, ignore_dirs=ignore_dirs)
    analyzers_result = analyzer_output
    if analyzers_result is None:
        analyzers_result = run_analyzers(shared_graph)

    # Calculate severity counts
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    total_findings = 0
    for res in analyzers_result.get("results", {}).values():
        for f in res.get("findings", []):
            sev = f.get("severity", "low")
            if sev in severity_counts:
                severity_counts[sev] += 1
            total_findings += 1

    total_files = shared_graph["summary"]["total_files"]
    weighted_sum = (
        severity_counts["high"] * 3
        + severity_counts["medium"] * 2
        + severity_counts["low"] * 1
    )
    pressure = weighted_sum / max(1, total_files)
    health_score = round(1.0 / (1.0 + pressure), 3)

    summary_data = {
        "total_files": total_files,
        "total_findings": total_findings,
        "findings_by_severity": severity_counts,
        "topological_health_score": health_score,
    }

    return {
        "schema_version": "3.0.0-kernel",
        "scan_root": scan_root,
        "total_files": total_files,
        "total_findings": total_findings,
        "findings_by_severity": severity_counts,
        "topological_health_score": health_score,
        "unified_summary": summary_data,
        "analyzers": analyzers_result,
    }


def encode_topological_invariants(
    scan_root: str,
    ignore_dirs: Optional[List[str]] = None,
    shared_graph: Optional[Dict[str, Any]] = None,
    analyzer_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mengencode topological fingerprint dari codebase."""
    try:
        from codebase.hott_analyzers import analyze_manifold
        from codebase.topology_analyzers import analyze_test_reachability
        from core.shared_graph import build_shared_graph
    except ImportError:
        from hott_analyzers import analyze_manifold
        from topology_analyzers import analyze_test_reachability
        from shared_graph import build_shared_graph

    graph = shared_graph
    if graph is None:
        graph = build_shared_graph(scan_root, ignore_dirs=ignore_dirs)
    analyzer_results = (
        analyzer_output.get("results", {})
        if isinstance(analyzer_output, dict)
        else {}
    )
    manifold_result = analyzer_results.get("hott.manifold")
    if not isinstance(manifold_result, dict) or manifold_result.get("error"):
        manifold_result = analyze_manifold(graph)
    test_reachability_result = analyzer_results.get("topo.test_reachability")
    if (
        not isinstance(test_reachability_result, dict)
        or test_reachability_result.get("error")
    ):
        test_reachability_result = analyze_test_reachability(graph)
    manifold = manifold_result.get("manifold", {})
    betti = manifold.get("betti_numbers", {})
    summary = manifold_result.get("summary", {})
    cycle_basis = manifold_result.get("cycle_basis", [])
    cycle_orientation_counts = manifold.get("cycle_orientation_counts", {})
    topological_model = manifold_result.get("topological_model", {})
    cycle_semantics = {
        "model": topological_model.get("name", "dependency_multigraph_1_complex"),
        "undirected_cycle_rank": betti.get("beta_1", 0),
        "directed_basis_witnesses": cycle_orientation_counts.get("directed", 0),
        "mixed_basis_witnesses": cycle_orientation_counts.get("mixed", 0),
        "cycle_basis_complete": manifold.get("cycle_basis_complete", False),
        "interpretation": (
            "beta_1 counts independent cycles after import orientation is ignored; "
            "use witness orientation or topo.circular for circular-import claims"
        ),
        "witnesses": [
            {
                "basis_index": item.get("basis_index"),
                "orientation": item.get("orientation"),
                "interpretation": item.get("interpretation"),
                "closed_path": item.get("closed_path", []),
            }
            for item in cycle_basis
        ],
    }
    test_summary = test_reachability_result.get("summary", {})
    test_topology = {
        "model": test_reachability_result.get("model", {}),
        "summary": test_summary,
        "high_influence_gaps": [
            {
                "file": item.get("file"),
                "fan_in": item.get("fan_in", 0),
                "reasons": item.get("reasons", []),
            }
            for item in test_reachability_result.get("findings", [])
            if item.get("type") == "high_influence_without_test_path"
        ],
        "testless_components": test_reachability_result.get("testless_components", []),
    }

    total_nodes = graph["summary"]["total_files"]
    total_edges = graph["summary"]["total_edges"]
    avg_degree = manifold.get("average_degree", (2.0 * total_edges / total_nodes) if total_nodes > 0 else 0.0)

    n_nodes = _saturate(total_nodes, 20.0)
    n_edges = _saturate(total_edges, 40.0)
    n_avg_degree = _saturate(avg_degree, 3.0)
    n_beta_0 = _saturate(betti.get("beta_0", 1), 3.0)
    n_beta_1 = _saturate(betti.get("beta_1", 0), 2.0)
    n_beta_2 = _saturate(betti.get("beta_2", 0), 2.0)

    complexity = manifold.get("complexity_score", (
        0.20 * n_nodes
        + 0.15 * n_edges
        + 0.15 * n_avg_degree
        + 0.15 * n_beta_0
        + 0.25 * n_beta_1
        + 0.10 * n_beta_2
    ))

    sig_src = f"V1|N:{total_nodes}|E:{total_edges}|B0:{betti.get('beta_0', 1)}|B1:{betti.get('beta_1', 0)}|B2:{betti.get('beta_2', 0)}"
    sig_hash = f"sha256:{hashlib.sha256(sig_src.encode('utf-8')).hexdigest()[:16]}"

    archetype = manifold.get("structural_archetype", "tree_like")

    normalized_vec = {
        "n_nodes": round(n_nodes, 4),
        "n_edges": round(n_edges, 4),
        "n_avg_degree": round(n_avg_degree, 4),
        "n_beta_0": round(n_beta_0, 4),
        "n_beta_1": round(n_beta_1, 4),
        "n_beta_2": round(n_beta_2, 4),
    }

    context_block = (
        f"[TOPOLOGICAL FINGERPRINT]\n"
        f"Signature: {sig_hash}\n"
        f"Archetype: {archetype}\n"
        f"Complexity: {complexity}\n"
        f"Betti: β₀={betti.get('beta_0', 1)}, β₁={betti.get('beta_1', 0)}, β₂={betti.get('beta_2', 0)}\n"
        f"Cycle Semantics: model={cycle_semantics['model']}, "
        f"directed_basis={cycle_semantics['directed_basis_witnesses']}, "
        f"mixed_basis={cycle_semantics['mixed_basis_witnesses']}\n"
        f"Interpretation: {cycle_semantics['interpretation']}\n"
    )
    witness_lines = [
        f"- basis#{item['basis_index']} [{item['orientation']}]: "
        f"{' -> '.join(item['closed_path'])}"
        for item in cycle_semantics["witnesses"][:5]
    ]
    if witness_lines:
        context_block += "Cycle Witnesses:\n" + "\n".join(witness_lines) + "\n"
    if len(cycle_semantics["witnesses"]) > 5:
        context_block += (
            f"- ... {len(cycle_semantics['witnesses']) - 5} additional basis witness(es) omitted\n"
        )
    context_block += (
        f"Test Topology: model=static_test_import_reachability, "
        f"reachable={test_summary.get('statically_reachable_files', 0)}/"
        f"{test_summary.get('total_production_files', 0)}, "
        f"ratio={test_summary.get('static_test_reachability_ratio', 0.0)}, "
        f"testless_components={test_summary.get('testless_component_count', 0)}, "
        f"high_influence_gaps={test_summary.get('high_influence_without_test_path', 0)}\n"
        "Test Interpretation: static import reachability is structural evidence, not runtime coverage.\n"
    )

    return {
        "available": True,
        "schema_version": "3.0.0-kernel",
        "topological_fingerprint": {
            "signature_hash": sig_hash,
            "normalized_vector": normalized_vec,
            "complexity_score": round(complexity, 4),
            "structural_archetype": archetype,
            "topological_model": cycle_semantics["model"],
            "cycle_orientation_counts": cycle_orientation_counts,
            "static_test_reachability_ratio": test_summary.get(
                "static_test_reachability_ratio", 0.0
            ),
        },
        "summary": {
            "betti_numbers": betti,
            "total_files": total_nodes,
            "total_edges": total_edges,
            "average_degree": avg_degree,
            "cycle_semantics": cycle_semantics,
            **summary,
        },
        "cycle_semantics": cycle_semantics,
        "test_topology": test_topology,
        "context_block": context_block,
    }


def establish_baseline(
    scan_root: str,
    baseline_path: Optional[str] = None,
    ignore_dirs: Optional[List[str]] = None,
    shared_graph: Optional[Dict[str, Any]] = None,
    analyzer_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Establish and save codebase topological baseline."""
    baseline_path = baseline_path or DEFAULT_BASELINE_PATH
    _ensure_baseline_dir(baseline_path)
    encoded = encode_topological_invariants(
        scan_root,
        ignore_dirs=ignore_dirs,
        shared_graph=shared_graph,
        analyzer_output=analyzer_output,
    )
    data = {
        "schema_version": "3.0.0-kernel",
        "created_at": (
            datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),
        "scan_root": scan_root,
        "fingerprint": encoded.get("topological_fingerprint", {}),
    }
    with open(baseline_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {
        "available": True,
        "status": "established",
        "baseline_path": baseline_path,
        **data,
    }


def load_baseline(baseline_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load baseline if exists, fallback to legacy location."""
    baseline_path = baseline_path or DEFAULT_BASELINE_PATH
    if os.path.exists(baseline_path):
        try:
            with open(baseline_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback to legacy location
    legacy_path = os.path.join(_TOOL_ROOT, "baseline", "topological_baseline.json")
    if os.path.exists(legacy_path):
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def steer_decoder(
    scan_root: str,
    baseline_path: Optional[str] = None,
    ignore_dirs: Optional[List[str]] = None,
    shared_graph: Optional[Dict[str, Any]] = None,
    analyzer_output: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate decoder steering signals for codebase."""
    baseline_path = baseline_path or DEFAULT_BASELINE_PATH
    current = encode_topological_invariants(
        scan_root,
        ignore_dirs=ignore_dirs,
        shared_graph=shared_graph,
        analyzer_output=analyzer_output,
    )
    curr_fp = current.get("topological_fingerprint", {})
    base = load_baseline(baseline_path)
    has_baseline = base is not None
    base_fp = base.get("fingerprint", {}) if base else {}

    # Distance calculation
    dist = 0.0
    if has_baseline and curr_fp and base_fp:
        v_curr = curr_fp.get("normalized_vector", {})
        v_base = base_fp.get("normalized_vector", {})
        sq_sum = sum((v_curr.get(k, 0) - v_base.get(k, 0)) ** 2 for k in v_curr)
        dist = round(math.sqrt(sq_sum), 4)

    archetype = curr_fp.get("structural_archetype", "tree_like")
    if archetype == "tree_like":
        strategy = "hierarchical_traversal"
    elif "cyclic" in archetype:
        strategy = "cycle_breaking_and_layering"
    else:
        strategy = "modular_component_expansion"

    complexity = curr_fp.get("complexity_score", 0.5)
    budget = "low" if complexity < 0.3 else ("medium" if complexity < 0.7 else "high")
    regrounding = dist > 0.25
    cycle_semantics = current.get("cycle_semantics", {})
    test_topology = current.get("test_topology", {})
    test_summary = test_topology.get("summary", {})

    prompt_block = (
        f"[TOPOLOGICAL STEERING SIGNAL]\n"
        f"Signature: {curr_fp.get('signature_hash', '')}\n"
        f"Archetype: {archetype}\n"
        f"Strategy: {strategy}\n"
        f"Budget: {budget}\n"
        f"Cycle Model: {cycle_semantics.get('model', 'unknown')}\n"
        f"Cycle Basis: directed={cycle_semantics.get('directed_basis_witnesses', 0)}, "
        f"mixed={cycle_semantics.get('mixed_basis_witnesses', 0)}\n"
        f"Cycle Interpretation: {cycle_semantics.get('interpretation', '')}\n"
        f"Test Topology: reachable={test_summary.get('statically_reachable_files', 0)}/"
        f"{test_summary.get('total_production_files', 0)}, "
        f"testless_components={test_summary.get('testless_component_count', 0)}, "
        f"high_influence_gaps={test_summary.get('high_influence_without_test_path', 0)}\n"
        "Test Interpretation: static import reachability, not runtime coverage.\n"
    )

    return {
        "available": True,
        "schema_version": "3.0.0-kernel",
        "baseline": {
            "exists": has_baseline,
            "path": baseline_path,
        },
        "has_baseline": has_baseline,
        "drift_analysis": {
            "has_drift": dist > 0.1,
            "drift_distance": dist,
            "topology_changed": dist > 0.05,
        },
        "drift_distance": dist,
        "steering_signals": {
            "reasoning_strategy": strategy,
            "reasoning_budget": budget,
            "regrounding_needed": regrounding,
        },
        "summary": current.get("summary"),
        "cycle_semantics": cycle_semantics,
        "test_topology": test_topology,
        "steering_prompt_block": prompt_block,
        "current_fingerprint": curr_fp,
        "baseline_fingerprint": base_fp if has_baseline else None,
    }
