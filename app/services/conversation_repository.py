"""Gorusme kayitlari — panelin izleme gorunumu icin (salt-okunur).

Bir turdaki user ve bot mesajlari ayri INSERT'lerle (farkli created_at) yazilir.
Bu yuzden her konusma (conversation) icinde mesajlari sirayla gezip LAG ile her
bot cevabini kendinden onceki user sorusuyla eslestiririz.

status filtresi:
  - answered   : bot gercek bir cevap verdi (k1_keyword / k2_similarity)
  - unanswered : bot bilemedi, iletisim toplamaya gecti (fallback)
  - all        : hepsi
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.core.context import TenantContext

_ANSWERED = ("k1_keyword", "k2_similarity")
_UNANSWERED = ("fallback",)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"Gecersiz tarih: {value!r} (YYYY-MM-DD bekleniyor)")


async def list_conversations(
    ctx: TenantContext,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str = "all",
    intent: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    df = _parse_date(date_from)
    dt = _parse_date(date_to)

    inner_where: list[str] = []
    params: list[Any] = []
    if df is not None:
        params.append(df)
        inner_where.append(f"m.created_at >= ${len(params)}::date")
    if dt is not None:
        params.append(dt)
        inner_where.append(f"m.created_at < (${len(params)}::date + INTERVAL '1 day')")
    inner_where_sql = ("WHERE " + " AND ".join(inner_where)) if inner_where else ""

    status_sql = ""
    if status == "answered":
        status_sql = "AND t.source IN ('k1_keyword', 'k2_similarity')"
    elif status == "unanswered":
        status_sql = "AND t.source = 'fallback'"

    intent_sql = ""
    if intent:
        params.append(intent)
        intent_sql = f"AND t.intent = ${len(params)}"

    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)

    # Bir turdaki user ve bot mesajlari AYRI transaction'larda (farkli NOW()) yazildigi
    # icin created_at'e gore gruplanamaz. Bunun yerine her konusma icinde sirayla
    # ilerleyip (LAG) her bot mesajini kendinden onceki user mesajiyla eslestiririz.
    query = f"""
        SELECT
            t.ts, t.session_id,
            CASE WHEN t.prev_role = 'user' THEN t.question END AS question,
            t.answer, t.intent, t.source, t.response_ms,
            COUNT(*) OVER() AS total
        FROM (
            SELECT
                m.created_at AS ts,
                c.session_id AS session_id,
                m.content AS answer,
                m.intent AS intent,
                m.source AS source,
                m.response_ms AS response_ms,
                m.role AS role,
                LAG(m.content) OVER w AS question,
                LAG(m.role)    OVER w AS prev_role
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            {inner_where_sql}
            WINDOW w AS (
                PARTITION BY m.conversation_id
                ORDER BY m.created_at, m.role DESC
            )
        ) t
        WHERE t.role = 'bot' {status_sql} {intent_sql}
        ORDER BY t.ts DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    total = rows[0]["total"] if rows else 0
    items = []
    for r in rows:
        d = dict(r)
        d.pop("total", None)
        d["answered"] = d.get("source") in _ANSWERED
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def list_conversation_intents(ctx: TenantContext) -> list[str]:
    """Gorusmelerde fiilen gecen intent (kategori) degerleri — filtre acilir listesi icin."""
    query = """
        SELECT DISTINCT intent
        FROM messages
        WHERE role = 'bot' AND intent IS NOT NULL AND intent <> ''
        ORDER BY intent
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [r["intent"] for r in rows]


# ─── İletişim talepleri (fallback_contacts) — panelde gösterim/yönetim ──────────
_CONTACT_STATUSES = ("new", "contacted", "closed")


async def list_contacts(
    ctx: TenantContext,
    status: str = "all",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Bot cevap bulamayinca toplanan iletisim taleplerini listeler (yeni once)."""
    params: list[Any] = []
    where = ""
    if status in _CONTACT_STATUSES:
        params.append(status)
        where = f"WHERE status = ${len(params)}::contact_status"
    params.append(limit)
    li = len(params)
    params.append(offset)
    oi = len(params)
    query = f"""
        SELECT id, session_id, name, contact_type, contact_value, status, created_at,
               COUNT(*) OVER() AS total
        FROM fallback_contacts
        {where}
        ORDER BY created_at DESC
        LIMIT ${li} OFFSET ${oi}
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    total = rows[0]["total"] if rows else 0
    items = []
    for r in rows:
        d = dict(r)
        d.pop("total", None)
        d["id"] = str(d["id"])
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def count_contacts(ctx: TenantContext, status: str | None = None) -> int:
    """Belirli durumdaki (veya tum) iletisim talebi sayisi — istatistik kartlari icin."""
    if status in _CONTACT_STATUSES:
        q = "SELECT COUNT(*) FROM fallback_contacts WHERE status = $1::contact_status"
        args = (status,)
    else:
        q = "SELECT COUNT(*) FROM fallback_contacts"
        args = ()
    async with ctx.pool.acquire() as conn:
        return int(await conn.fetchval(q, *args) or 0)


async def set_contact_status(ctx: TenantContext, contact_id: str, status: str) -> dict[str, Any]:
    """Bir iletisim talebinin durumunu gunceller (new/contacted/closed)."""
    if status not in _CONTACT_STATUSES:
        raise ValueError(f"Gecersiz durum: {status!r}")
    async with ctx.pool.acquire() as conn:
        res = await conn.execute(
            "UPDATE fallback_contacts SET status = $2::contact_status WHERE id = $1::uuid",
            contact_id, status,
        )
    if res.endswith(" 0"):
        raise ValueError("Kayit bulunamadi")
    return {"ok": True, "id": contact_id, "status": status}