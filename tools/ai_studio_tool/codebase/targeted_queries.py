"""
Targeted Queries — Codebase Analysis Domain
Schema Version: 3.0.0-kernel

Targeted file queries:
- impact: blast radius & impacted files
- outline: structural outline (imports, exports, types)
- brief: condensed summary for prompt injection
"""

from codebase.topology_analyzers import (
    query_impact,
    query_outline,
    query_brief,
    analyze_cycle_breaks,
)

__all__ = [
    "query_impact",
    "query_outline",
    "query_brief",
    "analyze_cycle_breaks",
]
