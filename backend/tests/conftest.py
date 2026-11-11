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
