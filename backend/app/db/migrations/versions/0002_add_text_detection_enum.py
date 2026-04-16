"""add TEXT_DETECTION to analysistype enum

Revision ID: 0002_add_text_detection
Revises: 0001_initial
Create Date: 2026-04-16

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_text_detection"
down_revision: str = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # For PostgreSQL: add the new value to the existing enum type
    op.execute("ALTER TYPE analysistype ADD VALUE IF NOT EXISTS 'TEXT_DETECTION'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; this is a no-op.
    pass
