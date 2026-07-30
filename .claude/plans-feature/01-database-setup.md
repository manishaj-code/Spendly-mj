# Plan: Step 1 — Database Setup (Spendly)

## Context

`database/db.py` currently contains only comments describing what it should do — no executable code. This is the first implementation step for Spendly, per `.claude/specs/01-database-setup.md`, and establishes the data layer (`users` and `expenses` tables) that every later feature (auth, profile, expense CRUD) will depend on. Currently `app.py` has no database imports or startup initialization at all. This step wires up `get_db()`, `init_db()`, and `seed_db()` in `database/db.py`, and calls `init_db()`/`seed_db()` from `app.py` on startup — without touching any existing routes (all 5 implemented routes and 5 stub routes stay exactly as they are, per the spec's "no new routes" instruction and CLAUDE.md's "don't implement a stub route unless the active task explicitly targets that step").

**DB filename decision**: The spec is ambiguous ("spendly.db" or "expense_tracker.db"), but `.gitignore` already contains the literal entry `expense_tracker.db` — a pre-existing, written-down decision in the repo. Plan uses `expense_tracker.db` at the project root.

## Implementation

### 1. `database/db.py` — replace comment stub with real code

```python
import os
import sqlite3
from datetime import date
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(BASE_DIR), "expense_tracker.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
    if existing["count"] > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    today = date.today()
    y, m = today.year, today.month

    sample_expenses = [
        (32.50, "Food",          f"{y:04d}-{m:02d}-02", "Groceries"),
        (15.00, "Transport",     f"{y:04d}-{m:02d}-05", "Bus pass top-up"),
        (85.00, "Bills",         f"{y:04d}-{m:02d}-07", "Electricity bill"),
        (40.00, "Health",        f"{y:04d}-{m:02d}-10", "Pharmacy"),
        (22.75, "Entertainment", f"{y:04d}-{m:02d}-13", "Movie tickets"),
        (60.00, "Shopping",      f"{y:04d}-{m:02d}-18", "New shoes"),
        (12.30, "Other",         f"{y:04d}-{m:02d}-21", "Misc purchase"),
        (18.90, "Food",          f"{y:04d}-{m:02d}-25", "Restaurant dinner"),
    ]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [(user_id, amt, cat, dt, desc) for amt, cat, dt, desc in sample_expenses],
    )
    conn.commit()
    conn.close()
```

Notes:
- `DB_PATH` is anchored via `os.path.dirname(__file__)` stepped up one level (out of `database/`) so the DB file lands at the project root, sibling to `app.py` — independent of CWD, no new packages needed.
- `PRAGMA foreign_keys = ON` is re-issued on every `get_db()` call since SQLite FK enforcement is per-connection, not persisted (per CLAUDE.md).
- `seed_db()` guards on `COUNT(*) FROM users` per spec section 5C, uses only parameterized (`?`) queries, hashes the password via `werkzeug.security.generate_password_hash`, and covers all 7 required categories across 8 rows (Food appears twice) with dates in the current month, zero-padded `YYYY-MM-DD`.
- `init_db()`/`seed_db()` each open and close their own connection — no shared/cached connection, no `flask.g`/teardown hook added in this step, since no route yet calls `get_db()` inside a request. That wiring is deferred to whichever later step first uses `get_db()` in a route handler.

### 2. `app.py` — two additive changes only

Add the import near the top:
```python
from flask import Flask, render_template
from database.db import get_db, init_db, seed_db
```

Add the startup call right before the entrypoint guard (after the last stub route, before `if __name__ == "__main__":`):
```python
with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
```

This runs at import time (not gated behind `__main__`), so the DB is ready before any request regardless of how the app is launched. `get_db` is imported per spec section 6 even though this step doesn't call it directly (no route uses it yet). No other line in `app.py` changes — all 10 existing routes stay byte-for-byte identical.

## Verification

No `tests/` directory exists and the spec's Definition of Done doesn't request tests, so verify manually:

1. Delete any stale `expense_tracker.db` at project root, then run `python app.py` — confirm it starts on port 5001 without a traceback.
2. Confirm `expense_tracker.db` now exists at the project root (not inside `database/`).
3. Via `sqlite3` CLI or a one-off Python snippet: `PRAGMA table_info(users)` / `PRAGMA table_info(expenses)` to confirm schema matches spec; `PRAGMA foreign_key_list(expenses)` to confirm the FK is registered.
4. `SELECT * FROM users` — expect exactly 1 row, `email = 'demo@spendly.com'`, `password_hash` starting with `scrypt:`/`pbkdf2:` (i.e., actually hashed, not the literal `demo123`).
5. `SELECT category, COUNT(*) FROM expenses GROUP BY category` — expect all 7 categories present, 8 rows total.
6. Stop and re-run `python app.py` (or call `init_db(); seed_db()` twice manually) — confirm user/expense counts are unchanged (still 1 and 8), proving no duplicate seeding.
7. In a throwaway Python shell: `get_db().execute("INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)", (99999, 10.0, "Food", "2026-07-01"))` — expect `sqlite3.IntegrityError: FOREIGN KEY constraint failed`. Also try inserting a duplicate email into `users` — expect `sqlite3.IntegrityError: UNIQUE constraint failed: users.email`.
8. Code-review check: confirm no SQL string in `db.py` uses f-strings/`.format()`/`%` interpolation — parameterized `?` placeholders only.

## Files touched

- `database/db.py` — implement `get_db()`, `init_db()`, `seed_db()` (replaces comment stub)
- `app.py` — add DB import + startup init/seed call only; no route changes
