# Plan: Login and Logout (Step 03)

## Context
Spendly's auth flow currently ends at registration (Step 02). `GET /login` renders a form but has no `POST` handler, and `GET /logout` is a placeholder string. Without a working login/logout cycle, no session state exists anywhere in the app, which blocks every later step that needs to know "who is the current user" (Profile, Expenses CRUD). This plan implements session-based login/logout per `.claude/specs/03-login-logout.md`, reusing the exact patterns already established by the registration feature (flash-message idiom, form structure, DB-helper style) so the two auth flows stay visually and structurally consistent.

## Files to change
- `database/db.py`
- `app.py`
- `templates/login.html`
- `templates/base.html`

No files created. No new dependencies (Flask's built-in `session` + `werkzeug.security.check_password_hash` — both already available).

## 1. `database/db.py` — add `get_user_by_email(email)`

Add after `create_user()` (currently ends at line 56), before `seed_db()`:
- `def get_user_by_email(email):` — opens a connection via `get_db()`, runs `SELECT * FROM users WHERE email = ?` with `(email,)` as the params tuple (parameterized, never f-string), returns `.fetchone()` result directly (naturally `None` if no match, thanks to `sqlite3.Row` factory already set in `get_db()`).
- Wrap in `try/finally` exactly like `create_user()` does, closing the connection in `finally`.
- No password comparison here — that stays in `app.py`, keeping `db.py` limited to data access (mirrors the existing division of labor).
- No email case-normalization — `create_user()` doesn't normalize either, so lookup stays exact-match for consistency with current behavior (not introducing new inconsistency).

## 2. `app.py` — imports, `login()`, `logout()`

**Imports** — extend existing lines:
- `from flask import Flask, abort, flash, redirect, render_template, request, session, url_for` (add `session`; `abort` optional, see note below)
- `from werkzeug.security import check_password_hash` (new import)
- `from database.db import create_user, get_db, get_user_by_email, init_db, seed_db` (add `get_user_by_email`)

**`login()`** (replace current stub at lines 48-50):
- `@app.route("/login", methods=["GET", "POST"])`
- `GET` → `return render_template("login.html")` (unchanged behavior)
- `POST` branch, mirroring `register()`'s structure:
  - Read `email = request.form.get("email", "").strip()`, `password = request.form.get("password", "")`
  - If either is empty → flash `"Invalid email or password"` (category `"error"`), re-render `login.html`
  - Call `get_user_by_email(email)`; if `None`, or `check_password_hash(user["password_hash"], password)` is `False` → flash the **same** generic message, re-render `login.html`
  - On success: `session["user_id"] = user["id"]`, `return redirect(url_for("landing"))`
- **Anti-enumeration rule**: all three failure modes (empty fields, unknown email, wrong password) use the identical flashed string "Invalid email or password" — never a distinct message that would reveal which part was wrong.
- Flask's `methods=["GET", "POST"]` restriction already returns HTTP 405 automatically for any other verb — this satisfies the spec's "abort(405) for unsupported methods" without an explicit call, exactly like `register()` does today. Decide at implementation time whether to keep the `abort` import for clarity or drop it if unused (avoid an unused-import warning either way).

**`logout()`** (replace stub at lines 67-69):
- Keep `@app.route("/logout")` (GET only, unchanged)
- Body: `session.clear()` then `return redirect(url_for("login"))`
- `session.clear()` is safe even when no session exists — no conditional guard needed to satisfy "must not error if nobody is logged in."

**Cosmetic (optional)**: `logout()` currently sits under the "Placeholder routes — students will implement these" comment block. Since it's no longer a placeholder, consider moving it up next to `login()`/`register()` so the comment continues to accurately describe only `/profile` and `/expenses/*`. Not required by spec, but avoids a stale comment.

## 3. `templates/login.html`

- Form tag: change `<form method="POST" action="/login">` → `<form method="post" action="{{ url_for('login') }}">` (lowercase `method` to match `register.html`'s convention).
- Replace the existing `{% if error %}...{% endif %}` block (lines 16-18) with the exact flash idiom already used in `register.html` (lines 16-20):
  ```
  {% with messages = get_flashed_messages(with_categories=True) %}
  {% for category, message in messages %}
  <div class="auth-{{ 'error' if category == 'error' else 'success' }}">{{ message }}</div>
  {% endfor %}
  {% endwith %}
  ```
- Delete the old `error`-variable block entirely — nothing in the new `login()` passes an `error=` kwarg, so it would silently never render if left in place; remove rather than leave as dead code.
- No other changes — keep existing markup/classes (`auth-header`, `auth-card`, `form-group`, `auth-switch`) untouched per spec's "keep all existing visual design."

## 4. `templates/base.html`

Replace the static nav-links content (lines 21-24) with a session-conditional block:
```
<div class="nav-links">
    {% if session.get('user_id') %}
    <a href="{{ url_for('logout') }}">Logout</a>
    {% else %}
    <a href="{{ url_for('login') }}">Sign in</a>
    <a href="{{ url_for('register') }}" class="nav-cta">Get started</a>
    {% endif %}
</div>
```
- `session` is auto-injected into Jinja context by Flask — no context processor needed.
- No new CSS required: existing `.nav-links a` styling (`style.css` line 105, `color: var(--ink-muted)`, hover `var(--ink)`) is enough for "Logout" — do **not** apply `.nav-cta` to it, that class is visually reserved for the primary "Get started" button.
- **Known pre-existing gap (flag, don't fix)**: `style.css` line 700, `@media (max-width: 600px) { .nav-links a:not(.nav-cta) { display: none; } }` hides any non-`.nav-cta` link on mobile — "Sign in" already disappears on mobile today, and "Logout" will too after this change. This is an existing CSS limitation, not a regression from this step, and fixing it is outside this spec's file list.

## Order of implementation
1. `database/db.py` — add `get_user_by_email()` first (pure, no dependencies); sanity-check against the seeded `demo@spendly.com` user before touching routes.
2. `app.py` — implement `logout()` (simplest, no branching); verify session-clear + redirect in isolation.
3. `app.py` — implement `login()` GET/POST logic, wired to `get_user_by_email()` + `check_password_hash()`.
4. `templates/login.html` — fix form action + swap in flash block, making step 3's flashed errors visible.
5. `templates/base.html` — add session-conditional nav last, since it's the integration check that confirms `session["user_id"]` is being set correctly end-to-end.

## Verification plan (no automated tests exist yet — manual, end-to-end)
Run `python app.py` (serves `http://127.0.0.1:5001`, `debug=True`). Seeded user: `demo@spendly.com` / `demo123`.

1. `GET /login` renders cleanly, no Jinja errors, no stray flash leaking in.
2. Valid login (`demo@spendly.com` / `demo123`) → redirects to `/`, no error flash.
3. Reload any page after login → nav shows "Logout" (confirms session persisted via cookie, not a one-request fluke).
4. Invalid login, unknown email → re-renders `/login`, flashes "Invalid email or password", nav still shows "Sign in"/"Get started".
5. Invalid login, wrong password for `demo@spendly.com` → same exact error text as case 4 (byte-identical — this is the anti-enumeration check).
6. Invalid login, empty fields → since HTML5 `required` blocks client submission, test server-side validation via `curl -X POST http://127.0.0.1:5001/login -d "email=&password="` and confirm a clean flash, not a crash.
7. Nav bar toggles correctly on at least two pages (e.g. landing + login) in both logged-in and logged-out state.
8. `GET /logout` while logged in → redirects to `/login`, nav reverts to logged-out state.
9. `GET /logout` while already logged out → no 500, clean redirect to `/login`.
10. `curl -X PUT http://127.0.0.1:5001/login` → confirm HTTP 405, not 500 or 200.
11. Regression: re-verify `GET /register` and a full registration round-trip still work after the shared `app.py` import/route edits.

## Risks / edge cases (flagged, not addressed in this step)
- `/profile` and `/expenses/*` remain unauthenticated stubs — no `@login_required`-style guard is added; explicitly out of scope per spec's file list. A future step presumably adds that guard.
- No "remember me" / permanent session — `session.permanent` is never set, so cookies expire on browser close. Consistent with spec (not mentioned), not a bug.
- Email lookup is case-sensitive, matching `create_user()`'s existing behavior — not a new inconsistency, but worth knowing if QA registers as `Demo@Spendly.com` and can't log in as `demo@spendly.com`.
- Mobile nav hides "Logout" same as it hides "Sign in" today (see CSS note above) — pre-existing gap, out of scope.
