#!/usr/bin/env python3
"""Tek komutla guvenli kurulum — hem yeni sunucu hem mevcut sistem icin.

Sirayla, hepsi IDEMPOTENT (tekrar calismasi zararsiz):
  1. Her tenant icin veritabanini olusturur (yoksa) + pgvector uzantisini kurar.
  2. Her tenant DB'sinde 'alembic upgrade head' calistirir (semayi olusturur).
  3. Varsayilan icerigi seed'ler:
        - seed_bfl.py      -> BFL varsayilan intent/kelime/form/mesaj/ayar
        - seed_common.py   -> tum tenant'lara fallback mesajlari + branding
     Seed'ler ON CONFLICT DO NOTHING kullanir; mevcut/duzenlenmis kayitlari EZMEZ,
     bu yuzden her acilista guvenle calisir ve veri geri yuklemesini bozmaz.

Container acilis komutunda cagrilir:  python scripts/bootstrap.py && uvicorn ...
"""
from __future__ import annotations

import os
import subprocess
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import Settings  # noqa: E402
from app.core.tenants import TENANTS, load_registry, tenant_dbname  # noqa: E402

_env_file = ".env.local" if os.path.exists(".env.local") else ".env"
settings = Settings(_env_file=_env_file)


def _connect(dbname: str):
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=dbname,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def ensure_databases() -> None:
    # 'postgres' bakim veritabanina baglanip eksik tenant DB'lerini olustur.
    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            for tenant_id in TENANTS:
                dbname = tenant_dbname(tenant_id, settings)
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{dbname}"')
                    print(f"[bootstrap] veritabani olusturuldu: {dbname}")
                else:
                    print(f"[bootstrap] veritabani zaten var: {dbname}")
    finally:
        admin.close()

    # pgvector uzantisi her DB'de ayri ayri kurulmali.
    for tenant_id in TENANTS:
        dbname = tenant_dbname(tenant_id, settings)
        conn = _connect(dbname)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            conn.close()
    print("[bootstrap] pgvector uzantilari hazir.")


def migrate() -> None:
    for tenant_id in TENANTS:
        print(f"[bootstrap] migration: {tenant_id}")
        subprocess.run(
            ["alembic", "-x", f"tenant={tenant_id}", "upgrade", "head"],
            check=True,
        )


def seed() -> None:
    for script in ("scripts/seed_bfl.py", "scripts/seed_common.py"):
        print(f"[bootstrap] seed: {script}")
        subprocess.run([sys.executable, script], check=True)


def main() -> int:
    # Tenant listesini kayit tablosundan yukle (tablo yoksa olusturur, yerlesikleri ekler).
    load_registry()
    print(f"[bootstrap] tenant'lar: {', '.join(TENANTS)}")
    ensure_databases()
    migrate()
    seed()
    print("[bootstrap] tamam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())