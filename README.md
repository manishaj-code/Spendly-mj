# Spendly

A lightweight personal expense tracker built with Flask and SQLite.

Track every rupee — add, edit, and delete expenses, filter your spending by date range, and see a breakdown of where your money goes.

**Live demo:** https://expense-tracker-production-4ae1.up.railway.app

## Features

- **Accounts** — register, log in, and log out with hashed passwords (Werkzeug)
- **Profile dashboard** — total spent, transaction count, and top spending category at a glance
- **Expense management** — add, edit, and delete expenses, each scoped to the logged-in user
- **Date filtering** — quick presets (This Month, Last 3 Months, Last 6 Months, All Time) or a custom date range
- **Category breakdown** — visual progress bars showing spend per category
- **Analytics page** — coming soon

## Tech stack

- **Backend:** Flask (single `app.py`, no blueprints)
- **Database:** SQLite via raw parameterized `sqlite3` queries (no ORM)
- **Templates:** Jinja2, all extending a shared `base.html` layout
- **Frontend:** vanilla CSS and vanilla JS (no frameworks, no build step)
- **Icons:** [Lucide](https://lucide.dev/)

## Project structure

```
expense-tracker/
├── app.py                  # All routes
├── database/
│   ├── db.py                # Connection helper, schema init, seed data
│   └── queries.py           # Parameterized DB query helpers
├── templates/                # Jinja2 templates (one per page)
├── static/
│   ├── css/                  # Global + page-specific stylesheets
│   └── js/                   # Vanilla JS
├── tests/                    # pytest test suite
└── requirements.txt
```

## Getting started

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

python app.py
```

The app runs at `http://localhost:5001`.

A demo account is seeded automatically on first run:

- **Email:** `demo@spendly.com`
- **Password:** `demo123`

## Running tests

```bash
pytest
```

## Deployment

Deployed on [Railway](https://railway.com). The app reads the `PORT` environment variable when present (falling back to `5001` for local development) and binds to `0.0.0.0`.

## Roadmap

Spendly is built incrementally, one feature at a time. See `.claude/specs/` for the spec behind each step:

| Step | Feature | Status |
|---|---|---|
| 1 | Database setup | Done |
| 2 | Registration | Done |
| 3 | Login / Logout | Done |
| 4 | Profile page | Done |
| 5 | Profile backend routes | Done |
| 6 | Date filter on profile page | Done |
| 7 | Add expense | Done |
| 8 | Edit expense | Done |
| 9 | Delete expense | Done |
| — | Advanced analytics | Planned |
