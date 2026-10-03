"""Create tariffs and payments. Tariffs are seeded by application startup."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(50), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title", name="uq_tariffs_title"),
        sa.CheckConstraint("price > 0", name="ck_tariffs_price_positive"),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tariff_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("discount", sa.BigInteger(), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("installment_months", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tariff_id"], ["tariffs.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint("discount >= 0", name="ck_payments_discount_nonnegative"),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        sa.CheckConstraint(
            "(method IN ('card', 'sbp') AND installment_months IS NULL) OR "
            "(method = 'installment' AND installment_months IS NOT NULL "
            "AND installment_months IN (3, 6, 12))",
            name="ck_payments_method_months",
        ),
    )


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("tariffs")
