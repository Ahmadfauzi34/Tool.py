"""
Performance Analyzers — HoTT Kernel
Schema Version: 3.0.0-kernel

Migrated dari standalone tools:
- async_waterfall_detector.py  → perf.async
- deopt_checker.py             → perf.deopt
- gc_pressure_analyzer.py      → perf.gc
- cache_auditor.py             → perf.cache

Semua analyzer mengonsumsi SharedGraph. Tidak ada os.walk() di sini.
"""

import re
from typing import Any, Dict, List, Set, Tuple


# ============================================================
# Shared Helpers
# ============================================================

def _strip_comments(content: str) -> str:
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"/\*[\s\S]*?\*/", "", content)
    return content


def _strip_strings(content: str) -> str:
    content = re.sub(r"'[^']*'", "''", content)
    content = re.sub(r'"[^"]*"', '""', content)
    content = re.sub(r"`[^`]*`", "``", content)
    return content


def _is_in_loop(lines: List[str], target_idx: int) -> bool:
    """Check apakah baris berada di dalam loop dengan brace counting."""
    brace_count = 0
    for i in range(target_idx, -1, -1):
        line = lines[i].strip()
        brace_count += line.count("}") - line.count("{")
        if re.match(r"^\s*(for\s*\(|for\s+(?:const|let|var)\s+\w+\s+(?:of|in)|while\s*\()", line):
            if brace_count <= 0:
                return True
    return False


# ============================================================
# perf.async — Async Waterfall Detector
# ============================================================

SEQUENTIAL_AWAIT_REGEX = re.compile(
    r"^\s*(?:const|let|var)\s+(\w+)\s*=\s*await\s+"
)

SYNC_IO_REGEX = re.compile(
    r"\b(readFileSync|writeFileSync|existsSync|mkdirSync|readdirSync|"
    r"statSync|unlinkSync|rmdirSync|renameSync|copyFileSync|"
    r"execSync|spawnSync)\s*\("
)

AWAIT_INSIDE_REGEX = re.compile(r"await\s+[\w.$]+\(")

# Variable dependency check: apakah await berikutnya bergantung pada hasil sebelumnya
DEPENDENCY_REGEX = re.compile(
    r"(?:const|let|var)\s+(\w+)\s*=\s*await\s+.*\b({deps})\b"
)


def analyze_async_waterfall(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari async_waterfall_detector.py.
    Deteksi: sequential_await, await_in_loop, sync_io.
    """
    findings: List[Dict[str, Any]] = []
    file_map = shared_graph.get("file_map", {})

    for file_path, raw_content in sorted(file_map.items()):
        content = _strip_comments(raw_content)
        lines = content.split("\n")

        # --- sequential_await (with dependency check) ---
        await_lines = []
        for i, line in enumerate(lines):
            match = SEQUENTIAL_AWAIT_REGEX.match(line)
            if match:
                await_lines.append({
                    "line": i + 1,
                    "variable": match.group(1),
                    "content": line.strip(),
                })

        # Group consecutive awaits, filter out dependent chains
        if len(await_lines) >= 2:
            groups: List[List[Dict]] = []
            current_group = [await_lines[0]]

            for i in range(1, len(await_lines)):
                prev = await_lines[i - 1]
                curr = await_lines[i]

                # Check apakah curr bergantung pada prev
                prev_var = prev["variable"]
                dep_pattern = re.compile(
                    rf"(?:const|let|var)\s+{re.escape(curr['variable'])}\s*=\s*await\s+.*\b{re.escape(prev_var)}\b"
                )
                is_dependent = dep_pattern.search(curr["content"])

                if curr["line"] - prev["line"] <= 3 and not is_dependent:
                    current_group.append(curr)
                else:
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = [curr]

            if len(current_group) >= 2:
                groups.append(current_group)

            for group in groups:
                findings.append({
                    "type": "sequential_await",
                    "severity": "medium",
                    "file": file_path,
                    "line_start": group[0]["line"],
                    "line_end": group[-1]["line"],
                    "count": len(group),
                    "variables": [item["variable"] for item in group],
                    "observation": (
                        f"{len(group)} independent sequential await statements "
                        f"(lines {group[0]['line']}-{group[-1]['line']}) "
                        f"could potentially be parallelized."
                    ),
                })

        # --- await_in_loop ---
        for i, line in enumerate(lines):
            stripped = line.strip()
            if AWAIT_INSIDE_REGEX.search(stripped) and _is_in_loop(lines, i):
                findings.append({
                    "type": "await_in_loop",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "content": stripped,
                    "observation": (
                        f"await inside loop at line {i + 1} — "
                        f"sequential execution per iteration."
                    ),
                })

        # --- sync_io ---
        for i, line in enumerate(lines):
            match = SYNC_IO_REGEX.search(line)
            if match:
                findings.append({
                    "type": "sync_io",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "sync_method": match.group(1),
                    "content": line.strip(),
                    "observation": (
                        f"Synchronous I/O '{match.group(1)}' at line {i + 1} "
                        f"blocks the event loop."
                    ),
                })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 3), f["file"], f.get("line", 0)))

    return {
        "analyzer": "perf.async",
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_type": {
                "sequential_await": sum(1 for f in findings if f["type"] == "sequential_await"),
                "await_in_loop": sum(1 for f in findings if f["type"] == "await_in_loop"),
                "sync_io": sum(1 for f in findings if f["type"] == "sync_io"),
            },
        },
    }


# ============================================================
# perf.deopt — V8 Deoptimization Checker
# ============================================================

DELETE_REGEX = re.compile(r"\bdelete\s+[\w.$\[\]'\"]+")
EVAL_REGEX = re.compile(r"\beval\s*\(")
NEW_FUNC_REGEX = re.compile(r"\bnew\s+Function\s*\(")


def analyze_deopt(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari deopt_checker.py.
    Deteksi: delete_operator, eval_usage, new_function.
    """
    findings: List[Dict[str, Any]] = []
    file_map = shared_graph.get("file_map", {})

    for file_path, raw_content in sorted(file_map.items()):
        content = _strip_comments(raw_content)
        lines = content.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()

            if DELETE_REGEX.search(stripped):
                findings.append({
                    "type": "delete_operator",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "content": stripped,
                    "observation": (
                        f"delete operator at line {i + 1} forces V8 into "
                        f"dictionary mode (slow properties)."
                    ),
                })

            if EVAL_REGEX.search(stripped):
                findings.append({
                    "type": "eval_usage",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "content": stripped,
                    "observation": (
                        f"eval() at line {i + 1} disables optimization "
                        f"in the enclosing scope."
                    ),
                })

            if NEW_FUNC_REGEX.search(stripped):
                findings.append({
                    "type": "new_function",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "content": stripped,
                    "observation": (
                        f"new Function() at line {i + 1} creates "
                        f"unoptimizable dynamic code."
                    ),
                })

    findings.sort(key=lambda f: (f["file"], f.get("line", 0)))

    return {
        "analyzer": "perf.deopt",
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_type": {
                "delete_operator": sum(1 for f in findings if f["type"] == "delete_operator"),
                "eval_usage": sum(1 for f in findings if f["type"] == "eval_usage"),
                "new_function": sum(1 for f in findings if f["type"] == "new_function"),
            },
        },
    }


# ============================================================
# perf.gc — GC Pressure Analyzer
# ============================================================

JSON_PARSE_REGEX = re.compile(r"JSON\.parse\s*\(")
JSON_STRINGIFY_REGEX = re.compile(r"JSON\.stringify\s*\(")
SET_INTERVAL_REGEX = re.compile(r"(?:const|let|var)\s+(\w+)\s*=\s*setInterval\s*\(")
CLEAR_INTERVAL_REGEX = re.compile(r"clearInterval\s*\(\s*(\w+)\s*\)")
MAP_SET_REGEX = re.compile(
    r"(?:const|let|var|private|public|protected|readonly)\s+"
    r"(\w*(?:cache|Cache|pool|Pool|registry|Registry|store|Store)\w*)\s*"
    r"=\s*new\s+(Map|Set)\s*\("
)
OBJ_ALLOC_REGEX = re.compile(r"(?:const|let|var)\s+\w+\s*=\s*\{")
ADD_EVENT_LISTENER_REGEX = re.compile(r"\.addEventListener\s*\(")
REMOVE_EVENT_LISTENER_REGEX = re.compile(r"\.removeEventListener\s*\(")


def analyze_gc_pressure(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari gc_pressure_analyzer.py.
    Deteksi: json_in_loop, allocation_in_loop, uncleared_timer,
             unbounded_collection, unclosed_event_listener.
    """
    findings: List[Dict[str, Any]] = []
    file_map = shared_graph.get("file_map", {})

    for file_path, raw_content in sorted(file_map.items()):
        content = _strip_comments(raw_content)
        lines = content.split("\n")

        # --- json_in_loop & allocation_in_loop ---
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not _is_in_loop(lines, i):
                continue

            if JSON_PARSE_REGEX.search(stripped) or JSON_STRINGIFY_REGEX.search(stripped):
                method = "JSON.parse" if JSON_PARSE_REGEX.search(stripped) else "JSON.stringify"
                findings.append({
                    "type": "json_in_loop",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "content": stripped,
                    "observation": f"{method} inside loop at line {i + 1}.",
                })

            if OBJ_ALLOC_REGEX.search(stripped):
                findings.append({
                    "type": "allocation_in_loop",
                    "severity": "medium",
                    "file": file_path,
                    "line": i + 1,
                    "content": stripped,
                    "observation": f"Object allocation inside loop at line {i + 1}.",
                })

        # --- uncleared_timer ---
        interval_vars: List[Tuple[str, int]] = []
        cleared_vars: Set[str] = set()

        for i, line in enumerate(lines):
            stripped = line.strip()
            match = SET_INTERVAL_REGEX.search(stripped)
            if match:
                interval_vars.append((match.group(1), i + 1))
            clear_match = CLEAR_INTERVAL_REGEX.search(stripped)
            if clear_match:
                cleared_vars.add(clear_match.group(1))

        for var_name, line_num in interval_vars:
            if var_name not in cleared_vars:
                findings.append({
                    "type": "uncleared_timer",
                    "severity": "high",
                    "file": file_path,
                    "line": line_num,
                    "variable": var_name,
                    "observation": (
                        f"setInterval '{var_name}' at line {line_num} "
                        f"without clearInterval (timer leak)."
                    ),
                })

        # --- unbounded_collection ---
        for i, line in enumerate(lines):
            match = MAP_SET_REGEX.search(line.strip())
            if match:
                var_name = match.group(1)
                coll_type = match.group(2)
                has_cleanup = bool(re.search(
                    rf"{re.escape(var_name)}\.(?:delete|clear)\s*\(|"
                    rf"{re.escape(var_name)}\.size\s*[<>]",
                    content
                ))
                if not has_cleanup:
                    findings.append({
                        "type": "unbounded_collection",
                        "severity": "medium",
                        "file": file_path,
                        "line": i + 1,
                        "variable": var_name,
                        "collection_type": coll_type,
                        "observation": (
                            f"new {coll_type}() '{var_name}' at line {i + 1} "
                            f"without apparent size limit or cleanup."
                        ),
                    })

        # --- unclosed_event_listener ---
        if ADD_EVENT_LISTENER_REGEX.search(content) and not REMOVE_EVENT_LISTENER_REGEX.search(content):
            for i, line in enumerate(lines):
                if ".addEventListener" in line:
                    findings.append({
                        "type": "unclosed_event_listener",
                        "severity": "high",
                        "file": file_path,
                        "line": i + 1,
                        "content": line.strip(),
                        "observation": (
                            f"addEventListener at line {i + 1} without "
                            f"corresponding removeEventListener (memory leak)."
                        ),
                    })
                    break  # satu finding per file cukup

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 3), f["file"], f.get("line", 0)))

    return {
        "analyzer": "perf.gc",
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_type": {
                "json_in_loop": sum(1 for f in findings if f["type"] == "json_in_loop"),
                "allocation_in_loop": sum(1 for f in findings if f["type"] == "allocation_in_loop"),
                "uncleared_timer": sum(1 for f in findings if f["type"] == "uncleared_timer"),
                "unbounded_collection": sum(1 for f in findings if f["type"] == "unbounded_collection"),
                "unclosed_event_listener": sum(1 for f in findings if f["type"] == "unclosed_event_listener"),
            },
        },
    }


# ============================================================
# perf.cache — Cache Auditor
# ============================================================

CACHE_SET_REGEX = re.compile(
    r"(\w*(?:cache|Cache)\w*)\s*\.\s*set\s*\("
)
NONDETERMINISTIC_KEY_REGEX = re.compile(
    r"(?:key|Key|cacheKey|cache_key)\s*=.*"
    r"(Date\.now\s*\(\)|Math\.random\s*\(\)|crypto\.randomUUID\s*\(\))"
)
KEY_CONCAT_REGEX = re.compile(
    r"(?:key|Key|cacheKey|cache_key)\s*=\s*[\w.'\"\[\]]+\s*\+\s*[\w.'\"\[\]]+"
)
TTL_MECHANISM_REGEX = re.compile(
    r"(?:ttl|TTL|expire|expiry|expiration|maxAge|max_age|timeToLive|"
    r"setTimeout.*(?:delete|remove|clear|evict))",
    re.IGNORECASE
)


def analyze_cache(shared_graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrated dari cache_auditor.py.
    Deteksi: nondeterministic_cache_key, key_collision_risk, missing_ttl.
    """
    findings: List[Dict[str, Any]] = []
    file_map = shared_graph.get("file_map", {})

    for file_path, raw_content in sorted(file_map.items()):
        content = _strip_comments(raw_content)
        lines = content.split("\n")

        # Skip file yang tidak punya cache context
        if not CACHE_SET_REGEX.search(content):
            continue

        has_ttl = bool(TTL_MECHANISM_REGEX.search(content))

        for i, line in enumerate(lines):
            stripped = line.strip()

            # --- nondeterministic_cache_key ---
            nondet_match = NONDETERMINISTIC_KEY_REGEX.search(stripped)
            if nondet_match:
                findings.append({
                    "type": "nondeterministic_cache_key",
                    "severity": "high",
                    "file": file_path,
                    "line": i + 1,
                    "value_used": nondet_match.group(1),
                    "content": stripped,
                    "observation": (
                        f"Non-deterministic value in cache key at line {i + 1}: "
                        f"{nondet_match.group(1)}."
                    ),
                })

            # --- key_collision_risk ---
            if KEY_CONCAT_REGEX.search(stripped):
                has_delimiter = bool(re.search(r"['\"][\-:_|.]+['\"]", stripped))
                if not has_delimiter:
                    findings.append({
                        "type": "key_collision_risk",
                        "severity": "medium",
                        "file": file_path,
                        "line": i + 1,
                        "content": stripped,
                        "observation": (
                            f"Cache key concatenation without delimiter "
                            f"at line {i + 1} (collision risk)."
                        ),
                    })

            # --- missing_ttl & unbounded_cache ---
            cache_match = CACHE_SET_REGEX.search(stripped)
            if cache_match and not has_ttl:
                findings.append({
                    "type": "missing_ttl",
                    "severity": "medium",
                    "file": file_path,
                    "line": i + 1,
                    "variable": cache_match.group(1),
                    "content": stripped,
                    "observation": (
                        f"cache.set() on '{cache_match.group(1)}' at line {i + 1} "
                        f"without TTL/expiration mechanism."
                    ),
                })
                findings.append({
                    "type": "unbounded_cache",
                    "severity": "medium",
                    "file": file_path,
                    "line": i + 1,
                    "variable": cache_match.group(1),
                    "content": stripped,
                    "observation": (
                        f"Unbounded cache collection '{cache_match.group(1)}' at line {i + 1}."
                    ),
                })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 3), f["file"], f.get("line", 0)))

    return {
        "analyzer": "perf.cache",
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_type": {
                "nondeterministic_cache_key": sum(1 for f in findings if f["type"] == "nondeterministic_cache_key"),
                "key_collision_risk": sum(1 for f in findings if f["type"] == "key_collision_risk"),
                "missing_ttl": sum(1 for f in findings if f["type"] == "missing_ttl"),
                "unbounded_cache": sum(1 for f in findings if f["type"] == "unbounded_cache"),
            },
        },
    }
