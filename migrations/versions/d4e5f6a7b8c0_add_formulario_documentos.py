"""add formulario de documentos do hospede (customizavel)

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2026-07-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c0'
down_revision = 'c3d4e5f6a7b9'
branch_labels = None
depends_on = None


def upgrade():
    # ### imoveis: configuração do formulário de documentos ###
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('documentos_ativo', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('documentos_dias_antes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('documentos_campos', sa.Text(), nullable=True))

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.alter_column('documentos_ativo', server_default=None)

    # ### formularios_documentos ###
    op.create_table(
        'formularios_documentos',
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
        sa.Column('expira_em', sa.Date(), nullable=True),
        sa.Column('respostas_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['estadia_id'], ['estadia.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['imovel_id'], ['imoveis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('estadia_id'),
        sa.UniqueConstraint('token'),
    )
    with op.batch_alter_table('formularios_documentos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_formularios_documentos_imovel_id'), ['imovel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_formularios_documentos_token'), ['token'], unique=True)
        batch_op.create_index(batch_op.f('ix_formularios_documentos_status'), ['status'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('formularios_documentos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_formularios_documentos_status'))
        batch_op.drop_index(batch_op.f('ix_formularios_documentos_token'))
        batch_op.drop_index(batch_op.f('ix_formularios_documentos_imovel_id'))
    op.drop_table('formularios_documentos')

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('documentos_campos')
        batch_op.drop_column('documentos_dias_antes')
        batch_op.drop_column('documentos_ativo')
