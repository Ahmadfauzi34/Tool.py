"""
Core Domain — Shared Infrastructure, Registry, Synthesizer & Safety
"""

from core.shared_graph import (
    build_shared_graph,
    discover_source_files,
    graph_content_signature,
    DEFAULT_IGNORE_DIRS,
    SOURCE_EXTENSIONS,
)
from core.graph_cache import (
    CACHE_MODES,
    build_cached_shared_graph,
    clear_graph_cache,
    get_graph_cache_status,
)
from core.analyzer_cache import (
    run_cached_analyzers,
    clear_analyzer_cache,
    get_analyzer_cache_status,
)
from core.analyzer_registry import (
    ANALYZER_REGISTRY,
    register_analyzer,
    run_analyzers,
    get_available_analyzers,
)
from core.synthesizer import (
    synthesize_topological_integrity,
    encode_topological_invariants,
    establish_baseline,
    load_baseline,
    steer_decoder,
)
from core.context_optimizer import build_context_pack
from core.safety import (
    check_memory_association_safety,
    check_betti_preservation,
    check_fiber_state_safety,
)
from core.deprecation import (
    deprecated_tool,
    DEPRECATION_MAP,
)

__all__ = [
    "build_shared_graph",
    "discover_source_files",
    "graph_content_signature",
    "DEFAULT_IGNORE_DIRS",
    "SOURCE_EXTENSIONS",
    "CACHE_MODES",
    "build_cached_shared_graph",
    "clear_graph_cache",
    "get_graph_cache_status",
    "run_cached_analyzers",
    "clear_analyzer_cache",
    "get_analyzer_cache_status",
    "ANALYZER_REGISTRY",
    "register_analyzer",
    "run_analyzers",
    "get_available_analyzers",
    "synthesize_topological_integrity",
    "encode_topological_invariants",
    "establish_baseline",
    "load_baseline",
    "steer_decoder",
    "build_context_pack",
    "check_memory_association_safety",
    "check_betti_preservation",
    "check_fiber_state_safety",
    "deprecated_tool",
    "DEPRECATION_MAP",
]
