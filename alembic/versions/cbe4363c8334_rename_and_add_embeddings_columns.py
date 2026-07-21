from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

revision: str = 'XXXX'  # otomatik gelecek
down_revision: Union[str, Sequence[str], None] = '369e090dd737'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Mevcut sütunları yeniden adlandır ────────────────────────────────────
    op.alter_column('qa_embeddings', 'embedding',
                    new_column_name='embedding_minilm_384')
    op.alter_column('qa_embeddings', 'embedding_768',
                    new_column_name='embedding_mpnet_768')
    op.alter_column('qa_embeddings', 'embedding_1024',
                    new_column_name='embedding_bge_1024')

    # ── Mevcut index'leri yeniden adlandır ───────────────────────────────────
    op.execute("ALTER INDEX qa_embeddings_embedding_idx RENAME TO qa_embeddings_minilm_384_idx;")
    op.execute("ALTER INDEX qa_embeddings_768_ivfflat_idx RENAME TO qa_embeddings_mpnet_768_idx;")
    op.execute("ALTER INDEX qa_embeddings_1024_ivfflat_idx RENAME TO qa_embeddings_bge_1024_idx;")

    # ── Yeni sütunlar ekle ───────────────────────────────────────────────────
    op.add_column('qa_embeddings',
        sa.Column('embedding_emrecan_768',
                  pgvector.sqlalchemy.Vector(768), nullable=True))
    op.add_column('qa_embeddings',
        sa.Column('embedding_convbert_768',
                  pgvector.sqlalchemy.Vector(768), nullable=True))

    # ── Yeni sütunlar için ivfflat index ────────────────────────────────────
    op.execute(
        "CREATE INDEX qa_embeddings_emrecan_768_idx "
        "ON qa_embeddings USING ivfflat (embedding_emrecan_768 vector_cosine_ops) "
        "WITH (lists = 100);"
    )
    op.execute(
        "CREATE INDEX qa_embeddings_convbert_768_idx "
        "ON qa_embeddings USING ivfflat (embedding_convbert_768 vector_cosine_ops) "
        "WITH (lists = 100);"
    )


def downgrade() -> None:
    # Index'leri sil
    op.execute("DROP INDEX IF EXISTS qa_embeddings_emrecan_768_idx;")
    op.execute("DROP INDEX IF EXISTS qa_embeddings_convbert_768_idx;")

    # Yeni sütunları sil
    op.drop_column('qa_embeddings', 'embedding_emrecan_768')
    op.drop_column('qa_embeddings', 'embedding_convbert_768')

    # Index'leri eski adına döndür
    op.execute("ALTER INDEX qa_embeddings_minilm_384_idx RENAME TO qa_embeddings_embedding_idx;")
    op.execute("ALTER INDEX qa_embeddings_mpnet_768_idx RENAME TO qa_embeddings_768_ivfflat_idx;")
    op.execute("ALTER INDEX qa_embeddings_bge_1024_idx RENAME TO qa_embeddings_1024_ivfflat_idx;")

    # Sütunları eski adına döndür
    op.alter_column('qa_embeddings', 'embedding_minilm_384',
                    new_column_name='embedding')
    op.alter_column('qa_embeddings', 'embedding_mpnet_768',
                    new_column_name='embedding_768')
    op.alter_column('qa_embeddings', 'embedding_bge_1024',
                    new_column_name='embedding_1024')