"""
Safety Module — HoTT Kernel
Schema Version: 4.0.0-kernel

Invariant enforcement & topological safety:
- Cycle prevention in memory graph
- Betti preservation checks (beta_1_reasoning == 0)
- Fiber state invariants
"""

from typing import Any, Dict, List, Optional, Set, Tuple


def check_memory_association_safety(
    associations: List[Dict[str, Any]],
    from_id: str,
    to_id: str,
    assoc_type: str,
) -> Tuple[bool, Optional[str]]:
    """
    Memeriksa apakah penambahan asosiasi aman (tidak membuat reasoning cycle liar).
    Asosiasi non-temporal tidak boleh membentuk siklus tertutup.
    """
    if from_id == to_id:
        return False, f"Self-loop detected: {from_id} -> {to_id}"

    # Asosiasi temporal diizinkan membentuk siklus waktu
    if assoc_type == "temporal":
        return True, None

    # Bangun adjacency dari non-temporal associations
    adjacency: Dict[str, Set[str]] = {}
    for a in associations:
        if a.get("type") != "temporal":
            u = a.get("from")
            v = a.get("to")
            if u and v:
                adjacency.setdefault(u, set()).add(v)

    # Tambahkan directed candidate edge: from_id -> to_id
    # Cek apakah ada path dari to_id kembali ke from_id (yang akan membentuk cycle)
    visited = set()
    stack = [to_id]
    while stack:
        curr = stack.pop()
        if curr == from_id:
            return False, f"Cycle detected in reasoning path: {from_id} -> ... -> {to_id} -> {from_id}"
        if curr not in visited:
            visited.add(curr)
            for neighbor in adjacency.get(curr, []):
                if neighbor not in visited:
                    stack.append(neighbor)

    return True, None


def check_betti_preservation(
    betti_before: Dict[str, int],
    betti_after: Dict[str, int],
    allowed_reasoning_loop: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Memeriksa apakah perubahan topologi memori menjaga invarian beta_1_reasoning == 0.
    """
    b1_reasoning_after = betti_after.get("beta_1_reasoning", 0)
    if not allowed_reasoning_loop and b1_reasoning_after > 0:
        return False, f"Topology violation: beta_1_reasoning increased to {b1_reasoning_after} (must be 0)"
    return True, None


def check_fiber_state_safety(fiber_state: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Memeriksa invarian fiber context window.
    """
    if not isinstance(fiber_state, dict):
        return False, "Invalid fiber state format"
    if "base_state" not in fiber_state or "active_memories" not in fiber_state:
        return False, "Fiber state missing base_state or active_memories"
    return True, None
