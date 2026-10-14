"""iteration one persistence
Revision: 3d822eb29121
"""
from alembic import op
import sqlalchemy as sa

revision = '3d822eb29121'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():

    op.create_table('api_throttles',
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('window_start', sa.Integer(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.CheckConstraint('count >= 1', name=op.f('ck_api_throttles_positive_count')),
    sa.PrimaryKeyConstraint('key_hash', name=op.f('pk_api_throttles'))
    )
    op.create_table('deletion_audits',
    sa.Column('subject_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deletion_audits')),
    sa.UniqueConstraint('subject_id', name=op.f('uq_deletion_audits_subject_id'))
    )
    op.create_table('idempotency_records',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('operation', sa.String(length=100), nullable=False),
    sa.Column('key_hash', sa.String(length=64), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('resource_id', sa.String(length=36), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_idempotency_records_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_idempotency_records')),
    sa.UniqueConstraint('user_id', 'operation', 'key_hash', name='uq_idempotency_scope')
    )
    op.create_index(op.f('ix_idempotency_records_user_id'), 'idempotency_records', ['user_id'], unique=False)
    op.create_table('recovery_tokens',
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("purpose IN ('reset','verify')", name=op.f('ck_recovery_tokens_valid_purpose')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_recovery_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_recovery_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_recovery_tokens_token_hash'))
    )
    op.create_index(op.f('ix_recovery_tokens_user_id'), 'recovery_tokens', ['user_id'], unique=False)
    op.drop_constraint(op.f('ck_trip_items_time_order'), 'trip_items', type_='check')
    op.create_check_constraint(op.f('ck_trip_items_time_order'), 'trip_items', '(start_minute IS NULL AND end_minute IS NULL) OR (start_minute IS NOT NULL AND end_minute IS NOT NULL AND start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440)')
    op.add_column('planning_jobs', sa.Column('result_deleted', sa.Boolean(), server_default='false', nullable=False))
    op.alter_column('trip_items', 'start_minute',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('trip_items', 'end_minute',
               existing_type=sa.INTEGER(),
               nullable=True)


def downgrade():
    op.drop_constraint(op.f('ck_trip_items_time_order'), 'trip_items', type_='check')
    op.create_check_constraint(op.f('ck_trip_items_time_order'), 'trip_items', 'start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440')
    op.alter_column('trip_items', 'end_minute',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('trip_items', 'start_minute',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('planning_jobs', 'result_deleted')
    op.drop_index(op.f('ix_recovery_tokens_user_id'), table_name='recovery_tokens')
    op.drop_table('recovery_tokens')
    op.drop_index(op.f('ix_idempotency_records_user_id'), table_name='idempotency_records')
    op.drop_table('idempotency_records')
    op.drop_table('deletion_audits')
    op.drop_table('api_throttles')

