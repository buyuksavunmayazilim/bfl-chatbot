"""icerik tablolari: intents, form_urls, intent_forms, bot_messages, bot_settings

Sirkete ozel icerik (keyword kurallari, form URL'leri, hazir metinler, guard
listeleri) artik kodda degil, her tenant'in kendi veritabaninda tutulur. Boylece
tek bir panelden istenen chatbot'un verileri deploy gerektirmeden duzenlenebilir.

Matching ALGORITMASI kodda kalir; bu tablolar yalnizca VERI tutar.

Bu migration 4 tenant DB'sinin her birinde ayri ayri calistirilir.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7c3f19b2e4d"
down_revision: Union[str, Sequence[str], None] = "XXXX"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Intent kayit defteri (K1 keyword + K2 similarity ortak intent isimleri)
    op.create_table(
        "intents",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("static_response", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "keywords",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )

    # 2. Form URL kayit defteri (tek yerden degistir -> her intent guncellensin)
    op.create_table(
        "form_urls",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
    )

    # 3. Intent -> hangi form butonlari gosterilsin
    op.create_table(
        "intent_forms",
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("button_label", sa.Text(), nullable=False),
        sa.Column("form_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["intent"], ["intents.name"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["form_key"], ["form_urls.key"]),
        sa.PrimaryKeyConstraint("intent", "button_label"),
    )

    # 4. Bagimsiz hazir metinler (fallback akisi + chat.py static mesajlari)
    op.create_table(
        "bot_messages",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
    )

    # 5. Ayar/liste config (guard listeleri, cancel_words, esikler, branding)
    op.create_table(
        "bot_settings",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
    )


def downgrade() -> None:
    # FK sirasina dikkat: once cocuk tablo (intent_forms) dusurulur.
    op.drop_table("intent_forms")
    op.drop_table("bot_settings")
    op.drop_table("bot_messages")
    op.drop_table("form_urls")
    op.drop_table("intents")