"""
Codebase Domain — Structural & Performance Analysis (Layer 1)
"""

from codebase.performance_analyzers import (
    analyze_async_waterfall,
    analyze_deopt,
    analyze_gc_pressure,
    analyze_cache,
)
from codebase.hott_analyzers import (
    analyze_isomorphism,
    analyze_sheaf,
    analyze_homotopy,
    analyze_manifold as analyze_codebase_manifold,
)
from codebase.topology_analyzers import (
    analyze_circular as analyze_codebase_circular,
    analyze_risk,
    query_impact,
    query_outline,
    query_brief,
    analyze_cycle_breaks,
)


def analyze_orphan(shared_graph):
    """Lazy registry adapter untuk menghindari circular import saat bootstrap."""
    from core.analyzer_registry import analyze_orphan as _analyze_orphan

    return _analyze_orphan(shared_graph)


def analyze_entrypoint_impact(shared_graph):
    """Lazy registry adapter untuk menghindari circular import saat bootstrap."""
    from core.analyzer_registry import analyze_entrypoint_impact as _analyze_entrypoint_impact

    return _analyze_entrypoint_impact(shared_graph)

__all__ = [
    "analyze_async_waterfall",
    "analyze_deopt",
    "analyze_gc_pressure",
    "analyze_cache",
    "analyze_isomorphism",
    "analyze_sheaf",
    "analyze_homotopy",
    "analyze_codebase_manifold",
    "analyze_orphan",
    "analyze_entrypoint_impact",
    "analyze_codebase_circular",
    "analyze_risk",
    "query_impact",
    "query_outline",
    "query_brief",
    "analyze_cycle_breaks",
]
