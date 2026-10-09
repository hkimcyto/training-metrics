"""race calendar

Moves each athlete's single race into a races table so an athlete can keep
several, then drops the old race columns.

Revision ID: d7a2f5c8e914
Revises: c41d9e7a5b23
Create Date: 2026-10-09 13:00:00.000000

"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a2f5c8e914"
down_revision: str | Sequence[str] | None = "c41d9e7a5b23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = ("race_name", "race_date", "race_type", "race_climb_m", "race_wetsuit", "race_temp_c")


RACES = sa.table(
    "races",
    sa.column("athlete_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("day", sa.Date),
    sa.column("race_type", sa.String),
    sa.column("priority", sa.String),
    sa.column("climb_m", sa.Float),
    sa.column("temp_c", sa.Float),
    sa.column("wetsuit", sa.Boolean),
)


def upgrade() -> None:
    """Upgrade schema."""
    # read the old races first: on SQLite, dropping columns rebuilds the
    # athletes table, which would cascade-delete rows already in races
    bind = op.get_bind()
    old = bind.execute(
        sa.text(
            "SELECT id, race_name, race_date, race_type, race_climb_m, race_temp_c, race_wetsuit "
            "FROM athletes WHERE race_date IS NOT NULL"
        )
    ).fetchall()
    with op.batch_alter_table("athletes", schema=None) as batch_op:
        for col in OLD:
            batch_op.drop_column(col)

    op.create_table(
        "races",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("athlete_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("race_type", sa.String(length=16), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(length=1), server_default="A", nullable=False),
        sa.Column("climb_m", sa.Float(), nullable=True),
        sa.Column("temp_c", sa.Float(), server_default="18", nullable=False),
        sa.Column("wetsuit", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("catalog_key", sa.String(length=40), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["athlete_id"], ["athletes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("races", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_races_athlete_id"), ["athlete_id"], unique=False)

    # each athlete's existing race becomes their A race
    if old:
        op.bulk_insert(
            RACES,
            [
                {
                    "athlete_id": r.id,
                    "name": r.race_name or "My race",
                    "day": r.race_date
                    if not isinstance(r.race_date, str)
                    else date.fromisoformat(r.race_date),
                    "race_type": r.race_type or "ironman",
                    "priority": "A",
                    "climb_m": r.race_climb_m,
                    "temp_c": r.race_temp_c if r.race_temp_c is not None else 18,
                    "wetsuit": bool(r.race_wetsuit) if r.race_wetsuit is not None else True,
                }
                for r in old
            ],
        )


def downgrade() -> None:
    """Downgrade schema."""
    # the earliest A race per athlete goes back onto the athlete row; read
    # them before the schema changes for the same cascade reason as above
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT athlete_id, name, day, race_type, climb_m, wetsuit, temp_c "
            "FROM races WHERE priority = 'A' ORDER BY day DESC"
        )
    ).fetchall()
    first = {r.athlete_id: r for r in rows}  # descending order, so the earliest wins

    with op.batch_alter_table("races", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_races_athlete_id"))
    op.drop_table("races")
    with op.batch_alter_table("athletes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("race_name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("race_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("race_type", sa.String(length=16), server_default="ironman", nullable=False)
        )
        batch_op.add_column(sa.Column("race_climb_m", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("race_wetsuit", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("race_temp_c", sa.Float(), nullable=True))
    for r in first.values():
        bind.execute(
            sa.text(
                "UPDATE athletes SET race_name = :name, race_date = :day, race_type = :type, "
                "race_climb_m = :climb, race_wetsuit = :wetsuit, race_temp_c = :temp "
                "WHERE id = :id"
            ),
            {
                "name": r.name,
                "day": r.day,
                "type": r.race_type if r.race_type != "run" else "marathon",
                "climb": r.climb_m,
                "wetsuit": r.wetsuit,
                "temp": r.temp_c,
                "id": r.athlete_id,
            },
        )
