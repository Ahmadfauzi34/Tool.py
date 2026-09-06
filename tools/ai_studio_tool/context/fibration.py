"""
Memory Fibration — HoTT Kernel Phase C
Schema Version: 4.1.0-memory

Implementasi Fibration-aware Context Management (hott3.txt):
- Fiber state management (context window sebagai fiber)
- Lifting (retrieval sebagai path lifting)
- Descent (fiber descent, bukan truncation)
- Section (benang merah narasi)
- Fiber Compatibility (penyaringan retrieval)
- Base Navigation (context switching)
"""

import os
import uuid
import datetime
import math
from typing import Any, Dict, List, Optional

from memory.runtime import (
    MemoryStateError,
    get_memory_runtime_paths,
    memory_runtime_lock,
    read_json_unlocked,
    write_json_unlocked,
)

SCHEMA_VERSION = "4.1.0-memory"

_INITIAL_PATHS = get_memory_runtime_paths(create=False)
FIBER_STATE_PATH = _INITIAL_PATHS["fiber_state_path"]
FIBER_ARCHIVE_DIR = _INITIAL_PATHS["fiber_archive_dir"]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================
# 1. FIBER STATE MANAGEMENT
# ============================================================

def _default_fiber_state() -> Dict[str, Any]:
    """Buat fiber state default (kosong)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "fiber_id": None,
        "base_state": {
            "task": None,
            "focus": None,
            "dialog_turn": 0,
            "created_at": None,
        },
        "active_memories": [],
        "section": {
            "name": None,
            "narrative": None,
            "memories": [],
        },
        "descent_log": [],
        "created_at": None,
        "last_updated": None,
    }


def load_fiber_state() -> Dict[str, Any]:
    """Load fiber state dari file."""
    def validate(value: Any) -> None:
        if not isinstance(value, dict):
            raise ValueError("fiber state must be an object")
        if not isinstance(value.get("active_memories", []), list):
            raise ValueError("fiber active_memories must be a list")

    with memory_runtime_lock() as paths:
        return read_json_unlocked(paths["fiber_state_path"], _default_fiber_state, validate)


def save_fiber_state(state: Dict[str, Any]) -> None:
    """Simpan fiber state ke file."""
    state["last_updated"] = _now_iso()
    with memory_runtime_lock() as paths:
        write_json_unlocked(paths["fiber_state_path"], state)


def init_fiber(task: str, focus: str) -> Dict[str, Any]:
    """
    Inisialisasi fiber baru untuk task/fokus tertentu.
    Ini adalah "Base Navigation" — membangun fiber baru untuk base state baru.
    """
    # Arsipkan fiber lama jika ada
    old_state = load_fiber_state()
    if old_state.get("fiber_id"):
        _archive_fiber(old_state)

    # Buat fiber baru
    fiber_id = f"fiber_{uuid.uuid4().hex[:8]}"
    new_state = _default_fiber_state()
    new_state["fiber_id"] = fiber_id
    new_state["base_state"] = {
        "task": task,
        "focus": focus,
        "dialog_turn": 0,
        "created_at": _now_iso(),
    }
    new_state["created_at"] = _now_iso()
    new_state["last_updated"] = _now_iso()

    save_fiber_state(new_state)
    return {
        "status": "initialized",
        "fiber_id": fiber_id,
        "base_state": new_state["base_state"],
        "archived_previous": bool(old_state.get("fiber_id")),
    }


def _archive_fiber(state: Dict[str, Any]) -> None:
    """Arsipkan fiber lama ke fiber_archive/."""
    fiber_id = state.get("fiber_id", "unknown")
    state["archived_at"] = _now_iso()
    with memory_runtime_lock() as paths:
        archive_path = os.path.join(paths["fiber_archive_dir"], f"{fiber_id}.json")
        write_json_unlocked(archive_path, state)


# ============================================================
# 2. LIFTING — Retrieval sebagai Path Lifting
# ============================================================

def lift_to_fiber(
    query: Optional[str] = None,
    memory_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    max_lift: int = 10,
    min_importance: float = 0.0,
) -> Dict[str, Any]:
    """
    Angkat memori relevan ke fiber berdasarkan query.
    Ini adalah "Retrieval sebagai Path Lifting" dari hott3.txt.
    
    Fiber Compatibility Check:
    - Memori baru harus relevan dengan query
    - Memori baru harus konsisten dengan fiber aktif (tag overlap)
    """
    try:
        from memory.store import recall_memories, load_store
    except ImportError:
        try:
            from memory_store import recall_memories, load_store
        except ImportError:
            return {"error": "memory_store not available"}

    state = load_fiber_state()

    if not state.get("fiber_id"):
        return {"error": "No active fiber. Run 'memory fiber_init' first."}

    # Recall memories berdasarkan query
    recalled = recall_memories(
        query=query,
        memory_type=memory_type,
        tags=tags,
        min_importance=min_importance,
        limit=max_lift * 2,  # Recall lebih banyak untuk filtering
    )

    # Fiber Compatibility Check
    active_memories = state.get("active_memories", [])
    store = load_store()
    memory_map = {m["id"]: m for m in store.get("memories", [])}

    # Ambil tags dari fiber aktif untuk compatibility check
    active_tags = set()
    for mid in active_memories:
        mem = memory_map.get(mid)
        if mem:
            active_tags.update(mem.get("tags", []))

    # Filter berdasarkan compatibility
    lifted = []
    skipped_incompatible = []
    for mem in recalled:
        if mem["id"] in active_memories:
            continue  # Sudah di fiber

        mem_tags = set(mem.get("tags", []))

        # Compatibility: jika fiber aktif punya tags, harus ada overlap
        # Jika fiber kosong, semua kompatibel
        if active_tags and not (mem_tags & active_tags):
            skipped_incompatible.append({
                "id": mem["id"],
                "reason": "no_tag_overlap_with_active_fiber",
            })
            continue

        lifted.append(mem)
        if len(lifted) >= max_lift:
            break

    # Update fiber state
    for mem in lifted:
        state["active_memories"].append(mem["id"])

    # Update dialog turn
    state["base_state"]["dialog_turn"] = state["base_state"].get("dialog_turn", 0) + 1

    save_fiber_state(state)

    return {
        "status": "lifted",
        "fiber_id": state["fiber_id"],
        "lifted_count": len(lifted),
        "lifted_memories": [
            {
                "id": m["id"],
                "type": m.get("type"),
                "content_preview": m.get("content", "")[:100],
                "importance": m.get("importance", 0),
            }
            for m in lifted
        ],
        "skipped_incompatible": len(skipped_incompatible),
        "fiber_size": len(state["active_memories"]),
        "dialog_turn": state["base_state"]["dialog_turn"],
    }


# ============================================================
# 3. DESCENT — Fiber Descent (Bukan Truncation)
# ============================================================

def descend_from_fiber(
    memory_id: Optional[str] = None,
    descend_all: bool = False,
    reason: str = "task_completed",
) -> Dict[str, Any]:
    """
    Turunkan memori dari fiber ke total space.
    Ini adalah "Fiber Descent" dari hott3.txt:
    informasi tidak dihapus, tapi dikembalikan ke total space
    dengan metadata relevansi dan konteks asal.
    """
    state = load_fiber_state()

    if not state.get("fiber_id"):
        return {"error": "No active fiber."}

    active = state.get("active_memories", [])
    descended = []

    if descend_all:
        to_descend = list(active)
    elif memory_id:
        to_descend = [memory_id] if memory_id in active else []
    else:
        return {"error": "Specify memory_id or use --all"}

    for mid in to_descend:
        if mid in active:
            active.remove(mid)
            descended.append(mid)
            # Log descent dengan metadata
            state["descent_log"].append({
                "memory_id": mid,
                "descended_at": _now_iso(),
                "reason": reason,
                "fiber_id": state["fiber_id"],
                "base_state": state["base_state"].get("task"),
            })

    state["active_memories"] = active
    save_fiber_state(state)

    return {
        "status": "descended",
        "descended_count": len(descended),
        "descended_ids": descended,
        "reason": reason,
        "fiber_size": len(active),
        "note": "Memories remain in total space (memory_store.json), only removed from active fiber.",
    }


# ============================================================
# 4. SECTION — Benang Merah Narasi
# ============================================================

def start_section(name: str, narrative: str) -> Dict[str, Any]:
    """
    Mulai section baru (benang merah narasi).
    Section adalah pemilihan elemen memori secara konsisten
    untuk setiap tahapan tugas (hott3.txt).
    """
    state = load_fiber_state()

    if not state.get("fiber_id"):
        return {"error": "No active fiber. Run 'memory fiber_init' first."}

    state["section"] = {
        "name": name,
        "narrative": narrative,
        "memories": [],
        "started_at": _now_iso(),
    }
    save_fiber_state(state)

    return {
        "status": "section_started",
        "section_name": name,
        "narrative": narrative,
        "fiber_id": state["fiber_id"],
    }


def add_to_section(memory_id: str) -> Dict[str, Any]:
    """Tambah memori ke section aktif."""
    state = load_fiber_state()

    section = state.get("section", {})
    if not section.get("name"):
        return {"error": "No active section. Run 'memory section_start' first."}

    if memory_id not in state.get("active_memories", []):
        return {"error": f"Memory {memory_id} not in active fiber. Lift it first."}

    if memory_id not in section.get("memories", []):
        section["memories"].append(memory_id)
        state["section"] = section
        save_fiber_state(state)

    return {
        "status": "added_to_section",
        "memory_id": memory_id,
        "section_name": section["name"],
        "section_size": len(section["memories"]),
    }


def get_section_status() -> Dict[str, Any]:
    """Lihat status section aktif."""
    state = load_fiber_state()
    section = state.get("section", {})

    return {
        "fiber_id": state.get("fiber_id"),
        "section_name": section.get("name"),
        "narrative": section.get("narrative"),
        "section_memories": section.get("memories", []),
        "section_size": len(section.get("memories", [])),
        "started_at": section.get("started_at"),
    }


# ============================================================
# 5. FIBER STATUS — Inspeksi Context Window
# ============================================================

def fiber_status() -> Dict[str, Any]:
    """
    Lihat apa yang ada di fiber aktif (context window).
    Ini adalah inspeksi dari "apa yang sedang dilihat agent".
    """
    try:
        from memory.store import load_store
    except ImportError:
        try:
            from memory_store import load_store
        except ImportError:
            return {"error": "memory_store not available"}

    state = load_fiber_state()

    if not state.get("fiber_id"):
        return {
            "status": "no_active_fiber",
            "message": "No fiber initialized. Run 'memory fiber_init' first.",
        }

    store = load_store()
    memory_map = {m["id"]: m for m in store.get("memories", [])}

    # Detail active memories
    active_details = []
    total_importance = 0.0
    for mid in state.get("active_memories", []):
        mem = memory_map.get(mid)
        if mem:
            active_details.append({
                "id": mid,
                "type": mem.get("type"),
                "content_preview": mem.get("content", "")[:80],
                "importance": mem.get("importance", 0),
                "tags": mem.get("tags", []),
            })
            total_importance += mem.get("importance", 0)

    section = state.get("section", {})

    return {
        "fiber_id": state["fiber_id"],
        "base_state": state["base_state"],
        "active_memories_count": len(state.get("active_memories", [])),
        "active_memories": active_details,
        "total_importance": round(total_importance, 3),
        "avg_importance": round(
            total_importance / max(1, len(active_details)), 3
        ),
        "section": {
            "name": section.get("name"),
            "memories_count": len(section.get("memories", [])),
        },
        "descent_log_count": len(state.get("descent_log", [])),
        "created_at": state.get("created_at"),
        "last_updated": state.get("last_updated"),
    }


# ============================================================
# 6. BASE NAVIGATION — Context Switching
# ============================================================

def switch_base(new_task: str, new_focus: str) -> Dict[str, Any]:
    """
    Pindah ke base state baru (context switching).
    Arsipkan fiber lama, bangun fiber baru.
    Ini adalah "Base Navigation" dari hott3.txt.
    """
    old_state = load_fiber_state()
    previous_task = old_state.get("base_state", {}).get("task")

    # Init fiber baru (ini akan mengarsipkan fiber lama secara utuh beserta memorinya)
    result = init_fiber(new_task, new_focus)
    result["previous_fiber_archived"] = bool(old_state.get("fiber_id"))
    result["previous_task"] = previous_task

    return result


# ============================================================
# 7. PARALLEL TRANSPORT — Cross-Session Coherence
# ============================================================

def compute_decay_factor(
    memory: Dict[str, Any],
    half_life_days: int = 30,
) -> float:
    """
    Hitung decay factor berdasarkan waktu sejak terakhir diakses.
    Menggunakan exponential decay dengan half-life.
    
    Args:
        memory: Memory dict dengan field 'last_accessed'
        half_life_days: Jumlah hari untuk score turun ke 50%
    
    Returns:
        factor [0.0, 1.0], di mana 1.0 = baru diakses, 0.0 = sangat lama
    """
    last_accessed_str = memory.get("last_accessed", "")
    if not last_accessed_str:
        return 0.5  # Default jika tidak ada data
    
    try:
        last_accessed = datetime.datetime.fromisoformat(
            last_accessed_str.replace("Z", "+00:00")
        )
        if last_accessed.tzinfo is None:
            last_accessed = last_accessed.replace(tzinfo=datetime.timezone.utc)
    except (ValueError, AttributeError):
        return 0.5
    
    days_since = (datetime.datetime.now(datetime.timezone.utc) - last_accessed).days
    
    # Exponential decay: factor = 0.5^(days/half_life)
    decay = math.pow(0.5, max(0, days_since) / half_life_days)
    return round(max(0.0, min(1.0, decay)), 4)


def compute_relevancy_score(
    memory: Dict[str, Any],
    new_base_state: Dict[str, Any],
    old_base_state: Dict[str, Any],
    use_decay: bool = True,
    half_life_days: int = 30,
) -> float:
    """
    Hitung relevansi memori terhadap base state baru.
    
    UPDATED Formula (dengan decay):
    - Tag overlap dengan task/focus baru: 0.35 weight
    - Importance memori: 0.25 weight
    - Content keyword overlap: 0.15 weight
    - Base state similarity (old vs new): 0.10 weight
    - Decay factor: 0.15 weight
    
    Returns: score [0.0, 1.0]
    """
    score = 0.0
    mem_tags = [t.lower() for t in memory.get("tags", [])]
    mem_content = memory.get("content", "").lower()

    # 1. Tag overlap dengan new task/focus (0.35)
    new_task_words = set(new_base_state.get("task", "").lower().split())
    new_focus_words = set(new_base_state.get("focus", "").lower().split())
    stop_words = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "pada", "untuk", "dari", "di", "ke"}
    new_keywords = (new_task_words | new_focus_words) - stop_words

    if new_keywords and mem_tags:
        matching_tags = sum(1 for tag in mem_tags if any(kw in tag or tag in kw for kw in new_keywords))
        tag_ratio = min(1.0, matching_tags / 1.0) if matching_tags > 0 else 0.0
        score += 0.35 * tag_ratio

    # 2. Importance (0.25)
    importance = memory.get("importance", 0.5)
    score += 0.25 * min(1.0, max(0.0, importance))

    # 3. Content keyword overlap (0.15)
    if new_keywords:
        matching_content_kws = sum(1 for kw in new_keywords if len(kw) > 2 and kw in mem_content)
        content_ratio = min(1.0, matching_content_kws / 1.0) if matching_content_kws > 0 else 0.0
        score += 0.15 * content_ratio

    # 4. Base state similarity / task continuity (0.10)
    old_task = old_base_state.get("task", "").lower()
    new_task = new_base_state.get("task", "").lower()
    if old_task and new_task:
        old_words = set(old_task.split()) - stop_words
        new_words = set(new_task.split()) - stop_words
        overlap = len(old_words & new_words)
        total = len(old_words | new_words)
        if total > 0:
            continuity = overlap / total
            score += 0.10 * continuity

    # 5. Decay factor (0.15)
    if use_decay:
        decay = compute_decay_factor(memory, half_life_days)
        score += 0.15 * decay

    return round(min(1.0, score), 4)


def transport_from_archive(
    source_fiber_id: str,
    new_task: str,
    new_focus: str,
    threshold: float = 0.6,
    max_transport: int = 10,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Parallel Transport: bawa memori relevan dari fiber lama ke fiber baru.
    
    Args:
        source_fiber_id: ID fiber yang diarsipkan (dari fiber_archive/)
        new_task: Task untuk fiber baru
        new_focus: Focus untuk fiber baru
        threshold: Minimum relevancy score untuk transport
        max_transport: Maximum memori yang ditransport
        dry_run: Preview tanpa eksekusi
    
    Returns:
        Dict dengan transported memories dan metadata translasi
    """
    def validate_archive(value: Any) -> None:
        if not isinstance(value, dict) or not value.get("fiber_id"):
            raise ValueError("fiber archive must be an object with fiber_id")

    try:
        with memory_runtime_lock() as paths:
            archive_dir = paths["fiber_archive_dir"]
            archive_path = os.path.join(archive_dir, f"{source_fiber_id}.json")
            archived_files = sorted(
                filename for filename in os.listdir(archive_dir)
                if filename.endswith(".json") and ".corrupt." not in filename
            )
            if not os.path.isfile(archive_path):
                matches = [filename for filename in archived_files if source_fiber_id in filename]
                if not matches:
                    return {
                        "status": "error",
                        "error": f"Archived fiber not found: {source_fiber_id}",
                        "available_archives": archived_files,
                    }
                archive_path = os.path.join(archive_dir, matches[0])
            archived_fiber = read_json_unlocked(archive_path, dict, validate_archive)
    except MemoryStateError:
        raise
    except Exception as exc:
        return {"status": "error", "error": f"Failed to read archive: {exc}"}

    # Load memory store
    try:
        from memory.store import load_store
        store = load_store()
        memory_map = {m["id"]: m for m in store.get("memories", [])}
    except ImportError:
        try:
            from memory_store import load_store
            store = load_store()
            memory_map = {m["id"]: m for m in store.get("memories", [])}
        except ImportError:
            return {"error": "memory_store not available"}

    old_active = archived_fiber.get("active_memories", [])
    if not old_active:
        # Fallback to section memories or descent log if active was cleared
        sec_mems = archived_fiber.get("section", {}).get("memories", [])
        desc_mems = [d.get("memory_id") for d in archived_fiber.get("descent_log", []) if d.get("memory_id")]
        combined = []
        for m in sec_mems + desc_mems:
            if m and m not in combined:
                combined.append(m)
        old_active = combined

    old_base = archived_fiber.get("base_state", {})
    new_base = {"task": new_task, "focus": new_focus}

    # Score each memory
    scored = []
    for mid in old_active:
        mem = memory_map.get(mid)
        if not mem:
            continue
        score = compute_relevancy_score(mem, new_base, old_base)
        scored.append({
            "memory_id": mid,
            "memory": mem,
            "relevancy_score": score,
            "passed_threshold": score >= threshold,
        })

    # Sort by relevancy desc
    scored.sort(key=lambda x: -x["relevancy_score"])

    # Filter
    eligible = [s for s in scored if s["passed_threshold"]]
    to_transport = eligible[:max_transport]

    if dry_run:
        return {
            "status": "dry_run",
            "source_fiber_id": source_fiber_id,
            "old_base_state": old_base,
            "new_base_state": new_base,
            "threshold": threshold,
            "total_in_source": len(old_active),
            "eligible_count": len(eligible),
            "to_transport_count": len(to_transport),
            "scored_memories": [
                {
                    "id": s["memory_id"],
                    "relevancy_score": s["relevancy_score"],
                    "passed_threshold": s["passed_threshold"],
                    "content_preview": s["memory"].get("content", "")[:80],
                }
                for s in scored
            ],
        }

    # Initialize new fiber (this archives current if any)
    init_fiber(new_task, new_focus)

    # Lift transported memories ke fiber baru
    state = load_fiber_state()
    transported = []
    for item in to_transport:
        mid = item["memory_id"]
        mem = item["memory"]
        if mid not in state["active_memories"]:
            state["active_memories"].append(mid)
            transported.append({
                "memory_id": mid,
                "relevancy_score": item["relevancy_score"],
                "content_preview": mem.get("content", "")[:80],
                "type": mem.get("type"),
            })

    # Update dialog turn (menandakan transport sudah terjadi)
    state["base_state"]["dialog_turn"] = 1
    state["base_state"]["transported_from"] = source_fiber_id
    state["base_state"]["transport_metadata"] = {
        "threshold": threshold,
        "transported_count": len(transported),
        "total_scored": len(scored),
        "eligible_count": len(eligible),
        "transported_at": _now_iso(),
    }
    save_fiber_state(state)

    return {
        "status": "transported",
        "source_fiber_id": source_fiber_id,
        "old_base_state": old_base,
        "new_base_state": new_base,
        "threshold": threshold,
        "transported_count": len(transported),
        "transported_memories": transported,
        "skipped_below_threshold": len(scored) - len(eligible),
        "fiber_id": state["fiber_id"],
        "note": "Memories transported via parallel transport. Irrelevant memories from source fiber were NOT carried over.",
    }


def list_archived_fibers() -> Dict[str, Any]:
    """List semua archived fibers untuk referensi transport."""
    archives = []

    with memory_runtime_lock() as paths:
        archive_dir = paths["fiber_archive_dir"]
        for filename in sorted(os.listdir(archive_dir)):
            if not filename.endswith(".json") or ".corrupt." in filename:
                continue
            filepath = os.path.join(archive_dir, filename)
            try:
                data = read_json_unlocked(filepath, dict)
                archives.append({
                    "fiber_id": data.get("fiber_id"),
                    "filename": filename,
                    "task": data.get("base_state", {}).get("task"),
                    "focus": data.get("base_state", {}).get("focus"),
                    "active_memories_count": len(data.get("active_memories", [])),
                    "archived_at": data.get("archived_at"),
                    "dialog_turns": data.get("base_state", {}).get("dialog_turn", 0),
                })
            except MemoryStateError:
                raise
    
    return {
        "archived_fibers": archives,
        "count": len(archives),
    }
