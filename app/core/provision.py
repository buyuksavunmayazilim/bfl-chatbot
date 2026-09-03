"""Yeni bir tenant'in altyapisini hazirlar (DB + sema + varsayilan icerik).

admin 'tenant olustur' ucundan cagrilir (thread icinde). Kayit tablosuna satir
EKLENDIKTEN sonra calisir; DB'yi olusturur, migration'i ve ortak seed'i calistirir.
Sonrasinda cagiran taraf context.add_tenant ile canliya alir.
"""
from __future__ import annotations

import os
import subprocess
import sys

import psycopg2

from app.core.config import settings
from app.core.tenants import tenant_dbname

# Repo koku (alembic.ini ve scripts/ burada)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _create_database(dbname: str) -> None:
    admin = psycopg2.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname="postgres", user=settings.postgres_user, password=settings.postgres_password,
    )
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone() is None:
                cur.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        admin.close()

    conn = psycopg2.connect(
        host=settings.postgres_host, port=settings.postgres_port,
        dbname=dbname, user=settings.postgres_user, password=settings.postgres_password,
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        conn.close()


def provision_tenant(tenant_id: str) -> None:
    """DB olustur + pgvector + migration (semayi kur) + ortak seed (mesaj/branding/esik)."""
    dbname = tenant_dbname(tenant_id)
    _create_database(dbname)
    subprocess.run(
        ["alembic", "-x", f"tenant={tenant_id}", "upgrade", "head"],
        check=True, cwd=_ROOT,
    )
    subprocess.run(
        [sys.executable, "scripts/seed_common.py", "--tenant", tenant_id],
        check=True, cwd=_ROOT,
    )