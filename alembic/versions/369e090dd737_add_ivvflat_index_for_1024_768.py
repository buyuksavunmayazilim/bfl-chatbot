# alembic/versions/369e090dd737_add_ivvflat_index_for_1024_768.py

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy

revision: str = '369e090dd737'
down_revision: Union[str, Sequence[str], None] = 'e4b061c8e48e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mevcut qa_embeddings tablosuna 2 yeni sütun ekle
    op.add_column('qa_embeddings',
        sa.Column('embedding_768', pgvector.sqlalchemy.Vector(768), nullable=True)
    )
    op.add_column('qa_embeddings',
        sa.Column('embedding_1024', pgvector.sqlalchemy.Vector(1024), nullable=True)
    )

    # ivfflat index'leri ekle
    op.execute(
        "CREATE INDEX qa_embeddings_768_ivfflat_idx "
        "ON qa_embeddings USING ivfflat (embedding_768 vector_cosine_ops) "
        "WITH (lists = 100);"
    )
    op.execute(
        "CREATE INDEX qa_embeddings_1024_ivfflat_idx "
        "ON qa_embeddings USING ivfflat (embedding_1024 vector_cosine_ops) "
        "WITH (lists = 100);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS qa_embeddings_768_ivfflat_idx;")
    op.execute("DROP INDEX IF EXISTS qa_embeddings_1024_ivfflat_idx;")
    op.drop_column('qa_embeddings', 'embedding_768')
    op.drop_column('qa_embeddings', 'embedding_1024')