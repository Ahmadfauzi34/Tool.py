"""
Cycle-Break Advisor — Codebase Topology Domain
Schema Version: 3.0.0-kernel

Provides code-aware, deterministic Feedback Arc Set (FAS) computation
and prescriptive refactoring advice to break circular dependencies.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
import os
import re

# Architectural layer ranking (higher number = higher abstraction layer)
LAYER_RANK = {
    "Helper": 1,
    "Module": 2,
    "Service": 3,
    "Component": 4,
    "Entrypoint": 5,
    "Other": 2,
}

IMPORT_REGEX = re.compile(
    r"""(?:import\s+(?P<type_kw>type\s+)?(?:(?P<clause>[^"';\n]+?)\s+from\s+)?|export\s+(?P<export_type>type\s+)?(?:(?P<export_clause>[^"';\n]+?)\s+from\s+)?|import\s*\(\s*)["'](?P<path>[^"']+)["']""",
    re.MULTILINE,
)


def _normalize_path(value: str) -> str:
    normalized = os.path.normpath(value).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _extract_imported_symbols(clause: str) -> List[str]:
    """Extract individual imported symbols from import clause."""
    if not clause:
        return []
    clause = clause.strip()
    symbols = []
    # Check for named imports inside { ... }
    named_match = re.search(r"\{([^}]+)\}", clause)
    if named_match:
        raw_named = named_match.group(1)
        for item in raw_named.split(","):
            cleaned = item.strip()
            if not cleaned:
                continue
            # Handle 'type Foo' inside named import
            if cleaned.startswith("type "):
                cleaned = cleaned[5:].strip()
            # Handle 'as alias'
            if " as " in cleaned:
                cleaned = cleaned.split(" as ")[0].strip()
            if cleaned:
                symbols.append(cleaned)
    else:
        # Default or namespace import (e.g. `import Foo` or `import * as Foo`)
        default_name = clause.split(",")[0].strip()
        if default_name.startswith("* as "):
            default_name = default_name[5:].strip()
        if default_name:
            symbols.append(default_name)
    return symbols


def _inspect_edge_import(
    source: str,
    target: str,
    file_map: Dict[str, str],
    type_shapes: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Inspect code in source file to find how target is imported,
    which symbols are used, and whether it is type-only.
    """
    content = file_map.get(source, "")
    if not content and os.path.isfile(source):
        try:
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            pass
    if not content:
        return {
            "has_import": False,
            "is_type_only": False,
            "symbols": [],
            "raw_statement": "",
        }

    target_norm = _normalize_path(target)
    target_base = os.path.splitext(target_norm)[0]
    target_filename = os.path.basename(target_norm)
    target_filebase = os.path.splitext(target_filename)[0]

    source_dir = os.path.dirname(_normalize_path(source))

    target_types = set(type_shapes.get(target_norm, {}).keys())

    for match in IMPORT_REGEX.finditer(content):
        raw_path = match.group("path")
        if not raw_path:
            continue

        # Resolve path relative to source
        if raw_path.startswith("."):
            resolved = _normalize_path(os.path.join(source_dir, raw_path))
        else:
            resolved = _normalize_path(raw_path)

        resolved_base = os.path.splitext(resolved)[0]

        # Check if this import matches target
        is_match = (
            resolved == target_norm
            or resolved_base == target_base
            or resolved.endswith("/" + target_filename)
            or resolved.endswith("/" + target_filebase)
        )

        if is_match:
            clause = match.group("clause") or match.group("export_clause") or ""
            is_type_kw = bool(match.group("type_kw") or match.group("export_type"))
            symbols = _extract_imported_symbols(clause)

            # Check if all symbols are interfaces/types defined in target
            all_types_in_target = bool(
                symbols and target_types and all(s in target_types for s in symbols)
            )
            is_type_only = is_type_kw or all_types_in_target

            return {
                "has_import": True,
                "is_type_only": is_type_only,
                "symbols": symbols,
                "raw_statement": match.group(0),
            }

    return {
        "has_import": False,
        "is_type_only": False,
        "symbols": [],
        "raw_statement": "",
    }


def _suggest_leaf_module(target: str, symbols: List[str], is_type_only: bool) -> str:
    """Generate a clean, deterministic path for extracting shared code."""
    directory = os.path.dirname(target)
    basename = os.path.splitext(os.path.basename(target))[0]
    if basename.endswith(".service"):
        prefix = basename[:-8]
    elif basename.endswith(".component"):
        prefix = basename[:-10]
    else:
        prefix = basename

    ext = os.path.splitext(target)[1] or ".ts"
    suffix = "types" if is_type_only or any("type" in s.lower() or "interface" in s.lower() for s in symbols) else "shared"
    new_filename = f"{prefix}.{suffix}{ext}"
    return os.path.join(directory, new_filename).replace("\\", "/")


def evaluate_edge_cut(
    source: Any,
    target: Any,
    shared_graph: Optional[Dict[str, Any]] = None,
    cycle_overlap_count: int = 1,
) -> Dict[str, Any]:
    """
    Evaluate the cost, feasibility, and prescriptive strategy for cutting an edge.
    Supports both (source, target, shared_graph) and (shared_graph, source, target).
    Lower cut_cost means easier, cleaner, and more recommended to sever.
    """
    if isinstance(source, dict) and isinstance(target, str):
        graph = source
        actual_source = target
        actual_target = str(shared_graph) if shared_graph else ""
        return _evaluate_edge_cut_impl(actual_source, actual_target, graph, cycle_overlap_count)

    return _evaluate_edge_cut_impl(str(source), str(target), shared_graph or {}, cycle_overlap_count)


def _evaluate_edge_cut_impl(
    source: str,
    target: str,
    shared_graph: Dict[str, Any],
    cycle_overlap_count: int = 1,
) -> Dict[str, Any]:
    node_metadata = shared_graph.get("node_metadata", {})
    file_map = shared_graph.get("file_map") or shared_graph.get("file_contents") or {}
    type_shapes = shared_graph.get("type_shapes", {})

    u_meta = node_metadata.get(source, {})
    v_meta = node_metadata.get(target, {})

    u_type = u_meta.get("type", "Other")
    v_type = v_meta.get("type", "Other")
    u_rank = LAYER_RANK.get(u_type, 2)
    v_rank = LAYER_RANK.get(v_type, 2)

    u_is_ep = u_meta.get("is_entrypoint", False)
    v_is_ep = v_meta.get("is_entrypoint", False)

    target_fan_in = v_meta.get("fan_in", 1)
    source_fan_out = u_meta.get("fan_out", 1)

    import_info = _inspect_edge_import(source, target, file_map, type_shapes)
    edge_natures = shared_graph.get("edge_natures", {})
    if edge_natures.get(f"{source} -> {target}") == "type_only":
        is_type_only = True
    else:
        is_type_only = import_info.get("is_type_only", False)
    symbols = import_info.get("symbols", [])

    # Base cost calibration
    cost = 60

    # Multi-cycle leverage discount: breaking this edge eliminates multiple cycles
    if cycle_overlap_count > 1:
        cost -= min(30, (cycle_overlap_count - 1) * 15)

    # Fan-in adjustment: lower target fan-in = more isolated = easier to refactor
    if target_fan_in <= 1:
        cost -= 15
    elif target_fan_in >= 5:
        cost += 15

    # Strategy determination
    strategy = "extract_shared_module"
    estimated_effort = "medium"
    rationale = ""
    actionable_steps: List[str] = []
    suggested_leaf = _suggest_leaf_module(target, symbols, is_type_only)

    if v_is_ep:
        # Internal file imports entrypoint -> severe anti-pattern, top priority to break
        strategy = "remove_entrypoint_dependency"
        estimated_effort = "low"
        cost -= 35
        rationale = (
            f"Internal module '{source}' imports entrypoint '{target}', violating "
            f"inversion of control. Entrypoints should orchestrate modules, not be imported."
        )
        actionable_steps = [
            f"Remove import of entrypoint '{target}' from '{source}'.",
            f"Move any reusable logic or configuration from '{target}' into a dedicated service or configuration file.",
            f"Pass runtime parameters or instances into '{source}' at startup.",
        ]
    elif is_type_only:
        # Type-only dependency -> zero runtime cost to break with TypeScript isolated declarations
        strategy = "type_only_import"
        estimated_effort = "trivial"
        cost -= 35
        sym_str = f" ({', '.join(symbols)})" if symbols else ""
        rationale = (
            f"File '{source}' only references type definitions{sym_str} from '{target}'. "
            f"Converting to 'import type' or isolated declarations eliminates runtime circularity."
        )
        actionable_steps = [
            f"Change import in '{source}' to: import type {{ {', '.join(symbols) if symbols else '...'} }} from '{target}'.",
            f"Ensure TypeScript compiler option 'isolatedDeclarations' or 'verbatimModuleSyntax' is satisfied.",
        ]
    elif u_rank < v_rank:
        # Layer violation: lower layer imports higher layer (e.g. Helper -> Service or Service -> Component)
        strategy = "architectural_inversion"
        estimated_effort = "low"
        cost -= 25
        rationale = (
            f"Architectural layer violation: {u_type} '{source}' (layer {u_rank}) imports "
            f"higher-level {v_type} '{target}' (layer {v_rank}). Dependencies should flow downward."
        )
        actionable_steps = [
            f"Refactor '{source}' to remove the direct upward dependency on '{target}'.",
            f"Extract shared data structures or callbacks so '{source}' operates on primitives or interfaces.",
            f"Pass '{target}' or its methods to '{source}' via dependency injection or function arguments.",
        ]
    elif u_type == "Service" and v_type == "Service":
        # Mutual service dependency -> Dependency Injection or Interface Segregation
        strategy = "dependency_injection"
        estimated_effort = "medium"
        cost -= 10
        rationale = (
            f"Co-dependent services '{source}' and '{target}' cause module loading coupling. "
            f"Inject the dependency dynamically or abstract behind an interface token."
        )
        actionable_steps = [
            f"Inject '{target}' into '{source}' via constructor parameter instead of static module import.",
            f"Alternatively, introduce a separate event emitter, observer, or state store to decouple their lifecycles.",
        ]
    else:
        # General module circularity -> Extract shared leaf module
        strategy = "extract_shared_module"
        estimated_effort = "medium"
        sym_disp = f" ({', '.join(symbols[:3])})" if symbols else ""
        rationale = (
            f"Extract shared symbols{sym_disp} from '{target}' into an independent leaf module "
            f"to sever the backward edge from '{source}' (target fan-in: {target_fan_in})."
        )
        actionable_steps = [
            f"Create a new leaf module at '{suggested_leaf}'.",
            f"Move shared definitions from '{target}' into '{suggested_leaf}'.",
            f"Update imports in '{source}' and '{target}' to reference '{suggested_leaf}'.",
        ]

    cost = max(5, min(100, cost))

    return {
        "source": source,
        "target": target,
        "cut_cost": cost,
        "strategy": strategy,
        "estimated_effort": estimated_effort,
        "rationale": rationale,
        "actionable_steps": actionable_steps,
        "symbols_involved": symbols,
        "is_type_only": is_type_only,
        "target_fan_in": target_fan_in,
        "source_fan_out": source_fan_out,
        "suggested_leaf": suggested_leaf,
    }


def compute_cycle_break_advisory(
    shared_graph: Dict[str, Any],
    detected_cycles: List[List[str]],
) -> Dict[str, Any]:
    """
    Computes prescriptive cycle-break advisories and an optimal Feedback Arc Set (FAS)
    for all detected directed cycles in the graph.

    Args:
        shared_graph: The shared graph dictionary.
        detected_cycles: List of normalized cycle paths (e.g. [a, b, c, a]).

    Returns:
        Dictionary containing:
        - cycle_break_plan: global minimal feedback arc set to resolve all cycles
        - advisories_by_cycle: breakdown for each cycle
    """
    if not detected_cycles:
        return {
            "cycle_break_plan": {
                "total_cycles": 0,
                "total_cuts_required": 0,
                "all_cycles_resolvable": True,
                "recommended_cuts": [],
            },
            "advisories_by_cycle": [],
        }

    # Extract all edges per cycle
    # Cycle format: [n0, n1, ..., nk-1, n0]
    cycle_edges_list: List[List[Tuple[str, str]]] = []
    edge_to_cycles: Dict[Tuple[str, str], Set[int]] = {}

    for c_idx, cycle in enumerate(detected_cycles):
        edges_in_cycle: List[Tuple[str, str]] = []
        n = len(cycle)
        # If cycle ends with start node, length is n - 1 edges
        edge_count = n - 1 if cycle[0] == cycle[-1] and n > 1 else n
        for i in range(edge_count):
            u = cycle[i]
            v = cycle[(i + 1) % n] if cycle[0] != cycle[-1] else cycle[i + 1]
            edge = (u, v)
            edges_in_cycle.append(edge)
            edge_to_cycles.setdefault(edge, set()).add(c_idx)
        cycle_edges_list.append(edges_in_cycle)

    # Evaluate each edge
    edge_evaluations: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for edge, cycle_indices in edge_to_cycles.items():
        eval_result = evaluate_edge_cut(
            edge[0],
            edge[1],
            shared_graph,
            cycle_overlap_count=len(cycle_indices),
        )
        eval_result["cycles_eliminated_count"] = len(cycle_indices)
        eval_result["cycle_indices"] = sorted(cycle_indices)
        edge_evaluations[edge] = eval_result

    # Feedback Arc Set (FAS) Solver — Greedy Set Cover Heuristic
    unresolved_cycles = set(range(len(detected_cycles)))
    recommended_cuts: List[Dict[str, Any]] = []

    while unresolved_cycles:
        best_edge = None
        best_score = -1.0
        best_cycles_covered: Set[int] = set()

        # Deterministic sorting of candidate edges
        candidate_edges = sorted(
            edge_to_cycles.keys(),
            key=lambda e: (e[0], e[1]),
        )

        for edge in candidate_edges:
            cycles_covered = edge_to_cycles[edge] & unresolved_cycles
            if not cycles_covered:
                continue

            cost = edge_evaluations[edge]["cut_cost"]
            # Score: leverage = cycles_covered / cost
            score = len(cycles_covered) / float(cost)

            # Tie-breaker: higher cycles covered, lower cost
            if (
                score > best_score
                or (abs(score - best_score) < 1e-6 and len(cycles_covered) > len(best_cycles_covered))
            ):
                best_score = score
                best_edge = edge
                best_cycles_covered = cycles_covered

        if best_edge is None:
            break

        edge_eval = edge_evaluations[best_edge]
        recommended_cuts.append({
            "source": best_edge[0],
            "target": best_edge[1],
            "cycles_eliminated": len(best_cycles_covered),
            "strategy": edge_eval["strategy"],
            "estimated_effort": edge_eval["estimated_effort"],
            "cut_cost": edge_eval["cut_cost"],
            "rationale": edge_eval["rationale"],
            "actionable_steps": edge_eval["actionable_steps"],
            "symbols_involved": edge_eval["symbols_involved"],
            "suggested_leaf": edge_eval.get("suggested_leaf"),
        })

        unresolved_cycles -= best_cycles_covered

    # Build per-cycle advisories
    advisories_by_cycle: List[Dict[str, Any]] = []
    for c_idx, cycle in enumerate(detected_cycles):
        edges = cycle_edges_list[c_idx]
        candidates = [edge_evaluations[e] for e in edges]
        # Sort candidates in this cycle by lowest cut_cost
        candidates.sort(key=lambda c: (c["cut_cost"], -c["cycles_eliminated_count"], c["source"], c["target"]))

        top_choice = candidates[0] if candidates else None

        advisories_by_cycle.append({
            "cycle_index": c_idx,
            "cycle": cycle,
            "cycle_length": len(cycle) - 1 if cycle[0] == cycle[-1] else len(cycle),
            "recommended_cut": {
                "source": top_choice["source"],
                "target": top_choice["target"],
                "strategy": top_choice["strategy"],
                "estimated_effort": top_choice["estimated_effort"],
                "cut_cost": top_choice["cut_cost"],
                "rationale": top_choice["rationale"],
                "actionable_steps": top_choice["actionable_steps"],
                "symbols_involved": top_choice["symbols_involved"],
            } if top_choice else None,
            "candidate_edges": [
                {
                    "source": c["source"],
                    "target": c["target"],
                    "cut_cost": c["cut_cost"],
                    "strategy": c["strategy"],
                    "estimated_effort": c["estimated_effort"],
                    "cycles_broken": c["cycles_eliminated_count"],
                    "rationale": c["rationale"],
                }
                for c in candidates
            ],
        })

    return {
        "cycle_break_plan": {
            "total_cycles": len(detected_cycles),
            "total_cuts_required": len(recommended_cuts),
            "all_cycles_resolvable": len(unresolved_cycles) == 0,
            "recommended_cuts": recommended_cuts,
        },
        "advisories_by_cycle": advisories_by_cycle,
    }


def analyze_cycle_breaks(
    shared_graph: Dict[str, Any],
    cycles: Optional[List[List[str]]] = None,
) -> Dict[str, Any]:
    """
    Public entrypoint to analyze cycles and generate cycle-break advisories.
    If cycles are not provided, runs DFS cycle detection on shared_graph.
    """
    if cycles is None:
        from codebase.topology_analyzers import analyze_circular
        circ_result = analyze_circular(shared_graph)
        cycles = [f["cycle"] for f in circ_result.get("findings", [])]

    advisory_data = compute_cycle_break_advisory(shared_graph, cycles)

    return {
        "analyzer": "topo.cycle_break",
        "summary": advisory_data["cycle_break_plan"],
        "advisories": advisory_data["advisories_by_cycle"],
    }
