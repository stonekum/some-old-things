from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any


def cache_key(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:32]


class JSONCache:
    """sha256-keyed JSON cache on disk. One file per key."""

    def __init__(self, root: Path) -> None:
        self.root = root
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self.path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Any) -> None:
        final_path = self.path(key)
        tmp_path = self.root / f".{key}.{uuid.uuid4().hex}.tmp"
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp_path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp_path, final_path)
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
