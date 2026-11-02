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

from datetime import date, datetime
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


def _parse_ts(value: str | None) -> datetime | None:
    """ISO 8601 zaman damgasini datetime'a cevirir ('Z' sonekini de kabul eder).

    asyncpg timestamptz parametresine str degil datetime verilmeli; aksi halde
    DataError (HTTP 500) olur. Cozulemezse None doner (pencere uygulanmaz)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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

    # ── Tarih filtresi: ham turlar (turns CTE) seviyesinde uygulanir ──────────
    inner_where: list[str] = []
    params: list[Any] = []
    if df is not None:
        params.append(df)
        inner_where.append(f"m.created_at >= ${len(params)}::date")
    if dt is not None:
        params.append(dt)
        inner_where.append(f"m.created_at < (${len(params)}::date + INTERVAL '1 day')")
    inner_where_sql = ("WHERE " + " AND ".join(inner_where)) if inner_where else ""

    # ── Durum/intent filtresi: birlestirilmis (collapsed) satirlara uygulanir ─
    final_where: list[str] = []
    if status == "answered":
        final_where.append("u.answered = TRUE")
    elif status == "unanswered":
        # cevaplanamadi = iletisim toplanamadan kalan fallback akislari
        final_where.append("u.source = 'fallback' AND u.answered = FALSE")
    elif status == "contact":
        final_where.append("u.contact_captured = TRUE")
    if intent:
        params.append(intent)
        final_where.append(f"u.intent = ${len(params)}")
    final_where_sql = ("WHERE " + " AND ".join(final_where)) if final_where else ""

    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)

    # İletişim toplama (fallback) akışı çok adımlıdır (ad → tercih → iletişim →
    # onay). Bu adımların HEPSİNİ tek bir satıra topluyoruz: akış bir oturumda
    # iletişim bırakılmışsa (fallback_contacts) "iletişim alındı" (başarı),
    # değilse "cevaplanamadı". Normal (k1/k2/static) turlar tek tek kalır.
    #   turns      : her bot mesajını kendinden önceki user mesajıyla eşle (LAG)
    #   individual : fallback OLMAYAN turlar (her biri ayrı satır)
    #   fb         : fallback turları konuşma başına TEK satıra indir
    #                (soru = akışı tetikleyen ilk soru, cevap = son bot mesajı)
    query = f"""
        WITH turns AS (
            SELECT
                m.created_at AS ts,
                m.conversation_id AS conversation_id,
                c.session_id AS session_id,
                m.content AS answer,
                m.intent::text AS intent,
                m.source::text AS source,
                m.response_ms AS response_ms,
                m.role::text AS role,
                LAG(m.content)     OVER w AS question,
                LAG(m.role::text)  OVER w AS prev_role
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            {inner_where_sql}
            WINDOW w AS (
                PARTITION BY m.conversation_id
                ORDER BY m.created_at, m.role DESC
            )
        ),
        bot AS (SELECT * FROM turns WHERE role = 'bot'),
        individual AS (
            SELECT
                ts, NULL::timestamptz AS ts_from, session_id,
                CASE WHEN prev_role = 'user' THEN question END AS question,
                answer, intent, source, response_ms,
                (source IN ('k1_keyword', 'k2_similarity')) AS answered,
                FALSE AS contact_captured
            FROM bot
            WHERE source <> 'fallback'
        ),
        fb AS (
            SELECT
                MAX(b.ts) AS ts,
                MIN(b.ts) AS ts_from,
                b.session_id,
                (array_agg(b.question ORDER BY b.ts ASC)
                    FILTER (WHERE b.prev_role = 'user'))[1] AS question,
                (array_agg(b.answer ORDER BY b.ts DESC))[1] AS answer,
                'iletisim'::text AS intent,
                'fallback'::text AS source,
                NULL::int AS response_ms,
                (COALESCE(fc.cnt, 0) > 0) AS answered,
                (COALESCE(fc.cnt, 0) > 0) AS contact_captured
            FROM bot b
            LEFT JOIN (
                SELECT session_id, COUNT(*) AS cnt
                FROM fallback_contacts GROUP BY session_id
            ) fc ON fc.session_id = b.session_id
            WHERE b.source = 'fallback'
            GROUP BY b.conversation_id, b.session_id, fc.cnt
        ),
        unified AS (
            SELECT ts, ts_from, session_id, question, answer, intent, source,
                   response_ms, answered, contact_captured FROM individual
            UNION ALL
            SELECT ts, ts_from, session_id, question, answer, intent, source,
                   response_ms, answered, contact_captured FROM fb
        )
        SELECT
            ts, ts_from, session_id, question, answer, intent, source, response_ms,
            answered, contact_captured,
            COUNT(*) OVER() AS total
        FROM unified u
        {final_where_sql}
        ORDER BY ts DESC
        LIMIT ${limit_idx} OFFSET ${offset_idx}
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

    total = rows[0]["total"] if rows else 0
    items = []
    for r in rows:
        d = dict(r)
        d.pop("total", None)
        # answered/contact_captured sorgudan bool olarak gelir
        d["answered"] = bool(d.get("answered"))
        d["contact_captured"] = bool(d.get("contact_captured"))
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def list_conversation_intents(ctx: TenantContext) -> list[str]:
    """Gorusmelerde fiilen gecen intent (kategori) degerleri — filtre acilir listesi icin."""
    # 'iletisim_alindi' eski bir ic isaretti; artik collapse 'iletisim'e indiriyor.
    query = """
        SELECT DISTINCT intent
        FROM messages
        WHERE role = 'bot' AND intent IS NOT NULL AND intent <> ''
          AND intent <> 'iletisim_alindi'
        ORDER BY intent
    """
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [r["intent"] for r in rows]


async def get_session_messages(
    ctx: TenantContext,
    session_id: str,
    ts_from: str | None = None,
    ts_to: str | None = None,
) -> list[dict[str, Any]]:
    """Panelde 'detay' acilir kismi: bir satirin mesajlarini kronolojik dondurur.

    Bir oturum (session) widget'ta uzun sure yasar ve ONLARCA alakasiz konusma
    biriktirebilir. Bu yuzden TUM oturumu degil, yalnizca ilgili EPISODU
    (ts_from..ts_to penceresi) dondururuz. Pencere, ilk fallback turundan
    (ts_from) once gelen tetikleyici kullanici mesajini da kapsar; boylece
    iletisim akisinin baslatan soru + tum ara adimlari gorunur, aradaki
    bagimsiz cevaplanmis sorular GELMEZ. ts_from/ts_to verilmezse (ornegin
    normal bir tur) tum oturum dondurulur.
    """
    dt_from = _parse_ts(ts_from)
    dt_to = _parse_ts(ts_to)
    if dt_from is not None and dt_to is not None:
        # asyncpg timestamptz parametresi icin datetime bekler (str verilirse
        # DataError/500 olur) — bu yuzden ISO stringleri datetime'a cevirdik.
        query = """
            SELECT m.created_at AS ts, m.role::text AS role, m.content AS content,
                   m.intent::text AS intent, m.source::text AS source
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.session_id = $1
              AND m.created_at <= $3
              AND m.created_at >= COALESCE((
                    SELECT MAX(m2.created_at)
                    FROM messages m2
                    JOIN conversations c2 ON c2.id = m2.conversation_id
                    WHERE c2.session_id = $1 AND m2.created_at < $2
              ), $2)
            ORDER BY m.created_at, m.role DESC
        """
        args = (session_id, dt_from, dt_to)
    else:
        query = """
            SELECT m.created_at AS ts, m.role::text AS role, m.content AS content,
                   m.intent::text AS intent, m.source::text AS source
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.session_id = $1
            ORDER BY m.created_at, m.role DESC
        """
        args = (session_id,)
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
    return [dict(r) for r in rows]


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