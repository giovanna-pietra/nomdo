"""add cidade/estado ao imovel (regiao pra precificacao)

Revision ID: db1a6bc9a5b9
Revises: a7b8c9d0e1f2
Create Date: 2026-07-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'db1a6bc9a5b9'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cidade', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('estado', sa.String(length=2), nullable=True))


def downgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('estado')
        batch_op.drop_column('cidade')
