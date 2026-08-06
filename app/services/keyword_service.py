"""K1 Keyword katmani — mesaji intent kelimeleriyle esleştirir.

ALGORITMA burada (Turkce normalize, guard'lar, oncelik dongusu); VERI ise
tenant'in DB'sinden gelir ve `ctx.content` uzerinden okunur. Boylece ayni kod
tum chatbot'lar icin calisir; kelimeler/cevaplar/URL'ler panelden duzenlenir.

Oncelik: content.priority_order (kelimesi olan enabled intent'ler, priority'ye gore)
Ilk eslesen intent doner; hicbiri eslesmezse matched=False -> K2 Similarity devreye girer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.content import TenantContent
from app.core.context import TenantContext


@dataclass
class KeywordResult:
    matched: bool
    intent: str | None = None
    response: str | None = None
    form_urls: dict = field(default_factory=dict)


# ─── Turkce normalize ────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    char_map = {
        "ı": "i", "ğ": "g", "ü": "u",
        "ş": "s", "ö": "o", "ç": "c",
        "İ": "i", "Ğ": "g", "Ü": "u",  # buyuk harfler — lower() bunlari duzgun cevirmiyor
        "Ş": "s", "Ö": "o", "Ç": "c",
    }
    for tr_char, en_char in char_map.items():
        text = text.replace(tr_char, en_char)
    return text.lower()


# ─── Guard'lar ───────────────────────────────────────────────────────────────
# Marker listeleri DB'de zaten normalize edilmis halde tutulur (ornek: "kac gun",
# "carpt"), bu yuzden mesajla dogrudan karsilastirilir.
def _is_informational(content: TenantContent, normalized_msg: str) -> bool:
    strong = content.setting("strong_action_markers", [])
    info = content.setting("info_markers", [])
    if any(a in normalized_msg for a in strong):
        return False
    return any(m in normalized_msg for m in info)


def _is_non_vehicle(content: TenantContent, normalized_msg: str) -> bool:
    vehicle = content.setting("vehicle_markers", [])
    non_vehicle = content.setting("non_vehicle_markers", [])
    if any(v in normalized_msg for v in vehicle):
        return False
    return any(nv in normalized_msg for nv in non_vehicle)


# ─── Ana eslesme fonksiyonu ──────────────────────────────────────────────────
def match_keyword(ctx: TenantContext, message: str) -> KeywordResult:
    """Kullanici mesajini tenant'in keyword listesiyle karsilastirir."""
    content = ctx.content
    normalized_msg = _normalize(message)

    # GUARD 1: arac-disi ozne ("sitede ariza var") -> K1 atla, K2'ye birak
    if _is_non_vehicle(content, normalized_msg):
        return KeywordResult(matched=False)

    # GUARD 2: bilgi sorusu ("lastik degisimi kac gunde") -> K1 atla, K2'ye birak
    if _is_informational(content, normalized_msg):
        return KeywordResult(matched=False)

    for intent in content.priority_order:
        for keyword in content.intent_keywords.get(intent, []):
            if _normalize(keyword) in normalized_msg:
                return KeywordResult(
                    matched=True,
                    intent=intent,
                    response=content.static_responses.get(intent),
                    form_urls=content.intent_forms.get(intent, {}),
                )

    return KeywordResult(matched=False)