# Plan: Spec 07 — Add Expense

## Context

`GET /expenses/add` currently returns a raw string stub (`app.py:294-296`).
This step (spec at `.claude/specs/07-add-expense.md`) turns it into a real
`GET`/`POST` route that inserts a row into `expenses` and redirects back to
`/profile`, following the same one-view-two-methods pattern already used by
`register()` and `login()` in `app.py`.

**Key differences from the `register`/`login` pattern, confirmed during
exploration:**
- `register`/`login` re-render their template on error using only `flash()`
  — they never repopulate the submitted values. The spec explicitly requires
  add-expense to **retain previously entered values** on validation failure,
  so the route must pass a `form` dict (raw submitted strings) into the
  template context on every error path, not just a flash message.
- `database/queries.py`'s existing functions are grouped under
  `# --- Subagent N begin/end --- #` markers from Step 5/6's parallel-agent
  work. `insert_expense` is a single, standalone function — no markers
  needed, just added at the end of the file in the same
  `get_db()` → `try/finally` → parameterized-SQL style as the rest.
- `tests/conftest.py` already defines a fixture literally named
  `insert_expense` (raw-SQL seeding helper for date-filter tests, not
  connected to the app). The new `database.queries.insert_expense` function
  has the same name — the test file must import it with an alias (e.g.
  `from database.queries import insert_expense as insert_expense_query`) to
  avoid colliding with the `insert_expense` fixture already injected by
  conftest.py.
- No `<select>` styling exists yet in `style.css` — reuse `.form-input` on
  the `<select>` element itself (same border/padding/font as text inputs);
  no new CSS needed for the form fields.
- Placing the "Add Expense" button next to the "Recent Transactions" heading
  needs one small new CSS rule in `profile.css` — today `.profile-panel`'s
  `<h2 class="profile-section-title">` has no sibling wrapper, so a flex
  header row must be added.

## Approach

Single sequential implementation (this route/template/query is one cohesive
unit, unlike Step 5's three independent data concerns — no parallel
subagents needed for the implementation itself). Per `CLAUDE.md`'s subagent
policy, test writing and test verification are still delegated to the
project's dedicated subagents.

### Step 1 — `database/queries.py`: add `insert_expense`
Append, after the existing functions:
```python
def insert_expense(user_id, amount, category, expense_date, description):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
    finally:
        conn.close()
```
Parameter named `expense_date`, not `date`, to avoid shadowing the
`datetime.date` import used elsewhere in the codebase.

### Step 2 — `app.py`: replace the `add_expense` stub
- Add `insert_expense` to the existing `from database.queries import (...)`
  block (`app.py:9-14`).
- Add a module-level constant near the placeholder-routes section:
  ```python
  EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]
  ```
  (matches the 7 categories seeded in `database/db.py::seed_db()` exactly).
- Replace the stub at `app.py:294-296` with:
  ```python
  @app.route("/expenses/add", methods=["GET", "POST"])
  def add_expense():
      if not session.get("user_id"):
          return redirect(url_for("login"))

      if request.method == "GET":
          form = {"amount": "", "category": "", "date": date.today().isoformat(), "description": ""}
          return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

      raw_amount = request.form.get("amount", "").strip()
      category = request.form.get("category", "").strip()
      raw_date = request.form.get("date", "").strip()
      description = request.form.get("description", "").strip()

      form = {"amount": raw_amount, "category": category, "date": raw_date, "description": description}

      try:
          amount = float(raw_amount)
      except ValueError:
          amount = None

      if amount is None or amount <= 0:
          flash("Enter a valid amount greater than 0.", "error")
          return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

      if category not in EXPENSE_CATEGORIES:
          flash("Select a valid category.", "error")
          return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

      try:
          datetime.strptime(raw_date, "%Y-%m-%d")
      except ValueError:
          flash("Enter a valid date.", "error")
          return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

      insert_expense(session["user_id"], amount, category, raw_date, description or None)
      flash("Expense added successfully.", "success")
      return redirect(url_for("profile"))
  ```
- `edit_expense`/`delete_expense` stubs (`app.py:299-306`) are untouched —
  out of scope for this spec.

### Step 3 — Create `templates/add_expense.html`
Reuses the auth-page markup/classes from `register.html`/`login.html`
(`.auth-section`, `.auth-container`, `.auth-header`, `.auth-card`,
`.auth-error`/`.auth-success`, `.form-group`, `.form-input`, `.btn-submit`,
`.auth-switch`) so the page matches the rest of the app with zero new CSS
for the form itself:
```html
{% extends "base.html" %}

{% block title %}Add Expense — Spendly{% endblock %}

{% block content %}

<section class="auth-section">
    <div class="auth-container">

        <div class="auth-header">
            <h1 class="auth-title">Add an expense</h1>
            <p class="auth-subtitle">Log a new transaction to your account</p>
        </div>

        <div class="auth-card">
            {% with messages = get_flashed_messages(with_categories=True) %}
            {% for category, message in messages %}
            <div class="auth-{{ 'error' if category == 'error' else 'success' }}">{{ message }}</div>
            {% endfor %}
            {% endwith %}

            <form method="post" action="{{ url_for('add_expense') }}">
                <div class="form-group">
                    <label for="amount">Amount</label>
                    <input type="number" id="amount" name="amount"
                           class="form-input" step="0.01" min="0.01"
                           placeholder="0.00" value="{{ form.amount }}" required autofocus>
                </div>
                <div class="form-group">
                    <label for="category">Category</label>
                    <select id="category" name="category" class="form-input" required>
                        <option value="" disabled {{ 'selected' if form.category not in categories else '' }}>Select a category</option>
                        {% for c in categories %}
                        <option value="{{ c }}" {{ 'selected' if form.category == c else '' }}>{{ c }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group">
                    <label for="date">Date</label>
                    <input type="date" id="date" name="date"
                           class="form-input" value="{{ form.date }}" required>
                </div>
                <div class="form-group">
                    <label for="description">Description (optional)</label>
                    <input type="text" id="description" name="description"
                           class="form-input" maxlength="200"
                           placeholder="e.g. Groceries" value="{{ form.description }}">
                </div>
                <button type="submit" class="btn-submit">Save Expense</button>
            </form>
        </div>

        <p class="auth-switch">
            <a href="{{ url_for('profile') }}">Cancel and return to profile</a>
        </p>

    </div>
</section>

{% endblock %}
```
The placeholder `<option>` is marked `selected` whenever `form.category` is
blank (GET) or invalid (POST error with a bad/missing category) — this
correctly re-shows "Select a category" instead of silently defaulting to
"Food".

### Step 4 — Modify `templates/profile.html`
Wrap the "Recent Transactions" heading (`profile.html:71-72`) in a header
row so the new button sits inline with the title:
```html
<div class="profile-panel">
    <div class="profile-panel-header">
        <h2 class="profile-section-title"><i data-lucide="receipt"></i>Recent Transactions</h2>
        <a href="{{ url_for('add_expense') }}" class="btn-primary">Add Expense</a>
    </div>
    <div class="profile-table-wrap">
        ...
```
(Only the opening wrapper changes; the table markup below is untouched.)

### Step 5 — Add one CSS rule to `static/css/profile.css`
After `.profile-section-title` (`profile.css:109-119`), add:
```css
.profile-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.25rem;
}

.profile-panel-header .profile-section-title { margin-bottom: 0; }
```
This preserves the exact spacing the bare `<h2>` had before (`margin-bottom:
1.25rem` moves from the `<h2>` to its new wrapper) and uses only existing
CSS variables indirectly (no new hex values introduced).

### Step 6 — Modify `templates/base.html`
Insert an "Add Expense" nav link between the existing Analytics and Logout
links (`base.html:26-27`), following the identical active-state pattern:
```html
<a href="{{ url_for('analytics') }}" class="{{ 'nav-active' if request.endpoint == 'analytics' else '' }}">Analytics</a>
<a href="{{ url_for('add_expense') }}" class="{{ 'nav-active' if request.endpoint == 'add_expense' else '' }}">Add Expense</a>
<a href="{{ url_for('logout') }}">Logout</a>
```
Already inside the `{% if session.get('user_id') %}` block, so it's
logged-in-only for free.

### Step 7 — Dispatch `spendly-test-writer` subagent
Per `CLAUDE.md`'s subagent policy, delegate test authoring to the project's
`spendly-test-writer` subagent (writes from the spec, not from reading the
implementation). Point it at `.claude/specs/07-add-expense.md`'s "Tests to
write" section and flag the `insert_expense` naming collision with
`tests/conftest.py`'s existing fixture so it aliases the import. Target
file: `tests/test_add_expense.py`, following the `class Test...:` grouping
and fixture conventions already established in
`tests/test_06-date-filter-profile-page.py` (`auth_client`,
`empty_user_client`, `seed_user_id`, `temp_db`).

### Step 8 — Dispatch `spendly-test-runner` subagent
Per `CLAUDE.md`'s subagent policy ("always use a subagent to verify test
results after any implementation"), run `pytest tests/test_add_expense.py
-v` (and the full suite `pytest -v` to confirm no regressions in
`test_06-date-filter-profile-page.py`) via the `spendly-test-runner`
subagent. Fix any failures following `superpowers:systematic-debugging` and
re-run until green.

### Step 9 — Manual verification
Run `python app.py`, log in as `demo@spendly.com` / `demo123`:
- Confirm the navbar shows "Add Expense".
- Confirm the "Add Expense" button appears next to "Recent Transactions" on
  `/profile`.
- Submit a valid expense — confirm redirect to `/profile`, success flash,
  and the new row appears in stats/transactions/category breakdown.
- Submit invalid amount / category / date individually — confirm the form
  re-renders with an error flash and the previously entered values are
  still filled in (except the field that failed, where applicable).
- Log out and visit `/expenses/add` directly — confirm redirect to
  `/login`.

## Critical files
- `database/queries.py` — add `insert_expense`
- `app.py` — add `EXPENSE_CATEGORIES`, import, replace `add_expense` stub
- `templates/add_expense.html` (new)
- `templates/profile.html` — wrap transactions panel heading
- `static/css/profile.css` — add `.profile-panel-header`
- `templates/base.html` — add nav link
- `tests/test_add_expense.py` (new, via `spendly-test-writer`)

## Verification
1. `pytest -v` from repo root — all tests green, including the pre-existing
   `test_06-date-filter-profile-page.py` suite (no regressions).
2. Manual walkthrough per Step 9 above.
3. Confirm every item in the spec's "Definition of done" checklist passes.
4. Confirm no hardcoded hex colors were introduced and every internal link
   uses `url_for()`.
