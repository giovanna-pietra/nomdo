"""remove custos fixos mensais (feature removida)

Revision ID: 1a91dcbf76fc
Revises: 76a693c08d73
Create Date: 2026-07-15 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a91dcbf76fc'
down_revision = '76a693c08d73'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('custo_manutencao_mensal')
        batch_op.drop_column('custo_contas_mensal')
        batch_op.drop_column('contas_mensais')


def downgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('custo_manutencao_mensal', sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column('custo_contas_mensal', sa.Numeric(10, 2), nullable=True))
        batch_op.add_column(sa.Column('contas_mensais', sa.Text(), nullable=True))
