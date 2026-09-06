"""
Memory Kan Extension — HoTT Kernel
Schema Version: 4.1.0-memory

Implementasi Kan Extension dari hott2.txt:
- Left Kan Extension (Lan): Bottom-up completion
  Diberikan fragmen, bangun memori spesifik yang konsisten
- Right Kan Extension (Ran): Top-down completion  
  Diberikan fragmen, bangun generalisasi yang mencakup fragmen

Perbedaan dengan recall_memories biasa:
- recall: FILTER (cari yang match query)
- Kan Extension: COMPLETE (lengkapi fragmen dengan konteks relasional)
"""

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple


def left_kan_extension(
    query_fragment: str,
    max_depth: int = 2,
    max_entry_points: int = 3,
    max_related_per_entry: int = 10,
    include_edge_types: bool = True,
) -> Dict[str, Any]:
    """
    Left Kan Extension (Lan): Bottom-up structured completion.
    
    Diberikan fragmen query, temukan entry points dan lengkapi
    dengan mengikuti asosiasi di memory graph.
    
    Ini adalah "recall sebagai path navigation" dari hott2.txt:
    "Alih-alih mencari titik terdekat di ruang metrik, proses mengingat
    dalam HoTT adalah mencari jalur (path) dari kondisi kognitif saat ini
    ke target memori."
    
    Args:
        query_fragment: Fragmen query untuk dicari
        max_depth: Maximum depth untuk BFS mengikuti asosiasi
        max_entry_points: Maximum entry points yang diproses
        max_related_per_entry: Maximum related memories per entry
        include_edge_types: Sertakan tipe edge di output
    
    Returns:
        Dict dengan completed memories dan relational context
    """
    try:
        from memory.store import recall_memories, load_store
        from memory.graph import build_memory_graph
    except ImportError:
        try:
            from memory_store import recall_memories, load_store
            from memory_graph import build_memory_graph
        except ImportError as exc:
            return {"error": f"Import failed: {exc}"}
    
    store = load_store()
    memory_map = {m["id"]: m for m in store.get("memories", [])}
    
    # Build graph untuk traversal
    memory_graph = build_memory_graph(include_archived=False)
    adjacency = memory_graph.get("adjacency", {})
    edge_types = memory_graph.get("edge_types", {})
    
    # Step 1: Cari entry points (memori yang match fragmen)
    entry_memories = recall_memories(
        query=query_fragment,
        limit=max_entry_points,
        include_archived=False,
    )
    
    if not entry_memories:
        return {
            "status": "no_match",
            "kan_type": "left",
            "query_fragment": query_fragment,
            "message": "No memories match the query fragment",
        }
    
    # Step 2: Untuk setiap entry, BFS mengikuti asosiasi
    completed = []
    total_related = 0
    
    for entry in entry_memories[:max_entry_points]:
        entry_id = entry["id"]
        
        # BFS dari entry point
        visited: Set[str] = {entry_id}
        frontier: List[str] = [entry_id]
        related_memories: List[Dict[str, Any]] = []
        paths_found: List[Dict[str, Any]] = []
        
        for depth in range(max_depth):
            next_frontier: List[str] = []
            for mid in frontier:
                for neighbor in adjacency.get(mid, []):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
                    
                    neighbor_mem = memory_map.get(neighbor)
                    if neighbor_mem and len(related_memories) < max_related_per_entry:
                        # Tentukan edge type
                        edge_type = "unknown"
                        if include_edge_types:
                            edge_type = edge_types.get((mid, neighbor), "unknown")
                            if edge_type == "unknown":
                                edge_type = edge_types.get((neighbor, mid), "unknown")
                        
                        related_memories.append({
                            "id": neighbor,
                            "type": neighbor_mem.get("type"),
                            "content_preview": neighbor_mem.get("content", "")[:120],
                            "importance": neighbor_mem.get("importance", 0),
                            "connected_via": edge_type,
                            "depth": depth + 1,
                            "from_memory": mid,
                        })
                        
                        paths_found.append({
                            "from": entry_id,
                            "to": neighbor,
                            "via": mid if depth > 0 else entry_id,
                            "edge_type": edge_type,
                            "depth": depth + 1,
                        })
            
            frontier = next_frontier
            if not frontier:
                break
        
        completed.append({
            "entry_memory": {
                "id": entry_id,
                "type": entry.get("type"),
                "content_preview": entry.get("content", "")[:150],
                "importance": entry.get("importance", 0),
                "tags": entry.get("tags", []),
            },
            "related_memories": related_memories,
            "paths_found": paths_found,
            "related_count": len(related_memories),
        })
        total_related += len(related_memories)
    
    return {
        "status": "completed",
        "kan_type": "left",
        "query_fragment": query_fragment,
        "entry_points_found": len(entry_memories),
        "completed_memories": completed,
        "total_related_found": total_related,
        "max_depth_used": max_depth,
        "interpretation": (
            f"Left Kan Extension: query '{query_fragment}' completed with "
            f"{total_related} related memories across {len(entry_memories)} entry points. "
            f"Relational context preserved via {max_depth}-depth traversal."
        ),
    }


def right_kan_extension(
    query_fragment: str,
    max_specific: int = 5,
    max_siblings: int = 5,
) -> Dict[str, Any]:
    """
    Right Kan Extension (Ran): Top-down structured completion.
    
    Diberikan fragmen spesifik, temukan generalisasi yang mencakupnya.
    Ini mengikuti relasi consolidated_into untuk menemukan pola yang lebih luas.
    
    Dari hott2.txt:
    "Right Kan Extension (Ran): Membangun generalisasi memori yang masih
    mencakup fragmen tersebut (pendekatan dari atas)."
    
    Args:
        query_fragment: Fragmen query untuk dicari
        max_specific: Maximum memori spesifik yang diproses
        max_siblings: Maximum sibling examples per generalisasi
    
    Returns:
        Dict dengan generalisasi dan sibling examples
    """
    try:
        from memory.store import recall_memories, load_store
    except ImportError:
        try:
            from memory_store import recall_memories, load_store
        except ImportError as exc:
            return {"error": f"Import failed: {exc}"}
    
    store = load_store()
    memory_map = {m["id"]: m for m in store.get("memories", [])}
    
    # Step 1: Cari memori spesifik yang match
    specific_memories = recall_memories(
        query=query_fragment,
        limit=max_specific,
        include_archived=True,  # Include archived untuk menemukan yang sudah consolidated
    )
    
    if not specific_memories:
        return {
            "status": "no_match",
            "kan_type": "right",
            "query_fragment": query_fragment,
            "message": "No memories match the query fragment",
        }
    
    # Step 2: Untuk setiap memori spesifik, cari generalisasinya
    generalizations: List[Dict[str, Any]] = []
    generalized_count = 0
    
    for mem in specific_memories[:max_specific]:
        consolidated_into = mem.get("consolidated_into")
        
        if consolidated_into and consolidated_into in memory_map:
            # Memori sudah di-consolidate → ambil generalisasinya
            general_mem = memory_map[consolidated_into]
            
            # Cari siblings (memori lain yang juga consolidated ke semantic yang sama)
            siblings = [
                m for m in store.get("memories", [])
                if m.get("consolidated_into") == consolidated_into
                and m["id"] != mem["id"]
                and m.get("status", "active") != "archived"
            ]
            
            generalizations.append({
                "specific_memory": {
                    "id": mem["id"],
                    "type": mem.get("type"),
                    "content_preview": mem.get("content", "")[:120],
                },
                "generalization": {
                    "id": consolidated_into,
                    "type": general_mem.get("type"),
                    "content_preview": general_mem.get("content", "")[:200],
                    "importance": general_mem.get("importance", 0),
                    "tags": general_mem.get("tags", []),
                },
                "sibling_examples": [
                    {
                        "id": s["id"],
                        "content_preview": s.get("content", "")[:80],
                    }
                    for s in siblings[:max_siblings]
                ],
                "sibling_count": len(siblings),
            })
            generalized_count += 1
        
        else:
            # Memori belum di-consolidate → tandai sebagai candidate
            generalizations.append({
                "specific_memory": {
                    "id": mem["id"],
                    "type": mem.get("type"),
                    "content_preview": mem.get("content", "")[:120],
                },
                "generalization": None,
                "note": "Not yet consolidated. Consider running memory consolidate.",
            })
    
    return {
        "status": "completed",
        "kan_type": "right",
        "query_fragment": query_fragment,
        "specific_memories_found": len(specific_memories),
        "generalizations": generalizations,
        "generalized_count": generalized_count,
        "not_yet_consolidated": len(specific_memories) - generalized_count,
        "interpretation": (
            f"Right Kan Extension: query '{query_fragment}' mapped to "
            f"{generalized_count} generalization(s). "
            f"{len(specific_memories) - generalized_count} memories not yet consolidated."
        ),
    }


def kan_retrieve(
    query_fragment: str,
    mode: str = "both",
    max_depth: int = 2,
    shared_graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Unified Kan Extension retrieval.
    
    Args:
        query_fragment: Fragmen query atau path file modul
        mode: "lan" (left only), "ran" (right only), "both", "impute" (new module relations)
        max_depth: Max depth untuk Lan traversal
        shared_graph: Optional SharedGraph instance
    
    Returns:
        Dict dengan hasil Lan, Ran, atau Impute
    """
    if mode == "impute":
        return impute_module_relations(query_fragment, shared_graph=shared_graph)

    result: Dict[str, Any] = {
        "status": "completed",
        "query_fragment": query_fragment,
        "mode": mode,
    }
    
    if mode in ("lan", "both"):
        result["left_kan_extension"] = left_kan_extension(
            query_fragment, max_depth=max_depth
        )
    
    if mode in ("ran", "both"):
        result["right_kan_extension"] = right_kan_extension(query_fragment)
    
    # Synthesize interpretation
    lan_result = result.get("left_kan_extension", {})
    ran_result = result.get("right_kan_extension", {})
    
    lan_related = lan_result.get("total_related_found", 0)
    ran_generalized = ran_result.get("generalized_count", 0)
    
    result["synthesis"] = {
        "specific_context_found": lan_related,
        "generalizations_found": ran_generalized,
        "recommendation": (
            "Use Left Kan results for detailed relational context. "
            "Use Right Kan results for high-level patterns and generalizations."
            if mode == "both"
            else f"Retrieved via {mode.upper()} only."
        ),
    }
    
    return result


# ============================================================================
# KAN EXTENSION MODULE IMPUTATION (Zero-Context / New Module Bridge)
# ============================================================================

ROLE_PATTERNS = [
    (r"\.service\.[jt]sx?$", "service"),
    (r"\.controller\.[jt]sx?$", "controller"),
    (r"\.component\.[jt]sx?$", "component"),
    (r"\.directive\.[jt]sx?$", "directive"),
    (r"\.pipe\.[jt]sx?$", "pipe"),
    (r"\.guard\.[jt]sx?$", "guard"),
    (r"\.interceptor\.[jt]sx?$", "interceptor"),
    (r"\.resolver\.[jt]sx?$", "resolver"),
    (r"\.(?:repository|repo)\.[jt]sx?$", "repository"),
    (r"\.(?:model|models|types|interface|interfaces|schema)\.[jt]sx?$", "model"),
    (r"\.(?:spec|test)\.[jt]sx?$", "test"),
    (r"\.(?:util|utils|helper|helpers)\.[jt]sx?$", "utility"),
    (r"\.(?:routes|routing)\.[jt]sx?$", "routes"),
    (r"\.module\.[jt]sx?$", "module"),
    (r"\.store\.[jt]sx?$", "store"),
    (r"\.facade\.[jt]sx?$", "facade"),
    (r"\.adapter\.[jt]sx?$", "adapter"),
]

DIR_ROLE_PATTERNS = [
    (r"/(?:services|service)/", "service"),
    (r"/(?:controllers|controller)/", "controller"),
    (r"/(?:components|component)/", "component"),
    (r"/(?:models|model|types|schemas)/", "model"),
    (r"/(?:repositories|repository|repo)/", "repository"),
    (r"/(?:pipes|pipe)/", "pipe"),
    (r"/(?:guards|guard)/", "guard"),
    (r"/(?:utils|util|helpers|helper)/", "utility"),
    (r"/(?:stores|store)/", "store"),
]

ROLE_ARCHITECTURAL_CONVENTIONS: Dict[str, Dict[str, Any]] = {
    "service": {
        "conventions": [
            "Deklarasikan decorator @Injectable({ providedIn: 'root' }) untuk tree-shakable singleton.",
            "Gunakan inject(...) ketimbang constructor parameter injection.",
            "Kelola reactive state melalui Angular Signals (signal, computed) secara deterministik.",
            "Hindari manipulasi langsung DOM atau objek window/document.",
        ],
        "patterns": [
            "Service-Repository segregation pattern",
            "Signal-based reactive state management",
            "Type-only domain interface elision",
        ],
        "guided_hints": [
            "Terapkan dependency injection bersih via inject(HttpClient) atau inject(Repository).",
            "Sediakan companion spec file *.service.spec.ts untuk menjamin test reachability.",
            "Import domain models via 'import type' untuk menjaga graph runtime tetap asiklik.",
        ],
    },
    "component": {
        "conventions": [
            "Gunakan standalone component (default Angular 20+; jangan deklarasikan standalone: true).",
            "Gunakan ChangeDetectionStrategy.OnPush untuk performa rendering optimal.",
            "Gunakan signal-based input() dan output() APIs.",
            "Gunakan native control flow (@if, @for, @switch), hindari *ngIf/*ngFor legacy.",
            "Wajib Reactive Forms (FormGroup, FormControl); dilarang keras ngModel / FormsModule.",
        ],
        "patterns": [
            "Container / Presentational component pattern",
            "Fine-grained signal reactivity",
        ],
        "guided_hints": [
            "Gunakan <mat-icon> untuk ikonografi dan utility classes Tailwind CSS.",
            "Pastikan template bersih tanpa business logic; delegasikan ke service atau computed signals.",
        ],
    },
    "model": {
        "conventions": [
            "Definisikan pure TypeScript interface / type tanpa runtime side-effects.",
            "Gunakan export interface atau export type.",
            "Konsumen harus mengimpor dengan 'import type' agar di-elide saat bundling.",
        ],
        "patterns": [
            "Immutable Domain Model / Value Object pattern",
            "Type-level boundary specification",
        ],
        "guided_hints": [
            "Ekspor interface yang kohesif; pisahkan read models dari command/write payloads bila kompleks.",
        ],
    },
    "controller": {
        "conventions": [
            "Validasi request payload di boundary sebelum masuk domain service.",
            "Delegasikan seluruh business rules ke domain service.",
        ],
        "patterns": [
            "Request-Response boundary mediation",
            "Controller-Service delegation",
        ],
        "guided_hints": [
            "Hindari logic database atau transformasi berat di controller; delegasikan ke service.",
        ],
    },
    "repository": {
        "conventions": [
            "Enkapsulasi seluruh akses data eksternal, HTTP, atau database.",
            "Kembalikan strongly-typed models atau Observables/Promises.",
        ],
        "patterns": [
            "Repository data abstraction pattern",
        ],
        "guided_hints": [
            "Pertahankan cache key deterministik dan tangani error boundary secara konsisten.",
        ],
    },
    "utility": {
        "conventions": [
            "Fungsi harus pure dan deterministic tanpa side-effects tak terduga.",
            "Sertakan unit tests komprehensif untuk boundary cases.",
        ],
        "patterns": [
            "Pure functional transformation",
        ],
        "guided_hints": [
            "Hindari state internal tersembunyi; ekspor fungsi-fungsi independen yang composable.",
        ],
    },
}

DEFAULT_MODULE_CONVENTIONS = {
    "conventions": [
        "Jaga batas modul eksplisit dan kohesi fungsional tinggi.",
        "Hindari circular import dependency; pisahkan type definitions bila terjadi siklus.",
        "Sediakan unit test pendamping untuk verifikasi deterministik.",
    ],
    "patterns": [
        "Modular decoupling",
        "Deterministic interface contracts",
    ],
    "guided_hints": [
        "Ikuti konvensi modul sejenis di direktori yang sama.",
        "Gunakan type-only imports bila hanya merujuk interface.",
    ],
}


def infer_module_role(file_path: str, content: str = "") -> str:
    """Infer architectural role from file naming, directory structure, or AST markers."""
    norm = file_path.replace("\\", "/").lower()
    for pattern, role in ROLE_PATTERNS:
        if re.search(pattern, norm):
            return role
    for pattern, role in DIR_ROLE_PATTERNS:
        if re.search(pattern, norm):
            return role
    if content:
        if "@Injectable" in content:
            return "service"
        if "@Component" in content:
            return "component"
        if "@Directive" in content:
            return "directive"
        if "@Pipe" in content:
            return "pipe"
        if "export interface" in content or "export type" in content:
            return "model"
    return "module"


def find_isomorphic_modules(
    target_file: str,
    target_role: str,
    vertices: List[str],
    shared_graph: Optional[Dict[str, Any]] = None,
    max_isomorphs: int = 5,
) -> List[Dict[str, Any]]:
    """
    Identifikasi modul-modul serupa (isomorphic modules) dalam codebase
    berdasarkan kesamaan role, kedekatan direktori, ekstensi, dan type shapes.
    """
    target_norm = target_file.replace("\\", "/")
    target_dir = os.path.dirname(target_norm)
    target_ext = os.path.splitext(target_norm)[1]

    type_shapes = shared_graph.get("type_shapes", {}) if shared_graph else {}
    target_shapes = set(type_shapes.get(target_norm, {}).keys()) if target_norm in type_shapes else set()
    node_metadata = shared_graph.get("node_metadata", {}) if shared_graph else {}

    candidates: List[Dict[str, Any]] = []
    for v in vertices:
        v_norm = v.replace("\\", "/")
        if v_norm == target_norm:
            continue
        v_role = infer_module_role(v_norm)
        if target_role != "test" and v_role == "test":
            continue

        score = 0.0
        # 1. Role match
        if v_role == target_role:
            score += 0.55
        elif target_role in ("service", "repository") and v_role in ("service", "repository"):
            score += 0.30

        # 2. Directory proximity
        v_dir = os.path.dirname(v_norm)
        if v_dir == target_dir:
            score += 0.25
        elif target_dir and (v_dir.startswith(target_dir) or target_dir.startswith(v_dir)):
            score += 0.15
        elif os.path.dirname(v_dir) == os.path.dirname(target_dir):
            score += 0.10

        # 3. File extension match
        v_ext = os.path.splitext(v_norm)[1]
        if v_ext == target_ext:
            score += 0.05

        # 4. Type shapes overlap
        if target_shapes and v_norm in type_shapes:
            v_shapes = set(type_shapes[v_norm].keys())
            if v_shapes and target_shapes:
                overlap = len(target_shapes.intersection(v_shapes))
                if overlap > 0:
                    score += 0.20

        if score >= 0.35:
            meta = node_metadata.get(v_norm, {})
            candidates.append({
                "file": v_norm,
                "role": v_role,
                "similarity_score": round(score, 3),
                "fan_in": meta.get("fan_in", 0),
                "fan_out": meta.get("fan_out", 0),
            })

    candidates.sort(
        key=lambda c: (c["similarity_score"], c["fan_in"] + c["fan_out"], -len(c["file"])),
        reverse=True,
    )
    return candidates[:max_isomorphs]


def compute_left_kan_colimit(
    target_file: str,
    target_role: str,
    isomorphs: List[Dict[str, Any]],
    shared_graph: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Left Kan Extension (Lan_K F):
    Colimit atas diagram relasi struktural modul-modul isomorphic.
    Mengimputasi dependensi (outgoing edges), pemanggil (incoming edges),
    dan companion test files dari konsensus modul serupa.
    """
    if not shared_graph or not isomorphs:
        return {
            "colimit_type": "architectural_relation_imputation",
            "imputed_dependencies": [],
            "imputed_dependents": [],
            "expected_companion_test": None,
            "colimit_confidence": 0.0,
        }

    edges = shared_graph.get("edges", [])
    outgoing_map: Dict[str, List[str]] = {}
    incoming_map: Dict[str, List[str]] = {}

    for u, v in edges:
        u_norm = u.replace("\\", "/")
        v_norm = v.replace("\\", "/")
        outgoing_map.setdefault(u_norm, []).append(v_norm)
        incoming_map.setdefault(v_norm, []).append(u_norm)

    iso_files = [m["file"] for m in isomorphs]
    num_isomorphs = len(iso_files)

    # 1. Colimit Outgoing: apa yang diimpor oleh modul-modul isomorphic?
    dep_role_counts: Dict[str, int] = {}
    dep_role_examples: Dict[str, List[str]] = {}

    for iso in iso_files:
        targets = outgoing_map.get(iso, [])
        seen_roles_for_iso: Set[str] = set()
        for t in targets:
            r = infer_module_role(t)
            seen_roles_for_iso.add(r)
            dep_role_examples.setdefault(r, []).append(t)
        for r in seen_roles_for_iso:
            dep_role_counts[r] = dep_role_counts.get(r, 0) + 1

    imputed_deps: List[Dict[str, Any]] = []
    for dep_role, count in sorted(dep_role_counts.items(), key=lambda x: x[1], reverse=True):
        freq = round(count / num_isomorphs, 2)
        if freq >= 0.25:
            examples = sorted(list(set(dep_role_examples.get(dep_role, []))))[:3]
            imputed_deps.append({
                "role": dep_role,
                "confidence": freq,
                "frequency": f"{count}/{num_isomorphs}",
                "example_targets": examples,
                "rationale": f"Diamati pada {count}/{num_isomorphs} modul {target_role} isomorphic.",
            })

    # 2. Colimit Incoming: siapa yang memanggil modul-modul isomorphic?
    caller_role_counts: Dict[str, int] = {}
    caller_role_examples: Dict[str, List[str]] = {}

    for iso in iso_files:
        callers = incoming_map.get(iso, [])
        seen_roles_for_iso: Set[str] = set()
        for c in callers:
            r = infer_module_role(c)
            seen_roles_for_iso.add(r)
            caller_role_examples.setdefault(r, []).append(c)
        for r in seen_roles_for_iso:
            caller_role_counts[r] = caller_role_counts.get(r, 0) + 1

    imputed_callers: List[Dict[str, Any]] = []
    for caller_role, count in sorted(caller_role_counts.items(), key=lambda x: x[1], reverse=True):
        freq = round(count / num_isomorphs, 2)
        if freq >= 0.25:
            examples = sorted(list(set(caller_role_examples.get(caller_role, []))))[:3]
            imputed_callers.append({
                "role": caller_role,
                "confidence": freq,
                "frequency": f"{count}/{num_isomorphs}",
                "example_callers": examples,
                "rationale": f"Modul {target_role} isomorphic dipanggil oleh {caller_role}.",
            })

    # 3. Companion test imputation
    vertices_set = set(v.replace("\\", "/") for v in shared_graph.get("vertices", []))
    spec_count = 0
    for iso in iso_files:
        base, _ = os.path.splitext(iso)
        if f"{base}.spec.ts" in vertices_set or f"{base}.test.ts" in vertices_set or f"{base}.spec.js" in vertices_set:
            spec_count += 1

    target_norm = target_file.replace("\\", "/")
    target_base, target_ext = os.path.splitext(target_norm)
    ext_suffix = ".spec.js" if target_ext == ".js" else ".spec.ts"
    expected_companion_test = f"{target_base}{ext_suffix}" if (num_isomorphs > 0 and spec_count / num_isomorphs >= 0.3) else None

    colimit_conf = min(1.0, 0.40 + 0.12 * num_isomorphs)

    return {
        "colimit_type": "architectural_relation_imputation",
        "imputed_dependencies": imputed_deps,
        "imputed_dependents": imputed_callers,
        "expected_companion_test": expected_companion_test,
        "colimit_confidence": round(colimit_conf, 3),
    }


def compute_right_kan_limit(
    target_file: str,
    target_role: str,
    memory_store: Optional[Dict[str, Any]] = None,
    isomorphs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Right Kan Extension (Ran_K F):
    Limit atas universal cone konvensi dan invariant arsitektural.
    Menghasilkan guided hints dan aturan desain yang mengikat modul kelas ini.
    """
    role_info = ROLE_ARCHITECTURAL_CONVENTIONS.get(target_role, DEFAULT_MODULE_CONVENTIONS)
    conventions = list(role_info.get("conventions", []))
    patterns = list(role_info.get("patterns", []))
    hints = list(role_info.get("guided_hints", []))

    # Recall relevant historical memory guidelines if available
    recalled_count = 0
    if memory_store and isinstance(memory_store, dict):
        memories = memory_store.get("memories", [])
        if isinstance(memories, list):
            target_keywords = {target_role, "architecture", "convention", "pattern", "guideline"}
            for m in memories:
                if not isinstance(m, dict):
                    continue
                content = str(m.get("content", ""))
                tags = m.get("tags", [])
                tag_set = set(tags) if isinstance(tags, list) else set()
                if tag_set.intersection(target_keywords) or any(kw in content.lower() for kw in target_keywords):
                    if len(content) < 160:
                        hints.append(f"Memory historis: {content}")
                        recalled_count += 1
                    if recalled_count >= 2:
                        break

    if isomorphs:
        iso_examples = [m["file"] for m in isomorphs[:2]]
        hints.append(f"Rujuk pola implementasi modul isomorphic: {', '.join(iso_examples)}")

    return {
        "limit_type": "top_down_convention_completion",
        "architectural_conventions": conventions,
        "design_patterns": patterns,
        "guided_hints": hints,
        "recalled_conventions_count": recalled_count,
    }


def impute_module_relations(
    target_file: str,
    shared_graph: Optional[Dict[str, Any]] = None,
    memory_store: Optional[Dict[str, Any]] = None,
    scan_root: str = ".",
    max_isomorphs: int = 5,
) -> Dict[str, Any]:
    """
    Aktivasi Kan Extension untuk Imputasi Relasi Modul Baru.
    
    Menjembatani zero-context modules ketika developer menambahkan modul baru
    yang belum memiliki memori historis atau belum tersambung ke graph:
    - Left Kan Extension (Lan): Colimit aproksimasi keterkaitan arsitektur dari modul serupa.
    - Right Kan Extension (Ran): Limit konvensi & guided hints untuk AI agent.
    """
    target_norm = target_file.replace("\\", "/")

    # Check content in file_map if available
    content = ""
    if shared_graph and "file_map" in shared_graph:
        content = shared_graph["file_map"].get(target_norm, "")

    target_role = infer_module_role(target_norm, content=content)

    # Assess whether target has historical context or active topology
    memory_count = 0
    if memory_store and isinstance(memory_store, dict):
        memories = memory_store.get("memories", [])
        if isinstance(memories, list):
            for m in memories:
                if isinstance(m, dict):
                    if m.get("file") == target_norm or target_norm in str(m.get("content", "")):
                        memory_count += 1

    vertices = shared_graph.get("vertices", []) if shared_graph else []
    node_meta = shared_graph.get("node_metadata", {}).get(target_norm, {}) if shared_graph else {}
    fan_in = node_meta.get("fan_in", 0)
    fan_out = node_meta.get("fan_out", 0)

    is_zero_context = (memory_count == 0) and (fan_in == 0 and fan_out == 0 or target_norm not in vertices)

    # 1. Find Isomorphic Modules
    isomorphs = find_isomorphic_modules(
        target_norm,
        target_role,
        vertices,
        shared_graph=shared_graph,
        max_isomorphs=max_isomorphs,
    )

    # 2. Left Kan Extension (Colimit)
    lan = compute_left_kan_colimit(target_norm, target_role, isomorphs, shared_graph)

    # 3. Right Kan Extension (Limit)
    ran = compute_right_kan_limit(target_norm, target_role, memory_store, isomorphs)

    iso_names = [m["file"] for m in isomorphs]
    dep_roles = [d["role"] for d in lan.get("imputed_dependencies", [])]
    caller_roles = [c["role"] for c in lan.get("imputed_dependents", [])]

    if isomorphs:
        summary = (
            f"Kan Extension mengimputasi {len(lan.get('imputed_dependencies', []))} relasi dependensi "
            f"dan {len(ran.get('guided_hints', []))} guided hint untuk '{target_norm}' (role: {target_role}) "
            f"melalui {len(isomorphs)} modul isomorphic ({', '.join(iso_names[:2])})."
        )
        status = "imputed"
    else:
        summary = (
            f"Kan Extension menyediakan {len(ran.get('guided_hints', []))} guided hint dan konvensi arsitektur "
            f"untuk modul '{target_norm}' (role: {target_role})."
        )
        status = "zero_context_role_convention"

    return {
        "target_file": target_norm,
        "inferred_role": target_role,
        "status": status,
        "is_new_or_zero_context": is_zero_context,
        "isomorphic_modules": isomorphs,
        "left_kan_extension": lan,
        "right_kan_extension": ran,
        "kan_synthesis": {
            "summary": summary,
            "isomorphic_references": iso_names,
            "colimit_imputed_dependencies": dep_roles,
            "colimit_imputed_dependents": caller_roles,
            "expected_companion_test": lan.get("expected_companion_test"),
            "confidence": lan.get("colimit_confidence", 0.0),
        },
    }

