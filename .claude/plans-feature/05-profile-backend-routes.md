# Plan: Spec 05 — Profile Backend Routes ("Backend Connection")

## Context

The `/profile` page currently renders four hardcoded Python constants
(`PROFILE_USER`, `PROFILE_STATS`, `PROFILE_TRANSACTIONS`, `PROFILE_CATEGORIES`)
in `app.py` — built that way deliberately in Step 4 so the UI could be
validated before the database layer existed. This step ("Step 5" per the
roadmap, spec saved at `.claude/specs/05-profile-backend-routes.md`) replaces
that hardcoded data with real queries against the `users`/`expenses` tables
for the logged-in user, without changing the route path, the auth guard, or
`profile.html`'s structure.

The user has asked for this implemented via **3 parallel subagents**, one per
data concern (transaction history, summary stats, category breakdown), each
restricted to editing only its own section of `app.py`. This plan defines a
scaffold step first so the three subagents' edits never touch the same lines.

**Resolved ambiguity (confirmed with user):** the spec text states the seed
user's total spend as ₹346.24; the actual `seed_db()` literal amounts in
`database/db.py` sum to **₹286.45** (verified by hand: 32.50+15.00+85.00+40.00
+22.75+60.00+12.30+18.90 = 286.45). The user confirmed treating 346.24 as a
spec typo — tests and Definition of Done use the real value, ₹286.45, and
`seed_db()` is left untouched.

**Key constraint discovered during exploration:** `templates/profile.html`
applies zero Jinja filters — every value it receives must already be a
fully-formatted display string (currency, dates) coming from Python. Also,
`static/css/profile.css`'s progress-bar width classes are fixed 5% steps
(`profile-bar-w-5` … `-100`, no 0% class), so any computed percentage must be
rounded to the nearest 5 and clamped to a 5–100 range before it can be used
as a CSS class.

## Approach

### Step 0 — Save this plan to the repo (sequential, first action after approval)
Write this plan's content to `.claude/plans-feature/05-profile-backend-routes.md`
as the user requested, before starting any code changes.

### Step 1 — Scaffold (sequential, done once, before any subagent runs)
This creates disjoint, clearly-marked regions so the 3 subagents can edit
`app.py` concurrently without conflict.

**`app.py` changes:**
- Delete the `PROFILE_USER` / `PROFILE_STATS` / `PROFILE_TRANSACTIONS` /
  `PROFILE_CATEGORIES` constants (lines 94-122).
- Add `from database.queries import (get_category_breakdown, get_recent_transactions, get_summary_stats, get_user_by_id)`.
- Add one shared, frozen utility (never touched by any subagent afterward):
  ```python
  def format_currency(amount):
      return f"₹{amount:,.2f}"
  ```
- Add four stub helpers, each bounded by `# --- Subagent N begin/end --- #`
  comment markers, currently `raise NotImplementedError`:
  - `_build_profile_user(user_id)` — Subagent 2
  - `_build_profile_stats(user_id)` — Subagent 2
  - `_build_profile_transactions(user_id)` — Subagent 1
  - `_build_profile_categories(user_id)` — Subagent 3
- Rewrite `profile()` once, final — no subagent touches this function:
  ```python
  @app.route("/profile")
  def profile():
      if not session.get("user_id"):
          return redirect(url_for("login"))
      user_id = session["user_id"]
      return render_template(
          "profile.html",
          user=_build_profile_user(user_id),
          stats=_build_profile_stats(user_id),
          transactions=_build_profile_transactions(user_id),
          categories=_build_profile_categories(user_id),
      )
  ```

**`database/queries.py` (new file) changes:**
- Header: `"""Pure DB query helpers for the profile page. No Flask imports here."""`
  followed by `from datetime import datetime` and `from database.db import get_db`
  — added once, up front, so no subagent needs to touch the import block.
- Four stub function signatures, each bounded by its own `# --- Subagent N
  begin/end --- #` markers, currently `raise NotImplementedError`:
  `get_user_by_id`, `get_summary_stats` (Subagent 2); `get_recent_transactions`
  (Subagent 1); `get_category_breakdown` (Subagent 3).

### Step 2 — Dispatch 3 subagents in parallel
Each subagent may edit **only** the code between its own begin/end markers in
`app.py` and `database/queries.py`. None may touch `profile()`,
`format_currency`, imports, another subagent's markers, templates, CSS, or
`database/db.py`.

**Subagent 1 — Transaction History**
- `database/queries.py::get_recent_transactions(user_id, limit=10)`:
  `SELECT date, description, category, amount FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?`.
  Returns list of dicts: `date` formatted `"%b %d, %Y"` (parsed from stored
  `"YYYY-MM-DD"` via `datetime.strptime`/`strftime`, using the already-imported
  `datetime`), `description` (`""` if `NULL`), `category` (raw), `amount`
  (raw float rounded to 2 decimals — **no ₹ here**).
- `app.py::_build_profile_transactions(user_id)`: calls the above, maps each
  row to `{"date", "description", "category", "category_class": f"profile-badge-{category.lower()}", "amount": format_currency(amount)}`.

**Subagent 2 — User Info & Summary Stats**
- `database/queries.py::get_user_by_id(user_id)`:
  `SELECT name, email, created_at FROM users WHERE id = ?`; `None` if no row;
  else `{"name", "email", "member_since": datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")}`.
- `database/queries.py::get_summary_stats(user_id)`:
  `SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS cnt FROM expenses WHERE user_id = ?`
  for `total_spent` (rounded float, **not** a string) and `transaction_count`;
  if count is 0, `top_category = "—"`; else
  `SELECT category FROM expenses WHERE user_id = ? GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1`.
- `app.py::_build_profile_user(user_id)`: calls `get_user_by_id`, computes
  `initials` (first letter of first + last word, uppercased; first two
  letters if one word; `""` if user is `None`), returns the dict the
  template expects.
- `app.py::_build_profile_stats(user_id)`: calls `get_summary_stats`, returns
  `[{"label": "Total Spent", "value": format_currency(total_spent), "icon": "wallet"}, {"label": "Transactions", "value": str(transaction_count), "icon": "receipt"}, {"label": "Top Category", "value": top_category, "icon": "tag"}]`
  — `top_category` is used as-is, never passed through `format_currency`.

**Subagent 3 — Category Breakdown**
- `database/queries.py::get_category_breakdown(user_id)`:
  `SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ? GROUP BY category ORDER BY total DESC, category ASC`;
  `[]` if no rows; else `grand_total = sum(totals)`, `pct = round(total/grand_total*100)`
  per row, then add `100 - sum(all pcts)` to **row 0's** pct (guaranteed
  largest due to `ORDER BY total DESC`) so pcts always sum to exactly 100.
  Returns `[{"name", "amount": round(float(total), 2), "pct": int}]`.
- `app.py`: add a small private helper inside its own marked region,
  `_pct_to_bar_class(pct)`: `stepped = max(5, min(100, round(pct / 5) * 5))`
  → `f"profile-bar-w-{stepped}"` (handles nearest-5 rounding, the missing
  0%-class case, and the defensive 100% cap).
- `app.py::_build_profile_categories(user_id)`: calls `get_category_breakdown`,
  maps each row to `{"name", "amount": format_currency(amount), "color_class": f"profile-progress-bar-{name.lower()}", "bar_class": _pct_to_bar_class(pct)}`
  — `pct` itself is never included in the returned dict (the template never
  renders it directly).

Verified by hand against the real seed data (total ₹286.45): percentages
round to Bills 30, Shopping 21, Food 18, Health 14, Entertainment 8,
Transport 5, Other 4 — sums to exactly 100. Bar classes: 30→30, 21→20, 18→20,
14→15, 8→10, 5→5, 4→5 (clamped) — all valid existing CSS classes.

### Step 3 — Tests & verification (sequential, one subagent, after the 3 above finish)
Per `CLAUDE.md`'s subagent policy ("always use a subagent to verify test
results after any implementation"):

1. Add `pytest.ini` at repo root:
   ```ini
   [pytest]
   pythonpath = .
   ```
   (needed so plain `pytest` resolves `import app` / `import database.db`,
   since no `tests/__init__.py` exists and pytest's default import mode only
   adds `tests/` to `sys.path`, not the repo root).

2. Create `tests/conftest.py`. Test-DB isolation strategy: `database/db.py`'s
   `DB_PATH` is a hardcoded module constant with no override hook, and
   `app.py` runs `init_db()`/`seed_db()` unconditionally at import time. Fix:
   monkeypatch the `DB_PATH` attribute on the **already-imported**
   `database.db` module object to a `tmp_path` file, call `init_db()`/
   `seed_db()` directly for pure query-function tests, and for route tests
   use a function-scoped `app` fixture that does `importlib.reload(app_module)`
   **after** the patch (never reload `database.db` itself — that would
   re-execute `DB_PATH = os.path.join(...)` and undo the patch). This works
   because `get_db()` resolves `DB_PATH` from the module namespace at call
   time, not at function-definition time.
   ```python
   import importlib
   import pytest
   from database.db import create_user, get_user_by_email, init_db, seed_db

   @pytest.fixture
   def temp_db(tmp_path, monkeypatch):
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
       import app as app_module
       importlib.reload(app_module)
       app_module.app.config.update(TESTING=True)
       return app_module.app
   ```
   (`client` fixture is auto-derived from `app` by `pytest-flask`.)

3. Write `tests/test_backend_connection.py` per the spec's test table:
   - **Unit tests** (no Flask): `get_user_by_id` valid/non-existent id;
     `get_summary_stats` with expenses (`total_spent == 286.45`,
     `transaction_count == 8`, `top_category == "Bills"`) and without
     (`{"total_spent": 0, "transaction_count": 0, "top_category": "—"}`);
     `get_recent_transactions` newest-first order and empty-list case;
     `get_category_breakdown` — all 7 categories, ordered by amount desc,
     `pct`s are ints summing to 100, empty-list case. Add one adversarial
     test (amounts that don't divide evenly, e.g. three equal categories) to
     actually exercise the remainder-adjustment branch, since the real seed
     data happens to sum to 100 without needing it.
   - **Route tests**: unauthenticated `GET /profile` → 302 to `/login`;
     logged in as seed user → 200, body contains "Demo User",
     "demo@spendly.com", "₹286.45", "Bills", all 7 category names, and
     transactions in newest-first order; a freshly registered user with no
     expenses → 200, shows "₹0.00", no category rows, no server error.

4. Run `pytest -v` from the repo root. If anything fails, follow
   `superpowers:systematic-debugging` — likely culprits: reload/double-import
   artifacts, date-format parsing off-by-ones, or the `client` fixture not
   registering (check `pytest --fixtures`). Fix and re-run until green.

5. Report final pass/fail summary.

## Critical files
- `app.py` — scaffold + 3 subagent regions
- `database/queries.py` (new) — scaffold + 3 subagent regions
- `database/db.py` — read-only reference, not modified
- `templates/profile.html` — read-only reference, confirmed no structural changes needed (all 4 loops/vars already match this design)
- `static/css/profile.css` — read-only reference, confirms badge/color classes exist for all 7 categories and bar-width classes are 5%-stepped
- `tests/conftest.py`, `tests/test_backend_connection.py`, `pytest.ini` (new)

## Verification
1. `pytest -v` from repo root — all unit + route tests green.
2. Manual check: `python app.py`, log in as `demo@spendly.com` / `demo123`,
   visit `/profile` — confirm real name/email, ₹286.45 total, 8 transactions
   newest-first, "Bills" as top category, all 7 categories with proportional
   bars, ₹ symbol everywhere, no hex colors.
3. Register a brand-new user, visit `/profile` — confirm ₹0.00, empty
   transaction list, empty category breakdown, no errors/tracebacks.
4. Confirm no `PROFILE_USER`/`PROFILE_STATS`/`PROFILE_TRANSACTIONS`/
   `PROFILE_CATEGORIES` constants remain in `app.py`.
