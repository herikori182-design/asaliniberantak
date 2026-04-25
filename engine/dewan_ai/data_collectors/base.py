import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class CollectorError(RuntimeError):
    pass


def _repo_root() -> Path:
    # engine/dewan_ai/data_collectors/base.py -> parents[3] is py-research root
    return Path(__file__).resolve().parents[3]


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CollectorResult:
    ok: bool
    data: Dict[str, Any]
    source: str = ""
    fetched_at: float = 0.0


class FileCache:
    """
    Simple file cache with TTL to reduce external API calls.
    Fail-closed: cache miss does not hide network errors.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        root = Path(os.getenv("DEWAN_AI_CACHE_DIR") or (_repo_root() / "data" / "dewan_cache"))
        self.cache_dir = cache_dir or root
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        return self.cache_dir / f"{_stable_hash(key)}.json"

    def get(self, key: str, ttl_s: int) -> Optional[Dict[str, Any]]:
        try:
            path = self._path_for_key(key)
            if not path.exists():
                return None
            obj = json.loads(path.read_text(encoding="utf-8"))
            ts = float(obj.get("_ts") or 0.0)
            if ttl_s > 0 and (time.time() - ts) > ttl_s:
                return None
            return obj.get("data")
        except Exception:
            return None

    def get_entry(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Return cached entry with timestamp, ignoring TTL.
        Shape: {"_ts": <float>, "data": <any>}
        """
        try:
            path = self._path_for_key(key)
            if not path.exists():
                return None
            obj = json.loads(path.read_text(encoding="utf-8"))
            return {"_ts": float(obj.get("_ts") or 0.0), "data": obj.get("data")}
        except Exception:
            return None

    def get_any(self, key: str) -> Optional[Any]:
        """Return cached data ignoring TTL (best-effort)."""
        entry = self.get_entry(key)
        if not entry:
            return None
        return entry.get("data")

    def set(self, key: str, data: Dict[str, Any]):
        try:
            path = self._path_for_key(key)
            payload = {"_ts": time.time(), "data": data}
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


class BaseCollector:
    def __init__(self, timeout_s: float = 20.0, cache: Optional[FileCache] = None):
        self.timeout_s = float(timeout_s)
        self.cache = cache or FileCache()
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def aclose(self):
        if self._client is None:
            return
        try:
            await self._client.aclose()
        except Exception:
            pass
        self._client = None
