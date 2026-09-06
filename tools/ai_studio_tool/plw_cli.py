#!/usr/bin/env python3
"""
PLW (Proof Logic Working) CLI — Native Linux Command Layer for HoTT Kernel
Provides zero-bloat, token-budgeted, single-command codebase intelligence.

Usage:
  plw context <query> [root] [--target file] [--budget N] [--json]
  plw kan <target_file_or_query> [root] [--mode lan|ran|both] [--json]
  plw check [root] [--analyzers a,b] [--json]
  plw steer [root] [--json]
  plw brief <file> [root] [--json]
  plw impact <file> [root] [--json]
  plw outline <file> [root] [--json]
  plw memory <subcommand> [args...]
  plw fiber <subcommand> [args...]
  plw <any hott_kernel mode> [args...]
"""

import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Automatically locate and resolve tools/ai_studio_tool directory
def _resolve_tool_root() -> Path:
    candidates = [
        Path(__file__).resolve().parent,
        Path.cwd() / "tools" / "ai_studio_tool",
        Path("/app/applet/tools/ai_studio_tool"),
    ]
    for c in candidates:
        if (c / "hott_kernel.py").is_file():
            return c
    return Path(__file__).resolve().parent

TOOL_ROOT = _resolve_tool_root()
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

# Import kernel functions
try:
    import hott_kernel
except ImportError as exc:
    print(f"[PLW Error] Unable to load hott_kernel from {TOOL_ROOT}: {exc}", file=sys.stderr)
    sys.exit(1)


def _format_context_output(result: Dict[str, Any], as_json: bool = False) -> None:
    if as_json or "error" in result:
        print(json.dumps(result, indent=2))
        return

    context_block = result.get("context_block", "")
    budget = result.get("budget", {})
    selection = result.get("selection", {})
    paths = selection.get("selected_paths", [])

    print(f"# [PLW Context Pack]")
    print(f"# Query: {result.get('query')}")
    print(f"# Budget: {budget.get('estimated_tokens', '?')}/{budget.get('budget_tokens', '?')} tokens (within_budget={budget.get('within_budget')})")
    print(f"# Selected: {len(paths)} files: {', '.join(paths[:5])}{'...' if len(paths) > 5 else ''}")
    print("-" * 60)
    print(context_block.strip())
    print("-" * 60)


def _format_kan_output(result: Dict[str, Any], as_json: bool = False) -> None:
    if as_json or "error" in result:
        print(json.dumps(result, indent=2))
        return

    query = result.get("target_file") or result.get("target") or result.get("query_fragment") or result.get("query", "")
    mode = result.get("mode", "both")
    print(f"# [PLW Kan Extension Imputation & Guidance]")
    print(f"# Target/Query: {query} (mode: {mode})")
    print("-" * 60)

    # Check for module imputation format
    lan = result.get("left_kan_extension") or result.get("lan_colimit", {})
    ran = result.get("right_kan_extension") or result.get("ran_limit", {})
    role = result.get("inferred_role") or (lan.get("role") if isinstance(lan, dict) else None) or "unknown"

    rendered_sections = False

    if lan and isinstance(lan, dict) and lan.get("status") != "no_match":
        rendered_sections = True
        print("[Left Kan Extension / Colimit (Imputed Topology)]")
        print(f"  Inferred Role: {role}")
        raw_isomorphs = result.get("isomorphic_modules", [])
        if raw_isomorphs:
            iso_strs = []
            for m in raw_isomorphs:
                if isinstance(m, dict):
                    f_name = m.get("file", "")
                    sim = m.get("similarity_score")
                    iso_strs.append(f"{f_name} (sim: {sim})" if sim else f_name)
                else:
                    iso_strs.append(str(m))
            print(f"  Isomorphic Modules: {', '.join(iso_strs[:4])}")

        deps = lan.get("imputed_dependencies", [])
        if deps:
            dep_strs = []
            for d in deps:
                if isinstance(d, dict):
                    conf = d.get("confidence")
                    freq = d.get("frequency")
                    label = f"{d.get('role')} (conf: {conf}, freq: {freq})" if conf and freq else d.get("role", str(d))
                    dep_strs.append(label)
                else:
                    dep_strs.append(str(d))
            print(f"  Expected Dependencies: {', '.join(dep_strs)}")

        callers = lan.get("imputed_dependents", [])
        if callers:
            caller_strs = []
            for c in callers:
                if isinstance(c, dict):
                    conf = c.get("confidence")
                    label = f"{c.get('role')} (conf: {conf})" if conf else c.get("role", str(c))
                    caller_strs.append(label)
                else:
                    caller_strs.append(str(c))
            print(f"  Expected Callers: {', '.join(caller_strs)}")

        comp_test = lan.get("expected_companion_test")
        if comp_test:
            print(f"  Expected Companion Test: {comp_test}")
        print()

    if ran and isinstance(ran, dict) and ran.get("status") != "no_match":
        rendered_sections = True
        print("[Right Kan Extension / Limit (Guided Hints & Conventions)]")
        hints = ran.get("guided_hints", [])
        for hint in hints:
            print(f"  * {hint}")
        conventions = ran.get("architectural_conventions", [])
        if conventions:
            print("  Architectural Conventions:")
            for conv in conventions:
                print(f"    - {conv}")
        print()

    synthesis = result.get("kan_synthesis")
    if synthesis and isinstance(synthesis, dict):
        summary = synthesis.get("summary")
        if summary:
            print(f"[Synthesis] {summary}\n")

    if not rendered_sections:
        # Fallback to general output
        print(json.dumps(result, indent=2))


def _format_check_output(result: Dict[str, Any], as_json: bool = False) -> None:
    if as_json or "error" in result:
        print(json.dumps(result, indent=2))
        return

    summary = result.get("unified_summary", {})
    findings = result.get("findings", [])
    failed = summary.get("analyzers_failed", 0)
    total = summary.get("total_findings", len(findings))

    print(f"# [PLW Architecture & Boundary Check]")
    print(f"# Total Files: {result.get('total_files', '?')} | Findings: {total}")
    print("-" * 60)

    critical_findings = [f for f in findings if f.get("severity") in ("critical", "high", "error")]
    if not critical_findings and failed == 0:
        print("✓ PASS: No critical architectural violations or circular imports detected.")
        if total > 0:
            print(f"  (Note: {total} low/info advisory findings present. Use --json to inspect).")
    else:
        print(f"✗ ISSUES FOUND: {len(critical_findings)} critical/high severity findings:")
        for f in critical_findings[:10]:
            print(f"  - [{f.get('severity', '').upper()}] {f.get('analyzer', '')}: {f.get('message', '')} ({f.get('file', '')})")
        if len(critical_findings) > 10:
            print(f"  ... and {len(critical_findings) - 10} more.")


def _format_steer_output(result: Dict[str, Any], as_json: bool = False) -> None:
    if as_json or "error" in result:
        print(json.dumps(result, indent=2))
        return

    prompt_block = result.get("steering_prompt_block") or result.get("cross_domain_prompt_block", "")
    print(f"# [PLW Steering Guidance]")
    print("-" * 60)
    if prompt_block:
        print(prompt_block.strip())
    else:
        # Cross-domain & codebase signals
        cb = result.get("codebase_steering", {})
        mem = result.get("memory_steering", {})
        x_sig = result.get("cross_domain_signal", {})
        kan_guide = result.get("kan_guidance", {})

        if cb or x_sig:
            strategy = x_sig.get("unified_strategy") or cb.get("strategy", "balanced")
            budget = x_sig.get("recommended_budget") or cb.get("budget", "standard")
            cb_health = x_sig.get("codebase_health", cb.get("health_score"))
            mem_health = x_sig.get("memory_health", mem.get("health_score"))

            print(f"  Unified Strategy: {strategy}")
            print(f"  Recommended Budget: {budget}")
            if cb_health is not None:
                print(f"  Codebase Health Score: {cb_health}")
            if mem_health is not None:
                print(f"  Memory Health Score: {mem_health}")
            if cb.get("archetype"):
                print(f"  Codebase Archetype: {cb.get('archetype')}")
            print()

        signals = result.get("steering_signals", [])
        if signals:
            print("Steering Signals:")
            for s in signals:
                print(f"  * {s}")
            print()

        if kan_guide and isinstance(kan_guide, dict):
            zero_count = kan_guide.get("zero_context_modules_count", 0)
            hints = kan_guide.get("guided_hints", [])
            if zero_count > 0:
                print(f"Kan Extension Imputation Active: {zero_count} zero-context module(s) detected.")
            if hints:
                print("Architecture Conventions & Guided Hints:")
                for h in hints:
                    print(f"  * {h}")
                print()

    print("-" * 60)


def cmd_context(args: List[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print("Usage: plw context <query> [root] [--target file[,file]] [--budget N] [--max-hops N] [--json]")
        return 0

    query = args[0]
    root = "."
    target_files = []
    budget = 1200
    max_hops = 2
    as_json = False

    i = 1
    if i < len(args) and not args[i].startswith("-"):
        root = args[i]
        i += 1

    while i < len(args):
        arg = args[i]
        if arg in ("--target", "--targets") and i + 1 < len(args):
            target_files.extend(v.strip() for v in args[i + 1].split(",") if v.strip())
            i += 1
        elif arg in ("--budget", "--budget-tokens") and i + 1 < len(args):
            try:
                budget = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        elif arg in ("--hops", "--max-hops") and i + 1 < len(args):
            try:
                max_hops = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        elif arg == "--json":
            as_json = True
        i += 1

    res = hott_kernel.kernel_context(
        scan_root=root,
        query=query,
        target_files=target_files if target_files else None,
        budget_tokens=budget,
        max_hops=max_hops,
        detail="source",
        output_mode="prompt",
    )
    _format_context_output(res, as_json=as_json)
    return 0 if "error" not in res else 1


def cmd_kan(args: List[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print("Usage: plw kan <target_module_or_query> [root] [--mode lan|ran|both] [--depth N] [--json]")
        return 0

    target = args[0]
    root = "."
    mode = "both"
    max_depth = 2
    as_json = False

    i = 1
    if i < len(args) and not args[i].startswith("-"):
        root = args[i]
        i += 1

    while i < len(args):
        arg = args[i]
        if arg == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 1
        elif arg in ("--depth", "--max-depth") and i + 1 < len(args):
            try:
                max_depth = int(args[i + 1])
            except ValueError:
                pass
            i += 1
        elif arg == "--json":
            as_json = True
        i += 1

    # Check if target is a module file or path
    is_module_target = (
        Path(target).exists()
        or "/" in target
        or any(target.endswith(ext) for ext in (".ts", ".js", ".tsx", ".jsx", ".py"))
    )
    if is_module_target:
        try:
            from memory.kan_extension import impute_module_relations
            from core.shared_graph import build_shared_graph
            shared_graph = build_shared_graph(root)
            res = impute_module_relations(target, shared_graph=shared_graph)
            _format_kan_output(res, as_json=as_json)
            return 0 if "error" not in res else 1
        except Exception:
            pass

    res = hott_kernel.kernel_memory_kan(target, mode=mode, max_depth=max_depth)
    _format_kan_output(res, as_json=as_json)
    return 0 if "error" not in res else 1


def cmd_check(args: List[str]) -> int:
    root = "."
    analyzers = None
    as_json = False

    i = 0
    if i < len(args) and not args[i].startswith("-"):
        root = args[i]
        i += 1

    while i < len(args):
        arg = args[i]
        if arg == "--analyzers" and i + 1 < len(args):
            analyzers = args[i + 1].split(",")
            i += 1
        elif arg == "--json":
            as_json = True
        i += 1

    res = hott_kernel.kernel_analyze(root, analyzer_names=analyzers, output_mode="summary")
    _format_check_output(res, as_json=as_json)
    return 0 if "error" not in res else 1


def cmd_steer(args: List[str]) -> int:
    root = "."
    as_json = False
    i = 0
    if i < len(args) and not args[i].startswith("-"):
        root = args[i]
        i += 1

    while i < len(args):
        if args[i] == "--json":
            as_json = True
        i += 1

    # Cross-domain steer preferred if available
    if getattr(hott_kernel, "CROSS_DOMAIN_AVAILABLE", False):
        res = hott_kernel.kernel_xsteer(root, output_mode="full")
    else:
        res = hott_kernel.kernel_steer(root, output_mode="full")
    _format_steer_output(res, as_json=as_json)
    return 0 if "error" not in res else 1


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("""PLW — Proof Logic Working & HoTT Kernel CLI
Usage:
  plw context <query> [root] [--target file] [--budget N] [--json]
      -> Generates budget-bounded prompt context with Kan Extension imputation
  plw kan <file_or_query> [root] [--mode lan|ran|both] [--json]
      -> Imputes expected imports, callers, and conventions for new/isolated files
  plw check [root] [--analyzers a,b] [--json]
      -> Quick architectural and boundary violation check
  plw steer [root] [--json]
      -> Cross-domain architectural steering guidance
  plw brief <file> [root] [--json]
      -> Brief profile of a single file
  plw impact <file> [root] [--json]
      -> Downstream impact analysis
  plw outline <file> [root] [--json]
      -> File symbols and exports outline
  plw memory <subcommand> [...]
      -> Episodic/semantic memory operations
  plw fiber <subcommand> [...]
      -> Fiber and parallel transport operations
  plw <hott_kernel command> [...]
      -> Passthrough to all standard HoTT Kernel modes
""")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    sub_args = sys.argv[2:]

    if cmd in ("context", "pack"):
        sys.exit(cmd_context(sub_args))
    elif cmd == "kan":
        sys.exit(cmd_kan(sub_args))
    elif cmd == "check":
        sys.exit(cmd_check(sub_args))
    elif cmd == "steer":
        sys.exit(cmd_steer(sub_args))
    else:
        # Standard passthrough to hott_kernel.main()
        # Rewriting sys.argv so hott_kernel sees original arguments
        sys.argv = [sys.argv[0]] + sys.argv[1:]
        try:
            hott_kernel.main()
        except SystemExit as se:
            sys.exit(se.code)
        except Exception as exc:
            print(f"[PLW Error] {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
