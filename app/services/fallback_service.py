"""
Fallback Servisi — Çok Adımlı İletişim Bilgisi Toplama

Akış:
    ask_name → ask_contact_pref → ask_phone | ask_email → confirm

Her adımda K1→K2 önce kontrol edilir (chat.py'de).
E�leşme yoksa bu servis devreye girer.
Fallback K1/K2 eşleşmesinde silinmez, askıya alınır.
"""
import re
import uuid
from dataclasses import dataclass

import asyncpg

from app.core.config import settings
from app.core.context import TenantContext
from app.services.session_service import (
    get_fallback_state,
    set_fallback_state,
    delete_fallback_state,
    mark_fallback_completed,
)

# ─── Adımlar ─────────────────────────────────────────────────────────────────
STEP_ASK_NAME    = "ask_name"
STEP_ASK_PREF    = "ask_contact_pref"
STEP_ASK_PHONE   = "ask_phone"
STEP_ASK_EMAIL   = "ask_email"
STEP_DONE        = "done"

# ─── Telefon/email keyword'leri ──────────────────────────────────────────────
PHONE_KEYWORDS = ["telefon", "tel", "ara", "aray", "phone", "call", "cep"]
EMAIL_KEYWORDS = ["mail", "email", "eposta", "e-posta", "elektronik"]

PHONE_RE = re.compile(r'[\d\s\-\(\)]{10,}')
EMAIL_RE  = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')

# ─── Statik mesajlar ─────────────────────────────────────────────────────────
MSG_TRIGGER     = (
    "Sorunuzu tam olarak anlayamadım, özür dilerim. "
    "Size daha iyi yardımcı olabilmemiz için ekibimiz "
    "sizinle iletişime geçmasi için "
    "adınızı ve soyadınızı paylaşır mısınız?"
)
MSG_ASK_PREF    = "Teşekkürler {name}! Sizi telefonla mı arayalım, yoksa e-posta mı atalım?"
MSG_ASK_PHONE   = "Telefon numaranızı paylaşır mısınız?"
MSG_ASK_EMAIL   = "E-posta adresinizi paylaşır mısınız?"
MSG_CONF_PHONE  = "Kaydettik! Ekibimiz en kısa sürede {contact} numaranızı arayacak."
MSG_CONF_EMAIL  = "Kaydettik! {contact} adresinize en kısa sürede dönüş yapacağız."
MSG_INVALID_PHONE = "Geçerli bir telefon numarası giriniz (örn: 0532 111 22 33)."
MSG_INVALID_EMAIL = "Geçerli bir e-posta adresi giriniz (örn: ad@ornek.com)."
MSG_INVALID_PREF  = "Telefon veya e-posta seçeneklerinden birini belirtir misiniz?"
MSG_DECLINED    = (
    "Anlaşıldı! İstediğiniz zaman 444 06 34 veya "
    "0 (850) 840 05 39 numaralı hattımızı arayabilirsiniz. İyi günler!"
)


# ─── Veri yapısı ─────────────────────────────────────────────────────────────
@dataclass
class FallbackResult:
    response: str
    is_done: bool = False
    should_save: bool = False


# ─── Yardımcı: tercih tespiti ────────────────────────────────────────────────
def _detect_pref(text: str) -> str | None:
    """
    Kullanıcı metninden telefon/email tercihini tespit eder.
    Tespit edilemezse None döner.
    """
    t = text.lower()
    if any(w in t for w in PHONE_KEYWORDS):
        return "phone"
    if any(w in t for w in EMAIL_KEYWORDS):
        return "email"
    # Hayır/istemiyorum
    if any(w in t for w in ["hayir", "hayır", "istemiyorum", "gerek yok", "iptal"]):
        return "declined"
    return None


def _detect_phone(text: str) -> str | None:
    """Metinden geçerli telefon numarası çıkarır."""
    match = PHONE_RE.search(text)

    if not match:
        return None

    phone = match.group().strip()
    digits = re.sub(r"\D", "", phone)

    min_length = 11 if digits.startswith("0") else 10

    if len(digits) >= min_length:
        return phone

    return None


def _detect_email(text: str) -> str | None:
    """Metinden email adresi çıkarır."""
    match = EMAIL_RE.search(text)
    return match.group() if match else None

async def _complete_fallback(
    ctx: TenantContext,
    session_id: str,
    state: dict,
    contact_type: str,
    contact_value: str,
) -> FallbackResult:
    """
    İletişim bilgisini kaydeder ve fallback akışını tamamlar.
    """

    await _save_contact(
        ctx=ctx,
        session_id=session_id,
        name=state.get("name", ""),
        contact_type=contact_type,
        contact_value=contact_value,
    )

    await mark_fallback_completed(session_id)
    await delete_fallback_state(session_id)

    if contact_type == "phone":
        response = ctx.content.msg("msg_conf_phone", MSG_CONF_PHONE).format(contact=contact_value)
    else:
        response = ctx.content.msg("msg_conf_email", MSG_CONF_EMAIL).format(contact=contact_value)

    return FallbackResult(
        response=response,
        is_done=True,
        should_save=True,
    )


# ─── Yeni fallback başlat ────────────────────────────────────────────────────
async def start_fallback(ctx: TenantContext, session_id: str) -> FallbackResult:
    """
    Fallback akışını başlatır, ad-soyad ister.
    """
    await set_fallback_state(session_id, {"step": STEP_ASK_NAME})
    return FallbackResult(response=ctx.content.msg("msg_trigger", MSG_TRIGGER))


# ─── Fallback adımını işle ───────────────────────────────────────────────────
async def process_fallback(ctx: TenantContext, session_id: str, user_input: str) -> FallbackResult:
    """
    Mevcut fallback adımını işler.
    Her adımda K1→K2 zaten chat.py'de kontrol edildi,
    eşleşme olmadığı için buraya gelindi.
    """
    state = await get_fallback_state(session_id)
    if state is None:
        # TTL dolmuş, yeniden başlat
        return await start_fallback(ctx, session_id)

    step = state.get("step")
    text = user_input.strip()

    # ── Adım 1: Ad-soyad al ──────────────────────────────────────────────────
    if step == STEP_ASK_NAME:
        if len(text) < 2:
            return FallbackResult(
                response=ctx.content.msg("ask_name_retry", "Adınızı ve soyadınızı yazabilir misiniz?")
            )

        first_name = text.split()[0]
        state["name"] = text
        state["step"] = STEP_ASK_PREF
        await set_fallback_state(session_id, state)

        return FallbackResult(
            response=ctx.content.msg("msg_ask_pref", MSG_ASK_PREF).format(name=first_name)
        )

    # ── Adım 2: Tercih al (telefon/email) ────────────────────────────────────
    if step == STEP_ASK_PREF:

        # Kullanıcı tercih belirtmeden doğrudan iletişim bilgisi paylaşmış olabilir.
        email = _detect_email(text)
        if email:
            return await _complete_fallback(
                ctx=ctx,
                session_id=session_id,
                state=state,
                contact_type="email",
                contact_value=email,
            )

        phone = _detect_phone(text)
        if phone:
            return await _complete_fallback(
                ctx=ctx,
                session_id=session_id,
                state=state,
                contact_type="phone",
                contact_value=phone,
            )

        # Doğrudan iletişim bilgisi yoksa tercihi anlamaya çalış.
        pref = _detect_pref(text)

        if pref == "declined":
            await delete_fallback_state(session_id)
            return FallbackResult(
                response=ctx.content.msg("msg_declined", MSG_DECLINED),
                is_done=True,
            )

        if pref == "phone":
            state["pref"] = "phone"
            state["step"] = STEP_ASK_PHONE
            await set_fallback_state(session_id, state)

            return FallbackResult(response=ctx.content.msg("msg_ask_phone", MSG_ASK_PHONE))

        if pref == "email":
            state["pref"] = "email"
            state["step"] = STEP_ASK_EMAIL
            await set_fallback_state(session_id, state)

            return FallbackResult(response=ctx.content.msg("msg_ask_email", MSG_ASK_EMAIL))

        return FallbackResult(response=ctx.content.msg("msg_invalid_pref", MSG_INVALID_PREF))

    # ── Adım 3a: Telefon al ──────────────────────────────────────────────────
    if step == STEP_ASK_PHONE:
        phone = _detect_phone(text)
        if not phone:
            return FallbackResult(response=ctx.content.msg("msg_invalid_phone", MSG_INVALID_PHONE))

        return await _complete_fallback(
            ctx=ctx,
            session_id=session_id,
            state=state,
            contact_type="phone",
            contact_value=phone,
        )

    # ── Adım 3b: Email al ────────────────────────────────────────────────────
    if step == STEP_ASK_EMAIL:
        email = _detect_email(text)
        if not email:
            return FallbackResult(response=ctx.content.msg("msg_invalid_email", MSG_INVALID_EMAIL))

        return await _complete_fallback(
            ctx=ctx,
            session_id=session_id,
            state=state,
            contact_type="email",
            contact_value=email,
        )

    # Bilinmeyen adım
    await delete_fallback_state(session_id)
    return await start_fallback(ctx, session_id)


# ─── PostgreSQL'e kaydet ─────────────────────────────────────────────────────
async def _save_contact(
    ctx: TenantContext,
    session_id: str,
    name: str,
    contact_type: str,
    contact_value: str,
) -> None:
    async with ctx.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fallback_contacts
                (id, session_id, name, contact_type, contact_value, status, created_at)
            VALUES ($1, $2, $3, $4, $5, 'new', NOW())
            """,
            uuid.uuid4(), session_id, name, contact_type, contact_value,
        )
        print(f"[Fallback] Kaydedildi: {name} | {contact_type}: {contact_value}")