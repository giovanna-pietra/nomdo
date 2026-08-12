"""add paywall (pagamentos) e formulario de condominio

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    # ### users: paywall ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column(
            'pagamento_ativo', existing_type=sa.Boolean(),
            nullable=False, server_default=sa.false(),
        )
        batch_op.add_column(sa.Column('asaas_customer_id', sa.String(length=60), nullable=True))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('pagamento_ativo', server_default=None)

    # ### imoveis: formulario do condominio ###
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('formulario_condominio_ativo', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('nome_condominio', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('email_portaria', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('regimento_resumo', sa.Text(), nullable=True))

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.alter_column('formulario_condominio_ativo', server_default=None)

    # ### pagamentos ###
    op.create_table(
        'pagamentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asaas_customer_id', sa.String(length=60), nullable=True),
        sa.Column('asaas_payment_id', sa.String(length=60), nullable=True),
        sa.Column('valor_cents', sa.Integer(), nullable=False),
        sa.Column('billing_type', sa.String(length=20), nullable=True),
        sa.Column('invoice_url', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('confirmado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asaas_payment_id'),
    )
    with op.batch_alter_table('pagamentos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pagamentos_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagamentos_asaas_payment_id'), ['asaas_payment_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_pagamentos_status'), ['status'], unique=False)

    # ### formularios_condominio ###
    op.create_table(
        'formularios_condominio',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('estadia_id', sa.Integer(), nullable=False),
        sa.Column('imovel_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('tentativas_envio', sa.Integer(), nullable=False),
        sa.Column('data_ultimo_envio', sa.Date(), nullable=True),
        sa.Column('respondido_em', sa.DateTime(), nullable=True),
        sa.Column('qtd_pets', sa.Integer(), nullable=True),
        sa.Column('pets_json', sa.Text(), nullable=True),
        sa.Column('pessoas_json', sa.Text(), nullable=True),
        sa.Column('placa_veiculo', sa.String(length=15), nullable=True),
        sa.Column('modelo_veiculo', sa.String(length=80), nullable=True),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['estadia_id'], ['estadia.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['imovel_id'], ['imoveis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('estadia_id'),
        sa.UniqueConstraint('token'),
    )
    with op.batch_alter_table('formularios_condominio', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_formularios_condominio_imovel_id'), ['imovel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_formularios_condominio_token'), ['token'], unique=True)
        batch_op.create_index(batch_op.f('ix_formularios_condominio_status'), ['status'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('formularios_condominio', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_formularios_condominio_status'))
        batch_op.drop_index(batch_op.f('ix_formularios_condominio_token'))
        batch_op.drop_index(batch_op.f('ix_formularios_condominio_imovel_id'))
    op.drop_table('formularios_condominio')

    with op.batch_alter_table('pagamentos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pagamentos_status'))
        batch_op.drop_index(batch_op.f('ix_pagamentos_asaas_payment_id'))
        batch_op.drop_index(batch_op.f('ix_pagamentos_user_id'))
    op.drop_table('pagamentos')

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('regimento_resumo')
        batch_op.drop_column('email_portaria')
        batch_op.drop_column('nome_condominio')
        batch_op.drop_column('formulario_condominio_ativo')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('asaas_customer_id')
