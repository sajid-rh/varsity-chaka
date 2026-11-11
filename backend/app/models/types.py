"""Shared column types and helpers for the models."""
from datetime import datetime, timezone

from sqlalchemy.dialects import mysql

# BIGINT UNSIGNED, used for every primary key and foreign key (docs/03-database-design.md).
# Foreign keys must use exactly the same type as the key they point to.
UBigInt = mysql.BIGINT(unsigned=True)


def utcnow() -> datetime:
    """Current time in UTC as a naive datetime. The database stores UTC only."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
