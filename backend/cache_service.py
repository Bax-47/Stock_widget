import json
import os
import time
from typing import List, Optional

from fastapi.encoders import jsonable_encoder
from models import StockPrice

try:
    import redis  # type: ignore
except ImportError:
    redis = None


class PriceCache:
    """
    Simple cache abstraction that prefers Redis but falls back to
    an in-memory store if Redis or the redis library isn't available.
    """

    def __init__(self, key: str = "smartstock:latest_prices"):
        self.key = key
        self.backend = "memory"
        self._memory_blob: Optional[str] = None
        self.redis_client = None

        if redis is None:
            print("[cache] redis library not installed; using in-memory cache.")
            return

        url = os.getenv("REDIS_URL")
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))

        try:
            if url:
                self.redis_client = redis.from_url(url)
            else:
                self.redis_client = redis.Redis(host=host, port=port, db=db)

            self.redis_client.ping()
            self.backend = "redis"
            print("[cache] Using Redis backend for price cache.")
        except Exception as e:
            print(f"[cache] Redis unavailable ({e}); falling back to in-memory cache.")
            self.redis_client = None
            self.backend = "memory"

    def save_prices(self, prices: List[StockPrice]) -> None:
        """
        Store latest prices as a JSON blob: { ts: unix_time, data: [...] }.
        Use jsonable_encoder so datetimes & Pydantic models become JSON-safe.
        """
        blob = {
            "ts": time.time(),
            "data": jsonable_encoder(prices),  # <- handles datetime & BaseModel
        }
        raw = json.dumps(blob)

        # Always keep an in-memory copy
        self._memory_blob = raw

        if self.redis_client is None:
            return

        try:
            self.redis_client.set(self.key, raw)
        except Exception as e:
            print(f"[cache] Failed to write to Redis, keeping in-memory only: {e}")

    def load_prices(self, max_age_seconds: int) -> Optional[List[StockPrice]]:
        """
        Return cached prices if they are not older than max_age_seconds.
        Otherwise return None to signal 'cache miss / stale'.
        """
        raw = None

        if self.redis_client is not None:
            try:
                value = self.redis_client.get(self.key)
                if value is not None:
                    raw = value.decode("utf-8")
            except Exception as e:
                print(f"[cache] Redis read failed, falling back to memory: {e}")

        if raw is None and self._memory_blob is not None:
            raw = self._memory_blob

        if raw is None:
            return None

        try:
            blob = json.loads(raw)
            ts = blob.get("ts")
            data = blob.get("data", [])
            if ts is None:
                return None

            age = time.time() - float(ts)
            if age > max_age_seconds:
                return None  # stale

            return [StockPrice(**item) for item in data]
        except Exception as e:
            print(f"[cache] Failed to parse cached data, ignoring cache: {e}")
            return None
