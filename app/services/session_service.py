"""
Redis Session Manager

Her kullanıcı konuşması bir session'dır.
Fallback akışının state'i Redis'te tutulur.

Key yapısı:
    session:{session_id}:fallback  → fallback state (JSON)

TTL: 1800 saniye (30 dakika)
"""
import json
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings


# ─── Redis client singleton ───────────────────────────────────────────────────
_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


# ─── Key yardımcıları ────────────────────────────────────────────────────────
def _fallback_key(session_id: str) -> str:
    return f"session:{session_id}:fallback"


# ─── Fallback state işlemleri ────────────────────────────────────────────────
async def get_fallback_state(session_id: str) -> dict | None:
    """
    Aktif fallback session varsa state'i döner, yoksa None.
    """
    r = await get_redis()
    raw = await r.get(_fallback_key(session_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set_fallback_state(session_id: str, state: dict) -> None:
    """
    Fallback state'i Redis'e yazar. TTL otomatik ayarlanır.
    """
    r = await get_redis()
    await r.setex(
        _fallback_key(session_id),
        settings.session_ttl,
        json.dumps(state, ensure_ascii=False),
    )


async def delete_fallback_state(session_id: str) -> None:
    """
    Fallback tamamlandığında session'ı sil.
    """
    r = await get_redis()
    await r.delete(_fallback_key(session_id))


async def has_active_fallback(session_id: str) -> bool:
    """
    Aktif fallback session var mı?
    """
    r = await get_redis()
    return await r.exists(_fallback_key(session_id)) == 1

async def mark_fallback_completed(session_id: str) -> None:
    """Fallback bu session'da tamamlandı olarak işaretle."""
    r = await get_redis()
    await r.setex(
        f"session:{session_id}:fallback_done",
        settings.session_ttl,
        "1",
    )

async def is_fallback_completed(session_id: str) -> bool:
    """Bu session'da fallback daha önce tamamlandı mı?"""
    r = await get_redis()
    return await r.exists(f"session:{session_id}:fallback_done") == 1