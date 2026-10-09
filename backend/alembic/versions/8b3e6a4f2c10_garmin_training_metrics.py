"""garmin training metrics

Revision ID: 8b3e6a4f2c10
Revises: 5d1f0c2b7a91
Create Date: 2026-10-09 11:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b3e6a4f2c10"
down_revision: str | Sequence[str] | None = "5d1f0c2b7a91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    ("training_status", sa.String(length=24)),
    ("fitness_trend", sa.String(length=16)),
    ("vo2max", sa.Float()),
    ("acute_load", sa.Float()),
    ("chronic_load", sa.Float()),
    ("load_status", sa.String(length=16)),
    ("readiness", sa.Float()),
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("wellness_days", schema=None) as batch_op:
        for name, type_ in COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("wellness_days", schema=None) as batch_op:
        for name, _ in reversed(COLUMNS):
            batch_op.drop_column(name)
