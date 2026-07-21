import re
from dataclasses import dataclass, field


# ─── Veri yapısı ─────────────────────────────────────────────────────────────
@dataclass
class KeywordResult:
    matched: bool
    intent: str | None = None
    response: str | None = None
    form_urls: dict = field(default_factory=dict)


# ─── Form URL'leri ────────────────────────────────────────────────────────────
#  NOT: Tümü https'e ve /tr/ locale'ine standardize edildi (önceden /en/ + http karışıktı).
#  Canlıda form path'in /en/ ise sadece bu sözlüğü değiştir; gerisi otomatik düzelir.
FORM_URLS = {
    "servis_agi":                   "https://buyukfilo.com/tr/map/",
    "hasar":                        "https://buyukfilo.com/tr/forms/hasar-bildirim-formu/",
    "lastik":                       "https://buyukfilo.com/tr/forms/lastik-degisim-formu/",
    "servis":                       "https://buyukfilo.com/tr/forms/servis-bakim-formu/",
    "teklif":                       "https://buyukfilo.com/teklif-al/",
    "iletisim":                     "https://buyukfilo.com/tr/iletisim/",
    "trafik_cezasi":                "https://onlineislemler.egm.gov.tr/Sayfalar/TrafikCezaSorgulama.aspx",
    "hgs_cezasi":                   "https://hgsmusteri.ptt.gov.tr/hgs.jsf#violation",
    "kaza_tespit_tutanagi":         "https://buyukfilo.com/api/file/uploads/1771244266332.pdf",
    "kariyer":                      "https://buyukfilo.com/en/kariyer/",
}

# ─── Intent → Form URL eşleşmesi ─────────────────────────────────────────────

# ÖNEMLİ: K2 (similarity) eşleştiğinde chat.py şunu yapar:
#     form_urls = INTENT_FORM_URLS.get(k2.intent_category, {})
# Yani qa_embeddings.intent_category değerleri buradaki anahtarlarla AYNI olmalı.
# Aşağıdaki anahtarlar v6 dataset'indeki intent_category değerleriyle birebir hizalıdır.
_TEKLIF = {"teklif_formu": FORM_URLS["teklif"]}
_ILETISIM = {"iletisim": FORM_URLS["iletisim"]}

INTENT_FORM_URLS: dict[str, dict] = {
    # ── Aksiyon intent'leri (K1 + K2 ortak isimler) ──
    "hasar":      {
        "hasar_formu": FORM_URLS["hasar"],
        "kaza_tutanagi": FORM_URLS["kaza_tespit_tutanagi"],
    },
    "lastik":     {"lastik_formu": FORM_URLS["lastik"]},
    "servis":     {
        "servis_formu": FORM_URLS["servis"],
        "servis_agi": FORM_URLS["servis_agi"],
    },
    "servis_agi": {"servis_agi": FORM_URLS["servis_agi"]},
    "trafik":     {"trafik_cezasi_sorgula": FORM_URLS["trafik_cezasi"]},
    "hgs":        {"hgs_cezasi_sorgula": FORM_URLS["hgs_cezasi"]},
    "kariyer":    {"kariyer": FORM_URLS["kariyer"]},
    # "ariza" → form yok (yalnızca acil hat / static response). Bilerek eklenmedi.

    # ── Teklife yönlenen intent'ler (hepsi teklif formu butonu gösterir) ──
    "teklif":             _TEKLIF,
    "filo_kiralama":      _TEKLIF,
    "araclar":            _TEKLIF,
    "premium_arac":       _TEKLIF,
    "yakit_yonetimi":     _TEKLIF,
    "dijital_cozumler":   _TEKLIF,
    "musteri_tipi":       _TEKLIF,

    # ── İletişime yönlenen intent'ler ──
    "iletisim":           _ILETISIM,
    "musteri_hizmetleri": _ILETISIM,
    "subeler":            _ILETISIM,
    "ikame_arac":         _ILETISIM,

    # ── Sadece bilgi (answer_only) intent'leri kasıtlı olarak burada YOK ──
    #   hakkimizda, kurumsal, neden_biz, sirket_bilgileri, operasyonel_avantajlar,
    #   finansal_avantajlar, sigorta_kasko, teslimat_iade, insan_kultur,
    #   egitim_gelisim, surdurulebilirlik, hizmetler, selamlama, kapanis, fallback
    #   → form butonu gösterilmez, sadece metin yanıtı döner.
}


# ─── Statik yanıtlar ──────────────────────────────────────────────────────────
STATIC_RESPONSES = {
    "ariza": (
        "Araç arızası için 7/24 acil hattımızı arayabilirsiniz: "
        "0 (850) 840 05 39. "
        "Hasar oluştuysa hasar bildirim formumuzu da doldurabilirsiniz."
    ),
    "hasar": (
        "Hemen hasar bildirim formumuza yönlendiriyorum. "
        "Kaza Tespit Tutanağı'nı da indirip doldurmanız gerekecek. "
        "Tüm tamir süreci Büyük Filo tarafından yönetilecek."
    ),
    "lastik": (
        "Lastik değişim formumuza yönlendiriyorum."
    ),
    "servis": (
        "Servis-bakım formumuza yönlendiriyorum. "
        "Ayrıca size en yakın yetkili servis için servis ağı haritamıza da bakabilirsiniz."
    ),
    "teklif": (
        "Teklif formuna yönlendiriyorum. "
        "Uzman danışmanımız en kısa sürede sizinle iletişime geçecek."
    ),
    "trafik": (
        "Trafik cezanızı EGM online işlemler üzerinden sorgulayabilirsiniz."
    ),
    "hgs": (
        "HGS cezanızı PTT HGS müşteri portalı üzerinden sorgulayabilirsiniz."
    ),
    "selamlama": (
        "Merhaba! Büyük Filo'ya hoş geldiniz. "
        "Arıza, hasar, lastik, servis, teklif veya genel sorularınız için buradayım."
    ),
    "kapanis": (
        "Rica ederim! İstediğiniz zaman tekrar yazabilirsiniz. "
        "İyi günler!"
    ),
}

# ─── Intent → Keyword listesi ────────────────────────────────────────────────
INTENT_KEYWORDS: dict[str, list[str]] = {
 
    # Arıza → form yok, acil hat yönlendirmesi
    "ariza": [
        "arıza", "ariza",
        "bozuldu", "bozulmuş", "bozulmus",
        "çalışmıyor", "calismiyor",
        "gitmedi", "gitmiyor",
        "durdu", "durmuş", "durmus",
        "yolda kaldım", "yolda kaldim",
        "mahsur kaldım", "mahsur kaldim",
        "takıldık", "takildik",
        "oturdu kaldı", "oturdu kaldi",
        "start almıyor", "start almiyor",
        "marş yapmıyor", "mars yapmiyor",
        "çekici", "cekici",
        "kurtarıcı", "kurtarici",
        "motordan ses",
        "motor ışığı", "motor isigi",
        "check engine",
        "kontrol lambası", "kontrol lambasi",
        "ısınıyor", "isiniyor",
        "su kaybı", "su kaybi",
        "radyatör", "radyator",
        "fren tutmuyor", "frenler çalışmıyor",
        "direksiyon sertleşti", "direksiyon sertlesti",
        "vites girmiyor",
        "akü bitti", "aku bitti",
        "klima çalışmıyor", "klima calismiyor",
        "yol yardım", "yol yardim",
    ],
 
    # Hasar → hasar formu + kaza tutanağı
    "hasar": [
        "kaza", "çarptım", "carptim", "çarptı", "carpti",
        "hasar",
        "ezildi", "ezilmiş", "ezilmis",
        "çizildi", "cizildi",
        "vurdu", "vurmuş", "vurmus",
        "çalındı", "calindi",
        "hırsız", "hirsiz",
        "kaza yaptım", "kaza yaptim",
        "trafik kazası", "trafik kazasi",
        "kaza tespit", "tutanak",
    ],
 
    # Lastik → lastik formu
    "lastik": [
        "lastik", "tekerlek", "teker",
        "patladı", "patladi", "patlama",
        "sönük", "sonuk",
        "kış lastiği", "kis lastiği",
        "yaz lastiği",
        "lastik değişim", "lastik degisim",
        "lastik servisi",
    ],
 
    # Servis → servis formu + servis ağı
    "servis": [
        "servis", "bakım", "bakim",
        "periyodik", "muayene",
        "yetkili servis", "servis ağı", "servis agi",
        "bakım zamanı", "bakim zamani",
        "revizyon",
    ],
 
    # Teklif → teklif formu
    "teklif": [
        "teklif",
        "fiyat", "ücret", "ucret",
        "ne kadar tutar",
        "kiralamak istiyorum", "kiralama fiyat",
        "uzun dönem", "uzun donem",
        "aylık ödeme", "aylik odeme",
        "kurumsal kiralama", "filo kiralama",
        "bireysel kiralama",
        "elektrikli araç kiralama",
        "ticari araç kiralama", "ticari arac kiralama",
    ],
 
    # Trafik cezası → EGM
    "trafik": [
        "trafik cezası", "trafik cezasi",
        "trafik ceza",
        "ceza geldi", "ceza yedim",
        "ehliyet ceza", "plaka ceza",
    ],
 
    # HGS cezası → PTT HGS
    "hgs": [
        "hgs ceza", "hgs cezası", "hgs cezasi",
        "ogs ceza", "ogs cezası",
        "geçiş ceza", "gecis ceza",
        "köprü ceza", "kopru ceza",
        "otoyol ceza",
        "hgs bakiye", "hgs arıza", "hgs arizasi",
        "hgs sorgu",
    ],
 
    "selamlama": [
        "iyi gunler",
        "iyi aksamlar",
        "yardım lazım", "yardim lazim",
    ],
 
    "kapanis": [
        "tesekkurler", "tesekkur ederim",
        "sagolun", "sag olun",
        "gorusuruz",
        "hosca kalin",
    ],
}

# ─── GUARD listeleri (K1'i bilgi/araç-dışı sorularda susturmak için) ─────────
# Bilgi-sorusu işaretleri: bunlar varsa kullanıcı FORM değil AÇIKLAMA istiyor.
# (Dikkat: "ne kadar" tek başına fiyat=teklif demek olabilir, o yüzden YOK;
#  sadece "ne kadar sürer/süre/zaman" gibi süreç ifadeleri var.)
INFO_MARKERS = [
    "kac gun", "kac gunde", "kac saat", "kac hafta", "kac ayda", "kac kez",
    "ne kadar surer", "ne kadar sure", "ne kadar zaman", "ne kadar siklikta",
    "ne zaman", "ne siklikta", "surec", "sureci",
    "nasil isliyor", "nasil yuruyor", "nasil oluyor", "nasil bir surec",
    "dahil mi", "dahil midir", "kapsiyor mu", "kapsaminda mi", "kapsam",
    "ucretsiz mi", "ucretli mi", "var mi", "veriliyor mu", "yapiliyor mu",
    "nedir", "ne demek", "hakkinda bilgi", "bilgi alabilir",
    "kim oduyor", "kim karsiliyor", "gerekiyor mu", "sart mi", "mumkun mu",
]
# Güçlü aksiyon işaretleri: bunlar varsa bilgi-bekçisi DEVRE DIŞI (form doğru cevap).
STRONG_ACTION_MARKERS = [
    "patladi", "kaza", "carpt", "carpi", "ezild", "cizild", "vurdu",
    "calind", "hirsiz", "yolda kald", "mahsur", "stop etti", "cekici",
    "kurtarici",
]
# Araç-dışı özneler: "sitede arıza var" gibi cümleleri araç arızasından ayırır.
NON_VEHICLE_MARKERS = [
    "site", "sayfa", "uygulama", " app", "internet", "wifi", "baglanti",
    "sifre", "giris", "login", "odeme", "yazici", "ekran", "chatbot", "hesab",
]
VEHICLE_MARKERS = [
    "arac", "araba", "oto", "lastik", "teker", "motor", "fren", "vites",
    "direksiyon", "aku", "far", "cam", "kaput", "tampon", "plaka", "ruhsat",
    "kasko", "servis", "bakim", "yakit", "hgs", "ogs",
]


def _is_informational(normalized_msg: str) -> bool:
    if any(a in normalized_msg for a in STRONG_ACTION_MARKERS):
        return False
    return any(m in normalized_msg for m in INFO_MARKERS)


def _is_non_vehicle(normalized_msg: str) -> bool:
    if any(v in normalized_msg for v in VEHICLE_MARKERS):
        return False
    return any(nv in normalized_msg for nv in NON_VEHICLE_MARKERS)


# ─── Türkçe normalize ────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    char_map = {
        "ı": "i", "ğ": "g", "ü": "u",
        "ş": "s", "ö": "o", "ç": "c",
        "İ": "i", "Ğ": "g", "Ü": "u",  # büyük harfler — lower() bunları düzgün çevirmiyor
        "Ş": "s", "Ö": "o", "Ç": "c",
    }
    for tr_char, en_char in char_map.items():
        text = text.replace(tr_char, en_char)
    return text.lower()


# ─── Ana eşleşme fonksiyonu ───────────────────────────────────────────────────
def match_keyword(message: str) -> KeywordResult:
    """
    Kullanıcı mesajını keyword listesiyle karşılaştırır.

    Öncelik sırası (kritik intentler önce kontrol edilir):
      ariza → hasar → lastik → servis → teklif → hgs → trafik → selamlama → kapanis

    İlk eşleşen intent döner.
    Hiçbiri eşleşmezse matched=False döner, K2 Similarity devreye girer.
    """
    normalized_msg = _normalize(message)

    # ── GUARD 1: araç-dışı özne ("sitede arıza var") → K1 atla, K2'ye bırak ──
    if _is_non_vehicle(normalized_msg):
        return KeywordResult(matched=False)

    # ── GUARD 2: bilgi sorusu ("lastik değişimi kaç günde") → K1 atla, K2'ye bırak ──
    if _is_informational(normalized_msg):
        return KeywordResult(matched=False)

    priority_order = [
        "ariza", "hasar", "lastik", "servis",
        "teklif", "hgs", "trafik", "selamlama", "kapanis",
    ]

    for intent in priority_order:
        keywords = INTENT_KEYWORDS.get(intent, [])
        for keyword in keywords:
            normalized_kw = _normalize(keyword)
            if normalized_kw in normalized_msg:
                return KeywordResult(
                    matched=True,
                    intent=intent,
                    response=STATIC_RESPONSES.get(intent),
                    form_urls=INTENT_FORM_URLS.get(intent, {}),  # selamlama/kapanis için None
                )

    return KeywordResult(matched=False)