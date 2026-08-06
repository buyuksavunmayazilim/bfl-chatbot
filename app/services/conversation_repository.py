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
        WHERE t.role = 'bot' {status_sql}
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