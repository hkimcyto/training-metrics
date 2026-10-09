"""garmin profile

Revision ID: c41d9e7a5b23
Revises: 8b3e6a4f2c10
Create Date: 2026-10-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c41d9e7a5b23"
down_revision: str | Sequence[str] | None = "8b3e6a4f2c10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("athletes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("garmin_profile", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("athletes", schema=None) as batch_op:
        batch_op.drop_column("garmin_profile")
