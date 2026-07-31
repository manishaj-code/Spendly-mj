import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
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

def format_currency(amount):
    return f"₹{amount:,.2f}"


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
def _build_profile_stats(user_id):
    stats = get_summary_stats(user_id)
    return [
        {"label": "Total Spent", "value": format_currency(stats["total_spent"]), "icon": "wallet"},
        {"label": "Transactions", "value": str(stats["transaction_count"]), "icon": "receipt"},
        {"label": "Top Category", "value": stats["top_category"], "icon": "tag"},
    ]
# --- Subagent 2 end --- #


# --- Subagent 1 begin (transactions) --- #
def _build_profile_transactions(user_id):
    transactions = get_recent_transactions(user_id, limit=10)
    return [
        {
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


def _build_profile_categories(user_id):
    breakdown = get_category_breakdown(user_id)
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
    return render_template(
        "profile.html",
        user=_build_profile_user(user_id),
        stats=_build_profile_stats(user_id),
        transactions=_build_profile_transactions(user_id),
        categories=_build_profile_categories(user_id),
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


with app.app_context():
    init_db()
    seed_db()


if __name__ == "__main__":
    app.run(debug=True, port=5001)
