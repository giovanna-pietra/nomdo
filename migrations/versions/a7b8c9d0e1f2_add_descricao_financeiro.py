"""add descricao ao financeiro (lançamento manual unificado com despesas)

Revision ID: a7b8c9d0e1f2
Revises: 1a91dcbf76fc
Create Date: 2026-07-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = '1a91dcbf76fc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('financeiros', schema=None) as batch_op:
        batch_op.add_column(sa.Column('descricao', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('financeiros', schema=None) as batch_op:
        batch_op.drop_column('descricao')
