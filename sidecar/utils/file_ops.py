from __future__ import annotations

import os
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Union

from loguru import logger

DEFAULT_RETRIES = 2
DEFAULT_DELAY = 0.5

PathLike = Union[str, Path]


class FileOpError(OSError):
    """Raised by FileOpResult.unwrap() when the caller wants a hard failure."""


@dataclass
class FileOpResult:
    """Outcome of one guarded file operation."""

    ok: bool
    path: str
    label: str = ""
    error: Optional[str] = None
    attempts: int = 1
    skipped: bool = False  # target was already gone and missing_ok was set
    locked: bool = False  # failed specifically because of PermissionError
    value: Any = None  # return value of the wrapped callable

    def unwrap(self) -> "FileOpResult":
        if not self.ok:
            raise FileOpError(self.error or f"{self.label or 'operation'} failed: {self.path}")
        return self

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "path": self.path,
            "skipped": self.skipped,
            "locked": self.locked,
            "attempts": self.attempts,
            "error": self.error,
        }


def safe_file_operation(
    op: Callable[..., Any],
    *args: Any,
    retries: int = DEFAULT_RETRIES,
    delay: float = DEFAULT_DELAY,
    label: str = "",
    missing_ok: bool = True,
    path: Optional[PathLike] = None,
    **kwargs: Any,
) -> FileOpResult:
    """
    Run `op(*args, **kwargs)` with PermissionError retries.

    PermissionError    -> log a warning, sleep(delay), retry up to `retries` times.
    FileNotFoundError  -> success with skipped=True when missing_ok, else failure.
    Other OSError      -> immediate failure, no retry (retrying won't help).

    Never raises: inspect the returned FileOpResult, or call .unwrap() to turn a
    failure into FileOpError.
    """
    target = str(path if path is not None else (args[0] if args else ""))
    name = label or getattr(op, "__name__", "file operation")
    attempts = max(1, retries + 1)

    for attempt in range(1, attempts + 1):
        try:
            value = op(*args, **kwargs)
            if attempt > 1:
                logger.info(f"{name} succeeded on attempt {attempt}: {target}")
            return FileOpResult(True, target, name, attempts=attempt, value=value)

        except FileNotFoundError:
            if missing_ok:
                logger.debug(f"{name}: already gone, nothing to do: {target}")
                return FileOpResult(True, target, name, attempts=attempt, skipped=True)
            return FileOpResult(False, target, name, error=f"Not found: {target}", attempts=attempt)

        except PermissionError as e:
            if attempt < attempts:
                logger.warning(
                    f"{name} blocked (attempt {attempt}/{attempts}), retrying in {delay}s: "
                    f"{target} — {e}"
                )
                time.sleep(delay)
                continue
            logger.error(f"{name} failed after {attempts} attempts (file locked): {target} — {e}")
            return FileOpResult(
                False,
                target,
                name,
                error=(
                    f"File is locked by another process (is Minecraft still running?): {target}"
                ),
                attempts=attempt,
                locked=True,
            )

        except OSError as e:
            logger.error(f"{name} failed: {target} — {e}")
            return FileOpResult(False, target, name, error=f"{type(e).__name__}: {e}", attempts=attempt)

    # Unreachable: the loop either returns or continues.
    return FileOpResult(False, target, name, error="Unknown failure", attempts=attempts)


def _clear_readonly(path: PathLike) -> None:
    """Windows marks some game/launcher files read-only; rmtree trips over them."""
    try:
        os.chmod(path, stat.S_IWRITE)
    except OSError:
        pass


def _rmtree_error_handler(func, path, exc_info) -> None:
    """Clear the read-only bit and retry once; re-raise so the wrapper can retry."""
    _clear_readonly(path)
    func(path)


def safe_delete(path: PathLike, *, missing_ok: bool = True, label: str = "delete", **kw: Any) -> FileOpResult:
    """Delete a single file."""
    target = Path(path)

    def _delete(*_args: Any, **_kwargs: Any) -> None:
        try:
            target.unlink()
        except PermissionError:
            _clear_readonly(target)
            target.unlink()

    return safe_file_operation(_delete, label=label, path=target, missing_ok=missing_ok, **kw)


def safe_rename(
    src: PathLike, dst: PathLike, *, overwrite: bool = False, label: str = "rename", **kw: Any
) -> FileOpResult:
    """
    Rename/move a file or directory. Used for the mod enable/disable toggle
    (`mod.jar` <-> `mod.jar.disabled`) and for renaming an instance folder.
    """
    source, dest = Path(src), Path(dst)

    def _rename(*_args: Any, **_kwargs: Any) -> None:
        if dest.exists() and not overwrite:
            raise FileExistsError(f"Target already exists: {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, dest)  # atomic on the same volume

    return safe_file_operation(_rename, label=label, path=source, missing_ok=False, **kw)


def safe_copy(src: PathLike, dst: PathLike, *, label: str = "copy", **kw: Any) -> FileOpResult:
    """Copy one file, metadata included, creating parent directories."""
    source, dest = Path(src), Path(dst)

    def _copy(*_args: Any, **_kwargs: Any) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        return shutil.copy2(source, dest)

    return safe_file_operation(_copy, label=label, path=source, missing_ok=False, **kw)


def safe_copytree(
    src: PathLike,
    dst: PathLike,
    *,
    symlinks: bool = False,
    ignore: Any = None,
    dirs_exist_ok: bool = True,
    label: str = "copytree",
    **kw: Any,
) -> FileOpResult:
    """
    Physically copy a directory tree — never symlinks or hardlinks (a cloned
    instance must be independent of its source).
    """
    source, dest = Path(src), Path(dst)

    def _copytree(*_args: Any, **copy_kw: Any) -> str:
        actual_dirs_exist_ok = copy_kw.get("dirs_exist_ok", dirs_exist_ok)
        actual_symlinks = copy_kw.get("symlinks", symlinks)
        actual_ignore = copy_kw.get("ignore", ignore)
        return str(
            shutil.copytree(
                source,
                dest,
                symlinks=actual_symlinks,
                ignore=actual_ignore,
                dirs_exist_ok=actual_dirs_exist_ok,
            )
        )

    return safe_file_operation(_copytree, label=label, path=source, missing_ok=False, **kw)


def safe_rmtree(path: PathLike, *, missing_ok: bool = True, label: str = "rmtree", **kw: Any) -> FileOpResult:
    """Delete a directory tree, clearing read-only flags as it goes."""
    target = Path(path)

    def _rmtree(*_args: Any, **_kwargs: Any) -> None:
        if sys.version_info >= (3, 12):
            shutil.rmtree(target, onexc=lambda f, p, e: _rmtree_error_handler(f, p, e))
        else:  # pragma: no cover - kept for older interpreters
            shutil.rmtree(target, onerror=_rmtree_error_handler)

    return safe_file_operation(_rmtree, label=label, path=target, missing_ok=missing_ok, **kw)


def safe_write_text(
    path: PathLike, content: str, *, encoding: str = "utf-8", label: str = "write", **kw: Any
) -> FileOpResult:
    """Write text atomically: temp file in the same directory, then os.replace."""
    target = Path(path)

    def _write(*_args: Any, **_kwargs: Any) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(content, encoding=encoding)
        os.replace(tmp, target)

    return safe_file_operation(_write, label=label, path=target, missing_ok=False, **kw)
