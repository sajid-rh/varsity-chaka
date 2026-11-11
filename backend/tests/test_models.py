"""Checks the migration-001 models without needing a running database."""
from decimal import Decimal

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

import app.models  # noqa: F401  (registers the tables)
from app.core.database import Base

EXPECTED_TABLES = {
    "universities",
    "university_settings",
    "campus_destinations",
    "users",
    "email_verification_tokens",
}


def test_expected_tables_are_registered():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_every_table_compiles_to_mysql_ddl():
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
        assert "CREATE TABLE" in ddl


def test_tenant_owned_tables_have_university_id():
    for name in ("university_settings", "campus_destinations", "users"):
        assert "university_id" in Base.metadata.tables[name].c


def test_user_email_is_unique_and_password_is_a_hash_column():
    users = Base.metadata.tables["users"]
    assert users.c.email.unique is True
    assert "password_hash" in users.c
    assert "password" not in users.c  # no plain-text password column can exist


def test_default_matching_weights_sum_to_one():
    settings = Base.metadata.tables["university_settings"]
    weight_columns = [c for c in settings.c if c.name.startswith("weight_")]
    assert len(weight_columns) == 6
    total = sum(Decimal(c.default.arg) for c in weight_columns)
    assert total == Decimal("1")
