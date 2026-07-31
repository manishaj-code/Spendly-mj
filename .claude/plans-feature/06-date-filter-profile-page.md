# Plan: Date-Range Filter for `/profile`

## Context
The `/profile` page (Spendly, Flask + SQLite) currently always shows all-time summary stats, the 10 most recent transactions, and an all-time category breakdown, with no way to narrow the view to a period. Spec `.claude/specs/06-date-filter-profile-page.md` (Step 6) adds a date-range filter — four presets ("This Month", "Last 3 Months", "Last 6 Months", "All Time") plus a custom `date_from`/`date_to` range — driven entirely by `GET /profile` query params, no new routes or DB schema. This plan implements that spec.

Researched via Explore + Plan subagents and verified directly: `app.py`, `database/queries.py`, `templates/profile.html`, `templates/base.html`, `static/css/style.css`, `static/css/profile.css`, `static/js/main.js`. Key facts confirmed:
- `base.html` defines blocks `title`, `head`, `content`, `scripts`; it does **not** render flash messages — `profile.html` must add its own flash block (following the `login.html`/`register.html` pattern using `.auth-error`/`.auth-success` classes, already global in `style.css`).
- `expenses.date` is stored as `YYYY-MM-DD` text, so SQL `BETWEEN ? AND ?` on the raw strings is chronologically correct — no `strftime()` needed.
- No `request.args` usage exists anywhere yet — this is new territory for `app.py`.
- Reusable CSS vars/components confirmed: `--paper-card`, `--accent`, `--accent-light`, `--ink-soft`, `--ink-muted`, `--border`, `--radius-sm`, `--radius-md`; `.btn-primary`, `.form-input`, `.hero-badge` (pill pattern), `.auth-error`/`.auth-success`.
- No JS changes needed — presets are server-rendered `<a>` links via `url_for`, custom range is a plain `method="get"` form.

## Implementation

### 1. `database/queries.py`
Add optional `date_from=None, date_to=None` params to all three functions. Build a static `date_clause` (`""` or `" AND date BETWEEN ? AND ?"`) and extend the params list — never string-format the date values themselves:

```python
def get_summary_stats(user_id, date_from=None, date_to=None):
    ...
    params = [user_id]
    date_clause = ""
    if date_from is not None and date_to is not None:
        date_clause = " AND date BETWEEN ? AND ?"
        params.extend([date_from, date_to])
    row = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt FROM expenses WHERE user_id = ?{date_clause}",
        params,
    ).fetchone()
    # top_category query reuses the same params/date_clause
```

Same pattern for `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None)` (append `limit` to `params` last, after the optional date bounds) and `get_category_breakdown(user_id, date_from=None, date_to=None)` (rounding-remainder logic untouched). When both dates are `None`, generated SQL is identical to current Step 5 queries — no behavior change when unfiltered.

### 2. `app.py`
Add `import calendar` and `from datetime import date, datetime` (module already imports `sqlite3`, Flask pieces).

**Parsing/validation:**
```python
def _parse_date_arg(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

def _resolve_date_filter():
    date_from = _parse_date_arg(request.args.get("date_from", ""))
    date_to = _parse_date_arg(request.args.get("date_to", ""))
    if date_from is None or date_to is None:
        return None, None
    if date_from > date_to:
        flash("Start date must be before end date.", "error")
        return None, None
    return date_from.isoformat(), date_to.isoformat()
```
A single missing/malformed param → silent fallback to unfiltered (no flash). Both present but reversed → flash + fallback. Both present and valid → filter applies.

**Preset math** (calendar-month based, all "ending today" — chosen because the spec's own vocabulary is "3-month"/"6-month", and calendar-month subtraction avoids day-count drift across months of different lengths):
```python
def _shift_months(d, months):
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))

def _date_presets():
    today = date.today()
    today_str = today.isoformat()
    return [
        {"key": "this_month", "label": "This Month",
         "date_from": today.replace(day=1).isoformat(), "date_to": today_str},
        {"key": "last_3_months", "label": "Last 3 Months",
         "date_from": _shift_months(today, 3).isoformat(), "date_to": today_str},
        {"key": "last_6_months", "label": "Last 6 Months",
         "date_from": _shift_months(today, 6).isoformat(), "date_to": today_str},
        {"key": "all_time", "label": "All Time", "date_from": None, "date_to": None},
    ]
```
This is plain date arithmetic, not DB logic, so per CLAUDE.md it correctly lives in `app.py` (not `database/db.py`) — and the spec forbids new files, so no separate helper module.

**Filter context for the template:**
```python
def _preset_url(preset):
    params = {}
    if preset["date_from"] is not None:
        params["date_from"] = preset["date_from"]
    if preset["date_to"] is not None:
        params["date_to"] = preset["date_to"]
    return url_for("profile", **params)

def _build_filter_context(date_from, date_to):
    presets = _date_presets()
    active_preset = None
    preset_links = []
    for p in presets:
        is_active = (date_from == p["date_from"] and date_to == p["date_to"])
        if is_active:
            active_preset = p["key"]
        preset_links.append({"key": p["key"], "label": p["label"], "url": _preset_url(p), "active": is_active})
    return {
        "presets": preset_links,
        "active_preset": active_preset,
        "is_custom": bool(date_from and date_to) and active_preset is None,
        "date_from": date_from or "",
        "date_to": date_to or "",
    }
```
Building `params` explicitly (rather than passing `None` into `url_for` kwargs) guarantees "All Time" produces a clean `/profile` with no query string. A bare `/profile` visit naturally matches `all_time` (`None == None`), so it's highlighted correctly with no special-casing.

**Thread through the `_build_profile_*` helpers and the route:**
```python
def _build_profile_stats(user_id, date_from=None, date_to=None):
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    ...  # unchanged body

def _build_profile_transactions(user_id, date_from=None, date_to=None):
    transactions = get_recent_transactions(user_id, limit=10, date_from=date_from, date_to=date_to)
    ...  # unchanged body

def _build_profile_categories(user_id, date_from=None, date_to=None):
    breakdown = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    ...  # unchanged body

@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    user_id = session["user_id"]
    date_from, date_to = _resolve_date_filter()
    return render_template(
        "profile.html",
        user=_build_profile_user(user_id),
        stats=_build_profile_stats(user_id, date_from, date_to),
        transactions=_build_profile_transactions(user_id, date_from, date_to),
        categories=_build_profile_categories(user_id, date_from, date_to),
        filter=_build_filter_context(date_from, date_to),
    )
```
Zero-expenses-in-range is already handled by existing logic in `queries.py` (`total_spent=0.0`, `transaction_count=0`, `top_category="—"`, empty lists) — no new edge-case code needed. `format_currency()` is applied unconditionally, so ₹ always displays.

### 3. `templates/profile.html`
Add a flash block (none exists yet) and a filter-bar section, placed between the user-info-card section and the summary-stats section:

```html
{% with messages = get_flashed_messages(with_categories=True) %}
{% for category, message in messages %}
<div class="auth-{{ 'error' if category == 'error' else 'success' }}">{{ message }}</div>
{% endfor %}
{% endwith %}

<section class="profile-section profile-filter-section">
    <div class="profile-filter-bar">
        <div class="profile-filter-presets">
            {% for preset in filter.presets %}
            <a href="{{ preset.url }}"
               class="profile-filter-preset{{ ' profile-filter-preset-active' if preset.active else '' }}">
                {{ preset.label }}
            </a>
            {% endfor %}
        </div>

        <form method="get" action="{{ url_for('profile') }}"
              class="profile-filter-custom{{ ' profile-filter-custom-active' if filter.is_custom else '' }}">
            <div class="profile-filter-field">
                <label for="date_from">From</label>
                <input type="date" id="date_from" name="date_from" class="form-input" value="{{ filter.date_from }}">
            </div>
            <div class="profile-filter-field">
                <label for="date_to">To</label>
                <input type="date" id="date_to" name="date_to" class="form-input" value="{{ filter.date_to }}">
            </div>
            <button type="submit" class="btn-primary profile-filter-apply">Apply</button>
        </form>
    </div>
</section>
```
No structural changes to the existing three sections (user card, stats, transactions/categories panels) — only the Jinja variables they already consume change. Preset URLs come entirely from `preset.url` (built server-side via `url_for` in `app.py`) — no hardcoded URLs in the template.

### 4. `static/css/profile.css`
Add new rules following the existing `.profile-<section>[-<element>[-<modifier>]]` naming convention, reusing existing `--*` vars only (no hex literals):

```css
.profile-filter-bar {
    background: var(--paper-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 1.25rem 1.5rem;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
}

.profile-filter-presets { display: flex; flex-wrap: wrap; gap: 0.6rem; }

.profile-filter-preset {
    display: inline-flex;
    align-items: center;
    padding: 0.5rem 1.1rem;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--ink-soft);
    font-size: 0.85rem;
    font-weight: 500;
    text-decoration: none;
    transition: border-color 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.profile-filter-preset:hover { border-color: var(--ink); color: var(--ink); }

.profile-filter-preset-active {
    background: var(--accent-light);
    border-color: var(--accent-light);
    color: var(--accent);
    font-weight: 600;
}

.profile-filter-custom {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 0.75rem;
    padding: 0.4rem;
    border-radius: var(--radius-sm);
}

.profile-filter-custom-active { background: var(--accent-light); }

.profile-filter-field { display: flex; flex-direction: column; gap: 0.3rem; }
.profile-filter-field label { font-size: 0.75rem; font-weight: 500; color: var(--ink-muted); }
.profile-filter-field .form-input { padding: 0.45rem 0.7rem; font-size: 0.85rem; }
.profile-filter-apply { padding: 0.55rem 1.25rem; font-size: 0.85rem; border-radius: var(--radius-sm); }

@media (max-width: 900px) {
    .profile-filter-bar { flex-direction: column; align-items: stretch; }
    .profile-filter-custom { flex-direction: column; align-items: stretch; }
}
```
`.profile-filter-preset-active` reuses the `--accent`/`--accent-light` pill treatment already used by `.hero-badge`, keeping the active-state visual language consistent with the rest of the app. `.btn-primary` (global, from `style.css`) is reused directly for the Apply button.

### 5. JavaScript
No changes. `static/js/main.js` stays as-is — presets are plain links, the custom range is a native GET form, both are pure server-rendered navigation.

## Order of implementation
1. `database/queries.py` — add the three optional date params (foundation, no Flask dependency).
2. `app.py` — imports, `_parse_date_arg`, `_resolve_date_filter`, `_shift_months`, `_date_presets`, `_preset_url`, `_build_filter_context`; update `_build_profile_*` signatures; update `profile()` route.
3. `templates/profile.html` — flash block + filter bar markup.
4. `static/css/profile.css` — filter-bar styles.

## Verification
Run `python app.py` (port 5001) and manually check, logged in as the seed user (`demo@spendly.com` / `demo123`):
- Bare `/profile` — same totals as before this change; "All Time" preset highlighted.
- Click each preset ("This Month", "Last 3 Months", "Last 6 Months") — transaction list/stats/category breakdown narrow correctly; preset visually highlighted; inputs pre-filled to match.
- Submit a valid custom range via the form — filters correctly, inputs retain submitted values, custom form shows active state (no preset highlighted unless it coincides).
- Submit `date_from` after `date_to` — flash message appears, view falls back to all-time, no crash.
- Manually hit `/profile?date_from=not-a-date` — silently falls back to all-time, no crash, no flash.
- Pick a range with zero matching expenses — ₹0.00, 0 transactions, empty category breakdown, no errors.
- Confirm ₹ symbol displays in every state.
- Visually confirm no hardcoded hex colors were introduced (only `var(--...)` used) in the diff of `profile.css`/`profile.html`.

After manual verification, hand off to `/test-feature 06-date-filter-profile-page` for automated pytest coverage (out of scope here — query-helper signatures are already keyword-arg/default-friendly for that step).

---

## Status: Implemented and verified
All four files were implemented per this plan and independently verified (manual HTTP smoke tests + a separate verification subagent) — no bugs found, all spec rules and Definition-of-Done items satisfied. See conversation history for the full verification report. Not yet committed.
