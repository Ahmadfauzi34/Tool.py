"""
Topology Analyzers — HoTT Kernel
Schema Version: 3.0.0-kernel

Migrated dari file_scanner.py:
- Circular dependency detection  → topo.circular  (global, registry)
- Change risk advisory           → topo.risk      (global, registry)
- Impact analysis                → query_impact   (targeted, kernel)
- File outline extraction        → query_outline  (targeted, kernel)
- Brief (outline + impact)       → query_brief    (targeted, kernel)

Semua fungsi mengonsumsi SharedGraph. Tidak ada os.walk() di sini.
"""

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================
# Regex patterns untuk outline extraction
# ============================================================

_IMPORT_RE = re.compile(
    r"import\s+(?:\{([^}]*)\}\s+from\s+)?"
    r"(?:\*\s+as\s+\w+\s+from\s+)?"
    r"(?:\w+\s*,\s*)?"
    r"['\"]([^'\"]+)['\"]"
)
_EXPORT_INTERFACE_RE = re.compile(r"(?:export\s+)?interface\s+(\w+)")
_EXPORT_TYPE_RE = re.compile(r"(?:export\s+)?type\s+(\w+)\s*=")
_EXPORT_CLASS_RE = re.compile(r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)")
_EXPORT_FUNCTION_RE = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)")
_EXPORT_CONST_RE = re.compile(r"(?:export\s+)?const\s+(\w+)\s*[=:]")
_EXPORT_ENUM_RE = re.compile(r"(?:export\s+)?enum\s+(\w+)")
_DECORATOR_RE = re.compile(r"^\s*@(\w+)", re.MULTILINE)
_EXPORT_DEFAULT_RE = re.compile(r"export\s+default")
_EXPORT_NAMED_RE = re.compile(r"export\s+\{([^}]*)\}")


def _strip_comments(content: str) -> str:
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"/\*[\s\S]*?\*/", "", content)
    return content


def _normalize_path(value: str) -> str:
    """Normalisasi path lokal tanpa bergantung pada legacy shared_graph module."""
    normalized = os.path.normpath(value).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


# ============================================================
# topo.circular — Circular Dependency Detection (GLOBAL)
# ============================================================

def analyze_circular(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deteksi semua circular dependency dalam graph menggunakan DFS.
    """
    findings: List[Dict[str, Any]] = []
    vertices = shared_graph.get("vertices", [])
    edges = shared_graph.get("edges", [])

    # Build adjacency
    adj: Dict[str, List[str]] = {}
    for src, tgt in edges:
        adj.setdefault(src, []).append(tgt)

    # DFS-based cycle detection
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

    # Deduplicate cycles (normalize rotation)
    seen: Set[str] = set()
    edge_natures = shared_graph.get("edge_natures", {})

    for cycle in cycles:
        core = cycle[:-1]
        if not core:
            continue
        min_idx = core.index(min(core))
        normalized = core[min_idx:] + core[:min_idx]
        key = " -> ".join(normalized)
        if key not in seen:
            seen.add(key)
            cycle_nodes = normalized + [normalized[0]]

            # Determine cycle nature based on constituent edges
            cycle_edge_natures = []
            for i in range(len(cycle_nodes) - 1):
                u = cycle_nodes[i]
                v = cycle_nodes[i + 1]
                cycle_edge_natures.append(edge_natures.get(f"{u} -> {v}", "runtime"))

            is_type_only = bool(cycle_edge_natures) and all(n == "type_only" for n in cycle_edge_natures)
            severity = "low" if is_type_only else "high"
            cycle_nature = "type_only" if is_type_only else "runtime"

            findings.append({
                "type": "circular_dependency",
                "severity": severity,
                "cycle_nature": cycle_nature,
                "is_type_only": is_type_only,
                "cycle": cycle_nodes,
                "cycle_length": len(normalized),
                "files": normalized,
                "observation": (
                    (
                        f"Type-only circular dependency ({len(normalized)} files): "
                        f"{' -> '.join(cycle_nodes)} [compiler-elided, no runtime crash risk]"
                    ) if is_type_only else (
                        f"Circular dependency ({len(normalized)} files): "
                        f"{' -> '.join(cycle_nodes)}"
                    )
                ),
            })

    findings.sort(key=lambda f: (f["cycle_length"], f["files"][0] if f["files"] else ""))

    files_in_cycles = set()
    for f in findings:
        files_in_cycles.update(f["files"])

    # Cycle-Break Advisory
    from codebase.cycle_break import compute_cycle_break_advisory
    detected_cycles = [f["cycle"] for f in findings]
    break_advisory_data = compute_cycle_break_advisory(shared_graph, detected_cycles)
    cycle_advisories = break_advisory_data.get("advisories_by_cycle", [])

    for idx, f in enumerate(findings):
        if idx < len(cycle_advisories):
            adv = cycle_advisories[idx]
            f["break_advisory"] = adv.get("recommended_cut")
            f["candidate_edges"] = adv.get("candidate_edges", [])

    return {
        "analyzer": "topo.circular",
        "findings": findings,
        "summary": {
            "total_cycles": len(findings),
            "runtime_cycles": sum(1 for f in findings if f.get("cycle_nature") == "runtime"),
            "type_only_cycles": sum(1 for f in findings if f.get("cycle_nature") == "type_only"),
            "files_in_cycles": len(files_in_cycles),
            "cycle_break_plan": break_advisory_data.get("cycle_break_plan", {}),
        },
    }


# ============================================================
# topo.risk — Change Risk Advisory (GLOBAL)
# ============================================================

def analyze_risk(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hitung change risk level untuk semua file.
    Menggunakan fan_in, entrypoint status, dan proximity ke entrypoint.
    """
    findings: List[Dict[str, Any]] = []
    node_metadata = shared_graph.get("node_metadata", {})
    edges = shared_graph.get("edges", [])

    # Build reverse adjacency (who imports this file)
    importers: Dict[str, List[str]] = {}
    for src, tgt in edges:
        importers.setdefault(tgt, []).append(src)

    # Get entrypoints
    entrypoints = {
        fp for fp, meta in node_metadata.items()
        if meta.get("is_entrypoint")
    }

    for fp in sorted(node_metadata.keys()):
        meta = node_metadata[fp]

        if meta.get("is_test"):
            continue

        fan_in = meta.get("fan_in", 0)
        fan_out = meta.get("fan_out", 0)
        is_ep = meta.get("is_entrypoint", False)

        risk_score = 0
        reasons: List[str] = []

        if is_ep:
            risk_score += 3
            reasons.append("is_entrypoint")

        if fan_in >= 3:
            risk_score += 2
            reasons.append("high_fan_in")
        elif fan_in >= 1:
            risk_score += 1
            reasons.append("has_dependents")

        # Check apakah entrypoint mengimpor file ini langsung
        direct_importers = importers.get(fp, [])
        ep_importers = [i for i in direct_importers if i in entrypoints]
        if ep_importers:
            risk_score += 2
            reasons.append("imported_by_entrypoint")

        # Classify
        if risk_score >= 5:
            level = "high"
        elif risk_score >= 2:
            level = "medium"
        else:
            level = "low"

        if risk_score > 0:
            findings.append({
                "type": "change_risk",
                "severity": level,
                "file": fp,
                "risk_level": level,
                "risk_score": risk_score,
                "reasons": reasons,
                "fan_in": fan_in,
                "fan_out": fan_out,
                "is_entrypoint": is_ep,
                "observation": (
                    f"File '{fp}': {level} change risk "
                    f"(score={risk_score}, {', '.join(reasons)})."
                ),
            })

    findings.sort(key=lambda f: (-f["risk_score"], f["file"]))

    return {
        "analyzer": "topo.risk",
        "findings": findings,
        "summary": {
            "total_assessed": len([
                m for m in node_metadata.values() if not m.get("is_test")
            ]),
            "high_risk": sum(1 for f in findings if f["risk_level"] == "high"),
            "medium_risk": sum(1 for f in findings if f["risk_level"] == "medium"),
            "low_risk": sum(1 for f in findings if f["risk_level"] == "low"),
        },
    }


# ============================================================
# topo.test_reachability — Static Test Import Topology
# ============================================================

def _reconstruct_path(parents: Dict[str, Optional[str]], target: str) -> List[str]:
    path: List[str] = []
    current: Optional[str] = target
    while current is not None:
        path.append(current)
        current = parents.get(current)
    path.reverse()
    return path


def analyze_test_reachability(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map static import reachability from test files into production files.

    This is intentionally not called runtime coverage: a resolved import path is
    evidence that a test can reach a source file statically, not that statements
    or branches execute at runtime.
    """
    vertices = sorted(shared_graph.get("vertices", []))
    edges = list(map(tuple, shared_graph.get("edges", [])))
    metadata = shared_graph.get("node_metadata", {})
    tests = sorted(vertex for vertex in vertices if metadata.get(vertex, {}).get("is_test"))
    production = sorted(set(vertices) - set(tests))
    production_set = set(production)

    forward: Dict[str, Set[str]] = {vertex: set() for vertex in vertices}
    undirected: Dict[str, Set[str]] = {vertex: set() for vertex in vertices}
    for source, target in edges:
        forward.setdefault(source, set()).add(target)
        undirected.setdefault(source, set()).add(target)
        undirected.setdefault(target, set()).add(source)

    coverage_by_test: Dict[str, Dict[str, Any]] = {}
    source_test_witnesses: Dict[str, List[Dict[str, Any]]] = {}
    reachable_sources: Set[str] = set()
    directly_tested_sources: Set[str] = set()
    findings: List[Dict[str, Any]] = []

    for test_file in tests:
        parents: Dict[str, Optional[str]] = {test_file: None}
        queue = [test_file]
        cursor = 0
        while cursor < len(queue):
            node = queue[cursor]
            cursor += 1
            for neighbor in sorted(forward.get(node, set())):
                if neighbor not in parents:
                    parents[neighbor] = node
                    queue.append(neighbor)

        direct_targets = sorted(forward.get(test_file, set()) & production_set)
        reachable = sorted(set(parents) & production_set)
        directly_tested_sources.update(direct_targets)
        reachable_sources.update(reachable)
        coverage_by_test[test_file] = {
            "direct_targets": direct_targets,
            "reachable_sources": reachable,
            "reachable_count": len(reachable),
        }

        for source_file in reachable:
            source_test_witnesses.setdefault(source_file, []).append({
                "test": test_file,
                "path": _reconstruct_path(parents, source_file),
            })

        if not reachable:
            findings.append({
                "type": "isolated_test",
                "severity": "medium",
                "file": test_file,
                "observation": (
                    f"Test '{test_file}' has no direct or transitive resolved "
                    "relative import path to a production source file."
                ),
                "model": "static_test_import_reachability",
            })

    unreachable_sources = sorted(production_set - reachable_sources)

    for source_file in unreachable_sources:
        meta = metadata.get(source_file, {})
        if meta.get("is_entrypoint") or meta.get("fan_in", 0) >= 2:
            reasons = []
            if meta.get("is_entrypoint"):
                reasons.append("is_entrypoint")
            if meta.get("fan_in", 0) >= 2:
                reasons.append("high_fan_in")
            findings.append({
                "type": "high_influence_without_test_path",
                "severity": "medium",
                "file": source_file,
                "fan_in": meta.get("fan_in", 0),
                "reasons": reasons,
                "observation": (
                    f"Influential source '{source_file}' has no static import path "
                    f"from a test ({', '.join(reasons)})."
                ),
                "model": "static_test_import_reachability",
            })

    # Connected components are computed on the undirected graph only to group
    # islands. Reachability above remains directional.
    seen: Set[str] = set()
    components: List[List[str]] = []
    for vertex in vertices:
        if vertex in seen:
            continue
        stack = [vertex]
        seen.add(vertex)
        component: List[str] = []
        while stack:
            node = stack.pop()
            component.append(node)
            for neighbor in sorted(undirected.get(node, set()), reverse=True):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))

    testless_components: List[Dict[str, Any]] = []
    for component in sorted(components, key=lambda item: item[0] if item else ""):
        component_tests = sorted(set(component) & set(tests))
        component_sources = sorted(set(component) & production_set)
        if component_sources and not component_tests:
            component_data = {
                "component_id": f"testless_{len(testless_components) + 1}",
                "source_files": component_sources,
                "source_count": len(component_sources),
            }
            testless_components.append(component_data)
            findings.append({
                "type": "testless_component",
                "severity": "low",
                **component_data,
                "observation": (
                    f"Undirected source component with {len(component_sources)} file(s) "
                    "contains no test file."
                ),
                "model": "static_test_import_reachability",
            })

    if not tests and production:
        findings.append({
            "type": "no_test_files",
            "severity": "high",
            "source_count": len(production),
            "observation": "No supported .spec/.test source files were found.",
            "model": "static_test_import_reachability",
        })

    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda item: (
        severity_order.get(item.get("severity", "info"), 4),
        item.get("type", ""),
        item.get("file", item.get("component_id", "")),
    ))

    ratio = round(len(reachable_sources) / len(production), 4) if production else 1.0
    return {
        "analyzer": "topo.test_reachability",
        "model": {
            "name": "static_test_import_reachability",
            "edge_semantics": "resolved relative import",
            "direction": "test or source file to imported dependency",
            "not_runtime_coverage": True,
            "interpretation": (
                "Reachability is structural evidence for LLM context and must not "
                "be reported as executed statements or branch coverage."
            ),
        },
        "findings": findings,
        "coverage_by_test": coverage_by_test,
        "source_test_witnesses": source_test_witnesses,
        "unreachable_sources": unreachable_sources,
        "testless_components": testless_components,
        "summary": {
            "total_tests": len(tests),
            "total_production_files": len(production),
            "directly_tested_files": len(directly_tested_sources),
            "statically_reachable_files": len(reachable_sources),
            "statically_unreachable_files": len(unreachable_sources),
            "static_test_reachability_ratio": ratio,
            "testless_component_count": len(testless_components),
            "high_influence_without_test_path": sum(
                1 for item in findings
                if item.get("type") == "high_influence_without_test_path"
            ),
            "isolated_test_count": sum(
                1 for item in findings if item.get("type") == "isolated_test"
            ),
        },
    }


# ============================================================
# TARGETED QUERY: Impact Analysis
# ============================================================

def query_impact(shared_graph: Dict[str, Any], target_file: str) -> Dict[str, Any]:
    """
    Analisis dampak perubahan untuk satu file spesifik.
    Migrated dari file_scanner.py get_impacted_files().
    """
    target = _normalize_path(target_file)

    vertices = shared_graph.get("vertices", [])
    edges = shared_graph.get("edges", [])
    node_metadata = shared_graph.get("node_metadata", {})

    if target not in set(vertices):
        return {
            "target": target,
            "exists": False,
            "error": "file_not_found_in_graph",
        }

    # Build adjacency
    adj_upstream: Dict[str, List[str]] = {}    # node -> what it imports
    adj_downstream: Dict[str, List[str]] = {}  # node -> who imports it

    for src, tgt in edges:
        adj_upstream.setdefault(src, []).append(tgt)
        adj_downstream.setdefault(tgt, []).append(src)

    # Deterministik
    for k in adj_upstream:
        adj_upstream[k] = sorted(set(adj_upstream[k]))
    for k in adj_downstream:
        adj_downstream[k] = sorted(set(adj_downstream[k]))

    # Transitive traversal with cycle safety
    def _traverse(start: str, adj: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        result: List[str] = []
        cycles: List[str] = []

        def _dfs(node: str) -> None:
            if node in rec_stack:
                cycles.append(node)
                return
            if node in visited:
                return
            rec_stack.add(node)
            visited.add(node)
            if node != start:
                result.append(node)
            for neighbor in adj.get(node, []):
                _dfs(neighbor)
            rec_stack.discard(node)

        _dfs(start)
        return result, cycles

    upstream_nodes, upstream_cycles = _traverse(target, adj_upstream)
    downstream_nodes, downstream_cycles = _traverse(target, adj_downstream)

    # Extract semantic usages targeting this file
    direct_downstream = sorted(set(adj_downstream.get(target, [])))
    semantic_usages = []
    edge_details = shared_graph.get("edge_details", [])
    for ed in edge_details:
        if ed.get("target") == target and ed.get("semantic_usages"):
            for usage in ed.get("semantic_usages"):
                semantic_usages.append(f"{ed.get('source')} -> {usage}")
    semantic_usages = sorted(list(set(semantic_usages)))

    # Affected entrypoints
    entrypoint_ids = {
        fp for fp, meta in node_metadata.items()
        if meta.get("is_entrypoint")
    }
    downstream_set = set(downstream_nodes)
    affected_entrypoints = sorted(entrypoint_ids & (downstream_set | {target}))
    target_is_entrypoint = target in entrypoint_ids

    # Metadata
    meta = node_metadata.get(target, {})
    target_fan_in = meta.get("fan_in", 0)
    target_fan_out = meta.get("fan_out", 0)
    target_is_test = meta.get("is_test", False)

    # Risk level
    risk_score = 0
    risk_reasons: List[str] = []

    if target_is_entrypoint:
        risk_score += 3
        risk_reasons.append("is_entrypoint")
    if len(affected_entrypoints) > 0 and not target_is_entrypoint:
        risk_score += 3
        risk_reasons.append("affects_entrypoints")
    if target_fan_in >= 3:
        risk_score += 2
        risk_reasons.append("high_fan_in")
    elif target_fan_in >= 1:
        risk_score += 1
        risk_reasons.append("has_dependents")
    if target_is_test:
        risk_score = max(0, risk_score - 2)
        risk_reasons.append("test_file")

    if risk_score >= 5:
        risk_level = "high"
    elif risk_score >= 2:
        risk_level = "medium"
    else:
        risk_level = "low"

    circular_refs = sorted(set(upstream_cycles + downstream_cycles))
    cycle_break_advisory = None
    if circular_refs:
        from codebase.cycle_break import compute_cycle_break_advisory
        circ_result = analyze_circular(shared_graph)
        relevant_cycles = [
            f["cycle"] for f in circ_result.get("findings", [])
            if any(target in node for node in f.get("cycle", []))
        ]
        if relevant_cycles:
            adv_data = compute_cycle_break_advisory(shared_graph, relevant_cycles)
            cycle_break_advisory = adv_data.get("cycle_break_plan")

    return {
        "target": target,
        "exists": True,
        "upstream": sorted(set(upstream_nodes)),
        "downstream": sorted(set(downstream_nodes)),
        "direct_upstream": sorted(set(adj_upstream.get(target, []))),
        "direct_downstream": direct_downstream,
        "semantic_usages": semantic_usages,
        "circular_references": circular_refs,
        "cycle_break_advisory": cycle_break_advisory,
        "target_is_entrypoint": target_is_entrypoint,
        "target_is_test": target_is_test,
        "affected_entrypoints": affected_entrypoints,
        "target_fan_in": target_fan_in,
        "target_fan_out": target_fan_out,
        "change_risk_level": risk_level,
        "change_risk_reasons": risk_reasons,
        "upstream_count": len(set(upstream_nodes)),
        "downstream_count": len(set(downstream_nodes)),
    }


# ============================================================
# TARGETED QUERY: File Outline Extraction
# ============================================================

def query_outline(shared_graph: Dict[str, Any], target_file: str) -> Dict[str, Any]:
    """
    Ekstrak outline ringkas dari satu file spesifik.
    Migrated dari file_scanner.py get_file_outline().
    """
    target = _normalize_path(target_file)

    file_map = shared_graph.get("file_map", {})

    if target not in file_map:
        return {
            "file": target,
            "exists": False,
            "error": "file_not_found_in_graph",
        }

    content = file_map[target]
    stripped = _strip_comments(content)
    lines = content.splitlines()

    # Extract imports
    imports: List[str] = []
    internal_imports: List[str] = []
    external_imports: List[str] = []

    for match in _IMPORT_RE.finditer(stripped):
        import_path = match.group(2)
        if import_path:
            imports.append(import_path)
            if import_path.startswith("."):
                internal_imports.append(import_path)
            else:
                external_imports.append(import_path)

    # Extract declarations
    declarations: List[Dict[str, Any]] = []

    decl_patterns = [
        ("interface", _EXPORT_INTERFACE_RE),
        ("type", _EXPORT_TYPE_RE),
        ("class", _EXPORT_CLASS_RE),
        ("function", _EXPORT_FUNCTION_RE),
        ("const", _EXPORT_CONST_RE),
        ("enum", _EXPORT_ENUM_RE),
    ]

    for kind, pattern in decl_patterns:
        for match in pattern.finditer(stripped):
            name = match.group(1)
            line_no = stripped[:match.start()].count("\n") + 1
            match_line = stripped.split("\n")[line_no - 1].strip() if line_no <= len(stripped.split("\n")) else ""
            is_exported = match_line.startswith("export")

            declarations.append({
                "line": line_no,
                "kind": kind,
                "name": name,
                "exported": is_exported,
                "signature": match_line[:220],
            })

    # Extract decorators
    decorators: List[str] = []
    for match in _DECORATOR_RE.finditer(stripped):
        dec_name = match.group(1)
        if dec_name not in decorators:
            decorators.append(dec_name)

    # Extract named exports
    exports: List[str] = []
    for decl in declarations:
        if decl["exported"] and decl["name"] not in exports:
            exports.append(decl["name"])

    # Check export default
    if _EXPORT_DEFAULT_RE.search(stripped):
        if "default" not in exports:
            exports.append("default")

    # Check export { ... }
    for match in _EXPORT_NAMED_RE.finditer(stripped):
        for item in match.group(1).split(","):
            item = item.strip()
            if " as " in item:
                item = item.split(" as ")[-1].strip()
            if item and item not in exports:
                exports.append(item)

    declarations.sort(key=lambda d: d["line"])

    return {
        "file": target,
        "exists": True,
        "imports": sorted(set(imports)),
        "internal_imports": sorted(set(internal_imports)),
        "external_imports": sorted(set(external_imports)),
        "exports": exports,
        "decorators": decorators,
        "declarations": declarations,
        "stats": {
            "total_lines": len(lines),
            "outline_entries": len(declarations),
            "export_count": len(exports),
            "import_count": len(set(imports)),
        },
    }


# ============================================================
# TARGETED QUERY: Brief (Outline + Impact)
# ============================================================

def query_brief(shared_graph: Dict[str, Any], target_file: str) -> Dict[str, Any]:
    """
    Gabungan outline + impact untuk satu file spesifik.
    Migrated dari file_scanner.py get_file_brief().
    """
    outline = query_outline(shared_graph, target_file)
    impact = query_impact(shared_graph, target_file)

    if not outline.get("exists") or not impact.get("exists"):
        return {
            "file": target_file,
            "exists": False,
            "error": outline.get("error") or impact.get("error"),
        }

    return {
        "file": target_file,
        "exists": True,
        "outline": {
            "imports": outline["imports"],
            "internal_imports": outline["internal_imports"],
            "external_imports": outline["external_imports"],
            "exports": outline["exports"],
            "decorators": outline["decorators"],
            "declarations": outline["declarations"],
            "stats": outline["stats"],
        },
        "impact": {
            "target_is_entrypoint": impact["target_is_entrypoint"],
            "target_is_test": impact["target_is_test"],
            "affected_entrypoints": impact["affected_entrypoints"],
            "direct_downstream": impact["direct_downstream"],
            "semantic_usages": impact.get("semantic_usages", []),
            "downstream_count": impact["downstream_count"],
            "upstream_count": impact["upstream_count"],
            "target_fan_in": impact["target_fan_in"],
            "target_fan_out": impact["target_fan_out"],
            "change_risk_level": impact["change_risk_level"],
            "change_risk_reasons": impact["change_risk_reasons"],
            "circular_references": impact["circular_references"],
            "cycle_break_advisory": impact.get("cycle_break_advisory"),
        },
    }


from codebase.cycle_break import analyze_cycle_breaks, compute_cycle_break_advisory
