"""remove formulario do condominio (feature removida)

Revision ID: b30cea1a6dbf
Revises: d4e5f6a7b8c0
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b30cea1a6dbf'
down_revision = 'd4e5f6a7b8c0'
branch_labels = None
depends_on = None


def upgrade():
    # ### formularios_condominio: dropar tabela + índices ###
    with op.batch_alter_table('formularios_condominio', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_formularios_condominio_status'))
        batch_op.drop_index(batch_op.f('ix_formularios_condominio_token'))
        batch_op.drop_index(batch_op.f('ix_formularios_condominio_imovel_id'))
    op.drop_table('formularios_condominio')

    # ### imoveis: dropar colunas do formulário de condomínio ###
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('regimento_resumo')
        batch_op.drop_column('email_portaria')
        batch_op.drop_column('nome_condominio')
        batch_op.drop_column('formulario_condominio_ativo')

    # ### end Alembic commands ###


def downgrade():
    # ### imoveis: recria as colunas do formulário de condomínio ###
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('formulario_condominio_ativo', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('nome_condominio', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('email_portaria', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('regimento_resumo', sa.Text(), nullable=True))

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.alter_column('formulario_condominio_ativo', server_default=None)

    # ### formularios_condominio: recria tabela + índices ###
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
