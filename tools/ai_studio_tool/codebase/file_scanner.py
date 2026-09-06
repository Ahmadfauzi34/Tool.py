import os
import re
import json
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA_VERSION = "1.8.0-brief"

DEFAULT_IGNORE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    ".angular",
    ".Jules",
    "coverage",
    ".next",
    "out",
}

SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
RESOLUTION_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")

ENTRYPOINT_RULES = [
    (re.compile(r"^main\.server\.(ts|js)$"), "ssr_bootstrap", 0.95),
    (re.compile(r"^main\.(ts|js)$"), "browser_bootstrap", 0.95),
    (re.compile(r"^server\.(ts|js)$"), "server_http", 0.90),
    (re.compile(r"^entry\.server\.(ts|js)$"), "ssr_bootstrap", 0.90),
    (re.compile(r"^entry\.client\.(ts|js)$"), "browser_bootstrap", 0.90),
    (re.compile(r"^bootstrap\.(ts|js)$"), "app_bootstrap", 0.80),
]

TEST_FILE_SUFFIXES = (
    ".spec.ts",
    ".spec.tsx",
    ".spec.js",
    ".spec.jsx",
    ".test.ts",
    ".test.tsx",
    ".test.js",
    ".test.jsx",
)


def _detect_test_file(file_path: str) -> bool:
    """
    Mendeteksi apakah file kemungkinan adalah file test.

    Heuristic berbasis nama file dan path:
    - *.spec.ts / *.spec.tsx / *.spec.js / *.spec.jsx
    - *.test.ts / *.test.tsx / *.test.js / *.test.jsx
    - folder __tests__, tests, atau test
    """
    base = os.path.basename(file_path).lower()

    if any(base.endswith(suffix) for suffix in TEST_FILE_SUFFIXES):
        return True

    lower_path = file_path.lower()

    return (
        "/__tests__/" in lower_path
        or "/tests/" in lower_path
        or "/test/" in lower_path
    )

IMPORT_EXPORT_REGEX = re.compile(
    r"""(?:import\s+(?:[^"';\n]*?\bfrom\s+)?|export\s+[^"';\n]*?\bfrom\s+|import\s*\(\s*)["']([^"']+)["']"""
)
IMPORT_REGEX = IMPORT_EXPORT_REGEX

IMPORT_STATEMENT_REGEX = re.compile(
    r"""(?:(?P<stmt>(?:import|export)\s+(?:[^"';]*?\bfrom\s+)?|import\s*\(\s*))["'](?P<path>[^"']+)["']""",
    re.MULTILINE,
)


def _strip_comments(content: str) -> str:
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"/\*[\s\S]*?\*/", "", content)
    return content


def classify_import_nature(stmt: str) -> str:
    """
    Classify whether an import/export statement is type-only or runtime:
    - 'type_only': compiler-only import (e.g. `import type`, `export type`, or all named specifiers are `type X`)
    - 'runtime': executed at runtime
    """
    stmt_clean = " ".join(stmt.strip().split())

    # 1. import type ... or export type ...
    if re.search(r"^(?:import|export)\s+type\b", stmt_clean):
        return "type_only"

    # 2. Check named specifiers: import { type A, type B } from '...'
    brace_match = re.search(r"\{([^}]+)\}", stmt_clean)
    if brace_match:
        raw_items = brace_match.group(1).split(",")
        specifiers = [s.strip() for s in raw_items if s.strip()]
        if specifiers and all(re.match(r"^type\s+[A-Za-z0-9_$]", s) for s in specifiers):
            return "type_only"

    return "runtime"


def parse_imports_with_nature(content: str) -> List[Dict[str, str]]:
    """
    Extract all imports from source content with their nature ('runtime' | 'type_only').
    Comments are stripped before matching.
    """
    clean_content = _strip_comments(content)
    results: List[Dict[str, str]] = []

    for match in IMPORT_STATEMENT_REGEX.finditer(clean_content):
        raw_path = match.group("path")
        stmt = match.group("stmt") or ""
        nature = classify_import_nature(stmt)
        results.append(
            {
                "raw_import": raw_path,
                "import_nature": nature,
                "statement": stmt,
            }
        )

    return results


OUTLINE_DECLARATION_REGEX = re.compile(
    r"^(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?"
    r"(class|function|const|let|var|interface|type|enum)\s+([A-Za-z0-9_$]+)"
)


def _normalize_path(value: str) -> str:
    """Normalisasi path menjadi slash-forward dan tanpa prefix ./"""
    normalized = os.path.normpath(value).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _coerce_roots(path: Any) -> List[str]:
    """
    Normalisasi input root scan.

    Mendukung:
    - single string: "src"
    - comma-separated string: "src,tools,server"
    - list/tuple/set: ["src", "tools", "server"]
    """
    raw_items: List[str] = []

    if isinstance(path, (list, tuple, set)):
        raw_items = [str(item) for item in path]
    else:
        value = str(path)
        if "," in value:
            raw_items = [item.strip() for item in value.split(",")]
        else:
            raw_items = [value]

    roots: List[str] = []
    seen: Set[str] = set()

    for item in raw_items:
        item = item.strip()
        normalized = _normalize_path(item) if item else "."

        if not normalized:
            normalized = "."

        if normalized not in seen:
            seen.add(normalized)
            roots.append(normalized)

    return roots or ["."]


def _is_source_file(filename: str) -> bool:
    """Cek apakah file termasuk file kode TS/JS/TSX/JSX."""
    return filename.endswith(SOURCE_EXTENSIONS) and not filename.endswith(".d.ts")


def scan_directory(path: str = ".", max_depth: int = 2) -> List[Dict[str, Any]]:
    """
    Surgical scanning: memindai metadata folder/file tanpa membaca isi kode.
    """
    structure = []
    base_depth = path.count(os.sep)

    for root, dirs, files in os.walk(path):
        curr_depth = root.count(os.sep)
        if curr_depth - base_depth <= max_depth:
            structure.append(
                {
                    "path": _normalize_path(root),
                    "dirs": len(dirs),
                    "files": len(files),
                }
            )

    return structure


def _resolve_import_path(base_file: str, import_path: str) -> str:
    """
    Menyelaraskan relative TS/JS import path menjadi workspace relative path.
    """
    if not import_path.startswith("."):
        return import_path

    base_dir = os.path.dirname(base_file)
    parts = base_dir.split("/") if base_dir else []

    for segment in import_path.split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment and segment != ".":
            parts.append(segment)

    resolved = "/".join(parts)
    return resolved


def _candidate_targets(resolved_base: str) -> List[str]:
    """
    Daftar kandidat resolusi untuk import tanpa ekstensi atau import folder.
    """
    candidates: List[str] = []
    seen: Set[str] = set()

    def add(candidate: str) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    add(resolved_base)

    # Jika import sudah eksplisit berekstensi, jangan tambahkan ekstensi ganda.
    if not any(resolved_base.endswith(ext) for ext in RESOLUTION_EXTENSIONS):
        for ext in RESOLUTION_EXTENSIONS:
            add(resolved_base + ext)

        for ext in RESOLUTION_EXTENSIONS:
            add(f"{resolved_base}/index{ext}")

    return candidates


def _edge_resolution_metadata(resolved_base: str, matched_target: str) -> Tuple[str, str, float]:
    """
    Tentukan status, method, dan confidence dari edge yang berhasil di-resolve.
    """
    if matched_target == resolved_base:
        return "resolved", "exact_match", 1.0

    for ext in RESOLUTION_EXTENSIONS:
        if matched_target == resolved_base + ext:
            confidence = 0.95 if ext in (".ts", ".tsx") else 0.90
            return "resolved_with_assumption", "extension_match", confidence

    for ext in RESOLUTION_EXTENSIONS:
        if matched_target == f"{resolved_base}/index{ext}":
            return "resolved_with_assumption", "index_match", 0.85

    return "resolved_with_assumption", "heuristic_fallback", 0.50


def _classify_node(file_path: str, content: str) -> str:
    """
    Mengklasifikasikan jenis node (Service, Component, Helper, Module, atau Other).
    """
    lower_path = file_path.lower()

    if (
        ".service." in lower_path
        or "@Injectable" in content
        or "Service" in os.path.basename(file_path)
    ):
        return "Service"

    if (
        ".component." in lower_path
        or "@Component" in content
        or "Component" in os.path.basename(file_path)
    ):
        return "Component"

    if (
        ".module." in lower_path
        or ".routes." in lower_path
        or "Module" in os.path.basename(file_path)
    ):
        return "Module"

    if "util" in lower_path or "helper" in lower_path or "/tools/" in lower_path:
        return "Helper"

    return "Other"


def _extract_main_name(file_path: str, content: str) -> str:
    """
    Mengekstrak nama kelas utama, fungsi, atau konstanta ekspor sebagai label visual.
    """
    class_match = re.search(r"export\s+class\s+([A-Za-z0-9_]+)", content)
    if class_match:
        return class_match.group(1)

    func_match = re.search(r"export\s+function\s+([A-Za-z0-9_]+)", content)
    if func_match:
        return func_match.group(1)

    const_match = re.search(r"export\s+const\s+([A-Za-z0-9_]+)", content)
    if const_match:
        return const_match.group(1)

    base = os.path.basename(file_path)
    if "." in base:
        base = base.split(".")[0]

    return "".join(word.capitalize() for word in re.split(r"[-_]", base))


def _detect_entrypoint(file_path: str) -> Tuple[bool, str, float]:
    """
    Mendeteksi apakah sebuah file kemungkinan adalah entrypoint aplikasi.

    Heuristic awal berbasis nama file:
    - main.ts
    - main.server.ts
    - server.ts
    - entry.client.ts
    - entry.server.ts
    - bootstrap.ts
    """
    base = os.path.basename(file_path)

    for pattern, kind, confidence in ENTRYPOINT_RULES:
        if pattern.match(base):
            return True, kind, confidence

    return False, "none", 0.0


def _assess_change_risk(
    target_is_entrypoint: bool,
    affected_entrypoints: List[str],
    target_fan_in: int,
    target_fan_out: int,
) -> Tuple[str, List[str]]:
    """
    Heuristic minimal untuk menilai risiko perubahan file.

    Level:
    - high    : menyentuh entrypoint dan fan_in tinggi
    - medium  : menyentuh entrypoint, atau fan_in tinggi, atau target sendiri entrypoint
    - low     : relatif terisolasi
    """
    reasons: List[str] = []

    if affected_entrypoints:
        reasons.append("impacts_entrypoints")

    if target_fan_in >= 2:
        reasons.append("high_fan_in")

    if target_is_entrypoint:
        reasons.append("target_is_entrypoint")

    if affected_entrypoints and target_fan_in >= 2:
        return "high", reasons

    if affected_entrypoints or target_fan_in >= 2 or target_is_entrypoint:
        return "medium", reasons

    if not reasons:
        reasons.append("isolated")

    return "low", reasons


def _strip_jsonc_comments(text: str) -> str:
    """
    Menghapus komentar JSONC sederhana dan trailing comma.

    Catatan:
    Ini heuristic, bukan parser JSONC penuh.
    Cukup untuk tsconfig/jsconfig pada umumnya.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(^\s*)//.*", r"\1", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _load_alias_rules(roots: List[str]) -> List[Dict[str, Any]]:
    """
    Membaca compilerOptions.paths dari tsconfig.json / jsconfig.json.

    Mendukung:
    - alias wildcard: "@app/*": ["src/app/*"]
    - alias exact: "@env": ["src/environments/environment.ts"]
    """
    config_candidates: List[str] = []
    seen_configs: Set[str] = set()

    search_dirs: List[str] = []
    for r in list(roots) + ["."]:
        curr = _normalize_path(r) if r else "."
        while curr:
            if curr not in search_dirs:
                search_dirs.append(curr)
            if curr in (".", ""):
                break
            parent = _normalize_path(os.path.dirname(curr))
            if parent == curr:
                break
            curr = parent
    if "." not in search_dirs:
        search_dirs.append(".")

    config_names = (
        "tsconfig.json",
        "jsconfig.json",
        "tsconfig.base.json",
        "tsconfig.app.json",
    )

    for directory in search_dirs:
        for config_name in config_names:
            cfg = _normalize_path(os.path.join(directory, config_name))
            if cfg not in seen_configs:
                seen_configs.add(cfg)
                config_candidates.append(cfg)

    rules: List[Dict[str, Any]] = []

    for cfg in config_candidates:
        if not os.path.isfile(cfg):
            continue

        try:
            with open(cfg, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()

            data = json.loads(_strip_jsonc_comments(raw))
        except Exception:
            continue

        compiler_options = data.get("compilerOptions", {}) or {}
        base_url = compiler_options.get("baseUrl")
        paths = compiler_options.get("paths", {}) or {}

        if not paths:
            continue

        config_dir = os.path.dirname(cfg) or "."

        if base_url:
            alias_base = _normalize_path(os.path.join(config_dir, base_url))
        else:
            alias_base = _normalize_path(config_dir)

        for pattern, targets in paths.items():
            if not isinstance(targets, list):
                continue

            for target in targets:
                if not isinstance(target, str):
                    continue

                if pattern.endswith("/*"):
                    prefix = pattern[:-1]

                    if target.endswith("/*"):
                        target_base = target[:-1]
                    else:
                        target_base = target

                    if alias_base and alias_base != ".":
                        full_base = _normalize_path(os.path.join(alias_base, target_base))
                    else:
                        full_base = _normalize_path(target_base)

                    rules.append(
                        {
                            "type": "wildcard",
                            "prefix": prefix,
                            "base": full_base,
                            "source": cfg,
                        }
                    )
                else:
                    if alias_base and alias_base != ".":
                        full_target = _normalize_path(os.path.join(alias_base, target))
                    else:
                        full_target = _normalize_path(target)

                    rules.append(
                        {
                            "type": "exact",
                            "pattern": pattern,
                            "target": full_target,
                            "source": cfg,
                        }
                    )

    # Deterministik: alias dengan prefix/pattern lebih panjang diprioritaskan
    rules.sort(
        key=lambda r: (
            len(r.get("prefix", r.get("pattern", ""))),
            r.get("source", ""),
        ),
        reverse=True,
    )

    return rules


def _alias_candidates(raw_import: str, alias_rules: List[Dict[str, Any]]) -> List[str]:
    """
    Mengubah import alias menjadi kandidat path internal.
    """
    candidates: List[str] = []
    seen: Set[str] = set()

    for rule in alias_rules:
        if rule.get("type") == "exact":
            if raw_import == rule.get("pattern"):
                candidate = rule.get("target")

                if candidate and candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)

        elif rule.get("type") == "wildcard":
            prefix = rule.get("prefix", "")

            if prefix and raw_import.startswith(prefix):
                rest = raw_import[len(prefix):]
                base = rule.get("base", "")

                if base:
                    candidate = _normalize_path(os.path.join(base, rest))
                else:
                    candidate = _normalize_path(rest)

                if candidate and candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)

    return candidates


def scan_topology(
    path: Any = ".",
    save_path: Optional[str] = None,
    ignore_dirs: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Memindai satu atau beberapa root folder secara read-only.

    Perilaku penting:
    - edge utama hanya berisi import yang berhasil di-resolve
    - unresolved import masuk diagnostics
    - external import dicatat, tidak dijadikan edge internal
    - mendukung multi-root scan
    - file_map global, sehingga import lintas root tetap bisa di-resolve
    """
    roots = _coerce_roots(path)

    if ignore_dirs is None:
        ignore_dirs = set(DEFAULT_IGNORE_DIRS)
    else:
        ignore_dirs = set(ignore_dirs)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    file_map: Set[str] = set()

    raw_edges: List[Dict[str, str]] = []

    unresolved_imports: List[Dict[str, Any]] = []
    external_imports: List[Dict[str, str]] = []
    non_relative_imports: List[Dict[str, str]] = []
    skipped_files: List[Dict[str, str]] = []
    parse_warnings: List[Dict[str, str]] = []

    seen_external: Set[Tuple[str, str]] = set()
    seen_non_relative: Set[Tuple[str, str]] = set()
    seen_unresolved: Set[Tuple[str, str]] = set()
    seen_files: Set[str] = set()

    for root_dir in roots:
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = sorted(
                [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            )

            for file in sorted(files):
                if not _is_source_file(file):
                    continue

                full_path = _normalize_path(os.path.join(root, file))

                if full_path in seen_files:
                    continue

                seen_files.add(full_path)

                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception as exc:
                    skipped_files.append(
                        {
                            "path": full_path,
                            "reason": "read_error",
                            "message": str(exc),
                        }
                    )
                    continue

                node_type = _classify_node(full_path, content)
                main_name = _extract_main_name(full_path, content)

                is_entrypoint, entrypoint_kind, entrypoint_confidence = _detect_entrypoint(full_path)
                is_test = _detect_test_file(full_path)

                nodes.append(
                    {
                        "id": full_path,
                        "path": full_path,
                        "label": main_name,
                        "type": node_type,
                        "is_entrypoint": is_entrypoint,
                        "entrypoint_kind": entrypoint_kind,
                        "entrypoint_confidence": entrypoint_confidence,
                        "is_test": is_test,
                    }
                )
                file_map.add(full_path)

                imports_with_nature = parse_imports_with_nature(content)

                for item in imports_with_nature:
                    raw_import = item["raw_import"]
                    nature = item["import_nature"]

                    if raw_import.startswith("."):
                        resolved_base = _resolve_import_path(full_path, raw_import)
                        raw_edges.append(
                            {
                                "source": full_path,
                                "raw_import": raw_import,
                                "resolved_base": resolved_base,
                                "import_nature": nature,
                            }
                        )
                    else:
                        key = (full_path, raw_import)
                        if key not in seen_non_relative:
                            seen_non_relative.add(key)
                            non_relative_imports.append(
                                {
                                    "importer": full_path,
                                    "raw_import": raw_import,
                                    "import_nature": nature,
                                }
                            )

    # Resolve semua edge setelah semua root selesai dipindai
    for raw_edge in raw_edges:
        source = raw_edge["source"]
        raw_import = raw_edge["raw_import"]
        resolved_base = raw_edge["resolved_base"]
        import_nature = raw_edge.get("import_nature", "runtime")

        candidates = _candidate_targets(resolved_base)
        matched_target = None

        for candidate in candidates:
            if candidate in file_map:
                matched_target = candidate
                break

        if matched_target:
            status, method, confidence = _edge_resolution_metadata(
                resolved_base, matched_target
            )

            edges.append(
                {
                    "source": source,
                    "target": matched_target,
                    "raw_import": raw_import,
                    "status": status,
                    "method": method,
                    "confidence": confidence,
                    "import_nature": import_nature,
                }
            )
        else:
            key = (source, raw_import)
            if key not in seen_unresolved:
                seen_unresolved.add(key)
                unresolved_imports.append(
                    {
                        "importer": source,
                        "raw_import": raw_import,
                        "reason": "no_candidate_found",
                        "attempted_candidates": candidates,
                    }
                )

    alias_rules = _load_alias_rules(roots)

    for item in non_relative_imports:
        importer = item["importer"]
        raw_import = item["raw_import"]
        import_nature = item.get("import_nature", "runtime")

        alias_bases = _alias_candidates(raw_import, alias_rules)

        if not alias_bases:
            key = (importer, raw_import)
            if key not in seen_external:
                seen_external.add(key)
                external_imports.append(
                    {
                        "importer": importer,
                        "raw_import": raw_import,
                    }
                )
            continue

        attempted_candidates: List[str] = []
        matched_target = None
        matched_alias_base = None

        for alias_base in alias_bases:
            candidates = _candidate_targets(alias_base)
            attempted_candidates.extend(candidates)

            for candidate in candidates:
                if candidate in file_map:
                    matched_target = candidate
                    matched_alias_base = alias_base
                    break

            if matched_target:
                break

        if matched_target:
            if matched_target == matched_alias_base:
                status = "resolved"
                confidence = 0.85
            else:
                status = "resolved_with_assumption"
                confidence = 0.80

            edges.append(
                {
                    "source": importer,
                    "target": matched_target,
                    "raw_import": raw_import,
                    "status": status,
                    "method": "alias_match",
                    "confidence": confidence,
                    "import_nature": import_nature,
                }
            )
        else:
            key = (importer, raw_import)
            if key not in seen_unresolved:
                seen_unresolved.add(key)
                unresolved_imports.append(
                    {
                        "importer": importer,
                        "raw_import": raw_import,
                        "reason": "alias_candidate_not_found",
                        "attempted_candidates": attempted_candidates,
                    }
                )

    # Deterministik: sort nodes dan edges
    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: (e["source"], e["target"], e.get("raw_import", "")))

    # Deduplikasi edge
    unique_edges: List[Dict[str, Any]] = []
    seen_edge_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for edge in edges:
        key = (edge["source"], edge["target"], edge.get("raw_import", ""))
        if key not in seen_edge_map:
            seen_edge_map[key] = edge
            unique_edges.append(edge)
        else:
            if edge.get("import_nature") == "runtime":
                seen_edge_map[key]["import_nature"] = "runtime"

    edges = unique_edges

    # Graph metrics
    fan_in = {}
    fan_out = {}

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")

        if src:
            fan_out[src] = fan_out.get(src, 0) + 1

        if tgt:
            fan_in[tgt] = fan_in.get(tgt, 0) + 1

    for node in nodes:
        node_id = node.get("id")
        node_fan_in = fan_in.get(node_id, 0)
        node_fan_out = fan_out.get(node_id, 0)
        node["fan_in"] = node_fan_in
        node["fan_out"] = node_fan_out
        node["direct_dependents_count"] = node_fan_in

    max_fan_in = max(fan_in.values()) if fan_in else 0
    max_fan_out = max(fan_out.values()) if fan_out else 0

    entrypoint_count = sum(1 for node in nodes if node.get("is_entrypoint"))
    test_file_count = sum(1 for node in nodes if node.get("is_test"))

    runtime_edge_count = sum(1 for e in edges if e.get("import_nature") == "runtime")
    type_only_edge_count = sum(1 for e in edges if e.get("import_nature") == "type_only")

    unreferenced_files = []

    for node in nodes:
        if (
            node.get("fan_in", 0) == 0
            and not node.get("is_entrypoint")
            and not node.get("is_test")
        ):
            unreferenced_files.append(
                {
                    "id": node.get("id"),
                    "type": node.get("type"),
                    "label": node.get("label"),
                    "fan_out": node.get("fan_out", 0),
                }
            )

    unreferenced_files.sort(key=lambda item: item.get("id", ""))
    unreferenced_file_count = len(unreferenced_files)

    # Deterministik diagnostics
    unresolved_imports.sort(key=lambda item: (item.get("importer", ""), item.get("raw_import", "")))
    external_imports.sort(key=lambda item: (item.get("importer", ""), item.get("raw_import", "")))
    skipped_files.sort(key=lambda item: item.get("path", ""))

    topology: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "root": roots[0] if roots else ".",
            "roots": roots,
            "scan_mode": "multi-root" if len(roots) > 1 else "single-root",
            "ignore_dirs": sorted(ignore_dirs),
            "resolver_mode": "standard-library",
            "unresolved_edge_policy": "exclude_from_main_graph",
            "source_extensions": list(SOURCE_EXTENSIONS),
            "alias_rules_count": len(alias_rules),
            "policy": {
                "mode": "informational_only",
                "blocking": False,
                "provides_change_recommendations": False,
            },
        },
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "total_files_scanned": len(nodes),
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "resolved_edge_count": len(edges),
            "runtime_edge_count": runtime_edge_count,
            "type_only_edge_count": type_only_edge_count,
            "unresolved_import_count": len(unresolved_imports),
            "external_import_count": len(external_imports),
            "skipped_file_count": len(skipped_files),
            "ambiguous_resolution_count": 0,
            "entrypoint_count": entrypoint_count,
            "max_fan_in": max_fan_in,
            "max_fan_out": max_fan_out,
            "test_file_count": test_file_count,
            "unreferenced_file_count": unreferenced_file_count,
        },
        "diagnostics": {
            "unresolved_imports": unresolved_imports,
            "external_imports": external_imports,
            "ambiguous_resolutions": [],
            "skipped_files": skipped_files,
            "parse_warnings": parse_warnings,
            "unreferenced_files": unreferenced_files,
        },
    }

    if save_path:
        try:
            parent_dir = os.path.dirname(save_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(save_path, "w", encoding="utf-8") as out_f:
                json.dump(topology, out_f, indent=2, ensure_ascii=False)
        except Exception as e:
            topology["save_error"] = str(e)

    return topology


def get_impacted_files(
    file_path: str,
    topology: Optional[Dict[str, Any]] = None,
    path: Any = ".",
) -> Dict[str, Any]:
    """
    Melacak dampak perubahan file secara transitif (upstream dan downstream).
    Aman terhadap circular dependency dan menjaga performa pencarian.
    """
    if topology is None:
        topology = scan_topology(path=path)

    target_norm = _normalize_path(file_path)

    node_ids = {
        node.get("id")
        for node in topology.get("nodes", [])
        if node.get("id")
    }

    entrypoint_ids = {
        node.get("id")
        for node in topology.get("nodes", [])
        if node.get("is_entrypoint")
    }

    adj_upstream: Dict[str, List[str]] = {}   # node -> imported targets
    adj_downstream: Dict[str, List[str]] = {}  # node -> importing sources

    for edge in topology.get("edges", []):
        src = edge.get("source")
        tgt = edge.get("target")

        if not src or not tgt:
            continue

        # Safety: hanya gunakan edge yang node-nya benar-benar ada
        if node_ids and (src not in node_ids or tgt not in node_ids):
            continue

        if src not in adj_upstream:
            adj_upstream[src] = []
        adj_upstream[src].append(tgt)

        if tgt not in adj_downstream:
            adj_downstream[tgt] = []
        adj_downstream[tgt].append(src)

    # Deterministik adjacency
    for key in adj_upstream:
        adj_upstream[key] = sorted(set(adj_upstream[key]))

    for key in adj_downstream:
        adj_downstream[key] = sorted(set(adj_downstream[key]))

    def traverse(start_node: str, adj_map: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        result: List[str] = []
        cycles: List[str] = []

        def dfs(node: str) -> None:
            if node in rec_stack:
                cycles.append(node)
                return

            if node in visited:
                return

            rec_stack.add(node)
            visited.add(node)

            if node != start_node:
                result.append(node)

            for neighbor in adj_map.get(node, []):
                dfs(neighbor)

            rec_stack.remove(node)

        dfs(start_node)
        return result, cycles

    upstream_nodes, upstream_cycles = traverse(target_norm, adj_upstream)
    downstream_nodes, downstream_cycles = traverse(target_norm, adj_downstream)

    unresolved_dependency_warnings = [
        item
        for item in topology.get("diagnostics", {}).get("unresolved_imports", [])
        if item.get("importer") == target_norm
    ]

    downstream_set = set(downstream_nodes)
    affected_entrypoints = sorted(entrypoint_ids & (downstream_set | {target_norm}))
    target_is_entrypoint = target_norm in entrypoint_ids

    nodes_by_id = {
        node.get("id"): node
        for node in topology.get("nodes", [])
    }

    target_node = nodes_by_id.get(target_norm, {})
    target_fan_in = target_node.get("fan_in", 0)
    target_fan_out = target_node.get("fan_out", 0)
    target_direct_dependents_count = target_node.get(
        "direct_dependents_count",
        target_fan_in
    )
    target_is_test = target_node.get("is_test", False)

    change_risk_level, change_risk_reasons = _assess_change_risk(
        target_is_entrypoint,
        affected_entrypoints,
        target_fan_in,
        target_fan_out,
    )

    return {
        "target": target_norm,
        "exists": target_norm in node_ids if node_ids else True,
        "upstream": sorted(set(upstream_nodes)),
        "downstream": sorted(set(downstream_nodes)),
        "direct_upstream": sorted(set(adj_upstream.get(target_norm, []))),
        "direct_downstream": sorted(set(adj_downstream.get(target_norm, []))),
        "circular_references": sorted(set(upstream_cycles + downstream_cycles)),
        "unresolved_dependency_warnings": unresolved_dependency_warnings,
        "target_is_entrypoint": target_is_entrypoint,
        "affected_entrypoints": affected_entrypoints,
        "target_fan_in": target_fan_in,
        "target_fan_out": target_fan_out,
        "target_direct_dependents_count": target_direct_dependents_count,
        "change_risk_level": change_risk_level,
        "change_risk_reasons": change_risk_reasons,
        "target_is_test": target_is_test,
    }


def _truncate_text(value: str, max_length: int = 220) -> str:
    """
    Memotong signature agar outline tetap ringkas.
    """
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def get_file_outline(
    file_path: str,
    max_signature_length: int = 220
) -> Dict[str, Any]:
    """
    Menghasilkan outline ringkas dari file TS/JS/TSX/JSX.

    Output berisi:
    - imports
    - internal imports
    - external imports
    - exports
    - decorators
    - outline deklarasi utama

    Ini dirancang untuk mengurangi kebutuhan membaca full file
    saat agent hanya perlu memahami struktur permukaan.
    """
    path_norm = _normalize_path(file_path)

    empty_result = {
        "schema_version": SCHEMA_VERSION,
        "file": path_norm,
        "exists": False,
        "error": None,
        "imports": [],
        "internal_imports": [],
        "external_imports": [],
        "exports": [],
        "decorators": [],
        "outline": [],
        "stats": {
            "total_lines": 0,
            "outline_entries": 0,
            "export_count": 0,
            "import_count": 0,
        },
    }

    if not os.path.isfile(path_norm):
        empty_result["error"] = "file_not_found"
        return empty_result

    try:
        with open(path_norm, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as exc:
        empty_result["error"] = f"read_error: {exc}"
        return empty_result

    imports = sorted(set(IMPORT_REGEX.findall(content)))
    internal_imports = sorted({item for item in imports if item.startswith(".")})
    external_imports = sorted({item for item in imports if not item.startswith(".")})

    outline: List[Dict[str, Any]] = []
    exports: List[str] = []
    decorators: List[str] = []

    lines = content.splitlines()

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()

        if not stripped:
            continue

        if (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
        ):
            continue

        if stripped.startswith("@"):
            decorator_name = stripped[1:].split("(")[0].strip()

            if decorator_name and decorator_name not in decorators:
                decorators.append(decorator_name)

            outline.append(
                {
                    "line": line_no,
                    "kind": "decorator",
                    "name": decorator_name,
                    "exported": False,
                    "signature": _truncate_text(stripped, max_signature_length),
                }
            )
            continue

        exported = stripped.startswith("export")

        if stripped.startswith("export default"):
            name = "default"
            kind = "default_export"

            outline.append(
                {
                    "line": line_no,
                    "kind": kind,
                    "name": name,
                    "exported": True,
                    "signature": _truncate_text(stripped, max_signature_length),
                }
            )

            if name not in exports:
                exports.append(name)

            continue

        match = OUTLINE_DECLARATION_REGEX.match(stripped)

        if match:
            kind = match.group(1)
            name = match.group(2)

            outline.append(
                {
                    "line": line_no,
                    "kind": kind,
                    "name": name,
                    "exported": exported,
                    "signature": _truncate_text(stripped, max_signature_length),
                }
            )

            if exported and name not in exports:
                exports.append(name)

    return {
        "schema_version": SCHEMA_VERSION,
        "file": path_norm,
        "exists": True,
        "error": None,
        "imports": imports,
        "internal_imports": internal_imports,
        "external_imports": external_imports,
        "exports": exports,
        "decorators": decorators,
        "outline": outline,
        "stats": {
            "total_lines": len(lines),
            "outline_entries": len(outline),
            "export_count": len(exports),
            "import_count": len(imports),
        },
    }


def get_file_brief(file_path: str, path: Any = ".") -> Dict[str, Any]:
    """
    Menggabungkan outline file dan impact analysis dalam satu panggilan.
    Dirancang untuk context budgeting: agent bisa memahami struktur, risiko,
    dan dampak file tanpa harus membaca isi file secara penuh.
    """
    outline = get_file_outline(file_path)

    # Jika file tidak ada, kembalikan outline error + impact kosong
    if not outline.get("exists"):
        return {
            "schema_version": SCHEMA_VERSION,
            "file": outline.get("file"),
            "exists": False,
            "error": outline.get("error"),
            "outline": None,
            "impact": None,
        }

    # Gunakan path yang sama untuk topology agar konsisten
    topology = scan_topology(path=path)
    impact = get_impacted_files(file_path, topology=topology, path=path)

    return {
        "schema_version": SCHEMA_VERSION,
        "file": outline.get("file"),
        "exists": True,
        "outline": {
            "imports": outline.get("imports", []),
            "internal_imports": outline.get("internal_imports", []),
            "external_imports": outline.get("external_imports", []),
            "exports": outline.get("exports", []),
            "decorators": outline.get("decorators", []),
            "declarations": outline.get("outline", []),
            "stats": outline.get("stats", {}),
        },
        "impact": {
            "target_is_entrypoint": impact.get("target_is_entrypoint"),
            "target_is_test": impact.get("target_is_test"),
            "target_fan_in": impact.get("target_fan_in"),
            "target_fan_out": impact.get("target_fan_out"),
            "change_risk_level": impact.get("change_risk_level"),
            "change_risk_reasons": impact.get("change_risk_reasons", []),
            "affected_entrypoints": impact.get("affected_entrypoints", []),
            "circular_references": impact.get("circular_references", []),
            "direct_downstream": impact.get("direct_downstream", []),
            "direct_upstream": impact.get("direct_upstream", []),
            "downstream_count": len(impact.get("downstream", [])),
            "upstream_count": len(impact.get("upstream", [])),
            "unresolved_dependency_warnings": impact.get("unresolved_dependency_warnings", []),
        },
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "impact":
        file_p = sys.argv[2] if len(sys.argv) > 2 else "src/app/app.ts"
        root_args = sys.argv[3:] if len(sys.argv) > 3 else ["."]
        path_arg = root_args[0] if len(root_args) == 1 else root_args

        print(json.dumps(get_impacted_files(file_p, path=path_arg), indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "outline":
        file_p = sys.argv[2] if len(sys.argv) > 2 else "src/app/app.ts"
        print(json.dumps(get_file_outline(file_p), indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "brief":
        file_p = sys.argv[2] if len(sys.argv) > 2 else "src/app/app.ts"
        root_args = sys.argv[3:] if len(sys.argv) > 3 else ["."]
        path_arg = root_args[0] if len(root_args) == 1 else root_args
        print(json.dumps(get_file_brief(file_p, path=path_arg), indent=2))

    else:
        out_p = sys.argv[1] if len(sys.argv) > 1 else "public/topology.json"
        roots = sys.argv[2:] if len(sys.argv) > 2 else ["."]

        if out_p == "-":
            topo = scan_topology(path=roots)
            print(json.dumps(topo, indent=2))
        else:
            topo = scan_topology(path=roots, save_path=out_p)
            scan_roots = topo.get("meta", {}).get("roots", ["."])

            payload = {
                "status": "success",
                "nodes_count": len(topo["nodes"]),
                "edges_count": len(topo["edges"]),
                "unresolved_count": topo["summary"]["unresolved_import_count"],
            }

            if len(scan_roots) == 1:
                payload["scan_root"] = scan_roots[0]
            else:
                payload["scan_root"] = scan_roots[0]
                payload["scan_roots"] = scan_roots

            print(json.dumps(payload))
