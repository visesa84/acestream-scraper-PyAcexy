"""Add recording_schedule table

Revision ID: 8a3349893ea2
Revises: 20250412_add_epg_channels_update_tv_channels
Create Date: 2026-03-13 07:50:49.136342

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a3349893ea2'
down_revision = '20250412_add_epg_channels_update_tv_channels'
branch_labels = None
depends_on = None


def upgrade():
    # Usamos una inspección para ver si la tabla ya existe antes de crearla
    from sqlalchemy.engine import reflection
    bind = op.get_bind()
    inspect_obj = reflection.Inspector.from_engine(bind)
    existing_tables = inspect_obj.get_table_names()

    if 'recording_schedules' not in existing_tables:
        op.create_table('recording_schedules',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('program_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(length=20), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['program_id'], ['epg_programs.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
    else:
        print("The recording_schedules table already exists, skipping creation.")

def downgrade():
    op.drop_table('recording_schedules')
