"""JSON cache files keyed by a fingerprint, written atomically under one directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sql_rag_util.atomic import atomic_write_text
from sql_rag_util.exceptions import MetadataPathError

if TYPE_CHECKING:
    import os

__all__ = ["JsonCache"]

_SUFFIX = ".json"


class JsonCache:
    """Named JSON payloads that are only valid for one fingerprint.

    Parameters
    ----------
    directory
        Where files live. Created on first write.
    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._directory = Path(directory).resolve()

    def _path(self, name: str) -> Path:
        if not name.isidentifier():
            raise MetadataPathError(f"cache name {name!r} is not an identifier")
        path = (self._directory / f"{name}{_SUFFIX}").resolve()
        if path.parent != self._directory:
            raise MetadataPathError(f"cache path for {name!r} escapes the cache directory")
        return path

    def load(self, name: str, fingerprint: str) -> Any | None:
        """Return the payload saved for ``name`` when its fingerprint matches, else ``None``."""
        path = self._path(name)
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(document, dict) or document.get("fingerprint") != fingerprint:
            return None
        return document.get("payload")

    def save(self, name: str, fingerprint: str, payload: Any) -> Path:
        """Write ``payload`` for ``name`` under ``fingerprint`` and return the path."""
        path = self._path(name)
        atomic_write_text(path, json.dumps({"fingerprint": fingerprint, "payload": payload}, separators=(",", ":"), ensure_ascii=False))
        return path
