"""Calisma zamani tenant baglami (context) ve baglanti havuzu yonetimi.

TenantConfig statik yapilandirmadir; TenantContext ise buna bir canli asyncpg
havuzu (pool) ekler. Uygulama basladiginda her tenant icin bir havuz acilir ve
istekler `asyncpg.connect(...)` yerine bu havuzdan baglanti alir.

Model (embedding) tenant'tan bagimsizdir ve similarity_service icinde tek bir
singleton olarak paylasilir; burada modelle ilgili bir sey yoktur.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg

from app.core.content import TenantContent, load_content
from app.core.tenants import (
    TENANTS,
    TenantConfig,
    get_tenant_config,
    load_registry,
)


@dataclass
class TenantContext:
    """Bir tenant'in yapilandirmasi + canli baglanti havuzu + icerigi."""

    config: TenantConfig
    pool: asyncpg.Pool
    content: TenantContent

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def similarity_column(self) -> str:
        return self.config.similarity_column


# tenant_id -> TenantContext
_registry: dict[str, TenantContext] = {}


async def init_tenants(min_size: int = 1, max_size: int = 10) -> None:
    """Startup: her tenant icin bir asyncpg havuzu acar.

    Idempotent — daha once acilmis tenant'lar tekrar acilmaz.
    """
    load_registry()  # Tenant listesini kayit tablosundan (DB) yukle
    for tenant_id, cfg in TENANTS.items():
        if tenant_id in _registry:
            continue
        try:
            pool = await asyncpg.create_pool(
                host=cfg.db.host,
                port=cfg.db.port,
                database=cfg.db.dbname,
                user=cfg.db.user,
                password=cfg.db.password,
                min_size=min_size,
                max_size=max_size,
            )
            content = await load_content(pool)
        except Exception as exc:
            # Bir tenant'in DB'si yoksa/hazir degilse tum uygulamayi cokertme;
            # o tenant'i atla, digerleri calismaya devam etsin.
            print(f"[Tenants] ATLANDI: {tenant_id} ({cfg.db.dbname}) -> {exc}")
            continue
        _registry[tenant_id] = TenantContext(config=cfg, pool=pool, content=content)
        print(
            f"[Tenants] Havuz acildi: {tenant_id} -> {cfg.db.dbname} "
            f"(intent={len(content.priority_order)}, mesaj={len(content.messages)})"
        )


async def close_tenants() -> None:
    """Shutdown: tum havuzlari kapatir."""
    for tenant_id, ctx in _registry.items():
        await ctx.pool.close()
        print(f"[Tenants] Havuz kapatildi: {tenant_id}")
    _registry.clear()


async def reload_content(tenant_id: str) -> None:
    """Bir tenant'in icerigini DB'den yeniden yukler (panel duzenlemesi sonrasi).

    Bellekteki icerik yerine yenisi konur; kilit gerekmez cunku atomik atama yapilir.
    """
    ctx = _registry.get(tenant_id)
    if ctx is None:
        raise RuntimeError(f"Tenant {tenant_id!r} yuklu degil; reload edilemez.")
    ctx.content = await load_content(ctx.pool)
    print(f"[Tenants] Icerik yeniden yuklendi: {tenant_id}")


async def add_tenant(tenant_id: str, min_size: int = 1, max_size: int = 10) -> None:
    """Yeni olusturulmus bir tenant'i canli registry'ye ekler (restart'siz).

    Kayit tablosunu tazeler, havuz acar ve icerigi yukler.
    """
    load_registry()
    cfg = TENANTS.get(tenant_id)
    if cfg is None:
        raise RuntimeError(f"Tenant {tenant_id!r} kayit tablosunda bulunamadi.")
    if tenant_id in _registry:
        # Zaten yukluyse icerigi tazele, yeni havuz acma.
        await reload_content(tenant_id)
        return
    pool = await asyncpg.create_pool(
        host=cfg.db.host, port=cfg.db.port, database=cfg.db.dbname,
        user=cfg.db.user, password=cfg.db.password,
        min_size=min_size, max_size=max_size,
    )
    content = await load_content(pool)
    _registry[tenant_id] = TenantContext(config=cfg, pool=pool, content=content)
    print(f"[Tenants] Canliya eklendi: {tenant_id} -> {cfg.db.dbname}")


def get_tenant(tenant_id: str) -> TenantContext:
    """tenant_id'ye karsilik gelen canli baglami doner.

    Bilinmeyen tenant -> KeyError.
    Tanimli ama havuzu baslatilmamis tenant -> RuntimeError.
    """
    ctx = _registry.get(tenant_id)
    if ctx is None:
        # Once yapilandirma var mi diye bak; yoksa KeyError firlatilir.
        get_tenant_config(tenant_id)
        raise RuntimeError(
            f"Tenant {tenant_id!r} havuzu baslatilmamis. "
            "init_tenants() startup'ta cagrildi mi?"
        )
    return ctx