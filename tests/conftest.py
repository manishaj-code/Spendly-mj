"""Shared fixtures for the Spendly test suite.

Mirrors the pattern already established in old-tests/conftest.py: every test
gets an isolated, throwaway SQLite file (the real expense_tracker.db is never
touched) via a monkeypatched DB_PATH, with app.py reloaded so its
module-level init_db()/seed_db() calls target that temp file.

`client` is supplied automatically by the pytest-flask plugin (see
requirements.txt) from the `app` fixture below — it is intentionally not
redefined here.
"""

import importlib

import pytest

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.db.DB_PATH at a throwaway sqlite file for this test only.

    Patches the DB_PATH attribute on the already-imported database.db module
    object (late-bound lookup inside get_db() means this is honored), then
    initializes and seeds the schema against that temp file. The real
    expense_tracker.db is never touched.
    """
    import database.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    init_db()
    seed_db()


@pytest.fixture
def seed_user_id(temp_db):
    return get_user_by_email("demo@spendly.com")["id"]


@pytest.fixture
def empty_user_id(temp_db):
    return create_user("No Expenses", "empty@example.com", "pw123456")


@pytest.fixture
def app(temp_db):
    """Reload app.py (never database.db!) so its module-level init_db()/seed_db()
    calls re-run against the patched temp DB_PATH instead of the real database.
    """
    import app as app_module

    importlib.reload(app_module)
    app_module.app.config.update(TESTING=True)
    return app_module.app


@pytest.fixture
def auth_client(client):
    """Test client already logged in as the seeded demo user (demo@spendly.com).

    Useful for date-filter tests that want the well-known Step 5 baseline
    (8 expenses, total ₹286.45, top category "Bills") as the unfiltered
    fallback to assert against.
    """
    client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
        follow_redirects=False,
    )
    return client


@pytest.fixture
def empty_user_client(client, empty_user_id):
    """Test client logged in as a freshly created user with zero expenses.

    Gives date-filter tests a blank slate so they can seed a fully
    controlled set of expenses at explicit dates, instead of depending on
    seed_db()'s dates (which are anchored to "today" and unsuitable for
    boundary testing).
    """
    client.post(
        "/login",
        data={"email": "empty@example.com", "password": "pw123456"},
        follow_redirects=False,
    )
    return client


@pytest.fixture
def insert_expense():
    """Factory fixture: insert_expense(user_id, amount, category, date_str, description).

    Raw SQL uses ? placeholders only, per project convention. Exists so
    date-filter tests can seed expenses at explicit, controlled dates.
    """

    def _insert(user_id, amount, category, date_str, description):
        conn = get_db()
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date_str, description),
        )
        conn.commit()
        conn.close()

    return _insert
