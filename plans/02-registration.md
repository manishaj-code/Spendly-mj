# Plan: Step 02 — Registration

## Context
`GET /register` currently just renders `register.html`; the form on that page already posts `name`/`email`/`password` to `/register`, but nothing handles the `POST` yet, so submitting it does nothing. This step (per `.claude/specs/02-registration.md`, itself built on Step 01's `users` table and `get_db()`/`init_db()`) implements the real `POST /register` handler: validate input, hash the password, insert the row, and either show an error or redirect the new user to `/login`. This unblocks every later step that needs a real (non-seeded) user — login, profile, expenses.

## Key design decision: flash messages stay local to `register.html`
The spec's Rules require `flash()` + `app.secret_key` (not the template's current `{{ error }}` var), because the success message must survive the redirect to `/login`. `login.html` has no flash-rendering block and is explicitly out of scope this step (its stub-to-real upgrade is a later step), so — confirmed with the user — the success flash will be queued in the session but **not visibly rendered** after redirecting to `/login` in this step. Only `register.html` gets a flash block. This is an accepted, temporary gap, not a bug to fix now.

## Order of implementation

### 1. `database/db.py` — add `create_user(name, email, password)`
- Hash the password with the already-imported `werkzeug.security.generate_password_hash` (same import used in `seed_db()`, don't re-import).
- Open a connection with the module's own `get_db()` (same convention as `init_db()`/`seed_db()` — this function owns commit/close, not the caller).
- Insert via parameterized SQL: `INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)` — never an f-string.
- Do **not** catch `sqlite3.IntegrityError` here — let it propagate uncaught on duplicate email (UNIQUE constraint). Use `try/finally` only to guarantee `conn.close()` runs even when the insert raises; the exception itself still bubbles up unmodified.
- On success: commit, capture `cursor.lastrowid`, close, return it as the new user's id.
- **No separate `get_user_by_email()` lookup helper** — non-empty-field and password-match checks are pure string checks (no DB access needed), and relying on the UNIQUE constraint for duplicate-email detection avoids a check-then-insert race that a pre-check `SELECT` would introduce.

### 2. `app.py` — wire up `register()`
- Add imports: `flash`, `redirect`, `url_for`, `request` from `flask`; `import sqlite3` (to catch `sqlite3.IntegrityError`); add `create_user` to the existing `from database.db import ...` line.
- Set `app.secret_key` to a hardcoded dev string right after `app = Flask(__name__)` (module load time, before any route can call `flash()`).
- Change the route to `@app.route("/register", methods=["GET", "POST"])`.
- `GET`: unchanged — `return render_template("register.html")`.
- `POST`, in this order:
  1. Read `name`, `email`, `password`, `confirm_password` from `request.form.get(..., "")`, `.strip()` on `name`/`email`. Using `.get()` (not `request.form["..."]`) means a missing field falls through to the validation branch below instead of raising an unhandled `400`.
  2. If any of the four is empty → `flash("All fields are required.", "error")` and re-render `register.html` (no redirect).
  3. Else if `password != confirm_password` → `flash("Passwords do not match.", "error")` and re-render.
  4. Else call `create_user(name, email, password)` in a `try`; on `except sqlite3.IntegrityError:` → `flash("Email already registered.", "error")` and re-render.
  5. On success → `flash("Account created successfully! Please sign in.", "success")`, `return redirect(url_for("login"))`.
- Skip a manual `abort(405)` block: Flask's routing layer already returns 405 automatically for any verb not in `methods=[...]`, before the view function is even called, so an explicit check would be dead code.
- Keep the function to this one responsibility (validate → call → flash → render/redirect); all hashing/insert logic stays in `database/db.py`.

### 3. `templates/register.html`
- Fix the hardcoded form target: `<form method="POST" action="/register">` → `<form method="post" action="{{ url_for('register') }}">`.
- Add a fourth field, `confirm_password`, in its own `.form-group` right after the existing `password` group, matching the existing three fields' markup/classes/`required` attribute exactly (label "Confirm password", `type="password"`, `id`/`name="confirm_password"`).
- Replace the current `{% if error %}<div class="auth-error">{{ error }}</div>{% endif %}` block with a loop over Flask's flashed messages, categorized:
  ```
  {% with messages = get_flashed_messages(with_categories=True) %}
    {% for category, message in messages %}
      <div class="auth-{{ 'error' if category == 'error' else 'success' }}">{{ message }}</div>
    {% endfor %}
  {% endwith %}
  ```
  Keep this in the same spot (top of `.auth-card`, above the `<form>`).

### 4. `static/css/style.css`
- Add a `--success` / `--success-light` variable pair to `:root` (after the existing `--danger`/`--danger-light` pair at lines 17–18), same convention.
- Add a new `.auth-success` rule right after the existing `.auth-error` rule (line 466–474), same properties (background/color/border/border-radius/padding/font-size/margin-bottom), swapped to the new success variables. Use a variable for the border color, not a hardcoded hex — do **not** touch the pre-existing hardcoded `#f5c6c2` in `.auth-error`, that's out of scope here.

## Files touched
- `database/db.py` — add `create_user()`
- `app.py` — imports, `secret_key`, rewritten `register()`
- `templates/register.html` — form action/method, new field, flash loop
- `static/css/style.css` — new success color variables + `.auth-success` class

Not touched: `templates/login.html`, `templates/base.html` — by design (see decision above).

## Verification (manual — no test file required by the spec)
1. `python app.py` — starts cleanly on port 5001.
2. Visit `/register` — form shows 4 fields, no flash message on first load.
3. Submit with an empty field → re-renders `/register` with an error, no DB row added.
4. Submit with `password` ≠ `confirm_password` → re-renders with mismatch error, no DB row added.
5. Submit valid, unique data → redirects to `/login` (success message not visible this step, per the decision above).
6. Resubmit the same email → re-renders `/register` with "Email already registered", no second row.
7. Inspect the DB directly: `sqlite3 expense_tracker.db "SELECT id, name, email, password_hash FROM users;"` (note: the actual file is `expense_tracker.db`, not `spendly.db` as the spec's Definition of Done literally says — a pre-existing naming mismatch in the spec doc, not something to fix by renaming the DB). Confirm the new row's `password_hash` is a werkzeug-style hash (`pbkdf2:sha256:...` or `scrypt:...`), never plaintext, and no duplicate emails exist after step 6.
