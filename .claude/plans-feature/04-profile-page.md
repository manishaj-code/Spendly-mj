# Plan: Profile Page (Step 4) — Static/Hardcoded UI

## Context
`.claude/specs/04-profile-page.md` requires replacing the `/profile` stub with a fully designed but static/hardcoded page (user info card, summary stats, transaction table, category breakdown) — no real DB queries yet, that's Step 5. A prior attempt at this exact feature was implemented earlier in this session but was lost/reverted before being committed, so this plan was built from a **fresh, re-verified** read of the current codebase (not from memory of the lost work), plus `CLAUDE.md` and `.claude/skills/frontend-design/SKILL.md` as the user explicitly requested. Two decisions carried forward from earlier in this session (re-confirmed, not re-litigated):
1. **Navbar username** (spec DoD requires "username + logout" but forbids new DB queries): resolved by storing `session["user_name"]` in the existing `login()` handler — zero new queries, since `login()` already fetches the full user row.
2. **Redirect to profile** (explicitly re-confirmed by the user for this plan): `login()`/`register()`'s already-logged-in guards, and the post-login redirect, change their target from `landing` to `profile` — this is additive to the spec, not derived from it, but the user asked for it to be folded back in here so it isn't lost again.

---

## Files to create
- `templates/profile.html` — extends `base.html`, four sections, zero hex, zero inline `style=`, zero `<script>` (no JS needed, see below).
- `static/css/profile.css` — all page-specific rules, `.profile-*` prefixed, linked via `profile.html`'s `{% block head %}`.

## Files to modify
- **`app.py`**
  - `login()`: add `session["user_name"] = user["name"]` immediately after the existing `session["user_id"] = user["id"]`. Change the already-logged-in guard (`if session.get("user_id"): return redirect(url_for(...))`) and the post-success redirect target from `landing` to `profile`.
  - `register()`: change its already-logged-in guard target from `landing` to `profile` (register itself still redirects to `login` after account creation — unchanged).
  - Replace the `/profile` stub with a real view: `if not session.get("user_id"): return redirect(url_for("login"))`, else `render_template("profile.html", user=..., stats=..., transactions=..., categories=...)` using four hardcoded module-level constants defined just above the route (`PROFILE_USER`, `PROFILE_STATS`, `PROFILE_TRANSACTIONS`, `PROFILE_CATEGORIES` — see data section below). One responsibility in the route function per CLAUDE.md.
- **`templates/base.html`**
  - Nav-links block: add a `.nav-username` span before "Logout", guarded by its own `{% if session.get('user_name') %}` nested inside the existing `{% if session.get('user_id') %}` — so a stale session (has `user_id`, not yet `user_name`) renders nothing instead of literal `None`.
  - Add `<script src="https://unpkg.com/lucide@latest"></script>` immediately before the existing `main.js` script tag (bottom of `<body>`), so Lucide is defined before `main.js` runs.
- **`static/js/main.js`** — append a guarded `if (window.lucide) { lucide.createIcons(); }` call. Global plumbing, benefits every page once Lucide is loaded, not profile-specific.
- **`static/css/style.css`**
  - Add new category color tokens to the existing `:root` block (this is the only place new hex is allowed to live, matching how `--accent`/`--danger` etc. are already hex-backed tokens): reuse `--accent-2`/`--accent-2-light` for `--cat-food`/`--cat-food-light` and `--ink-muted`/`--border-soft` for `--cat-other`/`--cat-other-light` (no new hex needed for these two); add genuinely new hex-backed pairs for `--cat-transport`, `--cat-bills`, `--cat-health`, `--cat-entertainment`, `--cat-shopping` (each with a `-light` companion).
  - Add a `.nav-username` rule near the existing Navbar section (color `var(--ink-soft)`, weight 500).
  - Add `.nav-username { display: none; }` to the existing `@media (max-width: 600px)` block, alongside the existing `.nav-links a:not(.nav-cta)` rule.

## No changes to
- `database/db.py` — spec forbids new DB queries/helpers this step; confirmed no `get_user_by_id()` exists and none is added.

---

## Hardcoded data (module-level constants in `app.py`, passed straight to `render_template`)

```
PROFILE_USER = {name, email, initials, member_since}
PROFILE_STATS = [ {label, value, icon}, ×3 ]              # Total Spent / Transactions / Top Category
PROFILE_TRANSACTIONS = [ {date, description, category, category_class, amount}, ×5 ]
PROFILE_CATEGORIES = [ {name, amount, percent, bar_class, color_class}, ×5 ]
```
- `category_class` / `bar_class` / `color_class` are precomputed directly in the Python dicts (not derived via Jinja `{% if/elif %}` chains) — keeps the template free of branching since every value is static.
- Reuses the app's seeded demo categories (`Food, Transport, Bills, Health, Entertainment`) from `database/db.py`'s `seed_db()` for narrative consistency; `Shopping`/`Other` CSS tokens/classes are still defined (unused by this step's rows) so Step 5's real data doesn't require another CSS pass.
- Currency formatted as `₹` to match the existing convention already used in `landing.html`'s `.mock-stat-value`.

---

## CSS class scheme (`static/css/profile.css`, `.profile-*` prefix)

- **Shell:** `.profile-page` (page container, `max-width: var(--max-width)`), `.profile-section` (per-section wrapper, vertical rhythm), `.profile-section-title` (heading row: icon + text, flex, gap).
- **User info card:** `.profile-user-card` (mirrors `.auth-card`: paper-card, border, `radius-md`, padding, but horizontal flex layout) → `.profile-avatar` (circle ~72px, `background: var(--accent-light)`, `color: var(--accent)`, holds initials — scaled sibling of `.dot`/`.hero-badge-dot`) + `.profile-user-info` → `.profile-user-name`, `.profile-user-email`, `.profile-user-meta` (with calendar icon).
- **Stats row:** `.profile-stats` (grid `repeat(3,1fr)`, mirrors `.mock-stats`) → `.profile-stat` (mirrors `.mock-stat`) → `.profile-stat-icon` (small circle, accent-tinted, holds the per-stat Lucide icon) + `.profile-stat-label` / `.profile-stat-value` (mirror `.mock-stat-label/-value`).
- **Transaction table (net new):** `.profile-table-wrap` (card, `overflow-x: auto`) → `.profile-table` (`width:100%`, `border-collapse: collapse`) with `thead th` (muted, bottom border), `tbody tr:hover` (`background: var(--paper-warm)` — skill's row-hover guidance), `.profile-table-amount` (right-aligned, `tabular-nums`, weight 600 — skill's numeric-column guidance). Category cells use `.profile-badge` (pill, mirrors `.hero-badge` shape) + one modifier per category (`.profile-badge-food`, `-transport`, `-bills`, `-health`, `-entertainment`, `-shopping`, `-other`) setting only `background`/`color` from the new `--cat-*` variables — zero hex, zero inline style in the template.
- **Category breakdown:** `.profile-progress-card` (mirrors `.mock-progress-card`) → `.profile-progress-row` (grid `120px 1fr auto` — wider label column than the landing page's `70px` since names like "Entertainment" are longer, plus a trailing amount column) → `.profile-progress-label`, `.profile-progress-track` (mirrors `.mock-progress-track`), `.profile-progress-bar` + color modifier (`.profile-progress-bar-food`, etc.) + a discrete width class.
  - **Width without inline style:** define `.profile-bar-w-5` through `.profile-bar-w-100` in 5%-steps once in `profile.css` (only `-10/-20/-25/-35` are used by the current hardcoded rows; the rest make future hardcoded-data edits free of further CSS changes). Applied as a second class alongside the color modifier — width and color fully decoupled, no hex, no inline `style="width:...`.
- **Responsive:** extend the two existing breakpoints only (no new tier) — `@media (max-width: 900px)`: `.profile-stats` → 1 column, `.profile-user-card` → stacked/centered. `@media (max-width: 600px)`: `.profile-progress-row` → drop/stack the trailing amount column, `.profile-table-wrap` scroll reaffirmed.

---

## Lucide icon integration (restrained — 8 instances total, per skill's density guidance)

| Location | Icon | Size |
|---|---|---|
| Section 1 heading | `user` | 24px |
| "Member since" meta | `calendar` | 16px |
| Section 2 heading | `bar-chart-3` | 24px |
| Stat: Total Spent | `wallet` | 20px |
| Stat: Transactions | `receipt` | 20px |
| Stat: Top Category | `tag` | 20px |
| Section 3 heading | `receipt` | 24px |
| Section 4 heading | `pie-chart` | 24px |

Deliberately **no icons** on table rows, badges, or breakdown rows — color + label already carries the meaning there (matches the landing page's existing icon-free `.mock-progress-*` precedent), and row-action icons would misleadingly imply edit/delete functionality that doesn't exist until Steps 8/9. Icon sizing applied via scoped selectors targeting the Lucide-generated `<svg>` (e.g. `.profile-stat-icon svg { width: 20px; height: 20px; }`), kept inside `profile.css`.

## JS needed: none for `profile.html`
Pure static display page — no sorting/filtering/pagination in scope. Only touch to JS is the 2-3 line global `lucide.createIcons()` addition to the already-existing `main.js` (icon-rendering plumbing shared by all pages, not profile-specific).

---

## Verification plan
1. **Static checks** on `templates/profile.html` before starting the server: no hex (`#[0-9a-fA-F]{3,6}`), no `style=`, no `<script`; confirm `{% extends "base.html" %}` present. Also visually confirm the `base.html` `.nav-username` guard nests correctly inside the `user_id` check.
2. Start the dev server with `& .\venv\Scripts\python.exe app.py` (plain `python app.py` fails here — Flask is only installed in the venv), port 5001; confirm no template/Jinja errors on first request.
3. **Auth guard:** request `/profile` with no session → expect `302` to `/login`.
4. **Redirect-to-profile:** while already logged in, request `/login` and `/register` → both expect `302` to `/profile` (not `/` or `landing`); after a fresh successful login POST → expect `302` to `/profile`. Landing page (`/`) itself stays reachable and unredirected when logged in (unchanged, out of scope).
5. **Authenticated content:** log in as the seeded demo account (`demo@spendly.com` / `demo123`); GET `/profile` → `200`; visually confirm all DoD items (user card, 3 stats with icons, 5 transaction rows with colored badges + right-aligned amounts, 5 category rows with distinct colors/widths).
6. **Navbar:** username appears next to "Logout" while logged in; after Logout, nav reverts to "Sign in"/"Get started" and `/profile` redirects again.
7. **Icons render:** confirm Lucide `<i data-lucide>` tags become real `<svg>` elements (not literal text) with no console errors.
8. **Responsive check:** <900px (stats collapse to 1 col) and <600px (existing nav-hiding rule + `.nav-username` hidden) — no new breakpoints, no layout breakage.
9. **Regression:** no `tests/` directory exists yet, so this is manual/grep-based verification only (consistent with Steps 1-3) — revisit `/`, `/login`, `/register`, `/terms`, `/privacy` to confirm nothing else broke.

### Critical files
- `app.py`, `templates/profile.html`, `static/css/profile.css`, `templates/base.html`, `static/css/style.css`, `static/js/main.js`
