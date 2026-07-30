import sqlite3

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

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

# Static demo data for the profile page (Step 4) — replaced with real queries in Step 5
PROFILE_USER = {
    "name": "Nitish Kumar",
    "email": "nitish@example.com",
    "initials": "NK",
    "member_since": "March 2026",
}

PROFILE_STATS = [
    {"label": "Total Spent", "value": "₹18,240", "icon": "wallet"},
    {"label": "Transactions", "value": "42", "icon": "receipt"},
    {"label": "Top Category", "value": "Food", "icon": "tag"},
]

PROFILE_TRANSACTIONS = [
    {"date": "Jul 28, 2026", "description": "Grocery shopping", "category": "Food", "category_class": "profile-badge-food", "amount": "₹1,240.00"},
    {"date": "Jul 25, 2026", "description": "Uber ride to office", "category": "Transport", "category_class": "profile-badge-transport", "amount": "₹350.00"},
    {"date": "Jul 20, 2026", "description": "Electricity bill", "category": "Bills", "category_class": "profile-badge-bills", "amount": "₹2,150.00"},
    {"date": "Jul 18, 2026", "description": "Movie night", "category": "Entertainment", "category_class": "profile-badge-entertainment", "amount": "₹680.00"},
    {"date": "Jul 12, 2026", "description": "Pharmacy purchase", "category": "Health", "category_class": "profile-badge-health", "amount": "₹920.00"},
]

PROFILE_CATEGORIES = [
    {"name": "Food", "amount": "₹6,384", "bar_class": "profile-bar-w-35", "color_class": "profile-progress-bar-food"},
    {"name": "Bills", "amount": "₹4,560", "bar_class": "profile-bar-w-25", "color_class": "profile-progress-bar-bills"},
    {"name": "Transport", "amount": "₹3,648", "bar_class": "profile-bar-w-20", "color_class": "profile-progress-bar-transport"},
    {"name": "Entertainment", "amount": "₹1,824", "bar_class": "profile-bar-w-10", "color_class": "profile-progress-bar-entertainment"},
    {"name": "Health", "amount": "₹1,824", "bar_class": "profile-bar-w-10", "color_class": "profile-progress-bar-health"},
]


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template(
        "profile.html",
        user=PROFILE_USER,
        stats=PROFILE_STATS,
        transactions=PROFILE_TRANSACTIONS,
        categories=PROFILE_CATEGORIES,
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
