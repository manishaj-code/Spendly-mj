# Plan: Delete Expense (Step 9)

## Context
Spendly's roadmap has reached Step 9. The `/expenses/<id>/delete` route currently
returns a placeholder string (`"Delete expense — coming in Step 9"`, `app.py:389-391`)
instead of doing real work. Per the approved spec (`.claude/specs/09-delete-expense.md`),
this step lets a logged-in user permanently remove one of their own expenses
directly from the profile transaction table: a "Delete" button per row POSTs to
`/expenses/<id>/delete`, guarded by a browser-side `confirm()` dialog (no separate
confirmation page), the handler verifies ownership and deletes the row, then
redirects to `/profile`. This builds directly on Step 8 (Edit Expense), reusing its
`get_expense_by_id` ownership-check helper and following its route/query/template/test
patterns exactly.

## Naming collision (must resolve first)
`app.py` already defines a Flask route function named `delete_expense` (the
placeholder at line 389). The spec's new DB helper in `database/queries.py` is also
named `delete_expense`, matching the `insert_expense`/`update_expense` naming
convention. These can't both be bare names in `app.py`'s namespace once imported.

**Resolution:** keep the query helper named `delete_expense` in `database/queries.py`,
and import it aliased in `app.py`:
```python
from database.queries import (
    delete_expense as delete_expense_row,
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
    update_expense,
)
```
(Inserted alphabetically by source name, matching the existing import block's style.)
The Flask route function keeps its name `delete_expense` (used by `url_for('delete_expense', id=...)` in the template). Inside the route body, call `delete_expense_row(...)`.

## Implementation order
1. **`database/queries.py`** — add `delete_expense(expense_id, user_id)`, mirroring
   `update_expense` (lines 168-178) exactly:
   ```python
   def delete_expense(expense_id, user_id):
       conn = get_db()
       try:
           conn.execute(
               "DELETE FROM expenses WHERE id = ? AND user_id = ?",
               (expense_id, user_id),
           )
           conn.commit()
       finally:
           conn.close()
   ```

2. **`app.py`**
   - Update the `database.queries` import block per the aliasing above.
   - Replace the placeholder (lines 389-391) with:
     ```python
     @app.route("/expenses/<int:id>/delete", methods=["POST"])
     def delete_expense(id):
         if not session.get("user_id"):
             return redirect(url_for("login"))

         expense = get_expense_by_id(id, session["user_id"])
         if expense is None:
             abort(404)

         delete_expense_row(id, session["user_id"])
         flash("Expense deleted successfully.", "success")
         return redirect(url_for("profile"))
     ```
   - `get_expense_by_id` and `abort` are already imported — no other import changes needed.
   - Declaring `methods=["POST"]` only means Flask automatically returns 405 for GET —
     no extra config required.

3. **`templates/profile.html`** — inside the existing `<td class="profile-table-action">`
   cell (lines 94-98, loop var is `txn`), add a delete form after the Edit link:
   ```html
   <td class="profile-table-action">
       <a href="{{ url_for('edit_expense', id=txn.id) }}" class="profile-action-link">
           <i data-lucide="pencil"></i>Edit
       </a>
       <form method="POST" action="{{ url_for('delete_expense', id=txn.id) }}"
             style="display:inline" onsubmit="return confirm('Delete this expense?')">
           <button type="submit" class="btn-delete"><i data-lucide="trash-2"></i>Delete</button>
       </form>
   </td>
   ```
   The `style="display:inline"` is the spec's one explicitly allowed inline-style
   exception (layout utility on the `<form>`, not a design value). No changes needed
   to `static/js/main.js` — its single `lucide.createIcons()` call runs at page load
   and will pick up the new server-rendered `trash-2` icon the same as the existing
   `pencil` icon.

4. **`static/css/style.css`** — add `.btn-delete` near `.btn-primary`/`.btn-submit`,
   using only existing `--danger`/`--danger-light` tokens (no hardcoded hex):
   ```css
   .btn-delete {
       display: inline-flex;
       align-items: center;
       gap: 0.3rem;
       background: var(--danger-light);
       color: var(--danger);
       padding: 0.4rem 0.9rem;
       border: none;
       border-radius: var(--radius-sm);
       font-family: var(--font-body);
       font-size: 0.85rem;
       font-weight: 500;
       cursor: pointer;
       transition: background 0.2s, color 0.2s;
   }
   .btn-delete:hover { background: var(--danger); color: var(--paper); }
   .btn-delete svg { width: 14px; height: 14px; }
   ```
   Sized to match the adjacent `.profile-action-link` (0.85rem font, 14px icon) so
   Edit/Delete read as a matched pair of row actions.

5. **`tests/test_delete_expense.py`** (new) — mirror `tests/test_edit_expense.py`'s
   structure/fixtures (`client`, `auth_client`, `seed_user_id`, `empty_user_id`,
   `insert_expense` from `tests/conftest.py`; local `_fetch_expense_by_description`
   and `_fetch_expense_by_id` raw-SQL helpers copied verbatim). Test classes:
   - `TestDeleteExpenseQueryHelper` — unit tests for `delete_expense`: correct owner
     removes the row; wrong user leaves row intact with no exception; non-existent id
     raises no error and leaves DB unchanged.
   - `TestDeleteExpenseAuthGuard` — unauthenticated POST redirects to `/login` (302),
     row untouched.
   - `TestDeleteExpenseNotFoundOrOwnership` — POST on non-existent id → 404; POST on
     another user's expense → 404 and row still exists.
   - `TestDeleteExpensePostValid` — authenticated POST on own expense → 302 to
     `/profile`, row removed from DB.
   - `TestDeleteExpenseMethodNotAllowed` — GET (both unauthenticated and authenticated)
     → 405.

## Verification
**Automated:**
```
pytest tests/test_delete_expense.py -v
pytest -v   # full suite, confirm no regressions in Step 8 or earlier
```

**Manual (dev server on port 5001):**
1. `python app.py`, log in as `demo@spendly.com` / `demo123`, go to `/profile`.
2. Confirm each transaction row shows both "Edit" and a red/danger "Delete" button.
3. Click Delete → `confirm()` dialog appears; Cancel leaves the row untouched.
4. Click Delete → Confirm → row disappears, redirected to `/profile`, success flash shown.
5. GET `/expenses/<id>/delete` directly in the browser → Flask's default 405 page.
6. Logged out, POST to `/expenses/<id>/delete` (e.g. via curl) → 302 to `/login`.
7. Logged in as demo user, POST to another user's expense id → 404, row unaffected.

### Critical files
- `database/queries.py`
- `app.py`
- `templates/profile.html`
- `static/css/style.css`
- `tests/test_delete_expense.py` (new)
