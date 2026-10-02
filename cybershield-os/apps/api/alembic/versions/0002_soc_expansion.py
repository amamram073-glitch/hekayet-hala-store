"""Add normalized SOC event fields and the Part 2 organization-scoped schema.

The original 0001 migration uses metadata.create_all; this upgrade is therefore
idempotent for both databases that already contain the original MVP schema and
fresh databases that were initialized from the current metadata.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.db import Base
from app import models  # noqa: F401 - register all metadata

revision = "0002_soc_expansion"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_column(bind, table, column):
    return table in inspect(bind).get_table_names() and column in {
        item["name"] for item in inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    # Create newly introduced tables on installations that previously ran 0001.
    Base.metadata.create_all(bind=bind, checkfirst=True)

    event_columns = [
        ("source_type", sa.Column("source_type", sa.String(32), nullable=False,
            server_default="APPLICATION")),
        ("event_timestamp", sa.Column("event_timestamp", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now())),
        ("hostname", sa.Column("hostname", sa.String(253), nullable=True)),
        ("ip_address", sa.Column("ip_address", sa.String(64), nullable=True)),
        ("username", sa.Column("username", sa.String(320), nullable=True)),
        ("asset_id", sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True)),
        ("processing_status", sa.Column("processing_status", sa.String(24), nullable=False,
            server_default="PENDING")),
    ]
    for name, column in event_columns:
        if not _has_column(bind, "security_events", name):
            op.add_column("security_events", column)

    audit_columns = [
        ("user_agent", sa.Column("user_agent", sa.String(300), nullable=True)),
        ("request_id", sa.Column("request_id", sa.String(64), nullable=True)),
        ("before_state", sa.Column("before_state", sa.JSON(), nullable=False,
            server_default=sa.text("'{}'"))),
        ("after_state", sa.Column("after_state", sa.JSON(), nullable=False,
            server_default=sa.text("'{}'"))),
    ]
    for name, column in audit_columns:
        if not _has_column(bind, "audit_logs", name):
            op.add_column("audit_logs", column)

    if not _has_column(bind, "approval_requests", "execution_result"):
        op.add_column("approval_requests", sa.Column("execution_result", sa.JSON(),
            nullable=False, server_default=sa.text("'{}'")))

    inspector = inspect(bind)
    existing_indexes = {item["name"] for item in inspector.get_indexes("security_events")}
    for index_name, columns in [
        ("ix_event_org_timestamp", ["organization_id", "event_timestamp"]),
        ("ix_event_org_severity", ["organization_id", "severity"]),
        ("ix_event_org_status", ["organization_id", "processing_status"]),
        ("ix_event_asset_timestamp", ["asset_id", "event_timestamp"]),
    ]:
        if index_name not in existing_indexes:
            op.create_index(index_name, "security_events", columns, unique=False)


def downgrade():
    # Keep organization data during rollback; removing evidence, alerts, and audit
    # records implicitly is unsafe. Previous application versions ignore these fields.
    pass
