"""${message}"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("reviewer_user_ids", sa.JSON, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, default="pending", index=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_workspace_idempotency"),
    )
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.String(12), sa.ForeignKey("approval_requests.id"), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(64), nullable=False, index=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade():
    op.drop_table("audit_entries")
    op.drop_table("approval_requests")
