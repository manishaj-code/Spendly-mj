# Spec: Login and Logout

## Overview
Implement session-based authentication so registered users can sign in and out of Spendly. This step upgrades the existing stub `GET /login` route into a full `GET`/`POST` route that verifies credentials against the `users` table and starts a Flask session, and implements the stub `GET /logout` route to clear that session. This is the second half of the auth flow started in Step 02 (Registration) and is a prerequisite for any user-specific pages (Profile, Expenses) that follow.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`)
- Step 02 — Registration (`create_user()`, working `/register` flow, passwords hashed with werkzeug)

## Routes
- `GET /login` — render login form — public (already exists as stub, upgrade it)
- `POST /login` — verify email/password, start session, redirect to a logged-in landing point — public
- `GET /logout` — clear session, redirect to `/login` — logged-in only (already exists as stub, implement it)

## Database changes
No new tables or columns. The existing `users` table (id, name, email, password_hash, created_at) covers all requirements.

A new DB helper must be added to `database/db.py`:
- `get_user_by_email(email)` — runs a parameterized `SELECT` against `users` for the given email, returns the row (or `None` if not found). Used by `POST /login` to fetch the stored `password_hash` for verification with `werkzeug.security.check_password_hash`.

## Templates
- **Modify**: `templates/login.html`
  - Change the form `action` from the hardcoded `"/login"` to `{{ url_for('login') }}`
  - Add a block to display a flashed error message (e.g. "Invalid email or password") — mirror the `auth-error` pattern already used in `register.html`
  - Keep all existing visual design
- **Modify**: `templates/base.html`
  - Nav links currently always show "Sign in" / "Get started". Update to conditionally show "Sign in" / "Get started" when logged out, and a link (e.g. "Logout", using `url_for('logout')`) when logged in. Logged-in state is determined by checking `session` for a user id.

## Files to change
- `app.py` — upgrade `login()` to handle `GET` and `POST`; implement `logout()`; add session logic
- `database/db.py` — add `get_user_by_email()` helper
- `templates/login.html` — wire up form action and flash message display
- `templates/base.html` — conditional nav based on session state

## Files to create
None.

## New dependencies
No new dependencies. Uses Flask's built-in `session` (backed by `app.secret_key`, already set) and `werkzeug.security.check_password_hash` (werkzeug already installed).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use f-strings in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Use `url_for()` for every internal link — never hardcode URLs
- Server-side validation for `POST /login` must check:
  1. Email and password are both non-empty
  2. A user exists for that email
  3. `check_password_hash` confirms the password matches
- On any failure, re-render the login form with a flashed error message ("Invalid email or password") — do not reveal whether the email exists or the password was wrong, use one generic message for both cases
- On success, store the user's id in `session` (e.g. `session["user_id"]`) and redirect to `url_for('landing')` (no dashboard/expenses list exists yet — that comes in a later step)
- `GET /logout` must clear the session (`session.clear()`) and redirect to `url_for('login')`; it should work even if no one is logged in (no error)
- Use `abort(405)` if an unsupported HTTP method reaches `/login`
- Do not implement `/profile` or any `/expenses/*` route — those are separate stubs for later steps

## Definition of done
- [ ] `GET /login` renders the login form without errors
- [ ] Submitting valid credentials logs the user in (session set) and redirects to the landing page
- [ ] Submitting an unknown email re-renders the form with "Invalid email or password", no session set
- [ ] Submitting a known email with the wrong password re-renders the form with "Invalid email or password", no session set
- [ ] Submitting with an empty email or password re-renders the form with a validation error
- [ ] After logging in, the nav bar shows a "Logout" link instead of "Sign in" / "Get started"
- [ ] Visiting `GET /logout` while logged in clears the session and redirects to `/login`
- [ ] Visiting `GET /logout` while logged out does not error, redirects to `/login`
