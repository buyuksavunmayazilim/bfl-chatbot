#!/usr/bin/env python3
"""BFL icerik seed'i.

keyword_service/fallback_service/chat.py icinde kodda gomulu olan tum BFL'e ozel
icerigi (intent kelimeleri, hazir cevaplar, form URL'leri, guard listeleri,
fallback metinleri, esikler, branding) tenant'in kendi veritabanina yazar.

- Idempotent: ON CONFLICT DO UPDATE -> tekrar calistirmak guvenli.
- Hedef DB, .env(.local)'deki POSTGRES_DB'dir (BFL dagitiminda BFL veritabani).
- Yeni tenant'lar (kfz vb.) BOS baslar; iceriklerini panelden girersiniz.

Calistirma:
    python scripts/seed_bfl.py
"""
from __future__ import annotations

import json
import os
import sys

import psycopg2
from psycopg2.extras import Json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import Settings  # noqa: E402

_env_file = ".env.local" if os.path.exists(".env.local") else ".env"
settings = Settings(_env_file=_env_file)

DATA = json.loads(r"""{
  "form_urls": {
    "servis_agi": "https://buyukfilo.com/tr/map/",
    "hasar": "https://buyukfilo.com/tr/forms/hasar-bildirim-formu/",
    "lastik": "https://buyukfilo.com/tr/forms/lastik-degisim-formu/",
    "servis": "https://buyukfilo.com/tr/forms/servis-bakim-formu/",
    "teklif": "https://buyukfilo.com/teklif-al/",
    "iletisim": "https://buyukfilo.com/tr/iletisim/",
    "trafik_cezasi": "https://onlineislemler.egm.gov.tr/Sayfalar/TrafikCezaSorgulama.aspx",
    "hgs_cezasi": "https://hgsmusteri.ptt.gov.tr/hgs.jsf#violation",
    "kaza_tespit_tutanagi": "https://buyukfilo.com/api/file/uploads/1771244266332.pdf",
    "kariyer": "https://buyukfilo.com/en/kariyer/"
  },
  "intents": [
    {
      "name": "ariza",
      "static_response": "Araç arızası için 7/24 acil hattımızı arayabilirsiniz: 0 (850) 840 05 39. Hasar oluştuysa hasar bildirim formumuzu da doldurabilirsiniz.",
      "priority": 10,
      "keywords": [
        "arıza",
        "ariza",
        "bozuldu",
        "bozulmuş",
        "bozulmus",
        "çalışmıyor",
        "calismiyor",
        "gitmedi",
        "gitmiyor",
        "durdu",
        "durmuş",
        "durmus",
        "yolda kaldım",
        "yolda kaldim",
        "mahsur kaldım",
        "mahsur kaldim",
        "takıldık",
        "takildik",
        "oturdu kaldı",
        "oturdu kaldi",
        "start almıyor",
        "start almiyor",
        "marş yapmıyor",
        "mars yapmiyor",
        "çekici",
        "cekici",
        "kurtarıcı",
        "kurtarici",
        "motordan ses",
        "motor ışığı",
        "motor isigi",
        "check engine",
        "kontrol lambası",
        "kontrol lambasi",
        "ısınıyor",
        "isiniyor",
        "su kaybı",
        "su kaybi",
        "radyatör",
        "radyator",
        "fren tutmuyor",
        "frenler çalışmıyor",
        "direksiyon sertleşti",
        "direksiyon sertlesti",
        "vites girmiyor",
        "akü bitti",
        "aku bitti",
        "klima çalışmıyor",
        "klima calismiyor",
        "yol yardım",
        "yol yardim"
      ],
      "enabled": true
    },
    {
      "name": "hasar",
      "static_response": "Hemen hasar bildirim formumuza yönlendiriyorum. Kaza Tespit Tutanağı'nı da indirip doldurmanız gerekecek. Tüm tamir süreci Büyük Filo tarafından yönetilecek.",
      "priority": 20,
      "keywords": [
        "kaza",
        "çarptım",
        "carptim",
        "çarptı",
        "carpti",
        "hasar",
        "ezildi",
        "ezilmiş",
        "ezilmis",
        "çizildi",
        "cizildi",
        "vurdu",
        "vurmuş",
        "vurmus",
        "çalındı",
        "calindi",
        "hırsız",
        "hirsiz",
        "kaza yaptım",
        "kaza yaptim",
        "trafik kazası",
        "trafik kazasi",
        "kaza tespit",
        "tutanak"
      ],
      "enabled": true
    },
    {
      "name": "lastik",
      "static_response": "Lastik değişim formumuza yönlendiriyorum.",
      "priority": 30,
      "keywords": [
        "lastik",
        "tekerlek",
        "teker",
        "patladı",
        "patladi",
        "patlama",
        "sönük",
        "sonuk",
        "kış lastiği",
        "kis lastiği",
        "yaz lastiği",
        "lastik değişim",
        "lastik degisim",
        "lastik servisi"
      ],
      "enabled": true
    },
    {
      "name": "servis",
      "static_response": "Servis-bakım formumuza yönlendiriyorum. Ayrıca size en yakın yetkili servis için servis ağı haritamıza da bakabilirsiniz.",
      "priority": 40,
      "keywords": [
        "servis",
        "bakım",
        "bakim",
        "periyodik",
        "muayene",
        "yetkili servis",
        "servis ağı",
        "servis agi",
        "bakım zamanı",
        "bakim zamani",
        "revizyon"
      ],
      "enabled": true
    },
    {
      "name": "teklif",
      "static_response": "Teklif formuna yönlendiriyorum. Uzman danışmanımız en kısa sürede sizinle iletişime geçecek.",
      "priority": 50,
      "keywords": [
        "teklif",
        "fiyat",
        "ücret",
        "ucret",
        "ne kadar tutar",
        "kiralamak istiyorum",
        "kiralama fiyat",
        "uzun dönem",
        "uzun donem",
        "aylık ödeme",
        "aylik odeme",
        "kurumsal kiralama",
        "filo kiralama",
        "bireysel kiralama",
        "elektrikli araç kiralama",
        "ticari araç kiralama",
        "ticari arac kiralama"
      ],
      "enabled": true
    },
    {
      "name": "hgs",
      "static_response": "HGS cezanızı PTT HGS müşteri portalı üzerinden sorgulayabilirsiniz.",
      "priority": 60,
      "keywords": [
        "hgs ceza",
        "hgs cezası",
        "hgs cezasi",
        "ogs ceza",
        "ogs cezası",
        "geçiş ceza",
        "gecis ceza",
        "köprü ceza",
        "kopru ceza",
        "otoyol ceza",
        "hgs bakiye",
        "hgs arıza",
        "hgs arizasi",
        "hgs sorgu"
      ],
      "enabled": true
    },
    {
      "name": "trafik",
      "static_response": "Trafik cezanızı EGM online işlemler üzerinden sorgulayabilirsiniz.",
      "priority": 70,
      "keywords": [
        "trafik cezası",
        "trafik cezasi",
        "trafik ceza",
        "ceza geldi",
        "ceza yedim",
        "ehliyet ceza",
        "plaka ceza"
      ],
      "enabled": true
    },
    {
      "name": "selamlama",
      "static_response": "Merhaba! Büyük Filo'ya hoş geldiniz. Arıza, hasar, lastik, servis, teklif veya genel sorularınız için buradayım.",
      "priority": 80,
      "keywords": [
        "iyi gunler",
        "iyi aksamlar",
        "yardım lazım",
        "yardim lazim"
      ],
      "enabled": true
    },
    {
      "name": "kapanis",
      "static_response": "Rica ederim! İstediğiniz zaman tekrar yazabilirsiniz. İyi günler!",
      "priority": 90,
      "keywords": [
        "tesekkurler",
        "tesekkur ederim",
        "sagolun",
        "sag olun",
        "gorusuruz",
        "hosca kalin"
      ],
      "enabled": true
    },
    {
      "name": "servis_agi",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "kariyer",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "filo_kiralama",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "araclar",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "premium_arac",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "yakit_yonetimi",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "dijital_cozumler",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "musteri_tipi",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "iletisim",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "musteri_hizmetleri",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "subeler",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    },
    {
      "name": "ikame_arac",
      "static_response": null,
      "priority": 100,
      "keywords": [],
      "enabled": true
    }
  ],
  "intent_forms": [
    {
      "intent": "hasar",
      "button_label": "hasar_formu",
      "form_key": "hasar"
    },
    {
      "intent": "hasar",
      "button_label": "kaza_tutanagi",
      "form_key": "kaza_tespit_tutanagi"
    },
    {
      "intent": "lastik",
      "button_label": "lastik_formu",
      "form_key": "lastik"
    },
    {
      "intent": "servis",
      "button_label": "servis_formu",
      "form_key": "servis"
    },
    {
      "intent": "servis",
      "button_label": "servis_agi",
      "form_key": "servis_agi"
    },
    {
      "intent": "servis_agi",
      "button_label": "servis_agi",
      "form_key": "servis_agi"
    },
    {
      "intent": "trafik",
      "button_label": "trafik_cezasi_sorgula",
      "form_key": "trafik_cezasi"
    },
    {
      "intent": "hgs",
      "button_label": "hgs_cezasi_sorgula",
      "form_key": "hgs_cezasi"
    },
    {
      "intent": "kariyer",
      "button_label": "kariyer",
      "form_key": "kariyer"
    },
    {
      "intent": "teklif",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "filo_kiralama",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "araclar",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "premium_arac",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "yakit_yonetimi",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "dijital_cozumler",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "musteri_tipi",
      "button_label": "teklif_formu",
      "form_key": "teklif"
    },
    {
      "intent": "iletisim",
      "button_label": "iletisim",
      "form_key": "iletisim"
    },
    {
      "intent": "musteri_hizmetleri",
      "button_label": "iletisim",
      "form_key": "iletisim"
    },
    {
      "intent": "subeler",
      "button_label": "iletisim",
      "form_key": "iletisim"
    },
    {
      "intent": "ikame_arac",
      "button_label": "iletisim",
      "form_key": "iletisim"
    }
  ],
  "bot_messages": {
    "msg_trigger": "Sorunuzu tam olarak anlayamadım, özür dilerim. Size daha iyi yardımcı olabilmemiz için ekibimiz sizinle iletişime geçmasi için adınızı ve soyadınızı paylaşır mısınız?",
    "msg_ask_pref": "Teşekkürler {name}! Sizi telefonla mı arayalım, yoksa e-posta mı atalım?",
    "msg_ask_phone": "Telefon numaranızı paylaşır mısınız?",
    "msg_ask_email": "E-posta adresinizi paylaşır mısınız?",
    "msg_conf_phone": "Kaydettik! Ekibimiz en kısa sürede {contact} numaranızı arayacak.",
    "msg_conf_email": "Kaydettik! {contact} adresinize en kısa sürede dönüş yapacağız.",
    "msg_invalid_phone": "Geçerli bir telefon numarası giriniz (örn: 0532 111 22 33).",
    "msg_invalid_email": "Geçerli bir e-posta adresi giriniz (örn: ad@ornek.com).",
    "msg_invalid_pref": "Telefon veya e-posta seçeneklerinden birini belirtir misiniz?",
    "msg_declined": "Anlaşıldı! İstediğiniz zaman 444 06 34 veya 0 (850) 840 05 39 numaralı hattımızı arayabilirsiniz. İyi günler!",
    "cancel_reply": "Tabii, iptal ettim. Araç arızası, hasar, servis, lastik, teklif veya genel sorularınız için buradayım.",
    "static_short_input": "Tam anlayamadım. Araç arızası, hasar, servis, lastik veya teklif hakkında yazabilirsiniz.",
    "static_completed": "Başka bir konuda yardımcı olabilir miyim? Araç arızası, hasar bildirimi, servis, lastik veya teklif konularında buradayım."
  },
  "bot_settings": {
    "info_markers": [
      "kac gun",
      "kac gunde",
      "kac saat",
      "kac hafta",
      "kac ayda",
      "kac kez",
      "ne kadar surer",
      "ne kadar sure",
      "ne kadar zaman",
      "ne kadar siklikta",
      "ne zaman",
      "ne siklikta",
      "surec",
      "sureci",
      "nasil isliyor",
      "nasil yuruyor",
      "nasil oluyor",
      "nasil bir surec",
      "dahil mi",
      "dahil midir",
      "kapsiyor mu",
      "kapsaminda mi",
      "kapsam",
      "ucretsiz mi",
      "ucretli mi",
      "var mi",
      "veriliyor mu",
      "yapiliyor mu",
      "nedir",
      "ne demek",
      "hakkinda bilgi",
      "bilgi alabilir",
      "kim oduyor",
      "kim karsiliyor",
      "gerekiyor mu",
      "sart mi",
      "mumkun mu"
    ],
    "strong_action_markers": [
      "patladi",
      "kaza",
      "carpt",
      "carpi",
      "ezild",
      "cizild",
      "vurdu",
      "calind",
      "hirsiz",
      "yolda kald",
      "mahsur",
      "stop etti",
      "cekici",
      "kurtarici"
    ],
    "non_vehicle_markers": [
      "site",
      "sayfa",
      "uygulama",
      " app",
      "internet",
      "wifi",
      "baglanti",
      "sifre",
      "giris",
      "login",
      "odeme",
      "yazici",
      "ekran",
      "chatbot",
      "hesab"
    ],
    "vehicle_markers": [
      "arac",
      "araba",
      "oto",
      "lastik",
      "teker",
      "motor",
      "fren",
      "vites",
      "direksiyon",
      "aku",
      "far",
      "cam",
      "kaput",
      "tampon",
      "plaka",
      "ruhsat",
      "kasko",
      "servis",
      "bakim",
      "yakit",
      "hgs",
      "ogs"
    ],
    "cancel_words": [
      "bastan",
      "baştan",
      "cik",
      "geri",
      "hayır",
      "iptal",
      "kapat",
      "menu",
      "menü",
      "vazgectim",
      "vazgeç",
      "vazgeçtim",
      "yok",
      "çık"
    ],
    "allow_interrupt_intents": [
      "ariza",
      "hasar",
      "hgs",
      "lastik",
      "servis",
      "teklif",
      "trafik"
    ],
    "similarity_threshold_high": 0.65,
    "similarity_threshold_low": 0.5,
    "widget_color": "#537286"
  }
}""")


def main() -> int:
    conn = psycopg2.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=settings.postgres_db, user=settings.postgres_user,
        password=settings.postgres_password,
    )
    try:
        with conn, conn.cursor() as cur:
            # 1) form_urls (intent_forms FK'i icin once)
            for key, url in DATA["form_urls"].items():
                cur.execute(
                    "INSERT INTO form_urls (key, url) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET url = EXCLUDED.url",
                    (key, url),
                )
            # 2) intents
            for it in DATA["intents"]:
                cur.execute(
                    "INSERT INTO intents (name, static_response, priority, keywords, enabled) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (name) DO UPDATE SET "
                    "static_response = EXCLUDED.static_response, "
                    "priority = EXCLUDED.priority, "
                    "keywords = EXCLUDED.keywords, "
                    "enabled = EXCLUDED.enabled",
                    (it["name"], it["static_response"], it["priority"], it["keywords"], it["enabled"]),
                )
            # 3) intent_forms
            for f in DATA["intent_forms"]:
                cur.execute(
                    "INSERT INTO intent_forms (intent, button_label, form_key) "
                    "VALUES (%s, %s, %s) "
                    "ON CONFLICT (intent, button_label) DO UPDATE SET form_key = EXCLUDED.form_key",
                    (f["intent"], f["button_label"], f["form_key"]),
                )
            # 4) bot_messages
            for key, text in DATA["bot_messages"].items():
                cur.execute(
                    "INSERT INTO bot_messages (key, text) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET text = EXCLUDED.text",
                    (key, text),
                )
            # 5) bot_settings (JSONB)
            for key, value in DATA["bot_settings"].items():
                cur.execute(
                    "INSERT INTO bot_settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    (key, Json(value)),
                )
        print(
            "Seed tamam -> DB={db} | form_urls={fu} intents={ic} "
            "intent_forms={iff} bot_messages={bm} bot_settings={bs}".format(
                db=settings.postgres_db,
                fu=len(DATA["form_urls"]), ic=len(DATA["intents"]),
                iff=len(DATA["intent_forms"]), bm=len(DATA["bot_messages"]),
                bs=len(DATA["bot_settings"]),
            )
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())