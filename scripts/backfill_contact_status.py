"""Gecmis gorusmeleri yeniden siniflandirir: iletisim alinan (fallback akisi
tamamlanan) turlari 'cevaplanamadi' yerine 'iletisim alindi' yapar.

Neden: Bot bir soruyu yanitlayamayinca iletisim bilgisi toplar (fallback). Bu
akistaki TUM turlar source='fallback' kaydedildigi icin, iletisim basariyla
alinip onaylandigi tur bile panelde "cevaplanamadi" gorunuyordu. Yeni kayitlar
artik dogru isaretleniyor (chat.py: tamamlanan tur intent='iletisim_alindi').
Bu script yalnizca ESKI kayitlari bir kez duzeltir.

Tespit: bir bot 'fallback' mesaji, ayni oturumda kaydedilmis bir iletisim
degerini (fallback_contacts.contact_value) iceriyorsa -> bu bir onay turudur.

Calistirma (ornek):
    docker compose exec api python -m scripts.backfill_contact_status
Idempotent: tekrar calistirmak guvenli.
"""
from __future__ import annotations

import psycopg2

from app.core.config import settings
from app.core.tenants import list_all_tenant_rows, tenant_dbname

UPDATE_SQL = """
    UPDATE messages m
    SET intent = 'iletisim_alindi'
    FROM conversations c
    JOIN fallback_contacts fc ON fc.session_id = c.session_id
    WHERE m.conversation_id = c.id
      AND m.role = 'bot'
      AND m.source = 'fallback'
      AND m.intent IS DISTINCT FROM 'iletisim_alindi'
      AND fc.contact_value <> ''
      AND position(fc.contact_value IN m.content) > 0
"""


def _connect(dbname: str):
    return psycopg2.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=dbname, user=settings.postgres_user, password=settings.postgres_password,
    )


def main() -> int:
    tenants = list_all_tenant_rows()  # [(id, label, enabled)]
    total = 0
    for tid, _label, _enabled in tenants:
        db = tenant_dbname(tid)
        try:
            conn = _connect(db)
        except Exception as exc:
            print(f"[backfill] ATLANDI: {tid} ({db}) -> {exc}")
            continue
        try:
            with conn, conn.cursor() as cur:
                cur.execute(UPDATE_SQL)
                n = cur.rowcount or 0
                total += n
                print(f"[backfill] {tid} ({db}) -> {n} tur 'iletisim_alindi' olarak guncellendi")
        finally:
            conn.close()
    print(f"[backfill] Tamam. Toplam {total} tur guncellendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())