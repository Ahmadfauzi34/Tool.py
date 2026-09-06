"""
Bridge Domain — Cross-Domain Integration (Layer 4)
"""

from bridge.xanalyze import (
    filter_findings_for_memory,
    auto_store_findings,
    check_consolidation_trigger,
)
from bridge.xsteer import cross_domain_steer
from bridge.xcontext import get_memory_context_for_file, get_memory_evidence

__all__ = [
    "filter_findings_for_memory",
    "auto_store_findings",
    "check_consolidation_trigger",
    "cross_domain_steer",
    "get_memory_context_for_file",
    "get_memory_evidence",
]
