"""
Context Domain — Fibration Context Management (Layer 3)
"""

from context.fibration import (
    init_fiber,
    lift_to_fiber,
    descend_from_fiber,
    fiber_status,
    switch_base,
    load_fiber_state,
    save_fiber_state,
)
from context.section import (
    start_section,
    add_to_section,
    get_section_status,
)
from context.transport import (
    transport_from_archive,
    list_archived_fibers,
    compute_relevancy_score,
    compute_decay_factor,
)
from context.compatibility import check_fiber_compatibility

__all__ = [
    "init_fiber",
    "lift_to_fiber",
    "descend_from_fiber",
    "fiber_status",
    "switch_base",
    "load_fiber_state",
    "save_fiber_state",
    "start_section",
    "add_to_section",
    "get_section_status",
    "transport_from_archive",
    "list_archived_fibers",
    "compute_relevancy_score",
    "compute_decay_factor",
    "check_fiber_compatibility",
]
