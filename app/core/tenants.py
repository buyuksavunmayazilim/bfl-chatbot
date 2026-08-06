"""Tenant kayit defteri.

Her chatbot bir "tenant"tir (bfl, kfz, kfz_lease, bsy). Bu dosya her tenant'in
statik yapilandirmasini tutar: hangi veritabanina baglanacagi, hangi embedding
sutununu ve benzerlik esiklerini kullanacagi.

Adim 1: Sadece "bfl" tanimli ve tum degerleri mevcut Settings'ten turetiliyor,
boylece davranis birebir ayni kalir. Yeni tenant'lar buraya eklenecek.

Icerik paketleri (keyword kurallari, form URL'leri, hazir metinler) Adim 2'de
bu yapiya eklenecek.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class DBConfig:
    """Bir tenant'in Postgres baglanti bilgisi."""

    host: str
    port: int
    dbname: str
    user: str
    password: str


@dataclass(frozen=True)
class TenantConfig:
    """Bir chatbot'un statik yapilandirmasi."""

    id: str
    label: str
    db: DBConfig
    similarity_column: str
    similarity_threshold_high: float
    similarity_threshold_low: float


# Uygulama genelinde varsayilan tenant (geriye donuk uyumluluk / fallback icin).
DEFAULT_TENANT_ID = "bfl"


# Tenant -> veritabani adi.
# Tumu ayni Postgres konteynerinde, farkli veritabanlarinda durur.
# Isimler POSTGRES_DB_<TENANT> env degiskeni ile override edilebilir.
_DBNAME_DEFAULTS = {
    "kfz": "kfz_chatbot",
    "kfz_lease": "kfz_lease_chatbot",
    "bsy": "bsy_chatbot",
}


def tenant_dbname(tenant_id: str, s=settings) -> str:
    """Bir tenant'in veritabani adini doner (bfl mevcut ayardan, digerleri konvansiyon)."""
    if tenant_id == "bfl":
        return s.postgres_db
    if tenant_id not in _DBNAME_DEFAULTS:
        raise KeyError(f"Bilinmeyen tenant: {tenant_id!r}")
    return os.getenv(f"POSTGRES_DB_{tenant_id.upper()}", _DBNAME_DEFAULTS[tenant_id])


def _make_tenant(tenant_id: str, label: str) -> TenantConfig:
    """Ayni konteynerde farkli DB'ye bakan bir TenantConfig kurar.

    Host/port/user/password tum tenant'larda ortaktir (tek Postgres); yalnizca
    dbname degisir. Embedding modeli ve esikler de simdilik BFL ile ayni.
    """
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


TENANTS: dict[str, TenantConfig] = {
    "bfl": _make_tenant("bfl", "Buyuk Filo"),
    "kfz": _make_tenant("kfz", "KFZ"),
    "kfz_lease": _make_tenant("kfz_lease", "KFZ Lease"),
    "bsy": _make_tenant("bsy", "BSY"),
}


def get_tenant_config(tenant_id: str) -> TenantConfig:
    """tenant_id'ye karsilik gelen yapilandirmayi doner, yoksa KeyError."""
    try:
        return TENANTS[tenant_id]
    except KeyError:
        raise KeyError(f"Bilinmeyen tenant: {tenant_id!r}") from None