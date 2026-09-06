"""Project-scoped durable runtime state for the Memory Domain.

Runtime state is intentionally separate from the portable Python source.  A
scope is derived from the project root (or an explicit stable scope name), so
one copied tool can analyze multiple projects without mixing their memories.

The module only uses the Python standard library.  JSON writes are serialized
between processes, written through ``os.replace``, kept at mode ``0600``, and
retain one last-known-good backup for recovery.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional


_SCRIPT_DIR = Path(__file__).resolve().parent
_TOOL_ROOT = _SCRIPT_DIR.parent
_DEFAULT_STATE_ROOT = _TOOL_ROOT / "data" / "runtime"
_SCOPE_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")

DEFAULT_LOCK_TIMEOUT_SECONDS: float = 10.0
LOCK_RETRY_INTERVAL_SECONDS: float = 0.05

_CONFIG: Dict[str, Optional[Any]] = {
    "project_root": None,
    "scope": None,
    "state_dir": None,
    "lock_timeout_seconds": None,
}
_LAST_RECOVERY: Dict[str, Dict[str, Any]] = {}


class MemoryStateError(RuntimeError):
    """Base class for durable-state failures visible to CLI callers."""

    error_code = "memory_state_error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.details = details


class MemoryStateCorruptionError(MemoryStateError):
    """Raised when neither the primary JSON nor its backup is usable."""

    error_code = "memory_store_corrupt"


class MemoryStateLockTimeoutError(MemoryStateError, TimeoutError):
    """Raised when acquiring the runtime lock exceeds the deadline."""

    error_code = "memory_lock_timeout"


def configure_memory_runtime(
    project_root: Optional[str] = None,
    scope: Optional[str] = None,
    state_dir: Optional[str] = None,
    lock_timeout_seconds: Optional[float] = None,
) -> Dict[str, Any]:
    """Configure this process; environment variables remain the default API."""
    if project_root is not None:
        _CONFIG["project_root"] = project_root
    if scope is not None:
        _CONFIG["scope"] = scope
    if state_dir is not None:
        _CONFIG["state_dir"] = state_dir
    if lock_timeout_seconds is not None:
        _CONFIG["lock_timeout_seconds"] = lock_timeout_seconds
    return get_memory_runtime_paths(create=False)


def reset_memory_runtime_configuration() -> None:
    """Reset process-local overrides (primarily useful for isolated tests)."""
    for key in _CONFIG:
        _CONFIG[key] = None


def _configured_value(config_key: str, env_key: str) -> Optional[str]:
    value = _CONFIG.get(config_key) or os.environ.get(env_key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _scope_slug(value: str) -> str:
    slug = _SCOPE_SLUG_RE.sub("-", value.strip()).strip("-._")
    return (slug or "project")[:40]


def _chmod_if_possible(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # Some filesystems (notably Windows mounts) do not expose POSIX modes.
        pass


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    _chmod_if_possible(path, 0o700)


def get_memory_runtime_paths(create: bool = True) -> Dict[str, Any]:
    """Resolve deterministic project scope and every runtime-state path."""
    state_dir_value = _configured_value("state_dir", "AI_STUDIO_STATE_DIR")
    state_root = Path(state_dir_value).expanduser() if state_dir_value else _DEFAULT_STATE_ROOT
    state_root = state_root.resolve()

    project_value = _configured_value("project_root", "AI_STUDIO_PROJECT_ROOT")
    project_root = Path(project_value).expanduser() if project_value else Path.cwd()
    project_root = project_root.resolve()

    explicit_scope = _configured_value("scope", "AI_STUDIO_MEMORY_SCOPE")
    if explicit_scope:
        identity = f"named:{explicit_scope}"
        display_name = explicit_scope
        scope_kind = "explicit"
    else:
        identity = f"path:{project_root}"
        display_name = project_root.name or "project"
        scope_kind = "project_path"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    scope_id = f"{_scope_slug(display_name)}-{digest}"
    scope_dir = state_root / "scopes" / scope_id
    archive_dir = scope_dir / "fiber_archive"

    if create:
        _ensure_directory(state_root)
        _ensure_directory(state_root / "scopes")
        _ensure_directory(scope_dir)
        _ensure_directory(archive_dir)

    return {
        "state_root": str(state_root),
        "scope_dir": str(scope_dir),
        "scope_id": scope_id,
        "scope_kind": scope_kind,
        "scope_name": display_name,
        "project_root": str(project_root),
        "store_path": str(scope_dir / "memory_store.json"),
        "recall_cache_path": str(scope_dir / "recall_projection_cache.json"),
        "recall_cells_dir": str(scope_dir / "recall_projection_cells"),
        "baseline_path": str(scope_dir / "memory_baseline.json"),
        "consolidation_log_path": str(scope_dir / "consolidation_log.json"),
        "fiber_state_path": str(scope_dir / "fiber_state.json"),
        "fiber_archive_dir": str(archive_dir),
        "lock_path": str(scope_dir / "runtime.lock"),
    }


def _resolve_lock_timeout(override: Optional[float] = None) -> float:
    if override is not None:
        try:
            val = float(override)
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass
    configured = _CONFIG.get("lock_timeout_seconds")
    if configured is not None:
        try:
            val = float(configured)
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass
    env_val = os.environ.get("AI_STUDIO_LOCK_TIMEOUT_SECONDS")
    if env_val:
        try:
            val = float(env_val.strip())
            if val > 0:
                return val
        except (TypeError, ValueError):
            pass
    return DEFAULT_LOCK_TIMEOUT_SECONDS


def _acquire_platform_lock(
    fd: int,
    timeout_seconds: Optional[float] = None,
    lock_path: Optional[str] = None,
) -> Callable[[], None]:
    timeout = _resolve_lock_timeout(timeout_seconds)
    deadline = time.time() + timeout

    try:
        import fcntl  # type: ignore

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lambda: fcntl.flock(fd, fcntl.LOCK_UN)
            except (BlockingIOError, OSError) as err:
                if time.time() >= deadline:
                    raise MemoryStateLockTimeoutError(
                        f"Gagal memperoleh lock runtime memori dalam batas waktu aman ({timeout:.1f} detik).",
                        timeout_seconds=timeout,
                        lock_path=lock_path,
                    ) from err
                remaining = deadline - time.time()
                time.sleep(min(LOCK_RETRY_INTERVAL_SECONDS, max(0.001, remaining)))
    except ImportError:
        import msvcrt  # type: ignore

        os.lseek(fd, 0, os.SEEK_SET)
        if os.fstat(fd).st_size == 0:
            try:
                os.write(fd, b"0")
                os.fsync(fd)
            except OSError:
                pass

        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError as err:
                if time.time() >= deadline:
                    raise MemoryStateLockTimeoutError(
                        f"Gagal memperoleh lock runtime memori dalam batas waktu aman ({timeout:.1f} detik).",
                        timeout_seconds=timeout,
                        lock_path=lock_path,
                    ) from err
                remaining = deadline - time.time()
                time.sleep(min(LOCK_RETRY_INTERVAL_SECONDS, max(0.001, remaining)))

        def release() -> None:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass

        return release


@contextlib.contextmanager
def memory_runtime_lock(
    resolved_paths: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[float] = None,
) -> Iterator[Dict[str, Any]]:
    """Serialize one scope, optionally pinned for a deferred lazy reader."""
    paths = resolved_paths or get_memory_runtime_paths(create=True)
    _ensure_directory(Path(paths["scope_dir"]))
    lock_path = Path(paths["lock_path"])
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    _chmod_if_possible(lock_path, 0o600)
    try:
        release = _acquire_platform_lock(
            fd,
            timeout_seconds=timeout_seconds,
            lock_path=str(lock_path),
        )
    except Exception:
        os.close(fd)
        raise

    try:
        yield paths
    finally:
        try:
            release()
        finally:
            os.close(fd)


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    _ensure_directory(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
        _chmod_if_possible(path, 0o600)
        _fsync_directory(path.parent)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def write_json_unlocked(
    path_value: str,
    payload: Any,
    *,
    retain_backup: bool = True,
    compact: bool = False,
) -> None:
    """Atomically write JSON. Caller must hold ``memory_runtime_lock``."""
    path = Path(path_value)
    if retain_backup and path.is_file():
        previous = path.read_bytes()
        _atomic_write_bytes(Path(f"{path}.bak"), previous)
    serialized = json.dumps(
        payload,
        indent=None if compact else 2,
        ensure_ascii=False,
        separators=(",", ":") if compact else None,
    ).encode("utf-8")
    _atomic_write_bytes(path, serialized)


def write_bytes_unlocked(path_value: str, payload: bytes) -> None:
    """Atomically write owner-only bytes while the caller holds the lock."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    _atomic_write_bytes(Path(path_value), payload)


def _load_and_validate(
    path: Path,
    validator: Optional[Callable[[Any], None]],
) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if validator is not None:
        validator(payload)
    return payload


def _quarantine_path(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = path.with_name(f"{path.stem}.corrupt.{timestamp}.{uuid.uuid4().hex[:8]}{path.suffix}")
    os.replace(str(path), str(quarantine))
    _chmod_if_possible(quarantine, 0o600)
    return quarantine


def read_json_unlocked(
    path_value: str,
    default_factory: Callable[[], Any],
    validator: Optional[Callable[[Any], None]] = None,
) -> Any:
    """Read JSON with last-known-good recovery. Caller holds the scope lock."""
    path = Path(path_value)
    if not path.is_file():
        backup = Path(f"{path}.bak")
        if not backup.exists():
            return default_factory()
        try:
            recovered = _load_and_validate(backup, validator)
        except Exception as backup_error:
            raise MemoryStateCorruptionError(
                f"Memory state primary is missing and its backup is invalid: {path}",
                store_path=str(path),
                backup_path=str(backup),
                quarantined_path=None,
                primary_error="primary_missing",
                backup_error=str(backup_error),
                blocked_until_repaired=True,
            ) from backup_error
        write_json_unlocked(str(path), recovered, retain_backup=False)
        _LAST_RECOVERY[str(path)] = {
            "status": "recovered_missing_primary_from_backup",
            "recovered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "backup_path": str(backup),
            "quarantined_path": None,
            "primary_error": "primary_missing",
        }
        return recovered
    try:
        payload = _load_and_validate(path, validator)
        _LAST_RECOVERY.pop(str(path), None)
        return payload
    except Exception as primary_error:
        backup = Path(f"{path}.bak")
        try:
            recovered = _load_and_validate(backup, validator)
        except Exception as backup_error:
            raise MemoryStateCorruptionError(
                f"Memory state is corrupt and no valid backup is available: {path}",
                store_path=str(path),
                backup_path=str(backup),
                quarantined_path=None,
                primary_error=str(primary_error),
                backup_error=str(backup_error),
                blocked_until_repaired=True,
            ) from primary_error

        quarantined = _quarantine_path(path)
        write_json_unlocked(str(path), recovered, retain_backup=False)
        _LAST_RECOVERY[str(path)] = {
            "status": "recovered_from_backup",
            "recovered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "backup_path": str(backup),
            "quarantined_path": str(quarantined) if quarantined else None,
            "primary_error": str(primary_error),
        }
        return recovered


def load_json_state(
    path_value: str,
    default_factory: Callable[[], Any],
    validator: Optional[Callable[[Any], None]] = None,
    *,
    timeout_seconds: Optional[float] = None,
) -> Any:
    with memory_runtime_lock(timeout_seconds=timeout_seconds):
        return read_json_unlocked(path_value, default_factory, validator)


def save_json_state(
    path_value: str,
    payload: Any,
    *,
    timeout_seconds: Optional[float] = None,
) -> None:
    with memory_runtime_lock(timeout_seconds=timeout_seconds):
        write_json_unlocked(path_value, payload)


def memory_runtime_provenance() -> Dict[str, Any]:
    paths = get_memory_runtime_paths(create=True)
    store_path = paths["store_path"]
    return {
        "state_root": paths["state_root"],
        "scope_id": paths["scope_id"],
        "scope_kind": paths["scope_kind"],
        "scope_name": paths["scope_name"],
        "project_root": paths["project_root"],
        "store_path": store_path,
        "recall_cache_path": paths["recall_cache_path"],
        "recall_cells_dir": paths["recall_cells_dir"],
        "recovery": _LAST_RECOVERY.get(store_path, {"status": "none"}),
        "storage_claim": "project-scoped local JSON runtime; not model memory",
    }


__all__ = [
    "DEFAULT_LOCK_TIMEOUT_SECONDS",
    "LOCK_RETRY_INTERVAL_SECONDS",
    "MemoryStateError",
    "MemoryStateCorruptionError",
    "MemoryStateLockTimeoutError",
    "configure_memory_runtime",
    "reset_memory_runtime_configuration",
    "get_memory_runtime_paths",
    "memory_runtime_lock",
    "read_json_unlocked",
    "write_bytes_unlocked",
    "write_json_unlocked",
    "load_json_state",
    "save_json_state",
    "memory_runtime_provenance",
]
