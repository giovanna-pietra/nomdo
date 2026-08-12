"""add custos recorrentes mensais ao imovel (dashboard financeiro do proprietario)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a8'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('custo_manutencao_mensal', sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column('custo_contas_mensal', sa.Numeric(10, 2), nullable=True))


def downgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('custo_contas_mensal')
        batch_op.drop_column('custo_manutencao_mensal')
