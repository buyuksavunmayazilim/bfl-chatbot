import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Proje importları
from app.core.config import Settings
from app.core.tenants import tenant_dbname
from app.db.database import Base
from app.models import tables  # noqa: F401

import os

env_file = ".env.local" if os.path.exists(".env.local") else ".env"
print(f"Using environment file: {env_file}")
settings = Settings(_env_file=env_file)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hedef tenant: `alembic -x tenant=kfz upgrade head`. Verilmezse bfl (varsayilan).
x_args = context.get_x_argument(as_dictionary=True)
tenant = x_args.get("tenant", "bfl")
try:
    dbname = tenant_dbname(tenant, settings)
except KeyError as exc:
    raise SystemExit(f"Gecersiz -x tenant ({exc}). Gecerli: bfl, kfz, kfz_lease, bsy")

sync_url = (
    f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
    f"@{settings.postgres_host}:{settings.postgres_port}/{dbname}"
)
config.set_main_option("sqlalchemy.url", sync_url)
print(f"[alembic] tenant={tenant} db={dbname}")

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()