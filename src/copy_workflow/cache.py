from __future__ import annotations

import hashlib
import json
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
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> Any | None:
        p = self.path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: Any) -> None:
        self.path(key).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
