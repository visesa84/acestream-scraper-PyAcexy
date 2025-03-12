"""Hydrate scraped urls

Revision ID: d626bf79a25c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = 'd626bf79a25c' 
down_revision = '4e3b1a9c8f21'
branch_labels = None
depends_on = None

def has_column(table, column):
    """Check if a column exists in a table"""
    conn = op.get_bind()
    insp = Inspector.from_engine(conn)
    columns = [c["name"] for c in insp.get_columns(table)]
    return column in columns

def upgrade():
    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table('scraped_urls') as batch_op:
        batch_op.add_column(sa.Column('enabled', sa.Boolean(), nullable=True, server_default='1'))
        batch_op.add_column(sa.Column('added_at', sa.DateTime(), nullable=True))
        if not has_column('scraped_urls', 'error_count'):
            batch_op.add_column(sa.Column('error_count', sa.Integer(), nullable=True, server_default='0'))
        if not has_column('scraped_urls', 'last_error'):    
            batch_op.add_column(sa.Column('last_error', sa.Text(), nullable=True))

def downgrade():
    with op.batch_alter_table('scraped_urls') as batch_op:
        batch_op.drop_column('enabled')
        batch_op.drop_column('added_at')
        if has_column('scraped_urls', 'error_count'):
            batch_op.drop_column('error_count')
        if has_column('scraped_urls', 'last_error'):
            batch_op.drop_column('last_error')