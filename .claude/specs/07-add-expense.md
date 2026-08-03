# Spec: Add Expense

## Overview
Step 7 lets a logged-in user submit a new expense through a dedicated form page
at `/expenses/add`. The route already exists as a GET placeholder; this step
upgrades it to a full GET + POST handler, inserts validated data into the
`expenses` table, and redirects back to the profile page on success. A reusable
`insert_expense` query helper is added to `database/queries.py`. An "Add Expense"
button is added to `profile.html` so users can navigate to the form.

## Depends on
- Step 1: Database setup (`expenses` table exists with all required columns)
- Step 3: Login / Logout (`session["user_id"]` is set and checked)
- Step 4 / 5: Profile page exists and is the natural redirect target after saving

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert the new expense — logged-in only

## Database changes
No database changes. The `expenses` table already has all required columns:
`id`, `user_id`, `amount`, `category`, `date`, `description`, `created_at`.

## Templates
- **Create**: `templates/add_expense.html`
  - Extends `base.html`
  - Form with `method="POST"` and `action="/expenses/add"`
  - Fields:
    - `amount` — number input, step="0.01", min="0.01", required
    - `category` — `<select>` with the 7 fixed options: Food, Transport, Bills, Health, Entertainment, Shopping, Other
    - `date` — `<input type="date">`, required, defaults to today's date
    - `description` — text input, optional, max 200 chars
  - Submit button ("Save Expense") and a cancel link back to `/profile`
  - Display flash/error message when validation fails, re-populating previous values
- **Modify**: `templates/profile.html`
  - Add an "Add Expense" button/link pointing to `/expenses/add` (e.g., near the transaction table heading)

- Modify: templates/base.html — add "Add Expense" link in 
  navbar visible only when session.user_id is set

## Files to change
- `app.py` — replace the GET-only placeholder at `/expenses/add` with a GET+POST handler:
  - GET: render `add_expense.html` (redirect to login if not authenticated)
  - POST: read form fields, validate, call `insert_expense`, redirect to `/profile`
- `database/queries.py` — add `insert_expense(user_id, amount, category, date, description)`
- `templates/profile.html` — add "Add Expense" button

## Files to create
- `templates/add_expense.html` — the add-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Foreign keys PRAGMA must be enabled on every connection (already done in `get_db()`)
- Unauthenticated access to both GET and POST `/expenses/add` must redirect to `/login`
- Validation rules for POST:
  - `amount`: required, must be a positive number greater than 0 (parse with `float()`; catch `ValueError`)
  - `category`: required, must be one of the 7 fixed categories (reject anything else)
  - `date`: required, must be a valid `YYYY-MM-DD` date (parse with `datetime.strptime`)
  - `description`: optional; strip whitespace; store `None` if blank
  - On any validation error, re-render the form with the error message and the previously submitted values pre-filled
- After successful insert, redirect to `url_for("profile")` — do NOT render the form again
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Currency must always display as ₹ — never £ or $

## Tests to write
File: `tests/test_add_expense.py`

### Unit tests
| Function | Input | Expected output |
|---|---|---|
| `insert_expense` | valid `user_id`, `amount=50.0`, `category="Food"`, `date="2026-03-20"`, `description="Lunch"` | row inserted; querying the DB returns the new row |
| `insert_expense` | `description=None` | row inserted with `description` stored as `NULL` |

### Route tests
`GET /expenses/add` — unauthenticated:
- Redirects to `/login` (302)

`GET /expenses/add` — authenticated:
- Returns 200
- Response body contains the category `<select>` with all 7 options
- Response body contains `<form` with `method` POST

`POST /expenses/add` — unauthenticated:
- Redirects to `/login` (302)

`POST /expenses/add` — authenticated, valid data (`amount=50.0`, `category=Food`, `date=2026-03-20`, `description=Lunch`):
- Redirects to `/profile` (302)
- New expense row exists in the database for the test user

`POST /expenses/add` — authenticated, missing amount:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/add` — authenticated, amount = 0:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/add` — authenticated, non-numeric amount:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/add` — authenticated, invalid category (not in fixed list):
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/add` — authenticated, invalid date string:
- Returns 200 (re-renders form)
- Response body contains an error message

`POST /expenses/add` — authenticated, no description (optional field):
- Redirects to `/profile` (302)
- Row inserted with `description = NULL`

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows a form with amount, category, date, and description fields
- [ ] The category dropdown contains exactly: Food, Transport, Bills, Health, Entertainment, Shopping, Other
- [ ] Submitting a valid expense redirects to `/profile` and the new expense appears in the transaction list
- [ ] Submitting with a missing or zero amount re-renders the form with an error and previously entered values retained
- [ ] Submitting with an invalid category re-renders the form with an error
- [ ] Submitting with an invalid date re-renders the form with an error
- [ ] Submitting without a description saves the expense with no description (no error)
- [ ] The "Add Expense" button on the profile page navigates to `/expenses/add`
- [ ] Navbar shows "Add Expense" link when logged in