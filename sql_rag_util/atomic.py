"""Atomic text file writes: temp file in the same directory, flush, fsync, replace."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

__all__ = ["atomic_write_text"]

_NEW_FILE_MODE = 0o666


def _existing_mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so readers see either the old or the new content.

    Lines end in ``\\n`` on every platform. A file that already exists keeps
    its permission bits; a new one gets the same mode as any file the process
    creates, which is ``0o666`` less the umask.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = _existing_mode(path)
    temp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _NEW_FILE_MODE)
    try:
        with open(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
