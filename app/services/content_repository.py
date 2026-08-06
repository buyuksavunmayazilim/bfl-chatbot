"""Icerik tablolari icin async CRUD (admin API kullanir).

Tablolar: intents, form_urls, intent_forms, bot_messages, bot_settings.
Yazma islemlerinden sonra admin endpoint'i reload_content() cagirir; boylece
bellekteki TenantContent tazelenir ve degisiklik aninda etkili olur.
"""
from __future__ import annotations

import json
from typing import Any

from app.core.context import TenantContext


class ContentError(Exception):
    """Beklenen icerik hatasi (endpoint 400/404'e cevirir)."""


# ─── intents ─────────────────────────────────────────────────────────────────
async def list_intents(ctx: TenantContext) -> list[dict]:
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name, static_response, priority, keywords, enabled "
            "FROM intents ORDER BY priority, name"
        )
    return [dict(r) for r in rows]


async def upsert_intent(
    ctx: TenantContext,
    name: str,
    static_response: str | None,
    priority: int,
    keywords: list[str],
    enabled: bool,
) -> dict:
    name = name.strip()
    if not name:
        raise ContentError("intent adi bos olamaz.")
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO intents (name, static_response, priority, keywords, enabled)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO UPDATE SET
                static_response = EXCLUDED.static_response,
                priority = EXCLUDED.priority,
                keywords = EXCLUDED.keywords,
                enabled = EXCLUDED.enabled
            RETURNING name, static_response, priority, keywords, enabled
            """,
            name, static_response, priority, list(keywords or []), enabled,
        )
    return dict(row)


async def delete_intent(ctx: TenantContext, name: str) -> dict:
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM intents WHERE name=$1 RETURNING name", name
        )
    if row is None:
        raise ContentError(f"intent bulunamadi: {name}")
    return {"deleted": True, "name": row["name"]}


# ─── form_urls ───────────────────────────────────────────────────────────────
async def list_form_urls(ctx: TenantContext) -> list[dict]:
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, url FROM form_urls ORDER BY key")
    return [dict(r) for r in rows]


async def upsert_form_url(ctx: TenantContext, key: str, url: str) -> dict:
    key = key.strip()
    url = url.strip()
    if not key or not url:
        raise ContentError("key ve url bos olamaz.")
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO form_urls (key, url) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET url = EXCLUDED.url
            RETURNING key, url
            """,
            key, url,
        )
    return dict(row)


async def delete_form_url(ctx: TenantContext, key: str) -> dict:
    async with ctx.pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "DELETE FROM form_urls WHERE key=$1 RETURNING key", key
            )
        except Exception as exc:  # FK: intent_forms tarafindan kullaniliyorsa
            raise ContentError(
                f"'{key}' silinemiyor, bir intent formunda kullaniliyor olabilir: {exc}"
            )
    if row is None:
        raise ContentError(f"form_url bulunamadi: {key}")
    return {"deleted": True, "key": row["key"]}


# ─── intent_forms ────────────────────────────────────────────────────────────
async def list_intent_forms(ctx: TenantContext) -> list[dict]:
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT intent, button_label, form_key FROM intent_forms "
            "ORDER BY intent, button_label"
        )
    return [dict(r) for r in rows]


async def upsert_intent_form(
    ctx: TenantContext, intent: str, button_label: str, form_key: str
) -> dict:
    intent = intent.strip()
    button_label = button_label.strip()
    form_key = form_key.strip()
    if not intent or not button_label or not form_key:
        raise ContentError("intent, button_label ve form_key bos olamaz.")
    async with ctx.pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO intent_forms (intent, button_label, form_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (intent, button_label) DO UPDATE SET form_key = EXCLUDED.form_key
                RETURNING intent, button_label, form_key
                """,
                intent, button_label, form_key,
            )
        except Exception as exc:  # FK: intent veya form_key yoksa
            raise ContentError(
                f"Kaydedilemedi. intent='{intent}' ve form_key='{form_key}' "
                f"var olmali: {exc}"
            )
    return dict(row)


async def delete_intent_form(
    ctx: TenantContext, intent: str, button_label: str
) -> dict:
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM intent_forms WHERE intent=$1 AND button_label=$2 "
            "RETURNING intent, button_label",
            intent, button_label,
        )
    if row is None:
        raise ContentError(f"intent_form bulunamadi: {intent}/{button_label}")
    return {"deleted": True, "intent": row["intent"], "button_label": row["button_label"]}


# ─── bot_messages ────────────────────────────────────────────────────────────
async def list_messages(ctx: TenantContext) -> list[dict]:
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, text FROM bot_messages ORDER BY key")
    return [dict(r) for r in rows]


async def upsert_message(ctx: TenantContext, key: str, text: str) -> dict:
    key = key.strip()
    if not key:
        raise ContentError("mesaj key bos olamaz.")
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bot_messages (key, text) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET text = EXCLUDED.text
            RETURNING key, text
            """,
            key, text,
        )
    return dict(row)


async def delete_message(ctx: TenantContext, key: str) -> dict:
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM bot_messages WHERE key=$1 RETURNING key", key
        )
    if row is None:
        raise ContentError(f"mesaj bulunamadi: {key}")
    return {"deleted": True, "key": row["key"]}


# ─── bot_settings ────────────────────────────────────────────────────────────
async def list_settings(ctx: TenantContext) -> list[dict]:
    async with ctx.pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM bot_settings ORDER BY key")
    out = []
    for r in rows:
        value = r["value"]
        out.append({"key": r["key"], "value": json.loads(value) if isinstance(value, str) else value})
    return out


async def upsert_setting(ctx: TenantContext, key: str, value: Any) -> dict:
    key = key.strip()
    if not key:
        raise ContentError("ayar key bos olamaz.")
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO bot_settings (key, value) VALUES ($1, $2::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            RETURNING key, value
            """,
            key, json.dumps(value),
        )
    v = row["value"]
    return {"key": row["key"], "value": json.loads(v) if isinstance(v, str) else v}


async def delete_setting(ctx: TenantContext, key: str) -> dict:
    async with ctx.pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM bot_settings WHERE key=$1 RETURNING key", key
        )
    if row is None:
        raise ContentError(f"ayar bulunamadi: {key}")
    return {"deleted": True, "key": row["key"]}