"""Shared column types and helpers for the models."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Integer
from sqlalchemy.dialects import mysql

# BIGINT UNSIGNED on MySQL, used for every primary key and foreign key
# (docs/03-database-design.md). Foreign keys must use exactly the same type as the key
# they point to. The SQLite variant exists only so unit tests can run without MySQL
# (SQLite auto-numbers only plain INTEGER primary keys).
UBigInt = (
    BigInteger()
    .with_variant(mysql.BIGINT(unsigned=True), "mysql")
    .with_variant(Integer(), "sqlite")
)


def utcnow() -> datetime:
    """Current time in UTC as a naive datetime. The database stores UTC only."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
