"""
SharedGraph Builder — HoTT Kernel Foundation
Schema Version: 3.0.0-kernel

Membangun SharedGraph dalam SATU discovery pass:
- Filesystem scan (1x, sebelumnya 9x)
- Import parsing (1x, sebelumnya 5x)
- Graph construction (1x, sebelumnya 4x)
- Node metadata extraction (1x)
- Boundary detection (1x)
- Type shape extraction (1x)

SharedGraph kemudian di-share ke semua analyzer. Cache layer boleh memakai
discovery manifest dan memasok snapshot file yang tervalidasi; analyzer tetap
tidak boleh scan filesystem sendiri.
"""

import os
import re
import json
import hashlib
import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA_VERSION = "3.0.0-kernel"

SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
RESOLUTION_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")
BARREL_FILENAMES = ("index.ts", "index.tsx", "index.js", "index.jsx", "public-api.ts")

DEFAULT_IGNORE_DIRS = {
    "node_modules", ".git", "dist", ".angular",
    ".Jules", "coverage", ".next", "out", "fixtures_min",
}

IMPORT_EXPORT_REGEX = re.compile(
    r"""(?:import\s+(?:[^"';\n]*?\bfrom\s+)?|export\s+[^"';\n]*?\bfrom\s+|import\s*\(\s*)["']([^"']+)["']"""
)
IMPORT_REGEX = IMPORT_EXPORT_REGEX

IMPORT_STATEMENT_REGEX = re.compile(
    r"""(?:(?P<stmt>(?:import|export)\s+(?:[^"';]*?\bfrom\s+)?|import\s*\(\s*))["'](?P<path>[^"']+)["']""",
    re.MULTILINE,
)


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


def _extract_imported_symbols(stmt: str) -> List[str]:
    stmt = re.sub(r'\b(?:import|export|from|type)\b', '', stmt)
    symbols = []
    
    named_match = re.search(r'\{([^}]+)\}', stmt)
    if named_match:
        named_str = named_match.group(1)
        for s in named_str.split(','):
            s = s.strip()
            if not s: continue
            if ' as ' in s:
                symbols.append(s.split(' as ')[1].strip())
            else:
                symbols.append(s)
        stmt = stmt.replace('{' + named_str + '}', '')
    
    stmt = stmt.strip()
    if stmt:
        for s in stmt.split(','):
            s = s.strip()
            if not s: continue
            if s.startswith('* as '):
                symbols.append(s[5:].strip())
            elif '*' not in s:
                symbols.append(s)
                
    return symbols

def _find_semantic_usages(symbols: List[str], content: str) -> List[str]:
    usages = []
    for sym in symbols:
        if not re.match(r'^[A-Za-z0-9_]+$', sym):
            continue
            
        if re.search(rf"\bnew\s+{sym}\b", content):
            usages.append(f"instantiated({sym})")
        elif re.search(rf"\b{sym}\s*\(", content):
            if re.search(rf"@{sym}\b", content):
                usages.append(f"decorator({sym})")
            else:
                usages.append(f"called({sym})")
        elif re.search(rf":\s*{sym}\b", content) or re.search(rf":\s*Promise<{sym}>", content) or re.search(rf":\s*Observable<{sym}>", content) or re.search(rf"<{sym}>", content):
            usages.append(f"typed({sym})")
        elif re.search(rf"<{sym}\b", content):
            usages.append(f"jsx_component({sym})")
        elif re.search(rf"\bextends\s+{sym}\b|\bimplements\s+{sym}\b", content):
            usages.append(f"inherited({sym})")
        elif re.search(rf"\b{sym}\.", content):
            usages.append(f"namespace_access({sym})")
            
    return list(set(usages))

def parse_imports_with_nature(content: str) -> List[Dict[str, Any]]:
    clean_content = _strip_comments(content)
    results: List[Dict[str, str]] = []

    for match in IMPORT_STATEMENT_REGEX.finditer(clean_content):
        raw_path = match.group("path")
        stmt = match.group("stmt") or ""
        nature = classify_import_nature(stmt)
        
        symbols = _extract_imported_symbols(stmt)
        usages = _find_semantic_usages(symbols, clean_content)
        
        results.append(
            {
                "raw_import": raw_path,
                "import_nature": nature,
                "statement": stmt,
                "symbols": symbols,
                "semantic_usages": usages,
            }
        )

    return results

ENTRYPOINT_RULES = [
    (re.compile(r"^main\.server\.(ts|js)$"), "ssr_bootstrap", 0.95),
    (re.compile(r"^main\.(ts|js)$"), "browser_bootstrap", 0.95),
    (re.compile(r"^server\.(ts|js)$"), "server_http", 0.90),
    (re.compile(r"^entry\.server\.(ts|js)$"), "ssr_bootstrap", 0.90),
    (re.compile(r"^entry\.client\.(ts|js)$"), "browser_bootstrap", 0.90),
    (re.compile(r"^bootstrap\.(ts|js)$"), "app_bootstrap", 0.80),
]

TEST_FILE_REGEX = re.compile(
    r"\.(spec|test)\.(ts|tsx|js|jsx)$"
)

INTERFACE_REGEX = re.compile(
    r"(?:export\s+)?interface\s+(\w+)[^{]*\{([^}]*)\}",
    re.DOTALL
)

TYPE_ALIAS_REGEX = re.compile(
    r"(?:export\s+)?type\s+(\w+)\s*=\s*\{([^}]*)\}",
    re.DOTALL
)


def _normalize_path(value: str) -> str:
    normalized = os.path.normpath(value).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _is_source_file(filename: str) -> bool:
    return filename.endswith(SOURCE_EXTENSIONS) and not filename.endswith(".d.ts")


def _is_test_file(filename: str) -> bool:
    return bool(TEST_FILE_REGEX.search(filename))


def _strip_comments(content: str) -> str:
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"/\*[\s\S]*?\*/", "", content)
    return content


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return None


def graph_content_signature(shared_graph: Dict[str, Any]) -> str:
    """Hash the stable semantic graph, excluding timestamp and cache metrics."""
    semantic_graph = {}
    for key, value in shared_graph.items():
        if key in ("scan_timestamp", "cache"):
            continue
        if isinstance(value, dict):
            semantic_graph[key] = {
                (f"{k[0]} -> {k[1]}" if isinstance(k, tuple) else str(k)): v
                for k, v in value.items()
            }
        else:
            semantic_graph[key] = value

    encoded = json.dumps(
        semantic_graph,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(encoded)
    return f"sha256:{digest.hexdigest()}"


def _detect_entrypoint(filename: str) -> Tuple[bool, str, float]:
    base = os.path.basename(filename)
    for pattern, kind, confidence in ENTRYPOINT_RULES:
        if pattern.match(base):
            return True, kind, confidence
    return False, "none", 0.0


def _classify_node(file_path: str, content: str) -> str:
    lower_path = file_path.lower()
    if ".service." in lower_path or "@Injectable" in content:
        return "Service"
    if ".component." in lower_path or "@Component" in content:
        return "Component"
    if ".module." in lower_path or ".routes." in lower_path:
        return "Module"
    if "util" in lower_path or "helper" in lower_path:
        return "Helper"
    return "Other"


def _resolve_import_path(base_file: str, import_path: str) -> str:
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
    return "/".join(parts)


def _candidate_targets(resolved_base: str) -> List[str]:
    candidates: List[str] = []
    seen: Set[str] = set()

    def add(c: str) -> None:
        if c and c not in seen:
            seen.add(c)
            candidates.append(c)

    add(resolved_base)
    if not any(resolved_base.endswith(ext) for ext in RESOLUTION_EXTENSIONS):
        for ext in RESOLUTION_EXTENSIONS:
            add(resolved_base + ext)
        for ext in RESOLUTION_EXTENSIONS:
            add(f"{resolved_base}/index{ext}")
    return candidates


def _strip_jsonc_comments(text: str) -> str:
    """Menghapus komentar JSONC sederhana dan trailing comma."""
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



def _find_matching_brace(content: str, start_idx: int) -> int:
    """
    Menemukan indeks '}' penutup yang cocok untuk '{' pada start_idx.
    Memperhatikan string literal ('...', "...", `...`) dan escape sequence.
    Mengembalikan -1 jika kurung kurawal tidak seimbang.
    """
    depth = 0
    in_quote: Optional[str] = None
    escaped = False
    n = len(content)

    for idx in range(start_idx, n):
        c = content[idx]
        if in_quote:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == in_quote:
                in_quote = None
            continue

        if c in ('"', "'", "`"):
            in_quote = c
            escaped = False
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return idx

    return -1


def _parse_body_props(body_str: str) -> Set[str]:
    """
    Mengekstrak nama properti dari body type/interface menggunakan
    brace-matching counter untuk mendukung tipe bertingkat (nested types).
    Menghasilkan properti tingkat atas serta jalur nested (e.g. 'user', 'user.profile.id').
    """
    props: Set[str] = set()
    bi = 0
    bn = len(body_str)
    path: List[str] = []
    current_token: List[str] = []
    in_quote: Optional[str] = None
    escaped = False
    paren_depth = 0
    angle_depth = 0

    def _flush_stmt():
        nonlocal current_token
        stmt = "".join(current_token).strip()
        current_token = []
        if stmt:
            m = re.match(r"^(?:readonly\s+)?([A-Za-z0-9_$]+)\s*\??\s*[:(]", stmt)
            if m:
                pname = m.group(1)
                if pname not in ("get", "set", "new", "type", "interface", "export", "default"):
                    if path:
                        non_anon = [p for p in path if p != "_anon"]
                        if non_anon:
                            dot_prefix = ".".join(non_anon)
                            props.add(f"{dot_prefix}.{pname}")
                        else:
                            props.add(pname)
                    else:
                        props.add(pname)

    while bi < bn:
        char = body_str[bi]
        if in_quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_quote:
                in_quote = None
            bi += 1
            continue

        if char in ('"', "'", "`"):
            in_quote = char
            escaped = False
            bi += 1
            continue

        if char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth = max(0, paren_depth - 1)
        elif char == "<":
            angle_depth += 1
        elif char == ">":
            angle_depth = max(0, angle_depth - 1)

        # Menangani kurung kurawal pembuka bersarang (nested object property)
        if char == "{" and paren_depth == 0:
            prefix = "".join(current_token).strip()
            current_token = []
            prop_name: Optional[str] = None
            m = re.search(r"(?:readonly\s+)?([A-Za-z0-9_$]+)\s*\??\s*:\s*$", prefix)
            if m:
                prop_name = m.group(1)
            elif prefix:
                m2 = re.search(r"([A-Za-z0-9_$]+)\s*$", prefix)
                if m2:
                    prop_name = m2.group(1)

            if prop_name and prop_name not in ("get", "set", "new", "type", "interface", "export", "default"):
                path.append(prop_name)
                full = ".".join(path)
                props.add(full)
            else:
                path.append("_anon")
            bi += 1
            continue
        elif char == "}":
            _flush_stmt()
            if path:
                path.pop()
            bi += 1
            continue

        if (char in (";", "\n", ",") or bi == bn - 1) and paren_depth == 0 and angle_depth == 0:
            if bi == bn - 1 and char not in (";", "\n", ","):
                current_token.append(char)
            _flush_stmt()
            bi += 1
            continue

        current_token.append(char)
        bi += 1

    return props


def _extract_type_shapes(
    content: str,
    known_shapes: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, Set[str]]:
    """
    Ekstrak nama type/interface dan himpunan property names dengan AST & shape rigor:
    - Menangani kurung kurawal bersarang (brace-matching counter) untuk nested types
    - Menangani generic types (interface ApiResponse<T>)
    - Menangani union/intersection types (type AdminUser = User & { role: 'admin' })
    - Menangani utility types (Partial<T>, Readonly<T>, Pick<T, ...>, Omit<T, ...>)
    - Menangani pewarisan interface (interface A extends B)
    """
    clean = _strip_comments(content)
    n = len(clean)
    raw_shapes: Dict[str, Set[str]] = {}
    inheritance: Dict[str, List[str]] = {}

    # 1. Scan interfaces
    interface_pattern = re.compile(
        r"(?:export\s+)?(?:default\s+)?interface\s+([A-Za-z0-9_$]+)"
    )
    for match in interface_pattern.finditer(clean):
        name = match.group(1)
        cursor = match.end()
        angle_d = 0
        open_brace = -1
        header_chars: List[str] = []

        while cursor < n:
            c = clean[cursor]
            if c == "<":
                angle_d += 1
            elif c == ">":
                angle_d = max(0, angle_d - 1)
            elif c == "{" and angle_d == 0:
                open_brace = cursor
                break
            else:
                header_chars.append(c)
            cursor += 1

        if open_brace != -1:
            close_brace = _find_matching_brace(clean, open_brace)
            if close_brace != -1:
                body = clean[open_brace + 1:close_brace]
                props = _parse_body_props(body)
                raw_shapes[name] = props

                header_str = "".join(header_chars)
                ext_match = re.search(r"\bextends\s+([^{]+)", header_str)
                if ext_match:
                    parents = [
                        p.strip().split("<")[0].strip()
                        for p in ext_match.group(1).split(",")
                        if p.strip()
                    ]
                    inheritance[name] = parents

    # 2. Scan type aliases
    type_pattern = re.compile(
        r"(?:export\s+)?(?:default\s+)?type\s+([A-Za-z0-9_$]+)(?:<[^>]*>)?\s*="
    )
    for match in type_pattern.finditer(clean):
        name = match.group(1)
        rhs_start = match.end()

        cursor = rhs_start
        angle_d = 0
        paren_d = 0
        brace_d = 0
        end_idx = n
        while cursor < n:
            c = clean[cursor]
            if c == "<":
                angle_d += 1
            elif c == ">":
                angle_d = max(0, angle_d - 1)
            elif c == "(":
                paren_d += 1
            elif c == ")":
                paren_d = max(0, paren_d - 1)
            elif c == "{":
                brace_d += 1
            elif c == "}":
                brace_d = max(0, brace_d - 1)
            elif c == ";" and angle_d == 0 and paren_d == 0 and brace_d == 0:
                end_idx = cursor
                break
            cursor += 1

        rhs = clean[rhs_start:end_idx]
        props: Set[str] = set()
        parents: List[str] = []

        rc = 0
        rn = len(rhs)
        while rc < rn:
            if rhs[rc] == "{":
                g_close = _find_matching_brace(clean, rhs_start + rc)
                if g_close != -1:
                    body = clean[rhs_start + rc + 1:g_close]
                    props.update(_parse_body_props(body))
                    rc = (g_close - rhs_start) + 1
                    continue
            rc += 1

        # Utility types: Partial<User>, Readonly<User>, Required<User>, Pick<User, ...>, Omit<User, ...>
        util_match = re.finditer(
            r"\b(?:Partial|Readonly|Required|Pick|Omit)\s*<\s*([A-Za-z0-9_$]+)",
            rhs
        )
        for um in util_match:
            parents.append(um.group(1))

        # Referensi type langsung: type AdminUser = User & { ... } atau type Alias = User
        ref_match = re.finditer(
            r"(?:^|&|\||=)\s*([A-Za-z0-9_$]+)\s*(?:&|\||;|$)",
            rhs
        )
        ts_primitives = {
            "true", "false", "null", "undefined", "any", "unknown", "never",
            "string", "number", "boolean", "object", "symbol", "bigint", "void"
        }
        for rm in ref_match:
            ref_name = rm.group(1).strip()
            if ref_name and ref_name not in ts_primitives:
                parents.append(ref_name)

        raw_shapes[name] = props
        if parents:
            inheritance[name] = parents

    # 3. Propagasi inheritance dan utility types
    shapes = {k: set(v) for k, v in raw_shapes.items()}
    for _ in range(5):
        changed = False
        for child, parent_list in inheritance.items():
            if child in shapes:
                for parent in parent_list:
                    if parent in shapes:
                        before_len = len(shapes[child])
                        shapes[child].update(shapes[parent])
                        if len(shapes[child]) != before_len:
                            changed = True
                    elif known_shapes and parent in known_shapes:
                        before_len = len(shapes[child])
                        shapes[child].update(known_shapes[parent])
                        if len(shapes[child]) != before_len:
                            changed = True
        if not changed:
            break

    return shapes


def _detect_boundaries(
    all_files: List[str],
    scan_root: str,
) -> Tuple[Dict[str, Dict], Dict[str, str]]:
    """
    Deteksi module boundaries.
    Boundary = folder dengan barrel file, atau top-level folder.
    """
    scan_root_norm = _normalize_path(scan_root)

    # Identifikasi folder dengan barrel
    barrel_folders: Dict[str, str] = {}
    for fp in all_files:
        dirname = os.path.dirname(fp)
        basename = os.path.basename(fp)
        if basename in BARREL_FILENAMES:
            barrel_folders[dirname] = fp

    # Assign setiap file ke boundary
    boundaries: Dict[str, Dict] = {}
    file_to_boundary: Dict[str, str] = {}

    for fp in all_files:
        current = os.path.dirname(fp)
        assigned = None

        while current and current.startswith(scan_root_norm):
            if current in barrel_folders:
                assigned = current
                break
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent

        if assigned is None:
            rel = os.path.relpath(fp, scan_root_norm)
            top_folder = rel.split("/")[0] if "/" in rel else ""
            if top_folder:
                assigned = _normalize_path(os.path.join(scan_root_norm, top_folder))
            else:
                assigned = scan_root_norm

        if assigned not in boundaries:
            boundaries[assigned] = {
                "barrel": barrel_folders.get(assigned),
                "files": [],
            }

        boundaries[assigned]["files"].append(fp)
        file_to_boundary[fp] = assigned

    return boundaries, file_to_boundary


def discover_source_files(
    scan_root: str = ".",
    ignore_dirs: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Discover supported source files and cheap stat fingerprints once."""
    ignored = set(DEFAULT_IGNORE_DIRS if ignore_dirs is None else ignore_dirs)
    discovered: Dict[str, Dict[str, int]] = {}
    for root, dirs, files in os.walk(scan_root):
        dirs[:] = sorted(
            [
                directory
                for directory in dirs
                if directory not in ignored and not directory.startswith(".")
            ]
        )
        for filename in sorted(files):
            if not _is_source_file(filename):
                continue
            full_path = _normalize_path(os.path.join(root, filename))
            try:
                stat = os.stat(full_path)
            except OSError:
                continue
            discovered[full_path] = {
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
                "ctime_ns": int(stat.st_ctime_ns),
            }
    return dict(sorted(discovered.items()))


def build_shared_graph(
    scan_root: str = ".",
    ignore_dirs: Optional[Set[str]] = None,
    _file_snapshot: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Bangun SharedGraph dari satu discovery pass atau snapshot tervalidasi.

    Discovery filesystem tetap terpusat di modul ini. Semua analyzer
    mengonsumsi output fungsi ini dan tidak melakukan scan sendiri.
    """
    if ignore_dirs is None:
        ignore_dirs = set(DEFAULT_IGNORE_DIRS)

    scan_root_norm = _normalize_path(scan_root)
    alias_rules = _load_alias_rules([scan_root_norm, "."])

    # ============================================================
    # PASS 1: Filesystem scan + file reading + import parsing
    # ============================================================
    all_files: List[str] = []
    file_map: Dict[str, str] = {}           # path -> content
    file_imports: Dict[str, List[Dict[str, str]]] = {}  # path -> list of import dicts

    if _file_snapshot is None:
        for full_path in discover_source_files(scan_root, ignore_dirs):
            content = _read_file(full_path)
            if content is None:
                continue

            all_files.append(full_path)
            file_map[full_path] = content
            file_imports[full_path] = parse_imports_with_nature(content)
    else:
        for full_path in sorted(_file_snapshot):
            record = _file_snapshot[full_path]
            content = record.get("content")
            imports = record.get("imports")
            if not isinstance(content, str) or not isinstance(imports, list):
                continue
            all_files.append(full_path)
            file_map[full_path] = content
            if content:
                file_imports[full_path] = parse_imports_with_nature(content)
            else:
                file_imports[full_path] = [
                    {"raw_import": str(value), "import_nature": "runtime"}
                    for value in imports
                ]

    # ============================================================
    # PASS 2: Node metadata extraction
    # ============================================================
    node_metadata: Dict[str, Dict[str, Any]] = {}

    for fp in all_files:
        content = file_map[fp]
        filename = os.path.basename(fp)

        is_entrypoint, ep_kind, ep_conf = _detect_entrypoint(filename)
        is_test = _is_test_file(filename)
        node_type = _classify_node(fp, content)

        node_metadata[fp] = {
            "type": node_type,
            "is_entrypoint": is_entrypoint,
            "entrypoint_kind": ep_kind,
            "entrypoint_confidence": ep_conf,
            "is_test": is_test,
        }

    # ============================================================
    # PASS 3: Import resolution + graph construction
    # ============================================================
    all_files_set = set(all_files)
    edges: List[Tuple[str, str]] = []
    resolved_imports: Dict[str, List[str]] = {}
    unresolved_imports: List[Dict[str, Any]] = []
    external_imports: List[Dict[str, Any]] = []
    resolved_edge_natures: Dict[Tuple[str, str], List[str]] = {}
    resolved_edge_usages: Dict[Tuple[str, str], List[str]] = {}

    for fp in all_files:
        resolved_targets: List[str] = []

        for item in file_imports.get(fp, []):
            raw_import = item["raw_import"]
            nature = item.get("import_nature", "runtime")
            usages = item.get("semantic_usages", [])

            if raw_import.startswith("."):
                resolved_base = _resolve_import_path(fp, raw_import)
                candidates = _candidate_targets(resolved_base)
                matched = None

                for cand in candidates:
                    if cand in all_files_set:
                        matched = cand
                        break

                if matched:
                    edges.append((fp, matched))
                    resolved_edge_natures.setdefault((fp, matched), []).append(nature)
                    resolved_edge_usages.setdefault((fp, matched), []).extend(usages)
                    resolved_targets.append(matched)
                else:
                    unresolved_imports.append({
                        "importer": fp,
                        "raw_import": raw_import,
                        "attempted_candidates": candidates,
                    })
            else:
                alias_bases = _alias_candidates(raw_import, alias_rules) if alias_rules else []
                if not alias_bases:
                    external_imports.append({
                        "importer": fp,
                        "raw_import": raw_import,
                    })
                    continue

                attempted_candidates: List[str] = []
                matched = None

                for alias_base in alias_bases:
                    candidates = _candidate_targets(alias_base)
                    attempted_candidates.extend(candidates)

                    for cand in candidates:
                        if cand in all_files_set:
                            matched = cand
                            break

                    if matched:
                        break

                if matched:
                    edges.append((fp, matched))
                    resolved_edge_natures.setdefault((fp, matched), []).append(nature)
                    resolved_edge_usages.setdefault((fp, matched), []).extend(usages)
                    resolved_targets.append(matched)
                else:
                    unresolved_imports.append({
                        "importer": fp,
                        "raw_import": raw_import,
                        "reason": "alias_candidate_not_found",
                        "attempted_candidates": attempted_candidates,
                    })

        resolved_imports[fp] = resolved_targets

    # Deduplicate edges
    edges = sorted(set(edges))

    edge_natures: Dict[str, str] = {}
    for edge in edges:
        u, v = edge
        natures = resolved_edge_natures.get(edge, [])
        nature = "runtime" if "runtime" in natures else ("type_only" if natures else "runtime")
        edge_natures[f"{u} -> {v}"] = nature

    edge_details = [
        {
            "source": u, 
            "target": v, 
            "import_nature": edge_natures.get(f"{u} -> {v}", "runtime"),
            "semantic_usages": list(set(resolved_edge_usages.get((u, v), [])))
        }
        for u, v in edges
    ]

    # ============================================================
    # PASS 4: Fan in/out calculation
    # ============================================================
    fan_in: Dict[str, int] = {}
    fan_out: Dict[str, int] = {}

    for src, tgt in edges:
        fan_out[src] = fan_out.get(src, 0) + 1
        fan_in[tgt] = fan_in.get(tgt, 0) + 1

    for fp in all_files:
        node_metadata[fp]["fan_in"] = fan_in.get(fp, 0)
        node_metadata[fp]["fan_out"] = fan_out.get(fp, 0)

    # ============================================================
    # PASS 5: Boundary detection
    # ============================================================
    boundaries, file_to_boundary = _detect_boundaries(all_files, scan_root)

    # ============================================================
    # PASS 6: Type shape extraction
    # ============================================================
    type_shapes: Dict[str, Dict[str, List[str]]] = {}
    known_global_shapes: Dict[str, Set[str]] = {}

    for fp in all_files:
        content = file_map[fp]
        shapes = _extract_type_shapes(content)
        if shapes:
            for sname, sprops in shapes.items():
                if sname not in known_global_shapes:
                    known_global_shapes[sname] = set(sprops)
                else:
                    known_global_shapes[sname].update(sprops)

    for fp in all_files:
        content = file_map[fp]
        shapes = _extract_type_shapes(content, known_shapes=known_global_shapes)
        if shapes:
            type_shapes[fp] = {
                name: sorted(props) for name, props in shapes.items()
            }

    # ============================================================
    # Assemble SharedGraph
    # ============================================================
    return {
        "schema_version": SCHEMA_VERSION,
        "scan_root": scan_root_norm,
        "scan_timestamp": (
            datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        ),

        # Core topology
        "vertices": sorted(all_files),
        "edges": edges,
        "edge_natures": edge_natures,
        "edge_details": edge_details,
        "file_map": file_map,
        "node_metadata": node_metadata,

        # Import resolution
        "resolved_imports": resolved_imports,
        "unresolved_imports": unresolved_imports,
        "external_imports": external_imports,

        # Boundaries
        "boundaries": boundaries,
        "file_to_boundary": file_to_boundary,

        # Type shapes
        "type_shapes": type_shapes,

        # Summary
        "summary": {
            "total_files": len(all_files),
            "total_edges": len(edges),
            "runtime_edge_count": sum(1 for (u, v) in edges if edge_natures.get(f"{u} -> {v}", "runtime") == "runtime"),
            "type_only_edge_count": sum(1 for (u, v) in edges if edge_natures.get(f"{u} -> {v}", "runtime") == "type_only"),
            "total_boundaries": len(boundaries),
            "total_type_shapes": sum(len(v) for v in type_shapes.values()),
            "total_unresolved": len(unresolved_imports),
            "total_external": len(external_imports),
            "alias_rules_count": len(alias_rules),
            "entrypoint_count": sum(
                1 for m in node_metadata.values() if m.get("is_entrypoint")
            ),
            "test_file_count": sum(
                1 for m in node_metadata.values() if m.get("is_test")
            ),
        },
    }


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    graph = build_shared_graph(root)
    # Jangan print file_map (terlalu besar), hapus untuk output
    output = {k: v for k, v in graph.items() if k != "file_map"}
    print(json.dumps(output, indent=2))
