# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the existing `/profile` route so users can
narrow the transaction list, summary stats, and category breakdown to a specific
period. The filter is driven entirely by query-string parameters (`date_from` and
`date_to`) on `GET /profile`, requiring no new routes. A compact filter bar
with four quick-select presets ("This Month", "Last 3 Months", "Last 6 Months",
"All Time") and two `<input type="date">` fields lets users pick any custom range.
All three data sections (summary stats, recent transactions, category breakdown)
must respect the active date filter.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column must exist)
- Step 4: Profile page UI (template with all four sections must exist)
- Step 5: Backend connection (`get_summary_stats`, `get_recent_transactions`,
  `get_category_breakdown` in `database/queries.py` must exist and be wired to
  the `/profile` route)

## Routes
No new routes. The existing `GET /profile` route is modified to read optional
query parameters:
- `date_from` — ISO date string `YYYY-MM-DD`, inclusive lower bound
- `date_to`   — ISO date string `YYYY-MM-DD`, inclusive upper bound

If either parameter is absent or malformed, the route falls back to an "All
Time" (unfiltered) view rather than erroring out.

## Database changes
No database changes. The `expenses.date` column (`TEXT`, `YYYY-MM-DD`) already
supports `BETWEEN` comparison in SQLite.

## Templates
- **Modify**: `templates/profile.html`
  - Add a filter bar section above the summary stats row containing:
    - Four quick-select preset buttons: "This Month", "Last 3 Months",
      "Last 6 Months", "All Time" — each a link to `/profile` with the
      appropriate `date_from`/`date_to` query params
    - A custom range sub-form with two `<input type="date">` fields
      (`date_from`, `date_to`) and an "Apply" submit button
    - The currently active preset or custom range must be visually highlighted
      (active state on the button)
  - No structural changes to any existing section; only Jinja variables fed
    to them change when the filter is active

## Files to change
- `app.py`
  - In the `profile()` view: read `date_from` and `date_to` from
    `request.args`; validate they are well-formed ISO dates; pass them to each
    query helper; pass the validated values back to the template so the filter
    bar can reflect the active state
- `database/queries.py`
  - `get_summary_stats(user_id, date_from=None, date_to=None)` — add optional
    date-range params; when both are provided, add `AND date BETWEEN ? AND ?`
    to the `expenses` queries
  - `get_recent_transactions(user_id, limit=10, date_from=None, date_to=None)` —
    same pattern; ordering and limit remain unchanged
  - `get_category_breakdown(user_id, date_from=None, date_to=None)` — same
    pattern; percentage recalculation logic remains unchanged
- `templates/profile.html` — add filter bar (see Templates section)
- `static/css/profile.css` — add styles for the filter bar and active-preset
  button state using CSS variables only

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format dates into SQL; use `?`
  placeholders even for the date-range bounds
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Date validation in `app.py`: attempt `datetime.strptime(value, "%Y-%m-%d")`;
  on `ValueError`, treat the param as absent (fall back to no filter)
- Preset links must be generated with `url_for("profile", date_from=..., date_to=...)`
  — never hardcoded URL strings in the template
- When `date_from` and `date_to` are both absent, all three query helpers must
  behave identically to their Step 5 behaviour (unfiltered)
- If `date_from > date_to` after validation, treat both as absent (no filter)
  and flash a user-visible error message: "Start date must be before end date."
- The "All Time" preset must pass no query params (clean `/profile` URL)
- Preset date calculations (e.g. "This Month" → first day of current month)
  must be computed in `app.py`, not in the template

## Definition of done
- [ ] Visiting `/profile` with no query params returns the same data as Step 5
  (unfiltered, all expenses)
- [ ] Clicking "This Month" filters all three sections to the current calendar
  month only
- [ ] Clicking "Last 3 Months" filters to expenses in the 3-month window ending
  today
- [ ] Clicking "Last 6 Months" filters to expenses in the 6-month window ending
  today
- [ ] Clicking "All Time" removes any active filter and shows all expenses
- [ ] Submitting a custom date range with valid `date_from` and `date_to` shows
  only expenses within that range in all three sections
- [ ] Submitting a range where `date_from > date_to` shows a flash error and
  falls back to the unfiltered view
- [ ] Submitting a malformed date string (e.g. `date_from=not-a-date`) does not
  crash the app — it silently falls back to the unfiltered view
- [ ] The active preset button or custom-range fields visually indicate which
  filter is currently applied
- [ ] All amounts continue to display the ₹ symbol regardless of the active filter
- [ ] A user with no expenses in the selected range sees ₹0.00 total spent, 0
  transactions, and an empty category breakdown — no errors