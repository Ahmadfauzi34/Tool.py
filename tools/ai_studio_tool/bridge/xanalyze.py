"""
Cross-Domain Analysis & Auto-Store — HoTT Kernel Bridge Domain
Schema Version: 4.1.0-memory
"""

import os
import json
import hashlib
import datetime
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "4.1.0-memory"

CONSOLIDATION_EPISODIC_THRESHOLD = 15
CONSOLIDATION_BETA0_THRESHOLD = 5
CRITICAL_IMPACT_FAN_IN_THRESHOLD = 3


def _stable_finding_subject(
    finding: Dict[str, Any],
    analyzer: Optional[str] = None,
    default_scope: Optional[str] = None,
) -> str:
    """Build logical identity from structured evidence, not prose/severity.
    
    Anti-churn invariant: Fallback identity must depend strictly on structured
    logical coordinates (analyzer_name, finding_type, target_scope) and never on
    free prose/observation text, ensuring redactorial changes result in in-place
    revisions rather than orphaned memory bloat.
    """
    file_path = str(finding.get("file", "")).replace("\\", "/")
    if file_path:
        return f"file:{file_path}"
    structured: Dict[str, Any] = {}
    for key in (
        "files", "related_files", "path", "cycle", "source", "target", "entrypoint",
        "boundary", "type_name", "name", "invariant", "dimension", "scope",
    ):
        value = finding.get(key)
        if value not in (None, "", []):
            structured[key] = sorted(value) if isinstance(value, list) else value
    if structured:
        encoded = json.dumps(structured, sort_keys=True, separators=(",", ":"))
        return f"structured:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"

    analyzer_name = str(
        analyzer
        or finding.get("source_analyzer")
        or finding.get("analyzer")
        or "global"
    )
    finding_type = str(
        finding.get("type")
        or finding.get("finding_type")
        or "general"
    )
    target_scope = str(
        finding.get("file")
        or finding.get("scope")
        or finding.get("boundary")
        or finding.get("target")
        or finding.get("invariant")
        or default_scope
        or "project"
    ).replace("\\", "/")

    fallback_payload = {
        "analyzer": analyzer_name,
        "type": finding_type,
        "scope": target_scope,
    }
    encoded = json.dumps(fallback_payload, sort_keys=True, separators=(",", ":"))
    return f"fallback:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


def _storeable_finding(
    analyzer: str,
    finding: Dict[str, Any],
    category: str,
) -> Dict[str, Any]:
    return {
        "source_analyzer": analyzer,
        "finding_type": finding.get("type", "unknown"),
        "severity": finding.get("severity", "info"),
        "file": finding.get("file", ""),
        "related_files": sorted(str(item) for item in finding.get("files", [])),
        "content": finding.get("observation", ""),
        "category": category,
        "stable_subject": _stable_finding_subject(finding, analyzer=analyzer),
    }


def filter_findings_for_memory(
    analyzer_results: Dict[str, Any],
    correlations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Filter findings berdasarkan severity dan relevansi."""
    storeable: List[Dict[str, Any]] = []

    for analyzer_name, result in analyzer_results.items():
        for finding in result.get("findings", []):
            severity = finding.get("severity", "info")

            if severity == "high":
                storeable.append(_storeable_finding(
                    analyzer_name, finding, "high_severity_finding"
                ))
            elif severity == "medium":
                ftype = finding.get("type", "")
                if ftype in ("circular_dependency", "entrypoint_high_risk", "change_risk"):
                    storeable.append(_storeable_finding(
                        analyzer_name, finding, "critical_medium_finding"
                    ))

    for corr in correlations:
        storeable.append(_storeable_finding(
            "cross_analyzer", corr, "cross_analyzer_correlation"
        ))

    return storeable


def auto_store_findings(
    storeable_findings: List[Dict[str, Any]],
    scan_root: str = "src",
    evidence_signature: Optional[str] = None,
    graph_content_signature: Optional[str] = None,
    active_files: Optional[Iterable[str]] = None,
    file_content_hashes: Optional[Dict[str, str]] = None,
    analyzers_observed: Optional[Iterable[str]] = None,
    analyzers_failed: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Atomically reconcile analyzer observations by logical identity."""
    try:
        from memory.store import upsert_memory_observations
        from memory.runtime import memory_runtime_provenance
    except ImportError:
        try:
            from memory_store import upsert_memory_observations
            from memory_runtime import memory_runtime_provenance
        except ImportError:
            return {"error": "memory_store not available", "stored_count": 0}

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    runtime = memory_runtime_provenance()
    scope_id = runtime["scope_id"]
    project_root = str(runtime.get("project_root", os.getcwd()))
    absolute_scan_root = os.path.abspath(scan_root)
    try:
        scan_scope = os.path.relpath(absolute_scan_root, project_root).replace("\\", "/")
    except ValueError:
        scan_scope = absolute_scan_root.replace("\\", "/")
    if scan_scope == ".":
        scan_scope = "project"
    normalized_hashes = {
        str(path).replace("\\", "/"): str(value)
        for path, value in (file_content_hashes or {}).items()
    }
    observed_analyzers = sorted({
        str(name) for name in (analyzers_observed or []) if name
    } | {"cross_analyzer"})
    reconcile_namespaces = [
        f"xanalyze:{scan_scope}:{name}" for name in observed_analyzers
    ]
    stale_namespaces = [
        f"xanalyze:{scan_scope}:{name}"
        for name in sorted({
            str(name) for name in (analyzers_failed or []) if name
        })
    ]
    observations: List[Dict[str, Any]] = []

    for finding in storeable_findings:
        content = (
            f"[{finding['category']}] "
            f"{finding['finding_type']} di {finding['file'] or scan_root}: "
            f"{finding['content']}"
        )

        tags = [
            finding["category"],
            finding["source_analyzer"],
            finding["severity"],
        ]
        if finding["file"]:
            file_dir = os.path.dirname(finding["file"])
            if file_dir:
                tags.append(file_dir.replace("/", "."))

        stable_subject = finding.get("stable_subject") or _stable_finding_subject(
            finding,
            analyzer=finding.get("source_analyzer"),
            default_scope=scan_scope,
        )

        context = {
            "scan_root": scan_root,
            "scan_scope": scan_scope,
            "source_analyzer": finding["source_analyzer"],
            "finding_type": finding["finding_type"],
            "severity": finding["severity"],
            "file": finding["file"],
            "related_files": finding.get("related_files", []),
            "stable_subject": stable_subject,
            "batch_timestamp": timestamp,
            "evidence_signature": graph_content_signature or evidence_signature,
            "topological_signature": evidence_signature,
            "graph_content_signature": graph_content_signature,
            "source_content_sha256": normalized_hashes.get(
                str(finding["file"]).replace("\\", "/")
            ),
            "memory_scope_id": scope_id,
            "observation_namespace": (
                f"xanalyze:{scan_scope}:{finding['source_analyzer']}"
            ),
        }
        identity_payload = {
            "scope_id": scope_id,
            "scan_scope": scan_scope,
            "category": finding["category"],
            "source_analyzer": finding["source_analyzer"],
            "finding_type": finding["finding_type"],
            "subject": stable_subject,
        }
        identity_json = json.dumps(identity_payload, sort_keys=True, separators=(",", ":"))
        dedup_key = f"finding:{hashlib.sha256(identity_json.encode('utf-8')).hexdigest()}"
        observations.append({
            "dedup_key": dedup_key,
            "memory_type": "episodic",
            "content": content,
            "source": f"hott_kernel xanalyze {scan_root}",
            "importance": 0.9 if finding["severity"] == "high" else 0.7,
            "tags": tags,
            "context": context,
        })

    result = upsert_memory_observations(
        observations,
        reconcile_namespaces=reconcile_namespaces,
        stale_namespaces=stale_namespaces,
        current_graph_signature=graph_content_signature,
        active_files=[str(path) for path in (active_files or [])],
        create_batch_links=False,
    )
    result.update({
        "status": "auto_reconciled",
        "batch_timestamp": timestamp,
        "evidence_signature": evidence_signature,
        "graph_content_signature": graph_content_signature,
        "reconciled_namespaces": reconcile_namespaces,
        "stale_namespaces": stale_namespaces,
        "memory_scope": runtime,
    })
    return result


def check_consolidation_trigger() -> Dict[str, Any]:
    """Cek apakah kondisi memori memerlukan consolidation."""
    try:
        from memory.store import load_store, is_semantically_current_memory
        from memory.graph import build_memory_graph
        from memory.analyzers import analyze_fragmentation
    except ImportError:
        try:
            from memory_store import load_store, is_semantically_current_memory
            from memory_graph import build_memory_graph
            from memory_analyzers import analyze_fragmentation
        except ImportError:
            return {"error": "memory modules not available", "trigger": False}

    store = load_store()
    memories = store.get("memories", [])
    episodic_memories = [
        memory for memory in memories
        if memory.get("type") == "episodic"
        and is_semantically_current_memory(memory)
    ]
    episodic_count = len(episodic_memories)

    unconsolidated = [
        m for m in episodic_memories
        if m.get("consolidated_into") is None
    ]
    unconsolidated_count = len(unconsolidated)

    memory_graph = build_memory_graph()
    frag_result = analyze_fragmentation(memory_graph)
    beta_0 = frag_result.get("summary", {}).get("beta_0", 0)

    isolated_episodic = [
        m for m in unconsolidated
        if memory_graph.get("node_metadata", {}).get(m["id"], {}).get("fan_in", 0) == 0
        and memory_graph.get("node_metadata", {}).get(m["id"], {}).get("fan_out", 0) == 0
    ]

    triggers: List[str] = []
    if unconsolidated_count >= CONSOLIDATION_EPISODIC_THRESHOLD:
        triggers.append(f"episodic_count_exceeded: {unconsolidated_count} >= {CONSOLIDATION_EPISODIC_THRESHOLD}")
    if beta_0 > CONSOLIDATION_BETA0_THRESHOLD:
        triggers.append(f"fragmentation_exceeded: beta_0={beta_0} > {CONSOLIDATION_BETA0_THRESHOLD}")
    if len(isolated_episodic) >= 5:
        triggers.append(f"isolated_episodic_exceeded: {len(isolated_episodic)} isolated")

    return {
        "trigger": len(triggers) > 0,
        "reasons": triggers,
        "metrics": {
            "total_episodic": episodic_count,
            "unconsolidated_episodic": unconsolidated_count,
            "isolated_episodic": len(isolated_episodic),
            "beta_0": beta_0,
            "thresholds": {
                "episodic_threshold": CONSOLIDATION_EPISODIC_THRESHOLD,
                "beta0_threshold": CONSOLIDATION_BETA0_THRESHOLD,
            },
        },
        "candidate_ids": [m["id"] for m in unconsolidated[:20]],
    }
