# Plan: Edit Expense (Step 8)

## Context
Spendly's roadmap has `GET /expenses/<id>/edit` as a stub that returns the raw
string `"Edit expense — coming in Step 8"`. Step 8 (spec at
`.claude/specs/08-edit-expense.md`) upgrades this into a real GET+POST
feature: a logged-in user can open an edit form pre-filled with an existing
expense's values and save changes, scoped so a user can only ever edit their
own expenses (others get a 404). This follows directly on Step 7 (Add
Expense), reusing its validation rules, form layout, and query-helper
pattern almost exactly, plus one addition: the profile page's transaction
table needs an "Edit" link per row, which requires the expense `id` to flow
through `get_recent_transactions` for the first time.

## Implementation

### 1. `database/queries.py`
- **Modify `get_recent_transactions`** (~line 78): add `id` to the `SELECT` column list (`SELECT id, date, description, category, amount FROM expenses ...`) and add `"id": row["id"]` to the dict built in the loop. Verified safe: only `tests/test_06-date-filter-profile-page.py` calls this function, and it only asserts `txns[0]["description"]` — no key-count/equality assertions that adding a field would break.
- **Add `get_expense_by_id(expense_id, user_id)`**: `SELECT id, amount, category, date, description FROM expenses WHERE id = ? AND user_id = ?`, `fetchone()`, return the row (or `None`) unmodified — no date/amount formatting, since this feeds form pre-fill, not display.
- **Add `update_expense(expense_id, user_id, amount, category, expense_date, description)`**: parameterized `UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? WHERE id = ? AND user_id = ?`, then `conn.commit()`. The `user_id` in the `WHERE` clause is the second ownership guard (first is the `get_expense_by_id` 404 check) — an update attempt against another user's row silently affects 0 rows.
- Both new functions follow the existing `insert_expense` pattern: `get_db()` → try/finally `conn.close()`.

### 2. `app.py`
- Add `abort` to the Flask import line; add `get_expense_by_id, update_expense` to the `database.queries` import (keep alphabetical, matching existing style).
- `_build_profile_transactions` (~line 238): add `"id": t["id"]` to the returned dict.
- Replace the stub (lines 337-339) with:
  ```python
  @app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
  def edit_expense(id):
      if not session.get("user_id"):
          return redirect(url_for("login"))

      expense = get_expense_by_id(id, session["user_id"])
      if expense is None:
          abort(404)

      if request.method == "GET":
          form = {
              "amount": str(expense["amount"]),
              "category": expense["category"],
              "date": expense["date"],
              "description": expense["description"] or "",
          }
          return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

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
          return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

      if category not in EXPENSE_CATEGORIES:
          flash("Select a valid category.", "error")
          return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

      try:
          datetime.strptime(raw_date, "%Y-%m-%d")
      except ValueError:
          flash("Enter a valid date.", "error")
          return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

      update_expense(id, session["user_id"], amount, category, raw_date, description or None)
      flash("Expense updated successfully.", "success")
      return redirect(url_for("profile"))
  ```
  This mirrors `add_expense` almost line-for-line. `expense` is fetched once up front (both branches reuse it), which is also what makes `url_for('edit_expense', id=expense.id)` in the template valid on every render path, including validation-failure re-renders.
- No custom 404 template exists in the app — Flask's default 404 page is acceptable; the spec only requires the status code.

### 3. `templates/edit_expense.html` (new)
Clone `templates/add_expense.html` and change only:
- `{% block title %}Edit Expense — Spendly{% endblock %}`
- Heading/subtitle: "Edit expense" / "Update the details of this transaction"
- `<form method="post" action="{{ url_for('edit_expense', id=expense.id) }}">`
- Submit button text: "Save Changes"
- Field values keep reading from `form.*` (not `expense.*`) — identical markup to `add_expense.html` for amount/category-select/date/description — so the re-render-with-errors path pre-fills from resubmitted values, and the flash block (`auth-error`/`auth-success`) is unchanged so it works with the same test-landmark convention.
- No new CSS file needed — reuses global `.auth-section`/`.auth-container`/`.form-group`/`.form-input`/`.btn-submit` from `static/css/style.css`.

### 4. `templates/profile.html` + `static/css/profile.css`
- In the transactions table `<thead>`, add `<th>Actions</th>` after Amount.
- In the row loop, add a matching `<td>`:
  ```html
  <td class="profile-table-action">
      <a href="{{ url_for('edit_expense', id=txn.id) }}" class="profile-action-link">
          <i data-lucide="pencil"></i>Edit
      </a>
  </td>
  ```
  (`url_for()` per project convention, rather than a hardcoded path.)
- `profile.css` has no existing action-link/icon-button class, so add one small block after `.profile-table-amount` (~line 248), using existing CSS variables only:
  ```css
  .profile-table-action { text-align: right; white-space: nowrap; }
  .profile-action-link { display: inline-flex; align-items: center; gap: 0.3rem; color: var(--accent); font-size: 0.85rem; font-weight: 500; text-decoration: none; }
  .profile-action-link:hover { text-decoration: underline; }
  .profile-action-link svg { width: 14px; height: 14px; }
  ```

### 5. `tests/test_edit_expense.py` (new)
Mirror `tests/test_add_expense.py` conventions exactly (module docstring citing the spec, regex landmark helpers, raw-SQL DB helpers, `VALID_PAYLOAD` + `{**VALID_PAYLOAD, ...}` overrides). Reuse conftest fixtures: `seed_user_id`, `empty_user_id`, `auth_client`, `empty_user_client`, `insert_expense`.

One gap to handle locally (don't touch shared `conftest.py`): the `insert_expense` fixture doesn't return the new row's id. Add a local helper `_fetch_expense_by_description(user_id, description)` (same shape as the one in `test_add_expense.py`) to look up the seeded row's `id` after inserting it with a unique description per test.

Test classes:
1. `TestGetExpenseByIdQueryHelper` — valid owner returns row; wrong user returns `None`; nonexistent id returns `None`.
2. `TestUpdateExpenseQueryHelper` — valid owner update persists; wrong-user update leaves the row unchanged (0 rows affected, no exception).
3. `TestEditExpenseAuthGuard` — unauthenticated GET and POST both redirect (302) to `/login`.
4. `TestEditExpenseNotFoundOrOwnership` — nonexistent id → 404; another user's expense via GET → 404; another user's expense via POST → 404 and DB row unchanged.
5. `TestEditExpenseGet` — 200 for owner; form pre-filled with current amount/date/description; category `<option>` for the current category is `selected`; form uses POST method.
6. `TestEditExpensePostValid` — valid data redirects to `/profile` and DB row reflects new values; submitting with no description redirects and stores `NULL`.
7. `TestEditExpensePostValidation` — one test per invalid field (missing amount, amount = 0, negative amount, non-numeric amount, invalid category, invalid date): each expects 200, `_has_error_message(body)` true, and the DB row unchanged from its pre-POST snapshot.

### Order of work
1. `database/queries.py` changes
2. `app.py` changes
3. `templates/edit_expense.html`
4. `templates/profile.html` + `static/css/profile.css`
5. `tests/test_edit_expense.py`
6. Verify (below)

## Verification
```powershell
python -m pytest tests/test_edit_expense.py -v
python -m pytest -v   # full suite — confirm no regressions, especially test_06-date-filter-profile-page.py and test_add_expense.py
```
Manual smoke test (`python app.py`, app on port 5001):
- Log in as `demo@spendly.com` / `demo123`, go to `/profile`, click "Edit" on a transaction row.
- Confirm the form is pre-filled (amount, correct category selected, date, description).
- Submit a valid change → redirected to `/profile`, updated values visible in the table.
- Submit invalid data (e.g. amount `0`) → form re-renders with an error, previously entered values retained.
- Visit `/expenses/999999/edit` while logged in → 404.

### Critical files
- `database/queries.py`
- `app.py`
- `templates/edit_expense.html` (new)
- `templates/profile.html`
- `static/css/profile.css`
- `tests/test_edit_expense.py` (new)
