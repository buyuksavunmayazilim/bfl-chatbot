"""Soru cogaltma (augmentation) — kural tabanli, LLM YOK.

Yeni bir Q&A eklenirken "augmentation" secilirse, sorunun benzer ifadeleri
uretilir ve her biri ayri kayit (is_augmented=True) olarak eklenir. Boylece ayni
soru farkli sekillerde soruldugunda K2 similarity daha iyi yakalar.

Uc yontem:
  1) Es anlamli kelime degisimi (kucuk, elle bakimli sozluk)
  2) Standart kelime ekleme (bas taraflarina "acaba", "peki" gibi)
  3) Harf silme (yazim hatasi taklidi)
"""
from __future__ import annotations

import random
import re

# ─── Es anlamli kelimeler (arac/filo alanina ozgu) ───────────────────────────
_SYNONYMS: dict[str, list[str]] = {
    "araç": ["araba", "oto", "vasıta"],
    "araba": ["araç", "oto"],
    "oto": ["araç", "araba"],
    "arıza": ["sorun", "problem", "bozukluk"],
    "arızalandı": ["bozuldu"],
    "bozuldu": ["arızalandı"],
    "hasar": ["kaza"],
    "kaza": ["hasar"],
    "lastik": ["teker", "tekerlek"],
    "servis": ["bakım"],
    "bakım": ["servis"],
    "fiyat": ["ücret", "tutar", "bedel"],
    "ücret": ["fiyat", "tutar"],
    "teklif": ["fiyat teklifi"],
    "yardım": ["destek"],
    "destek": ["yardım"],
    "nasıl": ["ne şekilde"],
    "istiyorum": ["talep ediyorum", "rica ediyorum"],
    "almak": ["edinmek"],
    "öğrenmek": ["bilmek"],
    "kaç": ["ne kadar"],
    "sözleşme": ["kontrat", "anlaşma"],
    "kiralama": ["kiralık"],
    "sigorta": ["kasko"],
}

# Bas tarafa eklenebilecek standart kelimeler
_PREFIXES = ["acaba", "peki", "merhaba", "bir de", "lütfen"]

# Yazim hatasi icin harf silmede korunacak minimum kelime uzunlugu
_MIN_TYPO_LEN = 5


def _norm_key(word: str) -> str:
    return re.sub(r"[^0-9a-zçğıöşü]", "", word.lower())


def _synonym_variants(words: list[str]) -> list[str]:
    out: list[str] = []
    for i, w in enumerate(words):
        syns = _SYNONYMS.get(_norm_key(w))
        if not syns:
            continue
        for syn in syns:
            new = words.copy()
            new[i] = syn
            out.append(" ".join(new))
    return out


def _prefix_variants(question: str) -> list[str]:
    return [f"{p} {question}" for p in _PREFIXES]


def _typo_variants(words: list[str], rng: random.Random, count: int = 2) -> list[str]:
    # Uzun kelimelerden birinden rastgele bir ic harf silerek yazim hatasi taklidi.
    candidates = [i for i, w in enumerate(words) if len(_norm_key(w)) >= _MIN_TYPO_LEN]
    out: list[str] = []
    rng.shuffle(candidates)
    for idx in candidates[:count]:
        w = words[idx]
        if len(w) < _MIN_TYPO_LEN:
            continue
        pos = rng.randint(1, len(w) - 2)  # bas/son harfi koru
        typo = w[:pos] + w[pos + 1:]
        new = words.copy()
        new[idx] = typo
        out.append(" ".join(new))
    return out


def generate_variations(question: str, n: int = 5) -> list[str]:
    """Sorunun kural tabanli n varyasyonunu uretir (LLM kullanmaz)."""
    q = question.strip()
    if not q:
        return []

    words = q.split()
    rng = random.Random(q)  # ayni soru icin tutarli sonuc

    pool: list[str] = []
    pool += _synonym_variants(words)
    pool += _typo_variants(words, rng)
    pool += _prefix_variants(q)

    # temizle + tekillestir + orijinali cikar
    seen = {q.lower()}
    result: list[str] = []
    for cand in pool:
        cand = re.sub(r"\s+", " ", cand).strip()
        low = cand.lower()
        if not cand or low in seen:
            continue
        seen.add(low)
        result.append(cand)
        if len(result) >= n:
            break
    return result