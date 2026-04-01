import sqlite3
import pytest


@pytest.fixture
def tmp_db():
    """In-memory SQLite connection for all DB tests. Never touches overseas_data.db."""
    conn = sqlite3.connect(':memory:')
    yield conn
    conn.close()
