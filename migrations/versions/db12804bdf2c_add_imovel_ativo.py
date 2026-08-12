"""add imovel ativo

Revision ID: db12804bdf2c
Revises: c706579a8807
Create Date: 2026-07-28 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'db12804bdf2c'
down_revision = 'c706579a8807'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()))

    # Remove o server_default depois de popular as linhas existentes (padrão
    # já usado nas outras migrações de coluna booleana deste projeto) — daqui
    # pra frente quem define o valor padrão em INSERTs novos é o `default=True`
    # do lado do SQLAlchemy (app/models/imovel.py), não o banco.
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.alter_column('ativo', server_default=None)


def downgrade():
    with op.batch_alter_table('imoveis', schema=None) as batch_op:
        batch_op.drop_column('ativo')
