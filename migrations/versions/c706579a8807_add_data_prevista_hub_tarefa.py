"""add data_prevista to hub_tarefas

Revision ID: c706579a8807
Revises: db1a6bc9a5b9
Create Date: 2026-07-27 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c706579a8807'
down_revision = 'db1a6bc9a5b9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('hub_tarefas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('data_prevista', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('hub_tarefas', schema=None) as batch_op:
        batch_op.drop_column('data_prevista')
