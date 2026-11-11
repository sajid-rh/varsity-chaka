from decimal import Decimal

from app.core.config import Settings
from app.seed import TENANTS, check_seed_settings


def make_settings(**overrides) -> Settings:
    # _env_file=None so a developer's real .env never affects the test
    values = dict(
        mysql_user="test_user",
        mysql_password="test_password",
        secret_key="test_secret_key_only_for_tests",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


VALID_SEED = dict(
    seed_super_admin_email="root@example.com",
    seed_admin_password="Demo12345",
    seed_fuel_price_per_litre=Decimal("100.00"),
    seed_max_rate_per_km=Decimal("10.00"),
)


def test_missing_seed_values_are_reported():
    problems = check_seed_settings(make_settings())
    assert any("SEED_SUPER_ADMIN_EMAIL" in p for p in problems)
    assert any("SEED_ADMIN_PASSWORD" in p for p in problems)
    assert any("SEED_FUEL_PRICE_PER_LITRE" in p for p in problems)
    assert any("SEED_MAX_RATE_PER_KM" in p for p in problems)


def test_complete_seed_values_pass():
    assert check_seed_settings(make_settings(**VALID_SEED)) == []


def test_weak_seed_password_is_rejected():
    problems = check_seed_settings(make_settings(**{**VALID_SEED, "seed_admin_password": "weak"}))
    assert any("SEED_ADMIN_PASSWORD" in p for p in problems)


def test_tenant_email_domains_are_unique():
    domains = [t["email_domain"] for t in TENANTS]
    assert len(domains) == len(set(domains))
