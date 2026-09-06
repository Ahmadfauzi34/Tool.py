"""
Memory Analyzers — HoTT Kernel Memory Domain
Schema Version: 4.1.0-memory

Analyzers untuk memory topology.
Setara dengan performance_analyzers.py + hott_analyzers.py untuk codebase.
"""

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# Edge type categories untuk Betti calculation
REASONING_EDGE_TYPES = {"inferential", "causal"}
STRUCTURAL_EDGE_TYPES = {"temporal", "consolidation", "derivation", "redundancy"}
NEUTRAL_EDGE_TYPES = {"semantic", "contradiction"}


def _typed_edge_records(
    memory_graph: Dict[str, Any],
    edge_type_filter: Optional[Set[str]] = None,
) -> List[Tuple[str, str, str, str]]:
    """Return every association 1-cell without collapsing parallel edges."""
    records = memory_graph.get("edge_records")
    typed: List[Tuple[str, str, str, str]] = []
    if isinstance(records, list):
        for record in records:
            edge_type = str(record.get("type", "semantic"))
            if edge_type_filter is not None and edge_type not in edge_type_filter:
                continue
            typed.append((
                str(record.get("from", "")),
                str(record.get("to", "")),
                edge_type,
                str(record.get("association_id", "")),
            ))
        return typed

    edge_types = memory_graph.get("edge_types", {})
    for index, edge in enumerate(memory_graph.get("edges", [])):
        source, target = edge
        edge_type = str(edge_types.get((source, target), "semantic"))
        if edge_type_filter is not None and edge_type not in edge_type_filter:
            continue
        typed.append((source, target, edge_type, f"legacy_{index}"))
    return typed


class _UnionFind:
    def __init__(self, items: List[str]):
        self.parent = {x: x for x in items}
        self.rank = {x: 0 for x in items}

    def find(self, x: str) -> str:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: str, y: str) -> bool:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        return True


# ============================================================
# mem.fragmentation — Knowledge Silos (β₀)
# ============================================================

def analyze_fragmentation(memory_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deteksi knowledge fragmentation (β₀).
    Memori yang terisolasi dalam komponen terpisah.
    """
    findings: List[Dict[str, Any]] = []
    vertices = memory_graph.get("vertices", [])
    edges = memory_graph.get("edges", [])

    if not vertices:
        return {
            "analyzer": "mem.fragmentation",
            "findings": [],
            "summary": {"total_components": 0, "largest_component": 0},
        }

    # Union-Find untuk connected components
    uf = _UnionFind(vertices)
    for src, tgt in edges:
        uf.union(src, tgt)

    # Group by component
    components: Dict[str, List[str]] = {}
    for v in vertices:
        root = uf.find(v)
        components.setdefault(root, []).append(v)

    beta_0 = len(components)
    largest = max(len(c) for c in components.values()) if components else 0

    # Report isolated components (size 1)
    isolated = [c for c in components.values() if len(c) == 1]
    for comp in isolated:
        mid = comp[0]
        meta = memory_graph.get("node_metadata", {}).get(mid, {})
        findings.append({
            "type": "isolated_memory",
            "severity": "low",
            "memory_id": mid,
            "memory_type": meta.get("type", "unknown"),
            "observation": (
                f"Memory '{mid}' is isolated (no associations). "
                f"Type: {meta.get('type', 'unknown')}."
            ),
        })

    # Report small components (size 2-3) as potential silos
    small_comps = [c for c in components.values() if 2 <= len(c) <= 3]
    for comp in small_comps:
        findings.append({
            "type": "knowledge_silo",
            "severity": "medium",
            "component_size": len(comp),
            "memory_ids": sorted(comp),
            "observation": (
                f"Knowledge silo detected: {len(comp)} memories "
                f"isolated from main knowledge base."
            ),
        })

    findings.sort(key=lambda f: (f.get("component_size", 1), f.get("memory_id", "")))

    return {
        "analyzer": "mem.fragmentation",
        "findings": findings,
        "summary": {
            "total_components": beta_0,
            "largest_component": largest,
            "isolated_count": len(isolated),
            "silo_count": len(small_comps),
            "beta_0": beta_0,
        },
    }


# ============================================================
# mem.circular — Directed Circular-Reasoning Witnesses
# ============================================================

def analyze_circular(
    memory_graph: Dict[str, Any],
    edge_type_filter: Optional[set] = None,
) -> Dict[str, Any]:
    """
    Deteksi directed circular-reasoning witnesses and report β₁ separately.
    
    Args:
        memory_graph: Graph dari build_memory_graph()
        edge_type_filter: Set of edge types untuk filter.
                          None = semua edge types (backward compatible).
                          {"inferential", "causal"} = hanya reasoning cycles.
    """
    findings: List[Dict[str, Any]] = []
    vertices = memory_graph.get("vertices", [])
    typed_edges = _typed_edge_records(memory_graph, edge_type_filter)
    edges = [(source, target) for source, target, _, _ in typed_edges]

    if not edges:
        return {
            "analyzer": "mem.circular",
            "findings": [],
            "summary": {
                "total_cycles": 0,
                "memories_in_cycles": 0,
                "beta_1": 0,
                "beta_1_semantics": "underlying undirected multigraph cycle rank",
                "directed_cycle_witness_count": 0,
                "directed_cycle_witness_semantics": (
                    "deduplicated DFS back-edge witnesses; not all elementary cycles"
                ),
                "edge_type_filter": sorted(edge_type_filter) if edge_type_filter else None,
            },
        }

    # Build directed adjacency
    adj: Dict[str, List[str]] = {}
    for src, tgt in edges:
        adj.setdefault(src, []).append(tgt)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {v: WHITE for v in vertices}
    cycles: List[List[str]] = []

    def _dfs(node: str, path: List[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in sorted(adj.get(node, [])):
            c = color.get(neighbor, WHITE)
            if c == GRAY:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif c == WHITE:
                _dfs(neighbor, path)
        path.pop()
        color[node] = BLACK

    for v in sorted(vertices):
        if color.get(v, WHITE) == WHITE:
            _dfs(v, [])

    # Deduplicate cycles
    seen: Set[str] = set()
    for cycle in cycles:
        core = cycle[:-1]
        if not core:
            continue
        min_idx = core.index(min(core))
        normalized = core[min_idx:] + core[:min_idx]
        key = " -> ".join(normalized)
        if key not in seen:
            seen.add(key)
            # Tentukan edge types dalam cycle ini
            cycle_edge_types: Set[str] = set()
            for i in range(len(normalized)):
                src = normalized[i]
                tgt = normalized[(i + 1) % len(normalized)]
                cycle_edge_types.update(
                    edge_type
                    for edge_src, edge_tgt, edge_type, _ in typed_edges
                    if edge_src == src and edge_tgt == tgt
                )

            findings.append({
                "type": "circular_reasoning",
                "severity": "high" if cycle_edge_types & REASONING_EDGE_TYPES else "low",
                "cycle": normalized + [normalized[0]],
                "cycle_length": len(normalized),
                "memory_ids": normalized,
                "edge_types_in_cycle": sorted(cycle_edge_types),
                "is_reasoning_cycle": bool(cycle_edge_types & REASONING_EDGE_TYPES),
                "observation": (
                    f"Circular pattern ({len(normalized)} memories, "
                    f"edges: {', '.join(sorted(cycle_edge_types))})"
                ),
            })

    # Compute β₁
    uf = _UnionFind(vertices)
    for source, target in edges:
        uf.union(source, target)
    beta_0 = len({uf.find(vertex) for vertex in vertices})
    beta_1 = max(0, len(edges) - len(vertices) + beta_0)

    findings.sort(key=lambda f: f.get("cycle_length", 0))

    return {
        "analyzer": "mem.circular",
        "findings": findings,
        "summary": {
            "total_cycles": len(findings),
            "reasoning_cycles": sum(1 for f in findings if f.get("is_reasoning_cycle")),
            "structural_cycles": sum(1 for f in findings if not f.get("is_reasoning_cycle")),
            "memories_in_cycles": len(set(
                mid for f in findings for mid in f.get("memory_ids", [])
            )),
            "beta_1": beta_1,
            "beta_1_semantics": "underlying undirected multigraph cycle rank",
            "directed_cycle_witness_count": len(findings),
            "directed_cycle_witness_semantics": (
                "deduplicated DFS back-edge witnesses; not all elementary cycles"
            ),
            "beta_1_is_not_directed_cycle_count": True,
            "edge_type_filter": sorted(edge_type_filter) if edge_type_filter else None,
        },
    }


# ============================================================
# mem.decay — Stale Memories
# ============================================================

def analyze_decay(
    memory_graph: Dict[str, Any],
    decay_threshold_days: int = 30,
) -> Dict[str, Any]:
    """
    Deteksi memori yang sudah lama tidak diakses (decay).
    """
    findings: List[Dict[str, Any]] = []
    memory_map = memory_graph.get("memory_map", {})
    now = datetime.datetime.utcnow()

    for mid, memory in sorted(memory_map.items()):
        last_accessed_str = memory.get("last_accessed", "")
        access_count = memory.get("access_count", 0)

        if not last_accessed_str:
            continue

        try:
            last_accessed = datetime.datetime.fromisoformat(
                last_accessed_str.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (ValueError, AttributeError):
            continue

        days_since = (now - last_accessed).days

        if days_since > decay_threshold_days and access_count <= 1:
            findings.append({
                "type": "decaying_memory",
                "severity": "low",
                "memory_id": mid,
                "memory_type": memory.get("type", "unknown"),
                "days_since_access": days_since,
                "access_count": access_count,
                "observation": (
                    f"Memory '{mid}' not accessed for {days_since} days "
                    f"(access_count={access_count}). Decay candidate."
                ),
            })

    findings.sort(key=lambda f: -f.get("days_since_access", 0))

    return {
        "analyzer": "mem.decay",
        "findings": findings,
        "summary": {
            "total_decaying": len(findings),
            "threshold_days": decay_threshold_days,
        },
    }


# ============================================================
# mem.hub — Critical Memory Hubs
# ============================================================

def analyze_hub(
    memory_graph: Dict[str, Any],
    hub_threshold: int = 4,
) -> Dict[str, Any]:
    """
    Deteksi memori yang menjadi hub (banyak koneksi).
    """
    findings: List[Dict[str, Any]] = []
    node_metadata = memory_graph.get("node_metadata", {})

    for mid, meta in sorted(node_metadata.items()):
        fan_in = meta.get("fan_in", 0)
        fan_out = meta.get("fan_out", 0)
        total_connections = fan_in + fan_out

        if total_connections >= hub_threshold:
            findings.append({
                "type": "memory_hub",
                "severity": "medium",
                "memory_id": mid,
                "memory_type": meta.get("type", "unknown"),
                "fan_in": fan_in,
                "fan_out": fan_out,
                "total_connections": total_connections,
                "observation": (
                    f"Memory '{mid}' is a hub with {total_connections} connections "
                    f"(fan_in={fan_in}, fan_out={fan_out}). "
                    f"Critical for knowledge navigation."
                ),
            })

    findings.sort(key=lambda f: -f.get("total_connections", 0))

    return {
        "analyzer": "mem.hub",
        "findings": findings,
        "summary": {
            "total_hubs": len(findings),
            "threshold": hub_threshold,
        },
    }


# ============================================================
# mem.manifold — Betti Numbers + Archetype
# ============================================================

def analyze_manifold(
    memory_graph: Dict[str, Any],
    edge_type_filter: Optional[set] = None,
) -> Dict[str, Any]:
    """
    Hitung Betti numbers dan archetype untuk memory graph.
    
    Args:
        memory_graph: Graph dari build_memory_graph()
        edge_type_filter: Set of edge types untuk filter edges.
                          None = semua edges (backward compatible).
    """
    vertices = memory_graph.get("vertices", [])
    typed_edges = _typed_edge_records(memory_graph, edge_type_filter)
    edges = [(source, target) for source, target, _, _ in typed_edges]

    n_vertices = len(vertices)
    n_edges = len(edges)

    if n_vertices == 0:
        return {
            "analyzer": "mem.manifold",
            "findings": [],
            "manifold": {
                "vertex_count": 0,
                "edge_count": 0,
                "betti_numbers": {"beta_0": 0, "beta_1": 0, "beta_2": 0},
                "average_degree": 0.0,
                "memory_archetype": "empty",
                "model": "memory_association_multigraph_1_complex",
            },
            "summary": {},
        }

    # β₀ via union-find
    uf = _UnionFind(vertices)
    for src, tgt in edges:
        uf.union(src, tgt)
    beta_0 = len(set(uf.find(v) for v in vertices))

    # β₁ = cyclomatic number
    beta_1 = max(0, n_edges - n_vertices + beta_0)
    beta_2 = 0

    average_degree = (2.0 * n_edges / n_vertices) if n_vertices > 0 else 0.0

    # Archetype classification
    is_fragmented = beta_0 > 1
    has_cycles = beta_1 > 0 or beta_2 > 0

    if n_vertices == 1:
        archetype = "trivial"
        archetype_desc = "Single memory node"
        confidence = 1.0
    elif not has_cycles:
        if not is_fragmented:
            archetype = "memory_tree"
            archetype_desc = "Connected acyclic memory structure"
            confidence = 0.95
        else:
            archetype = "memory_modular"
            archetype_desc = f"{beta_0} disconnected memory clusters"
            confidence = 0.90
    else:
        if is_fragmented:
            if average_degree < 2.5:
                archetype = "memory_fragmented_sparse_cyclic"
                archetype_desc = (
                    f"{beta_0} memory clusters with {beta_1} cycles; "
                    f"sparse (avg degree {average_degree:.2f})"
                )
                confidence = 0.80
            else:
                archetype = "memory_fragmented_cyclic"
                archetype_desc = (
                    f"{beta_0} memory clusters with {beta_1} cycles; "
                    f"moderate (avg degree {average_degree:.2f})"
                )
                confidence = 0.75
        else:
            if average_degree < 2.5:
                archetype = "memory_sparse_cyclic"
                archetype_desc = f"Connected with {beta_1} cycles, sparse"
                confidence = 0.80
            elif average_degree < 5.0:
                archetype = "memory_mixed_cyclic"
                archetype_desc = f"Connected with {beta_1} cycles, moderate"
                confidence = 0.70
            else:
                archetype = "memory_dense_mesh"
                archetype_desc = f"Highly interconnected with {beta_1} cycles"
                confidence = 0.75

    # Findings
    findings: List[Dict[str, Any]] = []
    if beta_1 > 0:
        findings.append({
            "type": "undirected_cycle_rank",
            "severity": "medium",
            "count": beta_1,
            "observation": (
                f"Underlying association multigraph has cycle rank {beta_1}; "
                "this is not by itself a directed circular-reasoning count."
            ),
            "invariant": "beta_1",
        })
    if beta_0 > 1:
        findings.append({
            "type": "knowledge_fragmentation",
            "severity": "low",
            "count": beta_0,
            "observation": f"{beta_0} disconnected knowledge clusters.",
            "invariant": "beta_0",
        })

    return {
        "analyzer": "mem.manifold",
        "findings": findings,
        "manifold": {
            "vertex_count": n_vertices,
            "edge_count": n_edges,
            "betti_numbers": {
                "beta_0": beta_0,
                "beta_1": beta_1,
                "beta_2": beta_2,
            },
            "average_degree": round(average_degree, 4),
            "memory_archetype": archetype,
            "archetype_description": archetype_desc,
            "archetype_confidence": confidence,
            "edge_type_filter": sorted(edge_type_filter) if edge_type_filter else None,
            "model": "memory_association_multigraph_1_complex",
            "edge_multiplicity_preserved": True,
            "beta_1_is_not_directed_cycle_count": True,
        },
        "summary": {
            "connected_components": beta_0,
            "independent_cycles": beta_1,
            "enclosed_voids": beta_2,
            "memory_archetype": archetype,
        },
    }


def analyze_betti_breakdown(memory_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hitung β₁ breakdown per kategori edge type.
    Pisahkan underlying multigraph cycle rank dari directed reasoning witnesses.
    """
    # Total β₁ (semua edges)
    total_result = analyze_manifold(memory_graph, edge_type_filter=None)
    beta_1_total = total_result["manifold"]["betti_numbers"]["beta_1"]

    # Reasoning β₁ (hanya inferential + causal)
    reasoning_result = analyze_manifold(memory_graph, edge_type_filter=REASONING_EDGE_TYPES)
    beta_1_reasoning = reasoning_result["manifold"]["betti_numbers"]["beta_1"]

    # Structural β₁ (temporal, consolidation, derivation, redundancy)
    structural_result = analyze_manifold(memory_graph, edge_type_filter=STRUCTURAL_EDGE_TYPES)
    beta_1_structural = structural_result["manifold"]["betti_numbers"]["beta_1"]

    directed_reasoning = analyze_circular(
        memory_graph,
        edge_type_filter=REASONING_EDGE_TYPES,
    )
    directed_reasoning_witnesses = directed_reasoning.get("findings", [])
    directed_reasoning_count = len(directed_reasoning_witnesses)
    directed_reasoning_semantics = directed_reasoning.get("summary", {}).get(
        "directed_cycle_witness_semantics",
        "deduplicated DFS back-edge witnesses; not all elementary cycles",
    )

    # β₀ tidak terpengaruh edge type filter (connectivity)
    beta_0 = total_result["manifold"]["betti_numbers"]["beta_0"]

    return {
        "analyzer": "mem.betti_breakdown",
        "topological_model": memory_graph.get("model", {
            "name": "memory_association_multigraph_1_complex",
            "one_cells": "association records with multiplicity preserved",
            "betti_semantics": "underlying undirected multigraph cycle rank",
            "not_directed_cycle_count": True,
        }),
        "betti_numbers": {
            "beta_0": beta_0,
            "beta_1_total": beta_1_total,
            "beta_1_reasoning": beta_1_reasoning,
            "beta_1_structural": beta_1_structural,
        },
        "interpretation": {
            "true_circular_reasoning": directed_reasoning_count,
            "directed_reasoning_cycle_witness_count": directed_reasoning_count,
            "directed_reasoning_cycle_witnesses": directed_reasoning_witnesses,
            "directed_reasoning_cycle_witness_semantics": directed_reasoning_semantics,
            "underlying_reasoning_cycle_rank": beta_1_reasoning,
            "structural_artifacts": beta_1_structural,
            "beta_1_is_not_directed_cycle_count": True,
            "assessment": (
                "No directed circular-reasoning witness detected"
                if directed_reasoning_count == 0
                else (
                    f"{directed_reasoning_count} directed circular-reasoning "
                    "witness(es) detected"
                )
            ),
        },
        "summary": {
            "beta_1_total": beta_1_total,
            "beta_1_reasoning": beta_1_reasoning,
            "beta_1_structural": beta_1_structural,
            "directed_reasoning_cycle_witness_count": directed_reasoning_count,
            "directed_reasoning_cycle_witness_semantics": directed_reasoning_semantics,
            "reasoning_percentage": round(
                beta_1_reasoning / max(1, beta_1_total) * 100, 1
            ),
        },
    }


# ============================================================
# MEMORY ANALYZER REGISTRY
# ============================================================

MEMORY_ANALYZER_REGISTRY = {
    "mem.fragmentation": analyze_fragmentation,
    "mem.circular": analyze_circular,
    "mem.decay": analyze_decay,
    "mem.hub": analyze_hub,
    "mem.manifold": analyze_manifold,
    "mem.betti_breakdown": analyze_betti_breakdown,
}


def register_memory_analyzer(name: str, fn: Any) -> None:
    """Register a new memory analyzer."""
    MEMORY_ANALYZER_REGISTRY[name] = fn


def get_available_memory_analyzers() -> List[str]:
    """Get list of registered memory analyzer names."""
    return list(MEMORY_ANALYZER_REGISTRY.keys())


def run_memory_analyzers(
    memory_graph: Dict[str, Any],
    analyzer_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Jalankan selected memory analyzers."""
    if analyzer_names is None:
        analyzer_names = list(MEMORY_ANALYZER_REGISTRY.keys())

    results = {}
    errors = {}

    for name in analyzer_names:
        if name not in MEMORY_ANALYZER_REGISTRY:
            errors[name] = f"Analyzer '{name}' not found"
            continue
        try:
            results[name] = MEMORY_ANALYZER_REGISTRY[name](memory_graph)
        except Exception as exc:
            errors[name] = str(exc)

    return {
        "results": results,
        "errors": errors,
        "analyzers_run": len(results),
        "analyzers_failed": len(errors),
    }
