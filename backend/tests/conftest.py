"""Test configuration.

Settings need a few variables to exist. Tests set harmless placeholder values
so they run without a real .env file. These are not real credentials.
"""
import os
import sys
from pathlib import Path

# Make `import app...` work when pytest is started from the backend folder
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("MYSQL_USER", "test_user")
os.environ.setdefault("MYSQL_PASSWORD", "test_password")
os.environ.setdefault("SECRET_KEY", "test_secret_key_only_for_tests")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture()
def db_session():
    """A fresh in-memory SQLite database per test (tests never touch real MySQL)."""
    import app.models  # noqa: F401  (registers the tables)
    from app.core.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """A test client whose database dependency points at the SQLite test database."""
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def universities(db_session):
    """The two demo tenants: DIU (id 1) and AIUB (id 2)."""
    from app.models import University

    diu = University(name="Daffodil International University", short_code="DIU", email_domain="diu.edu.bd")
    aiub = University(name="American International University-Bangladesh", short_code="AIUB", email_domain="aiub.edu")
    db_session.add_all([diu, aiub])
    db_session.commit()
    return {"DIU": diu, "AIUB": aiub}
