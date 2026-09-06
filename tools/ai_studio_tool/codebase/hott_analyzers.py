"""
HoTT Analyzers — HoTT Kernel
Schema Version: 3.0.0-kernel

Migrated dari Proto-HoTT standalone tools:
- type_isomorphism_observer.py    → hott.isomorphism
- boundary_sheaf_checker.py       → hott.sheaf
- homotopy_path_observer.py       → hott.homotopy
- topological_manifold_builder.py → hott.manifold

Semua analyzer mengonsumsi SharedGraph. Tidak ada os.walk() di sini.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================
# Shared Helpers
# ============================================================

class _UnionFind:
    """Union-Find untuk connected components."""
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


def _saturate(x: float, half_point: float) -> float:
    if x <= 0:
        return 0.0
    if half_point <= 0:
        return 1.0
    return x / (x + half_point)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _tree_path(
    adjacency: Dict[str, Set[str]],
    start: str,
    target: str,
) -> List[str]:
    """Return the deterministic path between two nodes in a forest."""
    parents: Dict[str, Optional[str]] = {start: None}
    queue = [start]
    cursor = 0

    while cursor < len(queue):
        node = queue[cursor]
        cursor += 1
        if node == target:
            break
        for neighbor in sorted(adjacency.get(node, set())):
            if neighbor not in parents:
                parents[neighbor] = node
                queue.append(neighbor)

    if target not in parents:
        return []

    path: List[str] = []
    current: Optional[str] = target
    while current is not None:
        path.append(current)
        current = parents[current]
    path.reverse()
    return path


def _build_undirected_cycle_basis(
    vertices: List[str],
    edges: List[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    """
    Build deterministic fundamental-cycle witnesses for the undirected graph.

    Betti-1 ignores import orientation. Each non-tree edge closes exactly one
    basis cycle; orientation is then restored as evidence for interpretation.
    """
    if not vertices:
        return []

    union_find = _UnionFind(vertices)
    tree: Dict[str, Set[str]] = {vertex: set() for vertex in vertices}
    directed_edges = set(map(tuple, edges))
    undirected_edges = sorted(
        (min(source, target), max(source, target), source, target)
        for source, target in directed_edges
    )
    basis: List[Dict[str, Any]] = []

    for source, target, directed_source, directed_target in undirected_edges:
        if source != target and union_find.union(source, target):
            tree[source].add(target)
            tree[target].add(source)
            continue

        if source == target:
            closed_path = [source, source]
        else:
            path = _tree_path(tree, source, target)
            if not path:
                continue
            closed_path = path + [source]

        witness_edges: List[Dict[str, Any]] = []
        forward_aligned = True
        reverse_aligned = True
        for left, right in zip(closed_path, closed_path[1:]):
            observed_directions: List[List[str]] = []
            if (left, right) in directed_edges:
                observed_directions.append([left, right])
            else:
                forward_aligned = False
            if (right, left) in directed_edges:
                observed_directions.append([right, left])
            else:
                reverse_aligned = False
            witness_edges.append({
                "undirected_edge": [left, right],
                "observed_directions": observed_directions,
            })

        orientation = (
            "directed"
            if forward_aligned or reverse_aligned
            else "mixed"
        )
        interpretation = (
            "directed_import_cycle_witness"
            if orientation == "directed"
            else "reconvergent_dependency_cycle_witness"
        )
        basis.append({
            "basis_index": len(basis) + 1,
            "vertices": closed_path[:-1],
            "closed_path": closed_path,
            "length": len(closed_path) - 1,
            "closing_edge": [directed_source, directed_target],
            "orientation": orientation,
            "interpretation": interpretation,
            "witness_edges": witness_edges,
        })

    return basis


# ============================================================
# hott.isomorphism — Type Isomorphism Observer
# ============================================================

def analyze_isomorphism(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari type_isomorphism_observer.py.
    Mendeteksi pasangan type/interface yang secara struktural isomorfik.

    Menggunakan shared_graph["type_shapes"] yang sudah di-extract
    oleh SharedGraph builder. Tidak perlu parse file lagi.
    """
    findings: List[Dict[str, Any]] = []
    type_shapes = shared_graph.get("type_shapes", {})

    # Kumpulkan semua type entries: (file, type_name, properties)
    all_types: List[Tuple[str, str, List[str]]] = []
    for file_path, shapes in sorted(type_shapes.items()):
        for type_name, props in sorted(shapes.items()):
            all_types.append((file_path, type_name, props))

    # Bandingkan setiap pair
    for i in range(len(all_types)):
        for j in range(i + 1, len(all_types)):
            file_a, name_a, props_a = all_types[i]
            file_b, name_b, props_b = all_types[j]

            # Skip jika di file yang sama dan nama sama (diri sendiri)
            if file_a == file_b and name_a == name_b:
                continue

            # Isomorfik jika property sets identik dan tidak kosong
            if props_a == props_b and len(props_a) > 0:
                findings.append({
                    "type": "structural_isomorphism",
                    "severity": "low",
                    "file": file_a,
                    "file_b": file_b,
                    "space_a": {
                        "name": name_a,
                        "file": file_a,
                        "property_count": len(props_a),
                        "properties": props_a,
                    },
                    "space_b": {
                        "name": name_b,
                        "file": file_b,
                        "property_count": len(props_b),
                        "properties": props_b,
                    },
                    "isomorphism_confidence": 0.95,
                    "observation": (
                        f"Type spaces '{name_a}' ({file_a}) and '{name_b}' ({file_b}) "
                        f"are structurally isomorphic ({len(props_a)} properties: {', '.join(props_a[:5])}{'...' if len(props_a) > 5 else ''})."
                    ),
                    "invariant": "univalence_candidate",
                })

    findings.sort(key=lambda f: (f["file"], f["space_a"]["name"]))

    return {
        "analyzer": "hott.isomorphism",
        "findings": findings,
        "summary": {
            "total_shapes": len(all_types),
            "isomorphic_pair_count": len(findings),
        },
    }


# ============================================================
# hott.sheaf — Boundary Sheaf Checker
# ============================================================

def analyze_sheaf(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari boundary_sheaf_checker.py.
    Mendeteksi boundary obstructions:
    - boundary_without_public_api
    - boundary_violation (bypass barrel)
    - circular_boundary
    """
    findings: List[Dict[str, Any]] = []
    boundaries = shared_graph.get("boundaries", {})
    file_to_boundary = shared_graph.get("file_to_boundary", {})
    resolved_imports = shared_graph.get("resolved_imports", {})

    # Build set of barrel files untuk quick lookup
    barrel_files: Set[str] = set()
    for bpath, bdata in boundaries.items():
        if bdata.get("barrel"):
            barrel_files.add(bdata["barrel"])

    # Track boundaries yang diimpor cross-boundary
    cross_boundary_targets: Dict[str, Set[str]] = {}  # target_boundary -> set of source_boundaries

    # --- Deteksi boundary_violation dan kumpulkan cross-boundary info ---
    for src_file, targets in sorted(resolved_imports.items()):
        src_boundary = file_to_boundary.get(src_file)
        if not src_boundary:
            continue

        for tgt_file in targets:
            tgt_boundary = file_to_boundary.get(tgt_file)
            if not tgt_boundary or tgt_boundary == src_boundary:
                continue

            # Cross-boundary import terdeteksi
            if tgt_boundary not in cross_boundary_targets:
                cross_boundary_targets[tgt_boundary] = set()
            cross_boundary_targets[tgt_boundary].add(src_boundary)

            # Check apakah import bypass barrel
            tgt_barrel = boundaries.get(tgt_boundary, {}).get("barrel")
            if tgt_barrel:
                barrel_no_ext = tgt_barrel.rsplit(".", 1)[0] if "." in tgt_barrel else tgt_barrel
                is_via_barrel = (
                    tgt_file == tgt_barrel
                    or tgt_file == barrel_no_ext
                    or tgt_file == tgt_boundary
                )
                if not is_via_barrel:
                    findings.append({
                        "type": "boundary_violation",
                        "severity": "high",
                        "file": src_file,
                        "source_boundary": src_boundary,
                        "target_file": tgt_file,
                        "target_boundary": tgt_boundary,
                        "observation": (
                            f"Import from '{src_boundary}' bypasses barrel of "
                            f"'{tgt_boundary}' — accesses '{tgt_file}' directly."
                        ),
                        "invariant": "H1_encapsulation_leak",
                    })

    # --- Deteksi boundary_without_public_api ---
    for tgt_boundary, src_boundaries in sorted(cross_boundary_targets.items()):
        tgt_barrel = boundaries.get(tgt_boundary, {}).get("barrel")
        if not tgt_barrel:
            findings.append({
                "type": "boundary_without_public_api",
                "severity": "low",
                "boundary": tgt_boundary,
                "observation": (
                    f"Boundary '{tgt_boundary}' is imported cross-boundary "
                    f"but has no barrel file. No explicit public API surface declared."
                ),
                "invariant": "H0_missing_public_api",
            })

    # --- Deteksi circular_boundary ---
    # Build boundary-level adjacency
    boundary_graph: Dict[str, Set[str]] = {}
    for src_file, targets in resolved_imports.items():
        src_boundary = file_to_boundary.get(src_file)
        if not src_boundary:
            continue
        for tgt_file in targets:
            tgt_boundary = file_to_boundary.get(tgt_file)
            if tgt_boundary and tgt_boundary != src_boundary:
                if src_boundary not in boundary_graph:
                    boundary_graph[src_boundary] = set()
                boundary_graph[src_boundary].add(tgt_boundary)

    # DFS cycle detection
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    cycles_found: List[List[str]] = []

    def _dfs(node: str, path: List[str]) -> None:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in sorted(boundary_graph.get(node, set())):
            if neighbor not in visited:
                _dfs(neighbor, path)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles_found.append(cycle)

        path.pop()
        rec_stack.discard(node)

    for node in sorted(boundary_graph.keys()):
        if node not in visited:
            _dfs(node, [])

    seen_cycles: Set[str] = set()
    for cycle in cycles_found:
        min_idx = cycle.index(min(cycle[:-1]))
        normalized = cycle[min_idx:] + cycle[1:min_idx + 1]
        cycle_key = " -> ".join(normalized)
        if cycle_key not in seen_cycles:
            seen_cycles.add(cycle_key)
            findings.append({
                "type": "circular_boundary",
                "severity": "high",
                "cycle": normalized,
                "cycle_length": len(normalized) - 1,
                "observation": (
                    f"Circular dependency across {len(normalized) - 1} boundaries: "
                    f"{cycle_key}"
                ),
                "invariant": "H1_coboundary_cycle",
            })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 3), f.get("type", "")))

    return {
        "analyzer": "hott.sheaf",
        "findings": findings,
        "summary": {
            "total_boundaries": len(boundaries),
            "total_obstructions": len(findings),
            "total_findings": len(findings),
            "by_type": {
                "boundary_violation": sum(1 for f in findings if f["type"] == "boundary_violation"),
                "boundary_without_public_api": sum(1 for f in findings if f["type"] == "boundary_without_public_api"),
                "circular_boundary": sum(1 for f in findings if f["type"] == "circular_boundary"),
            },
        },
    }


# ============================================================
# hott.homotopy — Homotopy Path Observer
# ============================================================

def analyze_homotopy(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari homotopy_path_observer.py.
    Mendeteksi:
    - diamond_dependency (dua jalur homotopic)
    - multi_importer_hub (node dengan banyak jalur masuk)
    - mergeable_import (multiple imports dari specifier yang sama dalam satu file)
    """
    findings: List[Dict[str, Any]] = []
    vertices = shared_graph.get("vertices", [])
    edges = shared_graph.get("edges", [])
    file_map = shared_graph.get("file_map", {})

    # Build adjacency
    forward: Dict[str, Set[str]] = {}   # src -> targets
    reverse: Dict[str, Set[str]] = {}   # tgt -> sources

    for src, tgt in edges:
        forward.setdefault(src, set()).add(tgt)
        reverse.setdefault(tgt, set()).add(src)

    # --- mergeable_import ---
    import_stmt_regex = re.compile(r"""(?:import\s+(?:(?:\{[^}]*\}|[\w$*]+|\*\s+as\s+[\w$]+)\s+from\s+)?['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"])""")
    for file_path, content in sorted(file_map.items()):
        specifier_counts: Dict[str, List[int]] = {}
        for idx, line in enumerate(content.splitlines(), start=1):
            m = import_stmt_regex.search(line)
            if m:
                spec = m.group(1) or m.group(2)
                if spec:
                    specifier_counts.setdefault(spec, []).append(idx)
        for spec, lines in sorted(specifier_counts.items()):
            if len(lines) > 1:
                findings.append({
                    "type": "mergeable_import",
                    "severity": "low",
                    "file": file_path,
                    "specifier": spec,
                    "lines": lines,
                    "observation": f"Multiple imports from '{spec}' in {file_path} at lines {lines}.",
                    "invariant": "homotopy_mergeable",
                })

    # --- diamond_dependency ---
    seen_diamonds: Set[Tuple[str, str, str, str]] = set()

    for node_d, importers in sorted(reverse.items()):
        if len(importers) < 2:
            continue

        importer_list = sorted(importers)
        for i in range(len(importer_list)):
            for j in range(i + 1, len(importer_list)):
                node_b = importer_list[i]
                node_c = importer_list[j]

                # Cari common dependents (A yang mengimpor B dan C)
                dependents_b = reverse.get(node_b, set())
                dependents_c = reverse.get(node_c, set())
                common_a = dependents_b & dependents_c

                for node_a in sorted(common_a):
                    normalized_key = (
                        node_a,
                        min(node_b, node_c),
                        max(node_b, node_c),
                        node_d,
                    )
                    if normalized_key in seen_diamonds:
                        continue
                    seen_diamonds.add(normalized_key)

                    findings.append({
                        "type": "diamond_dependency",
                        "severity": "medium",
                        "source": node_a,
                        "path_one": [node_a, node_b, node_d],
                        "path_two": [node_a, node_c, node_d],
                        "convergence": node_d,
                        "observation": (
                            f"Two homotopic paths from '{node_a}' to '{node_d}': "
                            f"via '{node_b}' and via '{node_c}'."
                        ),
                        "invariant": "H1_multiple_paths",
                    })

    # --- multi_importer_hub ---
    HUB_THRESHOLD = 4
    for node, importers in sorted(reverse.items()):
        if len(importers) >= HUB_THRESHOLD:
            findings.append({
                "type": "multi_importer_hub",
                "severity": "low",
                "node": node,
                "importer_count": len(importers),
                "observation": (
                    f"Node '{node}' is a path-concentration hub with "
                    f"{len(importers)} incoming import paths."
                ),
                "invariant": "H0_path_concentration",
            })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 3), f.get("type", "")))

    return {
        "analyzer": "hott.homotopy",
        "findings": findings,
        "summary": {
            "total_files": len(vertices),
            "total_edges": len(edges),
            "total_obstructions": len(findings),
            "total_findings": len(findings),
            "by_type": {
                "diamond_dependency": sum(1 for f in findings if f["type"] == "diamond_dependency"),
                "multi_importer_hub": sum(1 for f in findings if f["type"] == "multi_importer_hub"),
                "mergeable_import": sum(1 for f in findings if f["type"] == "mergeable_import"),
            },
        },
    }


# ============================================================
# hott.manifold — Topological Manifold Builder
# ============================================================

def _classify_archetype(
    beta_0: int, beta_1: int, beta_2: int,
    average_degree: float, vertex_count: int,
) -> Tuple[str, str, float]:
    """Archetype classification TERKALIBRASI (avg_degree + fragmentasi)."""
    if vertex_count == 0:
        return "empty", "No topological structure", 1.0
    if vertex_count == 1:
        return "trivial", "Single isolated node", 1.0

    is_fragmented = beta_0 > 1
    has_cycles = beta_1 > 0 or beta_2 > 0

    if not has_cycles:
        if not is_fragmented:
            return "tree_like", "Connected acyclic (hierarchical tree)", 0.95
        else:
            return "modular", f"{beta_0} disconnected acyclic components", 0.90

    if is_fragmented:
        if average_degree < 2.5:
            return (
                "fragmented_sparse_cyclic",
                f"{beta_0} components with {beta_1} cycles; sparse (avg degree {average_degree:.2f})",
                0.80,
            )
        else:
            return (
                "fragmented_cyclic",
                f"{beta_0} components with {beta_1} cycles; moderate (avg degree {average_degree:.2f})",
                0.75,
            )
    else:
        if average_degree < 2.5:
            return "sparse_cyclic", f"Connected with cycles, sparse (avg degree {average_degree:.2f})", 0.80
        elif average_degree < 5.0:
            return "mixed_cyclic", f"Connected with moderate cycles (avg degree {average_degree:.2f})", 0.70
        else:
            return "dense_mesh", f"Highly interconnected with cycles (avg degree {average_degree:.2f})", 0.75


def analyze_manifold(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari topological_manifold_builder.py.
    Menghitung Betti numbers, archetype, dan complexity score.

    Menggunakan shared_graph["vertices"] dan shared_graph["edges"].
    """
    vertices = shared_graph.get("vertices", [])
    edges = shared_graph.get("edges", [])

    n_vertices = len(vertices)
    n_edges = len(edges)
    cycle_basis = _build_undirected_cycle_basis(vertices, edges)

    # --- β₀ via union-find ---
    if n_vertices == 0:
        beta_0, beta_1, beta_2 = 0, 0, 0
        average_degree = 0.0
    else:
        uf = _UnionFind(vertices)
        for src, tgt in edges:
            uf.union(src, tgt)
        beta_0 = len(set(uf.find(v) for v in vertices))

        # β₁ = cyclomatic number = E - V + β₀
        beta_1 = max(0, n_edges - n_vertices + beta_0)

        # β₂ simplified: count triangles yang membentuk enclosed void
        # (versi lengkap ada di standalone topological_manifold_builder.py)
        beta_2 = 0

        average_degree = (2.0 * n_edges / n_vertices) if n_vertices > 0 else 0.0

    # --- Runtime vs Type-Level Betti Decomposition ---
    edge_natures = shared_graph.get("edge_natures", {})
    runtime_edges = [
        (u, v) for (u, v) in edges
        if edge_natures.get(f"{u} -> {v}", edge_natures.get((u, v), "runtime")) == "runtime"
    ]
    n_runtime_edges = len(runtime_edges)
    if n_vertices == 0:
        beta_0_runtime = 0
        beta_1_runtime = 0
    else:
        uf_rt = _UnionFind(vertices)
        for src, tgt in runtime_edges:
            uf_rt.union(src, tgt)
        beta_0_runtime = len(set(uf_rt.find(v) for v in vertices))
        beta_1_runtime = max(0, n_runtime_edges - n_vertices + beta_0_runtime)

    beta_1_type_level = max(0, beta_1 - beta_1_runtime)

    cycle_orientation_counts = {
        "directed": sum(1 for item in cycle_basis if item["orientation"] == "directed"),
        "mixed": sum(1 for item in cycle_basis if item["orientation"] == "mixed"),
    }
    topological_model = {
        "name": "dependency_multigraph_1_complex",
        "vertices": "supported source files",
        "edges": "resolved relative imports",
        "edge_orientation_for_betti": "ignored",
        "beta_0_interpretation": "connected components of the underlying undirected multigraph",
        "beta_1_interpretation": "independent cycles of the underlying undirected multigraph",
        "beta_2_interpretation": "zero by construction for this one-dimensional model",
        "formal_scope": "graph invariant used as semantic context; not a formal HoTT proof",
    }

    # --- Archetype classification (TERKALIBRASI) ---
    archetype, archetype_desc, archetype_conf = _classify_archetype(
        beta_0, beta_1, beta_2, average_degree, n_vertices
    )

    # --- Invariant vector (normalized) ---
    invariant_vector = {
        "beta_0": float(beta_0),
        "beta_1": float(beta_1),
        "beta_2": float(beta_2),
        "beta_0_normalized": round(_clamp01(_saturate(beta_0, 4.0)), 4),
        "beta_1_normalized": round(_clamp01(_saturate(beta_1, 8.0)), 4),
        "beta_2_normalized": round(_clamp01(_saturate(beta_2, 4.0)), 4),
        "n_vertex_scale": round(_clamp01(_saturate(n_vertices, 100.0)), 4),
        "n_edge_scale": round(_clamp01(_saturate(n_edges, 200.0)), 4),
        "n_avg_degree": round(_clamp01(_saturate(average_degree, 5.0)), 4),
    }

    # --- Complexity score (TERKALIBRASI dengan n_avg_degree) ---
    weights = {
        "beta_1_normalized": 0.30,
        "beta_0_normalized": 0.10,
        "beta_2_normalized": 0.10,
        "n_avg_degree": 0.25,
        "n_edge_scale": 0.10,
    }
    complexity = sum(weights[k] * invariant_vector.get(k, 0.0) for k in weights)
    complexity = round(_clamp01(complexity), 4)

    # --- Findings: laporkan obstructions topologis ---
    findings: List[Dict[str, Any]] = []

    if beta_1 > 0:
        findings.append({
            "type": "independent_cycles",
            "severity": "low" if beta_1_runtime == 0 else "medium",
            "count": beta_1,
            "runtime_count": beta_1_runtime,
            "type_level_count": beta_1_type_level,
            "observation": (
                (
                    f"{beta_1} independent cycle(s) detected, all at type level "
                    "(runtime beta_1 = 0; compiler-elided, no runtime crash risk)."
                ) if beta_1_runtime == 0 else (
                    f"{beta_1} independent undirected cycle(s) detected in the dependency graph "
                    f"({beta_1_runtime} runtime, {beta_1_type_level} type-level). "
                    "This does not by itself imply circular imports."
                )
            ),
            "invariant": "beta_1",
            "cycle_basis": cycle_basis,
            "orientation_counts": cycle_orientation_counts,
        })

    if beta_0 > 1:
        findings.append({
            "type": "disconnected_components",
            "severity": "low",
            "count": beta_0,
            "observation": f"{beta_0} disconnected components detected (knowledge fragmentation).",
            "invariant": "beta_0",
        })

    if beta_2 > 0:
        findings.append({
            "type": "enclosed_voids",
            "severity": "medium",
            "count": beta_2,
            "observation": f"{beta_2} enclosed void(s) detected (missing higher-order structure).",
            "invariant": "beta_2",
        })

    return {
        "analyzer": "hott.manifold",
        "findings": findings,
        "invariant_vector": invariant_vector,
        "topological_model": topological_model,
        "cycle_basis": cycle_basis,
        "manifold": {
            "vertex_count": n_vertices,
            "edge_count": n_edges,
            "betti_numbers": {
                "beta_0": beta_0,
                "beta_1": beta_1,
                "beta_2": beta_2,
                "beta_1_runtime": beta_1_runtime,
                "beta_1_type_level": beta_1_type_level,
                "beta_0_runtime": beta_0_runtime,
            },
            "cycle_basis": cycle_basis,
            "cycle_basis_complete": len(cycle_basis) == beta_1,
            "cycle_orientation_counts": cycle_orientation_counts,
            "topological_model": topological_model,
            "average_degree": round(average_degree, 4),
            "invariant_vector": invariant_vector,
            "complexity_score": complexity,
            "structural_archetype": archetype,
            "archetype_description": archetype_desc,
            "archetype_confidence": archetype_conf,
        },
        "summary": {
            "connected_components": beta_0,
            "independent_cycles": beta_1,
            "independent_cycles_runtime": beta_1_runtime,
            "independent_cycles_type_level": beta_1_type_level,
            "undirected_cycle_rank": beta_1,
            "cycle_basis_witnesses": len(cycle_basis),
            "cycle_orientation_counts": cycle_orientation_counts,
            "enclosed_voids": beta_2,
            "complexity_score": complexity,
            "structural_archetype": archetype,
        },
    }
