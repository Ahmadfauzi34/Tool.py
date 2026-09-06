"""
Deprecation Layer — HoTT Kernel
Schema Version: 3.0.0-kernel

Menyediakan utility untuk menandai standalone tools sebagai deprecated
tanpa menghapus fungsionalitasnya. Tool lama tetap berjalan, tapi
mengeluarkan warning yang mengarahkan ke hott_kernel.

Penggunaan di tool lama:
    from deprecation import deprecated_tool
    deprecated_tool("async_waterfall_detector.py", "hott_kernel.py analyze src --analyzers perf.async")
"""

import sys
import json
from typing import Optional

# Mapping tool lama → equivalent kernel command
DEPRECATION_MAP = {
    "file_scanner.py": {
        "default": "hott_kernel.py analyze src --output graph",
        "impact": "hott_kernel.py impact <file> src",
        "outline": "hott_kernel.py outline <file> src",
    },
    "async_waterfall_detector.py": "hott_kernel.py analyze src --analyzers perf.async --output findings",
    "deopt_checker.py": "hott_kernel.py analyze src --analyzers perf.deopt --output findings",
    "gc_pressure_analyzer.py": "hott_kernel.py analyze src --analyzers perf.gc --output findings",
    "cache_auditor.py": "hott_kernel.py analyze src --analyzers perf.cache --output findings",
    "type_isomorphism_observer.py": "hott_kernel.py analyze src --analyzers hott.isomorphism --output findings",
    "boundary_sheaf_checker.py": "hott_kernel.py analyze src --analyzers hott.sheaf --output findings",
    "homotopy_path_observer.py": "hott_kernel.py analyze src --analyzers hott.homotopy --output findings",
    "topological_manifold_builder.py": "hott_kernel.py analyze src --analyzers hott.manifold --output findings",
    "topological_integrity_orchestrator.py": "hott_kernel.py synthesize src --output summary",
    "invariant_encoder.py": "hott_kernel.py synthesize src --output summary",
    "decoder_steering.py": "hott_kernel.py steer src",
}


def deprecated_tool(
    tool_name: str,
    kernel_command: Optional[str] = None,
    suppress_warning: bool = False,
) -> None:
    """
    Cetak deprecation warning ke stderr.

    Args:
        tool_name: Nama tool lama yang dipanggil
        kernel_command: Override perintah kernel (optional, auto-lookup jika None)
        suppress_warning: Jika True, tidak cetak warning (untuk testing)
    """
    if suppress_warning:
        return

    if kernel_command is None:
        cmd_mapping = DEPRECATION_MAP.get(tool_name, "hott_kernel.py analyze src")
        if isinstance(cmd_mapping, dict):
            kernel_command = cmd_mapping.get("default", "hott_kernel.py analyze src")
        else:
            kernel_command = cmd_mapping

    # Handle file_scanner.py yang punya multiple subcommands
    if tool_name == "file_scanner.py" and len(sys.argv) > 1:
        subcommand = sys.argv[1]
        mapping = DEPRECATION_MAP.get(tool_name)
        if isinstance(mapping, dict):
            kernel_command = mapping.get(
                subcommand, mapping.get("default", "hott_kernel.py analyze src")
            )

    warning = {
        "deprecation_warning": True,
        "tool": tool_name,
        "message": f"'{tool_name}' is deprecated. Use unified kernel instead.",
        "kernel_command": kernel_command,
        "note": "This tool still works for backward compatibility.",
    }

    # Cetak ke stderr agar tidak mengganggu stdout (JSON output)
    print(json.dumps(warning, indent=2), file=sys.stderr)


def get_kernel_equivalent(tool_name: str) -> Optional[str]:
    """Return equivalent kernel command untuk tool lama."""
    return DEPRECATION_MAP.get(tool_name)
