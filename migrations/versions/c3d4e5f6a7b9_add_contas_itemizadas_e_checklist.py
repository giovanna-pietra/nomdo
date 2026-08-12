"""add contas mensais itemizadas e checklist de hospedagem

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-07-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b9'
down_revision = 'b2c3d4e5f6a8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        # Lista itemizada de contas mensais (luz, água, internet, gás...).
        # custo_contas_mensal (valor único) é mantido pra não perder dado
        # de imóveis antigos — vira fallback quando contas_mensais está vazio.
        batch_op.add_column(sa.Column('contas_mensais', sa.Text(), nullable=True))
        # Template editável do checklist de hospedagem (antes/depois).
        batch_op.add_column(sa.Column('checklist_itens', sa.Text(), nullable=True))

    with op.batch_alter_table('estadia', schema=None) as batch_op:
        # Progresso do checklist específico de cada estadia.
        batch_op.add_column(sa.Column('checklist_status', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.drop_column('checklist_status')

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('checklist_itens')
        batch_op.drop_column('contas_mensais')
