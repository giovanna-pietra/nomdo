"""add lembrete_configs table + hub_tarefas novos campos

Revision ID: c1a2b3d4e5f6
Revises: b7e4d1f9a2c6
Create Date: 2026-07-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1a2b3d4e5f6'
down_revision = 'b7e4d1f9a2c6'
branch_labels = None
depends_on = None


def upgrade():
    # ### lembrete_configs ###
    op.create_table(
        'lembrete_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('imovel_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=30), nullable=False),
        sa.Column('titulo', sa.String(length=150), nullable=True),
        sa.Column('descricao', sa.Text(), nullable=True),
        sa.Column('intervalo_dias', sa.Integer(), nullable=True),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('ultimo_envio', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['imovel_id'], ['imoveis.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('lembrete_configs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lembrete_configs_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_lembrete_configs_imovel_id'), ['imovel_id'], unique=False)

    # ### hub_tarefas: novos campos ###
    with op.batch_alter_table('hub_tarefas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('estadia_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('lembrete_config_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('email_enviado', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f('ix_hub_tarefas_estadia_id'), ['estadia_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_hub_tarefas_lembrete_config_id'), ['lembrete_config_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_hub_tarefas_estadia_id', 'estadia', ['estadia_id'], ['id'], ondelete='SET NULL'
        )
        batch_op.create_foreign_key(
            'fk_hub_tarefas_lembrete_config_id', 'lembrete_configs', ['lembrete_config_id'], ['id'], ondelete='SET NULL'
        )

    # remove o server_default depois de popular as linhas existentes (padrão Alembic)
    with op.batch_alter_table('hub_tarefas', schema=None) as batch_op:
        batch_op.alter_column('email_enviado', server_default=None)


def downgrade():
    with op.batch_alter_table('hub_tarefas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_hub_tarefas_lembrete_config_id', type_='foreignkey')
        batch_op.drop_constraint('fk_hub_tarefas_estadia_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_hub_tarefas_lembrete_config_id'))
        batch_op.drop_index(batch_op.f('ix_hub_tarefas_estadia_id'))
        batch_op.drop_column('email_enviado')
        batch_op.drop_column('lembrete_config_id')
        batch_op.drop_column('estadia_id')

    with op.batch_alter_table('lembrete_configs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lembrete_configs_imovel_id'))
        batch_op.drop_index(batch_op.f('ix_lembrete_configs_user_id'))

    op.drop_table('lembrete_configs')
