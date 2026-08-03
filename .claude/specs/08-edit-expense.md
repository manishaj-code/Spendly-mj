# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user edit any of their own expenses via a pre-populated
form at `/expenses/<id>/edit`. The GET handler loads the existing expense from
the database and renders the form with its current values; the POST handler
validates the submission and updates the row in place. Ownership is enforced:
a user can only edit expenses that belong to them. Two new query helpers are
added to `database/queries.py`: `get_expense_by_id` and `update_expense`.
The transactions table in `profile.html` gains an "Edit" action link per row,
which requires `get_recent_transactions` to also return the expense `id`.

## Depends on
- Step 1: Database setup (`expenses` table exists with all required columns)
- Step 3: Login / Logout (`session["user_id"]` is set and enforced)
- Step 5: Profile page renders transactions (the edit link lives there)
- Step 7: Add Expense (establishes the form pattern this step follows)

## Routes
- `GET /expenses/<int:id>/edit` — render edit form pre-populated with existing
  expense values — logged-in only
- `POST /expenses/<int:id>/edit` — validate and save updated expense — logged-in only

## Database changes
No new tables or columns. All required columns already exist in `expenses`:
`id`, `user_id`, `amount`, `category`, `date`, `description`.

## Templates
- **Create**: `templates/edit_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and `action="/expenses/{{ expense.id }}/edit"`
  - Same fields as `add_expense.html`:
    - `amount` — number input, `step="0.01"`, `min="0.01"`, required, pre-filled
    - `category` — `<select>` with the 7 fixed options, pre-selected to current value
    - `date` — `<input type="date">`, required, pre-filled to current value
    - `description` — text input, optional, max 200 chars, pre-filled
  - Submit button ("Save Changes") and a cancel link back to `/profile`
  - Display error message when validation fails, re-populating submitted values

- **Modify**: `templates/profile.html`
  - Add an "Actions" column header to the transactions table `<thead>`
  - Add an "Edit" link cell per transaction row pointing to
    `/expenses/{{ tx.id }}/edit`

## Files to change
- `database/queries.py`
  - Add `get_expense_by_id(expense_id, user_id)` — fetches a single expense
    row only if it belongs to the given user; returns `None` otherwise
  - Add `update_expense(expense_id, user_id, amount, category, date, description)`
    — issues a parameterised `UPDATE` scoped to both `id` and `user_id` for
    ownership safety
  - Modify `get_recent_transactions` — add `id` to the `SELECT` column list so
    templates can build edit links
- `app.py`
  - Import `get_expense_by_id` and `update_expense` from `database.queries`
  - Replace the GET-only placeholder at `/expenses/<int:id>/edit` with a
    full GET + POST handler:
    - GET: call `get_expense_by_id`; 404 if not found or not owned; render
      `edit_expense.html` with `expense` and `categories`
    - POST: read form fields, validate (same rules as add), call `update_expense`,
      redirect to `/profile` on success; re-render form with errors otherwise
  - Change the route decorator to accept both methods:
    `@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])`

- `templates/profile.html`
  - Add `<th>Actions</th>` to the table header
  - Add `<td><a href="/expenses/{{ tx.id }}/edit">Edit</a></td>` per row

## Files to create
- `templates/edit_expense.html` — the edit-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in `get_db()`)
- `get_expense_by_id` must scope its query to `id = ? AND user_id = ?` to prevent
  one user editing another user's expense — return `None` if not found
- `update_expense` must also include `user_id = ?` in its `WHERE` clause as a
  second ownership guard
- Unauthenticated access to both GET and POST must redirect to `/login`
- If the expense does not exist or belongs to another user, return a 404
- Validation rules for POST (identical to add expense):
  - `amount`: required, must be a positive number > 0 (parse with `float()`; catch `ValueError`)
  - `category`: required, must be one of the 7 fixed categories
  - `date`: required, must be a valid `YYYY-MM-DD` string (parse with `datetime.strptime`)
  - `description`: optional; strip whitespace; store `None` if blank
  - On any validation error, re-render the form with the error message and the
    submitted (not original) values pre-filled
- After a successful update, redirect to `url_for("profile")` — do NOT render
  the form again
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_edit_expense.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `get_expense_by_id` | valid `expense_id`, correct `user_id` | returns the matching row as a dict-like object |
| `get_expense_by_id` | valid `expense_id`, wrong `user_id` | returns `None` |
| `get_expense_by_id` | non-existent `expense_id` | returns `None` |
| `update_expense` | valid `expense_id`, correct `user_id`, new `amount=99.0` | row in DB reflects updated amount |
| `update_expense` | valid `expense_id`, wrong `user_id` | row in DB unchanged (0 rows affected, no error raised) |

### Route tests
`GET /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)

`GET /expenses/<id>/edit` — authenticated, own expense:
- Returns 200
- Response body contains form pre-filled with the expense's current values
- Response body contains `<select>` with the correct category pre-selected

`GET /expenses/<id>/edit` — authenticated, other user's expense:
- Returns 404

`GET /expenses/<id>/edit` — authenticated, non-existent id:
- Returns 404

`POST /expenses/<id>/edit` — unauthenticated:
- Redirects to `/login` (302)

`POST /expenses/<id>/edit` — authenticated, valid data:
- Redirects to `/profile` (302)
- Updated values are reflected in the database

`POST /expenses/<id>/edit` — authenticated, other user's expense:
- Returns 404

`POST /expenses/<id>/edit` — authenticated, missing amount:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, amount = 0:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, non-numeric amount:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, invalid category:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, invalid date string:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/<id>/edit` — authenticated, no description:
- Redirects to `/profile` (302)
- Row updated with `description = NULL`

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for a non-existent or other user's expense returns 404
- [ ] Visiting `/expenses/<id>/edit` while logged in shows a form pre-filled with the expense's current values
- [ ] The category dropdown has the correct category pre-selected
- [ ] Submitting valid changes redirects to `/profile` and the updated values appear in the transaction list
- [ ] Submitting with a missing or zero amount re-renders the form with an error and the submitted values retained
- [ ] Submitting with an invalid category re-renders the form with an error
- [ ] Submitting with an invalid date re-renders the form with an error
- [ ] Submitting without a description saves the expense with no description (no error)
- [ ] Each row in the profile transaction table has an "Edit" link pointing to the correct URL