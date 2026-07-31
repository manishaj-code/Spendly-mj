"""Tests for the /profile backend: query helpers in database/queries.py and
the Flask /profile route in app.py.

All DB access in these tests goes through a per-test temp sqlite file (see
tests/conftest.py) — the real expense_tracker.db is never touched.
"""

from datetime import datetime

from database.db import create_user, get_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


# --------------------------------------------------------------------- #
# get_user_by_id
# --------------------------------------------------------------------- #

def test_get_user_by_id_valid(seed_user_id):
    user = get_user_by_id(seed_user_id)
    assert user is not None
    assert user["name"] == "Demo User"
    assert user["email"] == "demo@spendly.com"
    # created_at is stamped with datetime('now') at seed time, so member_since
    # should match "%B %Y" for the current moment.
    assert user["member_since"] == datetime.now().strftime("%B %Y")


def test_get_user_by_id_nonexistent(temp_db):
    assert get_user_by_id(999999) is None


# --------------------------------------------------------------------- #
# get_summary_stats
# --------------------------------------------------------------------- #

def test_get_summary_stats_seed_user(seed_user_id):
    stats = get_summary_stats(seed_user_id)
    assert stats["total_spent"] == 286.45
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_empty_user(empty_user_id):
    stats = get_summary_stats(empty_user_id)
    assert stats["total_spent"] == 0
    assert stats["transaction_count"] == 0
    assert stats["top_category"] == "—"  # em dash


# --------------------------------------------------------------------- #
# get_recent_transactions
# --------------------------------------------------------------------- #

def test_get_recent_transactions_seed_user(seed_user_id):
    txns = get_recent_transactions(seed_user_id)
    assert len(txns) == 8

    for t in txns:
        assert set(t.keys()) == {"date", "description", "category", "amount"}

    # Newest first: the last-seeded expense (Jul 25, "Restaurant dinner")
    # should come before the first-seeded one (Jul 02, "Groceries").
    assert txns[0]["description"] == "Restaurant dinner"
    assert txns[-1]["description"] == "Groceries"

    parsed_dates = [datetime.strptime(t["date"], "%b %d, %Y") for t in txns]
    assert parsed_dates == sorted(parsed_dates, reverse=True)


def test_get_recent_transactions_empty_user(empty_user_id):
    assert get_recent_transactions(empty_user_id) == []


# --------------------------------------------------------------------- #
# get_category_breakdown
# --------------------------------------------------------------------- #

def test_get_category_breakdown_seed_user(seed_user_id):
    breakdown = get_category_breakdown(seed_user_id)

    names = [c["name"] for c in breakdown]
    assert set(names) == {
        "Food", "Transport", "Bills", "Health",
        "Entertainment", "Shopping", "Other",
    }
    assert len(breakdown) == 7

    amounts = [c["amount"] for c in breakdown]
    assert amounts == sorted(amounts, reverse=True)
    assert breakdown[0]["name"] == "Bills"
    assert breakdown[0]["amount"] == 85.00

    pcts = [c["pct"] for c in breakdown]
    assert all(isinstance(p, int) for p in pcts)
    assert sum(pcts) == 100


def test_get_category_breakdown_empty_user(empty_user_id):
    assert get_category_breakdown(empty_user_id) == []


def test_get_category_breakdown_remainder_adjustment(temp_db):
    """Three equal categories (33.33% each, rounding to 33/33/33 = 99) must
    exercise the remainder-adjustment branch so the pcts still sum to 100.
    """
    user_id = create_user("Remainder Tester", "remainder@example.com", "pw123456")

    conn = get_db()
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (user_id, 10.00, "Food", "2026-01-01", "a"),
            (user_id, 10.00, "Transport", "2026-01-02", "b"),
            (user_id, 10.00, "Bills", "2026-01-03", "c"),
        ],
    )
    conn.commit()
    conn.close()

    breakdown = get_category_breakdown(user_id)
    assert len(breakdown) == 3
    assert sum(c["pct"] for c in breakdown) == 100


# --------------------------------------------------------------------- #
# Route: GET /profile
# --------------------------------------------------------------------- #

def test_profile_unauthenticated_redirects_to_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_profile_authenticated_seed_user(client):
    login_response = client.post(
        "/login",
        data={"email": "demo@spendly.com", "password": "demo123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.data.decode("utf-8")

    assert "Demo User" in body
    assert "demo@spendly.com" in body
    assert "₹286.45" in body  # ₹286.45
    assert "Bills" in body

    for category in (
        "Food", "Transport", "Bills", "Health",
        "Entertainment", "Shopping", "Other",
    ):
        assert category in body

    # Newest-first ordering: "Restaurant dinner" (Jul 25) should render
    # before "Groceries" (Jul 02) in the transactions table.
    assert body.index("Restaurant dinner") < body.index("Groceries")


def test_profile_authenticated_new_user_has_no_expenses(client):
    register_response = client.post(
        "/register",
        data={
            "name": "Brand New",
            "email": "brandnew@example.com",
            "password": "pw123456",
            "confirm_password": "pw123456",
        },
        follow_redirects=False,
    )
    assert register_response.status_code == 302

    login_response = client.post(
        "/login",
        data={"email": "brandnew@example.com", "password": "pw123456"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    response = client.get("/profile")
    assert response.status_code == 200

    body = response.data.decode("utf-8")

    assert "₹0.00" in body  # ₹0.00
    assert "Traceback" not in body
    assert "Error" not in body
    assert "profile-progress-row" not in body
    assert "profile-badge " not in body
