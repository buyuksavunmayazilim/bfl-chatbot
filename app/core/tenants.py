"""Tenant kayit defteri — dinamik (veritabani destekli).

Her chatbot bir "tenant"tir. Tenant listesi ARTIK kodda sabit degil; varsayilan
veritabanindaki (settings.postgres_db) 'tenants' tablosunda tutulur. Boylece yeni
tenant panelden acilir, kod degisikligi ve restart gerekmez.

Bir tenant tamamen (id, label) ile tanimlidir; gerisi turer:
  - dbname: '<id>_chatbot' (bfl icin settings.postgres_db) — POSTGRES_DB_<ID> ile override
  - host/port/user/password: tum tenant'larda ortak (tek Postgres)
  - similarity_column ve varsayilan esikler: Settings'ten
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import psycopg2

from app.core.config import settings


@dataclass(frozen=True)
class DBConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


@dataclass(frozen=True)
class TenantConfig:
    id: str
    label: str
    db: DBConfig
    similarity_column: str
    similarity_threshold_high: float
    similarity_threshold_low: float


DEFAULT_TENANT_ID = "bfl"

# Ilk kurulumda 'tenants' tablosu bossa eklenecek yerlesik tenant'lar.
BUILTIN_TENANTS: list[tuple[str, str]] = [
    ("bfl", "Buyuk Filo"),
    ("kfz", "KFZ"),
    ("kfz_lease", "KFZ Lease"),
    ("bsy", "BSY"),
]

# Calisma zamani registry (startup'ta load_registry ile doldurulur).
TENANTS: dict[str, TenantConfig] = {}


# ─── id / dbname yardimcilari ────────────────────────────────────────────────
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")


def valid_tenant_id(tenant_id: str) -> bool:
    """Kucuk harf, rakam, alt cizgi; harfle baslar (guvenli DB/URL adi)."""
    return bool(_ID_RE.match(tenant_id))


def tenant_dbname(tenant_id: str, s=settings) -> str:
    """Bir tenant'in veritabani adi (bfl varsayilan DB, digerleri '<id>_chatbot')."""
    if tenant_id == "bfl":
        return s.postgres_db
    return os.getenv(f"POSTGRES_DB_{tenant_id.upper()}", f"{tenant_id}_chatbot")


def build_config(tenant_id: str, label: str) -> TenantConfig:
    """Ayni konteynerde farkli DB'ye bakan bir TenantConfig kurar."""
    return TenantConfig(
        id=tenant_id,
        label=label,
        db=DBConfig(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=tenant_dbname(tenant_id),
            user=settings.postgres_user,
            password=settings.postgres_password,
        ),
        similarity_column=settings.similarity_column,
        similarity_threshold_high=settings.similarity_threshold_high,
        similarity_threshold_low=settings.similarity_threshold_low,
    )


# ─── Kayit tablosu (varsayilan DB icinde) ────────────────────────────────────
def _meta_connect():
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )


def ensure_meta() -> None:
    """'tenants' tablosunu olusturur (yoksa) ve bossa yerlesik tenant'lari ekler."""
    conn = _meta_connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tenants (
                    id         TEXT PRIMARY KEY,
                    label      TEXT NOT NULL,
                    enabled    BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("SELECT COUNT(*) FROM tenants")
            if cur.fetchone()[0] == 0:
                for tid, label in BUILTIN_TENANTS:
                    cur.execute(
                        "INSERT INTO tenants (id, label) VALUES (%s, %s) "
                        "ON CONFLICT (id) DO NOTHING",
                        (tid, label),
                    )
    finally:
        conn.close()


def list_tenant_rows() -> list[tuple[str, str]]:
    conn = _meta_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, label FROM tenants WHERE enabled ORDER BY created_at, id"
            )
            return [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        conn.close()


def add_tenant_row(tenant_id: str, label: str) -> None:
    """Yeni tenant'i kayit tablosuna ekler; zaten varsa hata."""
    conn = _meta_connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tenants WHERE id = %s", (tenant_id,))
            if cur.fetchone():
                raise ValueError(f"Tenant zaten var: {tenant_id}")
            cur.execute(
                "INSERT INTO tenants (id, label) VALUES (%s, %s)",
                (tenant_id, label),
            )
    finally:
        conn.close()


def load_registry() -> None:
    """Kayit tablosunu okuyup TENANTS'i (bellek) yeniden doldurur."""
    ensure_meta()
    rows = list_tenant_rows()
    TENANTS.clear()
    for tid, label in rows:
        TENANTS[tid] = build_config(tid, label)


def get_tenant_config(tenant_id: str) -> TenantConfig:
    try:
        return TENANTS[tenant_id]
    except KeyError:
        raise KeyError(f"Bilinmeyen tenant: {tenant_id!r}") from None