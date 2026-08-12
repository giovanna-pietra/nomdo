"""add push_subscriptions + push_checkin_enviado

Revision ID: e1f2a3b4c5d6
Revises: db12804bdf2c
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'db12804bdf2c'
branch_labels = None
depends_on = None


def upgrade():
    # ### estadia: flag de idempotencia do push de "check-in hoje" ###
    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.add_column(sa.Column('push_checkin_enviado', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.alter_column('push_checkin_enviado', server_default=None)

    # ### push_subscriptions ###
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(length=512), nullable=False),
        sa.Column('p256dh', sa.String(length=255), nullable=False),
        sa.Column('auth', sa.String(length=255), nullable=False),
        sa.Column('user_agent', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint'),
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_push_subscriptions_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_push_subscriptions_endpoint'), ['endpoint'], unique=True)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_push_subscriptions_endpoint'))
        batch_op.drop_index(batch_op.f('ix_push_subscriptions_user_id'))
    op.drop_table('push_subscriptions')

    with op.batch_alter_table('estadia', schema=None) as batch_op:
        batch_op.drop_column('push_checkin_enviado')
