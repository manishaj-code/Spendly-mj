import calendar
import sqlite3
from datetime import date, datetime

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
    update_expense,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # TODO: replace with a real secret before production


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        flash("All fields are required.", "error")
        return render_template("register.html")

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return render_template("register.html")

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        flash("Email already registered.", "error")
        return render_template("register.html")

    flash("Account created successfully! Please sign in.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email) if email and password else None

    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid email or password", "error")
        return render_template("login.html")

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]

def format_currency(amount):
    return f"₹{amount:,.2f}"


def _parse_date_arg(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_date_filter():
    date_from = _parse_date_arg(request.args.get("date_from"))
    date_to = _parse_date_arg(request.args.get("date_to"))

    if date_from is None or date_to is None:
        return None, None

    if date_from > date_to:
        flash("Start date must be before end date.", "error")
        return None, None

    return date_from.isoformat(), date_to.isoformat()


def _shift_months(d, months):
    # Shift d back by `months` calendar months, clamping the day-of-month
    # to the last valid day of the target month (e.g. Mar 31 - 1mo -> Feb 28/29).
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _date_presets():
    today = date.today()
    today_str = today.isoformat()
    return [
        {
            "key": "this_month",
            "label": "This Month",
            "date_from": today.replace(day=1).isoformat(),
            "date_to": today_str,
        },
        {
            "key": "last_3_months",
            "label": "Last 3 Months",
            "date_from": _shift_months(today, 3).isoformat(),
            "date_to": today_str,
        },
        {
            "key": "last_6_months",
            "label": "Last 6 Months",
            "date_from": _shift_months(today, 6).isoformat(),
            "date_to": today_str,
        },
        {"key": "all_time", "label": "All Time", "date_from": None, "date_to": None},
    ]


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
    for preset in presets:
        is_active = date_from == preset["date_from"] and date_to == preset["date_to"]
        if is_active:
            active_preset = preset["key"]
        preset_links.append(
            {
                "key": preset["key"],
                "label": preset["label"],
                "url": _preset_url(preset),
                "active": is_active,
            }
        )

    return {
        "presets": preset_links,
        "active_preset": active_preset,
        "is_custom": bool(date_from and date_to) and active_preset is None,
        "date_from": date_from or "",
        "date_to": date_to or "",
    }


# --- Subagent 2 begin (user info) --- #
def _build_profile_user(user_id):
    data = get_user_by_id(user_id)
    if data is None:
        return {"name": "", "email": "", "initials": "", "member_since": ""}

    parts = data["name"].split()
    if len(parts) >= 2:
        initials = (parts[0][0] + parts[-1][0]).upper()
    elif parts:
        initials = parts[0][:2].upper()
    else:
        initials = ""

    return {
        "name": data["name"],
        "email": data["email"],
        "initials": initials,
        "member_since": data["member_since"],
    }
# --- Subagent 2 end --- #


# --- Subagent 2 begin (summary stats) --- #
def _build_profile_stats(user_id, date_from=None, date_to=None):
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    return [
        {"label": "Total Spent", "value": format_currency(stats["total_spent"]), "icon": "wallet"},
        {"label": "Transactions", "value": str(stats["transaction_count"]), "icon": "receipt"},
        {"label": "Top Category", "value": stats["top_category"], "icon": "tag"},
    ]
# --- Subagent 2 end --- #


# --- Subagent 1 begin (transactions) --- #
def _build_profile_transactions(user_id, date_from=None, date_to=None):
    transactions = get_recent_transactions(user_id, limit=10, date_from=date_from, date_to=date_to)
    return [
        {
            "id": t["id"],
            "date": t["date"],
            "description": t["description"],
            "category": t["category"],
            "category_class": f"profile-badge-{t['category'].lower()}",
            "amount": format_currency(t["amount"]),
        }
        for t in transactions
    ]
# --- Subagent 1 end --- #


# --- Subagent 3 begin (categories) --- #
def _pct_to_bar_class(pct):
    stepped = max(5, min(100, round(pct / 5) * 5))
    return f"profile-bar-w-{stepped}"


def _build_profile_categories(user_id, date_from=None, date_to=None):
    breakdown = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    return [
        {
            "name": c["name"],
            "amount": format_currency(c["amount"]),
            "color_class": f"profile-progress-bar-{c['name'].lower()}",
            "bar_class": _pct_to_bar_class(c["pct"]),
        }
        for c in breakdown
    ]
# --- Subagent 3 end --- #


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


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        form = {"amount": "", "category": "", "date": date.today().isoformat(), "description": ""}
        return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

    raw_amount = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    raw_date = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    form = {"amount": raw_amount, "category": category, "date": raw_date, "description": description}

    try:
        amount = float(raw_amount)
    except ValueError:
        amount = None

    if amount is None or amount <= 0:
        flash("Enter a valid amount greater than 0.", "error")
        return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

    if category not in EXPENSE_CATEGORIES:
        flash("Select a valid category.", "error")
        return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

    try:
        datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError:
        flash("Enter a valid date.", "error")
        return render_template("add_expense.html", categories=EXPENSE_CATEGORIES, form=form)

    insert_expense(session["user_id"], amount, category, raw_date, description or None)
    flash("Expense added successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        form = {
            "amount": str(expense["amount"]),
            "category": expense["category"],
            "date": expense["date"],
            "description": expense["description"] or "",
        }
        return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

    raw_amount = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    raw_date = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    form = {"amount": raw_amount, "category": category, "date": raw_date, "description": description}

    try:
        amount = float(raw_amount)
    except ValueError:
        amount = None

    if amount is None or amount <= 0:
        flash("Enter a valid amount greater than 0.", "error")
        return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

    if category not in EXPENSE_CATEGORIES:
        flash("Select a valid category.", "error")
        return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

    try:
        datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError:
        flash("Enter a valid date.", "error")
        return render_template("edit_expense.html", categories=EXPENSE_CATEGORIES, form=form, expense=expense)

    update_expense(id, session["user_id"], amount, category, raw_date, description or None)
    flash("Expense updated successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
