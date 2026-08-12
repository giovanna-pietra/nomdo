"""add hierarquia proprietario/anfitriao-ajudante

Revision ID: a1b2c3d4e5f7
Revises: f6a7b8c9d0e1
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # ### users: vínculo Anfitrião-ajudante -> Proprietário ###
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proprietario_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_proprietario_id'), ['proprietario_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_users_proprietario_id_users',
            'users', ['proprietario_id'], ['id'],
            ondelete='SET NULL',
        )

    # ### convites_anfitriao ###
    op.create_table(
        'convites_anfitriao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('proprietario_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('aceito_em', sa.DateTime(), nullable=True),
        sa.Column('anfitriao_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['proprietario_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['anfitriao_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    with op.batch_alter_table('convites_anfitriao', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_convites_anfitriao_proprietario_id'), ['proprietario_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_convites_anfitriao_email'), ['email'], unique=False)
        batch_op.create_index(batch_op.f('ix_convites_anfitriao_token'), ['token'], unique=True)

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('convites_anfitriao', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_convites_anfitriao_token'))
        batch_op.drop_index(batch_op.f('ix_convites_anfitriao_email'))
        batch_op.drop_index(batch_op.f('ix_convites_anfitriao_proprietario_id'))
    op.drop_table('convites_anfitriao')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_proprietario_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_users_proprietario_id'))
        batch_op.drop_column('proprietario_id')
