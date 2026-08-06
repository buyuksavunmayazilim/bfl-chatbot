"""
POST /chat — Ana chatbot endpoint'i

Akış (her mesajda):
    1. K1 Keyword → eşleşti → yanıt ver (fallback askıda kalır)
    2. K2 Similarity → eşleşti → yanıt ver (fallback askıda kalır)
    3. Fallback aktif mi? → adıma devam et
    4. Fallback yok → fallback başlat
"""
import time
import uuid

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.context import TenantContext, get_tenant
from app.core.tenants import DEFAULT_TENANT_ID
from app.services.keyword_service import match_keyword
from app.services.similarity_service import search_similar
from app.services.session_service import has_active_fallback, is_fallback_completed, delete_fallback_state
from app.services.fallback_service import start_fallback, process_fallback

router = APIRouter()

VALID_SOURCES = {"k1_keyword", "k2_similarity", "fallback", "static"}

# ─── Request / Response ──────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    message: str
    test: bool = False   # True ise mesaj kaydedilmez (panel/gelistirme denemeleri)


class ChatResponse(BaseModel):
    session_id: str
    message: str
    intent: str | None
    source: str
    confidence: float | None
    form_urls: dict
    response_ms: int


# ─── DB kayıt ────────────────────────────────────────────────────────────────
async def _save_message(
    ctx: TenantContext,
    session_id: str,
    user_content: str,
    bot_content: str,
    intent: str | None,
    source: str,
    confidence: float | None,
    response_ms: int,
) -> None:
    try:

        if source not in {"k1_keyword", "k2_similarity", "fallback", "static"}:
            source = "static"

        async with ctx.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversations (id, session_id, created_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (session_id) DO NOTHING
                """,
                uuid.uuid4(), session_id,
            )
            conv_id = await conn.fetchval(
                "SELECT id FROM conversations WHERE session_id = $1",
                session_id,
            )
            for role, content in [("user", user_content), ("bot", bot_content)]:
                await conn.execute(
                    """
                    INSERT INTO messages
                        (id, conversation_id, role, content, intent,
                         source, confidence, response_ms, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                    """,
                    uuid.uuid4(), conv_id, role, content,
                    intent, source, confidence, response_ms,
                )
            await conn.execute(
                """
                INSERT INTO analytics_events
                    (id, session_id, intent, layer_hit, response_ms, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                uuid.uuid4(), session_id, intent, source, response_ms,
            )
    except Exception as e:
        print(f"[Chat] DB kayit hatasi: {e}")


# ─── Ana endpoint ─────────────────────────────────────────────────────────────
async def _run_chat(ctx: TenantContext, req: ChatRequest) -> ChatResponse:
    t_start = time.time()
    message = req.message.strip()
    session_id = req.session_id

    intent = None
    source = "unknown"
    confidence = None
    form_urls = {}
    bot_reply = ""

    fallback_active = await has_active_fallback(session_id)
 
    # ══════════════════════════════════════════════════════════════════════
    # FALLBACK AKTİF
    # ══════════════════════════════════════════════════════════════════════
    if fallback_active:
        text_low = message.lower().strip()
 
        # (a) İptal/çıkış
        if text_low in set(ctx.content.setting("cancel_words", [])):
            await delete_fallback_state(session_id)
            source = "static"
            bot_reply = ctx.content.msg(
                "cancel_reply",
                "Tabii, iptal ettim. Araç arızası, hasar, servis, lastik, "
                "teklif veya genel sorularınız için buradayım.",
            )
 
        else:
            k1 = match_keyword(ctx, message)
 
            # (b) Net aksiyon intenti -> fallback'ten çık
            if k1.matched and k1.intent in set(ctx.content.setting("allow_interrupt_intents", [])):
                await delete_fallback_state(session_id)
                intent = k1.intent
                source = "k1_keyword"
                confidence = 1.0
                form_urls = k1.form_urls if isinstance(k1.form_urls, dict) else {}
                bot_reply = k1.response or ""
 
            else:
                # (d) Değilse fallback akışına DEVAM (isim/telefon topla)
                fb = await process_fallback(ctx, session_id, message)
                source = "fallback"
                intent = "iletisim"
                bot_reply = fb.response
 
    # ══════════════════════════════════════════════════════════════════════
    # FALLBACK AKTİF DEĞİL  → normal akış
    # ══════════════════════════════════════════════════════════════════════
    else:
        # ── 1: Keyword ────────────────────────────────────────────────────
        k1 = match_keyword(ctx, message)
        if k1.matched:
            intent = k1.intent
            source = "k1_keyword"
            confidence = 1.0
            form_urls = k1.form_urls if isinstance(k1.form_urls, dict) else {}
            bot_reply = k1.response or ""
 
        else:
            # ── 2: Similarity ─────────────────────────────────────────────
            k2 = await search_similar(ctx, message)
            if k2.matched:
                intent = k2.intent_category
                source = "k2_similarity"
                confidence = k2.score
                bot_reply = k2.answer or ""
                form_urls = ctx.content.intent_forms.get(intent, {})
 
            else:
                # ── 3: Kısa/anlamsız girdi -> fallback BAŞLATMA ────────────
                if len(message) < 3:
                    source = "static"
                    bot_reply = ctx.content.msg(
                        "static_short_input",
                        "Tam anlayamadım. Araç arızası, hasar, servis, "
                        "lastik veya teklif hakkında yazabilirsiniz.",
                    )
                elif not await is_fallback_completed(session_id):
                    fb = await start_fallback(ctx, session_id)
                    source = "fallback"
                    bot_reply = fb.response
                else:
                    source = "static"
                    bot_reply = ctx.content.msg(
                        "static_completed",
                        "Başka bir konuda yardımcı olabilir miyim? "
                        "Araç arızası, hasar bildirimi, servis, lastik veya "
                        "teklif konularında buradayım.",
                    )
 
    response_ms = int((time.time() - t_start) * 1000)

    if not req.test:
        await _save_message(
            ctx=ctx,
            session_id=session_id,
            user_content=message,
            bot_content=bot_reply,
            intent=intent,
            source=source,
            confidence=confidence,
            response_ms=response_ms,
        )

    return ChatResponse(
        session_id=session_id,
        message=bot_reply,
        intent=intent,
        source=source,
        confidence=confidence,
        form_urls=form_urls,
        response_ms=response_ms,
    )

def _resolve(tenant: str) -> TenantContext:
    """URL'deki tenant slug'ini canli baglama (TenantContext) cevirir."""
    try:
        return get_tenant(tenant)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen tenant: {tenant}")
    except RuntimeError:
        raise HTTPException(status_code=503, detail=f"Tenant su an kullanilamiyor: {tenant}")


# Geriye donuk uyum: eski /api/v1/chat -> bfl.
# {tenant} route'undan ONCE tanimlanir ki "v1" bir tenant sanilmasin.
@router.post("/v1/chat", response_model=ChatResponse)
async def chat_legacy(req: ChatRequest) -> ChatResponse:
    return await _run_chat(_resolve(DEFAULT_TENANT_ID), req)


# Cok-kiracili route: /api/{tenant}/chat
@router.post("/{tenant}/chat", response_model=ChatResponse)
async def chat(tenant: str, req: ChatRequest) -> ChatResponse:
    return await _run_chat(_resolve(tenant), req)


# ─── Public widget yapilandirmasi (baslik/alt baslik/avatar/karsilama/renk) ───
@router.get("/{tenant}/config")
async def public_config(tenant: str) -> dict:
    ctx = _resolve(tenant)
    s = ctx.content.settings
    return {
        "title": s.get("widget_title") or ctx.config.label,
        "subtitle": s.get("widget_subtitle") or "",
        "avatar": s.get("widget_avatar") or "",
        "greeting": s.get("widget_greeting") or "",
        "color": s.get("widget_color") or "#537286",
    }