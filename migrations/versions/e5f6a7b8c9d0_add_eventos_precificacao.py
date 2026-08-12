"""add eventos_precificacao + percentuais sugeridos em users

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # ### users: percentuais editáveis de aumento sugerido ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pct_precificacao_alta', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('pct_precificacao_media', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('pct_precificacao_baixa', sa.Integer(), nullable=True))

    # ### eventos_precificacao ###
    op.create_table(
        'eventos_precificacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('imovel_id', sa.Integer(), nullable=True),
        sa.Column('titulo', sa.String(length=150), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('recorrente', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('nivel_impacto', sa.String(length=10), nullable=False, server_default='media'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['imovel_id'], ['imoveis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('eventos_precificacao', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_eventos_precificacao_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_eventos_precificacao_imovel_id'), ['imovel_id'], unique=False)

    with op.batch_alter_table('eventos_precificacao', schema=None) as batch_op:
        batch_op.alter_column('recorrente', server_default=None)
        batch_op.alter_column('nivel_impacto', server_default=None)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('eventos_precificacao', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_eventos_precificacao_imovel_id'))
        batch_op.drop_index(batch_op.f('ix_eventos_precificacao_user_id'))
    op.drop_table('eventos_precificacao')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('pct_precificacao_baixa')
        batch_op.drop_column('pct_precificacao_media')
        batch_op.drop_column('pct_precificacao_alta')
