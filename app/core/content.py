"""Tenant icerigi: DB'deki icerik tablolarini bellege yukler.

Sirkete ozel VERI (intent kelimeleri, hazir cevaplar, form URL'leri, guard
listeleri, mesajlar, ayarlar) her tenant'in kendi veritabaninda durur. Bu modul
o veriyi startup'ta (ve panelden degisiklik sonrasi reload'da) bir kez okuyup
`TenantContent` nesnesine yukler. K1/chat/fallback bu nesneyi bellekten okur;
her mesajda DB'ye gidilmez.

Matching ALGORITMASI kodda (keyword_service) kalir; burasi sadece VERI'dir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import asyncpg


@dataclass
class TenantContent:
    # intent adi -> keyword listesi (yalnizca enabled ve kelimesi olan intent'ler)
    intent_keywords: dict[str, list[str]] = field(default_factory=dict)
    # intent adi -> hazir K1 cevabi
    static_responses: dict[str, str] = field(default_factory=dict)
    # intent adi -> {buton_etiketi: url}
    intent_forms: dict[str, dict[str, str]] = field(default_factory=dict)
    # K1 oncelik sirasi (kelimesi olan enabled intent'ler, priority'ye gore)
    priority_order: list[str] = field(default_factory=list)
    # anahtar -> hazir metin (fallback akisi + chat static mesajlari)
    messages: dict[str, str] = field(default_factory=dict)
    # anahtar -> deger (guard listeleri, cancel_words, esikler, branding ...)
    settings: dict[str, Any] = field(default_factory=dict)

    def msg(self, key: str, default: str = "") -> str:
        """Hazir metni doner; DB'de yoksa koddaki default kullanilir."""
        return self.messages.get(key, default)

    def setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)


async def load_content(pool: asyncpg.Pool) -> TenantContent:
    """Icerik tablolarini okuyup bir TenantContent olusturur."""
    async with pool.acquire() as conn:
        intent_rows = await conn.fetch(
            "SELECT name, static_response, priority, keywords, enabled FROM intents"
        )
        form_rows = await conn.fetch(
            "SELECT i.intent, i.button_label, f.url "
            "FROM intent_forms i JOIN form_urls f ON f.key = i.form_key "
            "ORDER BY i.intent, i.button_label"
        )
        msg_rows = await conn.fetch("SELECT key, text FROM bot_messages")
        setting_rows = await conn.fetch("SELECT key, value FROM bot_settings")

    content = TenantContent()

    enabled = [r for r in intent_rows if r["enabled"]]
    for r in enabled:
        if r["static_response"] is not None:
            content.static_responses[r["name"]] = r["static_response"]
        keywords = list(r["keywords"] or [])
        if keywords:
            content.intent_keywords[r["name"]] = keywords

    # K1 dongusu yalnizca kelimesi olan enabled intent'leri, priority sirasiyla gezer.
    content.priority_order = [
        r["name"]
        for r in sorted(enabled, key=lambda x: (x["priority"], x["name"]))
        if (r["keywords"] or [])
    ]

    forms: dict[str, dict[str, str]] = {}
    for r in form_rows:
        forms.setdefault(r["intent"], {})[r["button_label"]] = r["url"]
    content.intent_forms = forms

    content.messages = {r["key"]: r["text"] for r in msg_rows}

    # asyncpg JSONB'yi varsayilan olarak str dondurur -> json.loads gerekir.
    settings: dict[str, Any] = {}
    for r in setting_rows:
        value = r["value"]
        settings[r["key"]] = json.loads(value) if isinstance(value, str) else value
    content.settings = settings

    return content