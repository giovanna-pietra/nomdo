"""add ponto_referencia ao imovel (busca por cidade/referência)

Revision ID: 76a693c08d73
Revises: b30cea1a6dbf
Create Date: 2026-07-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '76a693c08d73'
down_revision = 'b30cea1a6dbf'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ponto_referencia', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('ponto_referencia')
