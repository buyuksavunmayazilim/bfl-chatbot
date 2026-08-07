"""Admin API — panel tarafindan kullanilan yonetim uclari.

GUVENLIK: Bu uclarda kimlik dogrulama YOKTUR. Yalnizca ic agdan erisilebilir
olmalidir (public reverse-proxy'ye acilmamali; VPN/localhost/IP allowlist).

Uclar:
    GET    /api/admin/tenants                 -> tenant listesi (panel dropdown'i)
    GET    /api/admin/{tenant}/qa             -> Q&A listele (filtre + sayfalama)
    POST   /api/admin/{tenant}/qa             -> Q&A ekle (soru embed edilir)
    GET    /api/admin/{tenant}/qa/{id}        -> tek Q&A
    PUT    /api/admin/{tenant}/qa/{id}        -> Q&A guncelle (soru degisirse re-embed)
    DELETE /api/admin/{tenant}/qa/{id}        -> Q&A sil
    POST   /api/admin/{tenant}/qa/search      -> semantik arama (panelde test icin)
    POST   /api/admin/{tenant}/reload         -> icerigi DB'den yeniden yukle
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.context import TenantContext, get_tenant, reload_content
from app.core.tenants import TENANTS
from app.services import qa_repository as qa
from app.services.qa_repository import QAError
from app.services import content_repository as content
from app.services import conversation_repository as convo
from app.services import augment_service as augment
from app.services.content_repository import ContentError

router = APIRouter()


def _tenant(tenant: str) -> TenantContext:
    try:
        return get_tenant(tenant)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Bilinmeyen tenant: {tenant}")
    except RuntimeError:
        raise HTTPException(status_code=503, detail=f"Tenant su an kullanilamiyor: {tenant}")


# ─── Modeller ────────────────────────────────────────────────────────────────
class QACreate(BaseModel):
    question: str
    answer: str
    intent: str
    is_augmented: bool = False
    allow_duplicate: bool = False
    augment: bool = False   # True ise soru LLM ile cogaltilir (varyasyonlar eklenir)


class QAUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    intent: str | None = None
    is_augmented: bool | None = None


class QASearch(BaseModel):
    query: str
    intent: str | None = None
    limit: int = 5


# ─── Tenant listesi ──────────────────────────────────────────────────────────
@router.get("/tenants")
async def list_tenants() -> list[dict]:
    return [{"id": t.id, "label": t.label} for t in TENANTS.values()]


# ─── Q&A CRUD ────────────────────────────────────────────────────────────────
@router.get("/{tenant}/qa")
async def qa_list(
    tenant: str,
    intent: str | None = None,
    text: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    ctx = _tenant(tenant)
    return await qa.list_qa(ctx, intent=intent, text=text, limit=limit, offset=offset)


@router.post("/{tenant}/qa")
async def qa_create(tenant: str, body: QACreate) -> dict:
    ctx = _tenant(tenant)
    try:
        row = await qa.create_qa(
            ctx, body.question, body.answer, body.intent,
            is_augmented=False, allow_duplicate=body.allow_duplicate,
        )
    except QAError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    added = 0
    if body.augment:
        try:
            variations = augment.generate_variations(body.question)
            for v in variations:
                try:
                    await qa.create_qa(
                        ctx, v, body.answer, body.intent,
                        is_augmented=True, allow_duplicate=True,
                    )
                    added += 1
                except QAError:
                    pass
        except Exception as exc:
            row["augment_error"] = str(exc)
    row["augmented_added"] = added
    return row


@router.get("/{tenant}/qa/{qa_id}")
async def qa_get(tenant: str, qa_id: int) -> dict:
    ctx = _tenant(tenant)
    try:
        return await qa.get_qa(ctx, qa_id)
    except QAError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{tenant}/qa/{qa_id}")
async def qa_update(tenant: str, qa_id: int, body: QAUpdate) -> dict:
    ctx = _tenant(tenant)
    try:
        return await qa.update_qa(
            ctx, qa_id,
            question=body.question, answer=body.answer,
            intent=body.intent, is_augmented=body.is_augmented,
        )
    except QAError as exc:
        # "bulunamadi" -> 404, digerleri -> 400
        code = 404 if "bulunamadi" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc))


@router.delete("/{tenant}/qa/{qa_id}")
async def qa_delete(tenant: str, qa_id: int) -> dict:
    ctx = _tenant(tenant)
    try:
        return await qa.delete_qa(ctx, qa_id)
    except QAError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{tenant}/qa/search")
async def qa_search(tenant: str, body: QASearch) -> list[dict]:
    ctx = _tenant(tenant)
    try:
        return await qa.search_qa(ctx, body.query, intent=body.intent, limit=body.limit)
    except QAError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ─── Icerik reload ───────────────────────────────────────────────────────────
@router.post("/{tenant}/reload")
async def content_reload(tenant: str) -> dict:
    _tenant(tenant)  # tenant gecerli mi?
    await reload_content(tenant)
    return {"reloaded": tenant}


# ─── Icerik modelleri ────────────────────────────────────────────────────────
class IntentBody(BaseModel):
    static_response: str | None = None
    priority: int = 100
    keywords: list[str] = []
    enabled: bool = True


class FormButton(BaseModel):
    button_label: str
    url: str


class IntentFullBody(BaseModel):
    static_response: str | None = None
    priority: int = 100
    keywords: list[str] = []
    enabled: bool = True
    forms: list[FormButton] = []


class FormUrlBody(BaseModel):
    url: str


class IntentFormBody(BaseModel):
    intent: str
    button_label: str
    form_key: str


class MessageBody(BaseModel):
    text: str


class SettingBody(BaseModel):
    value: Any


def _content_err(exc: ContentError) -> HTTPException:
    code = 404 if "bulunamadi" in str(exc) else 400
    return HTTPException(status_code=code, detail=str(exc))


# ─── intents ─────────────────────────────────────────────────────────────────
@router.get("/{tenant}/intents")
async def intents_list(tenant: str) -> list[dict]:
    return await content.list_intents(_tenant(tenant))


@router.put("/{tenant}/intents/{name}")
async def intent_upsert(tenant: str, name: str, body: IntentBody) -> dict:
    _tenant(tenant)
    try:
        row = await content.upsert_intent(
            _tenant(tenant), name, body.static_response,
            body.priority, body.keywords, body.enabled,
        )
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


@router.delete("/{tenant}/intents/{name}")
async def intent_delete(tenant: str, name: str) -> dict:
    _tenant(tenant)
    try:
        row = await content.delete_intent(_tenant(tenant), name)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


# Intent'i form butonlariyla birlikte tek istekte kaydet (panelde tek ekran)
@router.put("/{tenant}/intents-full/{name}")
async def intent_full_upsert(tenant: str, name: str, body: IntentFullBody) -> dict:
    try:
        row = await content.upsert_intent_with_forms(
            _tenant(tenant), name, body.static_response, body.priority,
            body.keywords, body.enabled, [f.model_dump() for f in body.forms],
        )
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


# ─── form_urls ───────────────────────────────────────────────────────────────
@router.get("/{tenant}/form_urls")
async def form_urls_list(tenant: str) -> list[dict]:
    return await content.list_form_urls(_tenant(tenant))


@router.put("/{tenant}/form_urls/{key}")
async def form_url_upsert(tenant: str, key: str, body: FormUrlBody) -> dict:
    try:
        row = await content.upsert_form_url(_tenant(tenant), key, body.url)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


@router.delete("/{tenant}/form_urls/{key}")
async def form_url_delete(tenant: str, key: str) -> dict:
    try:
        row = await content.delete_form_url(_tenant(tenant), key)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


# ─── intent_forms ────────────────────────────────────────────────────────────
@router.get("/{tenant}/intent_forms")
async def intent_forms_list(tenant: str) -> list[dict]:
    return await content.list_intent_forms(_tenant(tenant))


@router.put("/{tenant}/intent_forms")
async def intent_form_upsert(tenant: str, body: IntentFormBody) -> dict:
    try:
        row = await content.upsert_intent_form(
            _tenant(tenant), body.intent, body.button_label, body.form_key
        )
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


@router.delete("/{tenant}/intent_forms")
async def intent_form_delete(tenant: str, intent: str, button_label: str) -> dict:
    try:
        row = await content.delete_intent_form(_tenant(tenant), intent, button_label)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


# ─── bot_messages ────────────────────────────────────────────────────────────
@router.get("/{tenant}/messages")
async def messages_list(tenant: str) -> list[dict]:
    return await content.list_messages(_tenant(tenant))


@router.put("/{tenant}/messages/{key}")
async def message_upsert(tenant: str, key: str, body: MessageBody) -> dict:
    try:
        row = await content.upsert_message(_tenant(tenant), key, body.text)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


@router.delete("/{tenant}/messages/{key}")
async def message_delete(tenant: str, key: str) -> dict:
    try:
        row = await content.delete_message(_tenant(tenant), key)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


# ─── bot_settings ────────────────────────────────────────────────────────────
@router.get("/{tenant}/settings")
async def settings_list(tenant: str) -> list[dict]:
    return await content.list_settings(_tenant(tenant))


@router.put("/{tenant}/settings/{key}")
async def setting_upsert(tenant: str, key: str, body: SettingBody) -> dict:
    try:
        row = await content.upsert_setting(_tenant(tenant), key, body.value)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


@router.delete("/{tenant}/settings/{key}")
async def setting_delete(tenant: str, key: str) -> dict:
    try:
        row = await content.delete_setting(_tenant(tenant), key)
    except ContentError as exc:
        raise _content_err(exc)
    await reload_content(tenant)
    return row


# ─── Gorusme kayitlari (salt-okunur izleme) ──────────────────────────────────
@router.get("/{tenant}/conversations")
async def conversations_list(
    tenant: str,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str = "all",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    ctx = _tenant(tenant)
    try:
        return await convo.list_conversations(
            ctx, date_from=date_from, date_to=date_to,
            status=status, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))