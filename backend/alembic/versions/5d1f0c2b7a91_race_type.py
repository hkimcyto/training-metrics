"""race type

Revision ID: 5d1f0c2b7a91
Revises: ac67b173c6ab
Create Date: 2026-10-09 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d1f0c2b7a91"
down_revision: str | Sequence[str] | None = "ac67b173c6ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("athletes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("race_type", sa.String(length=16), server_default="ironman", nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("athletes", schema=None) as batch_op:
        batch_op.drop_column("race_type")
