"""add avaliacoes + campos de email automatico ao hospede

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3d4e5f6
Create Date: 2026-07-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c1a2b3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # ### imoveis: config dos e-mails automaticos ###
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_guia_ativo', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('email_guia_dias_antes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('email_avaliacao_ativo', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('email_avaliacao_dias_depois', sa.Integer(), nullable=True))

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.alter_column('email_guia_ativo', server_default=None)
        batch_op.alter_column('email_avaliacao_ativo', server_default=None)

    # ### estadia: email do hospede + flags/token dos e-mails automaticos ###
    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_hospede', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('email_guia_enviado', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('email_avaliacao_enviado', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('token_avaliacao', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_estadia_token_avaliacao'), ['token_avaliacao'], unique=True)

    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.alter_column('email_guia_enviado', server_default=None)
        batch_op.alter_column('email_avaliacao_enviado', server_default=None)

    # ### avaliacoes ###
    op.create_table(
        'avaliacoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('estadia_id', sa.Integer(), nullable=False),
        sa.Column('imovel_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('nome_hospede', sa.String(length=200), nullable=True),
        sa.Column('nota', sa.Integer(), nullable=False),
        sa.Column('comentario', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['estadia_id'], ['estadia.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['imovel_id'], ['imoveis.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('estadia_id'),
    )
    with op.batch_alter_table('avaliacoes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_avaliacoes_imovel_id'), ['imovel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_avaliacoes_user_id'), ['user_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('avaliacoes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_avaliacoes_user_id'))
        batch_op.drop_index(batch_op.f('ix_avaliacoes_imovel_id'))
    op.drop_table('avaliacoes')

    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_estadia_token_avaliacao'))
        batch_op.drop_column('token_avaliacao')
        batch_op.drop_column('email_avaliacao_enviado')
        batch_op.drop_column('email_guia_enviado')
        batch_op.drop_column('email_hospede')

    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('email_avaliacao_dias_depois')
        batch_op.drop_column('email_avaliacao_ativo')
        batch_op.drop_column('email_guia_dias_antes')
        batch_op.drop_column('email_guia_ativo')
