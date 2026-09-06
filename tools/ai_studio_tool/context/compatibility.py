"""
Fiber Compatibility — Fibration Context Domain
Schema Version: 4.1.0-memory
"""

from typing import Any, Dict, Tuple


def check_fiber_compatibility(
    memory: Dict[str, Any],
    active_fiber: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Memeriksa kompatibilitas memori kandidat dengan fiber yang aktif.
    """
    active_mems = active_fiber.get("active_memories", [])
    if memory.get("id") in active_mems:
        return True, "already_in_fiber"

    # Jika fiber kosong, semua memori kompatibel
    if not active_mems:
        return True, "empty_fiber"

    return True, "compatible"


__all__ = [
    "check_fiber_compatibility",
]
