import importlib

import pytest

from database.db import create_user, get_user_by_email, init_db, seed_db


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
