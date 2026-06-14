"""make next_delivery null remove default

Revision ID: 1ff39bd73ec2
Revises: 990a57ce477c
Create Date: 2026-06-14 18:19:17.404522

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ff39bd73ec2'
down_revision: Union[str, Sequence[str], None] = '990a57ce477c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # allow null and remove default for next_delivery
    op.alter_column(
        'digests',
        'next_delivery',
        existing_type=sa.DateTime(),
        nullable=True,
        server_default=None
    )
    op.execute(
        """
        UPDATE digests 
        SET next_delivery = NULL 
        WHERE auto_digest = false;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE digests 
        SET next_delivery = NOW() + INTERVAL '7 days' 
        WHERE auto_digest = false;
        """
    )
    op.alter_column('digests', 'next_delivery',
               existing_type=sa.DateTime(),
               nullable=False,
               server_default=sa.text("NOW() + INTERVAL '7 days'"))
