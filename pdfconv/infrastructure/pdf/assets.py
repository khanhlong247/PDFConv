from __future__ import annotations

import hashlib
import threading
from pathlib import Path


class AssetWriter:
    def __init__(self, root: Path, subdir: str = "images"):
        self.root = Path(root)
        self.subdir = subdir
        (self.root / subdir).mkdir(parents=True, exist_ok=True)
        self._by_digest: dict[str, str] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def save(self, data: bytes, ext: str, prefix: str = "img") -> tuple[str, str]:
        digest = hashlib.sha1(data).hexdigest()
        with self._lock:
            if digest in self._by_digest:
                return self._by_digest[digest], digest
            self._counter += 1
            rel = f"{self.subdir}/{prefix}_{self._counter:04d}.{ext.lstrip('.')}"
            (self.root / rel).write_bytes(data)
            self._by_digest[digest] = rel
            return rel, digest

    def path(self, rel: str) -> Path:
        return self.root / rel
