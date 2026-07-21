"""add_ivfflat_index

Revision ID: e4b061c8e48e
Revises: 8fe183e5515d
Create Date: 2026-04-27 10:41:14.605706

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4b061c8e48e'
down_revision: Union[str, Sequence[str], None] = '8fe183e5515d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE INDEX ON qa_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);")
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTSqa_embeddings_embedding_ivfflat_idx;")
    pass
