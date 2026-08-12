"""add assinaturas (assinatura mensal recorrente)

Revision ID: a9b8c7d6e5f4
Revises: e1f2a3b4c5d6
Create Date: 2026-08-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9b8c7d6e5f4'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    # ### assinaturas ###
    op.create_table(
        'assinaturas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asaas_subscription_id', sa.String(length=60), nullable=True),
        sa.Column('plano', sa.String(length=20), nullable=False),
        sa.Column('valor_cents', sa.Integer(), nullable=False),
        sa.Column('ciclo', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('proximo_vencimento', sa.Date(), nullable=True),
        sa.Column('cancelado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asaas_subscription_id'),
    )
    with op.batch_alter_table('assinaturas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_assinaturas_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_assinaturas_asaas_subscription_id'), ['asaas_subscription_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_assinaturas_status'), ['status'], unique=False)

    # ### pagamentos: vínculo com a assinatura que gerou a cobrança ###
    with op.batch_alter_table('pagamentos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assinatura_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_pagamentos_assinatura_id'), ['assinatura_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_pagamentos_assinatura_id',
            'assinaturas',
            ['assinatura_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('pagamentos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pagamentos_assinatura_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_pagamentos_assinatura_id'))
        batch_op.drop_column('assinatura_id')

    with op.batch_alter_table('assinaturas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_assinaturas_status'))
        batch_op.drop_index(batch_op.f('ix_assinaturas_asaas_subscription_id'))
        batch_op.drop_index(batch_op.f('ix_assinaturas_user_id'))
    op.drop_table('assinaturas')
