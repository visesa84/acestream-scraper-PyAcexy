"""
Revision ID: recording_schedules_02
Revises: f6550830694d
Create Date: 2026-03-15

"""
from alembic import op
import sqlalchemy as sa

# Identificadores de revisión
revision = 'recording_schedules_02'
# Usamos solo el ID alfanumérico para el down_revision
down_revision = 'f6550830694d' 
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('recording_schedules') as batch_op:
        batch_op.alter_column('created_at', 
                              new_column_name='start_time', 
                              existing_type=sa.DateTime())
        batch_op.alter_column('updated_at', 
                              new_column_name='end_time', 
                              existing_type=sa.DateTime())

def downgrade():
    with op.batch_alter_table('recording_schedules') as batch_op:
        batch_op.alter_column('start_time', 
                              new_column_name='created_at', 
                              existing_type=sa.DateTime())
        batch_op.alter_column('end_time', 
                              new_column_name='updated_at', 
                              existing_type=sa.DateTime())
