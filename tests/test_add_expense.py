"""Tests for Step 7: Add Expense (GET/POST /expenses/add).

Spec: .claude/specs/07-add-expense.md

These tests are written strictly from that spec's contract, not from reading
app.py's route-handling implementation:
  - GET /expenses/add renders a form (amount, category select with the 7
    fixed categories, date, optional description) — logged-in only.
  - POST /expenses/add validates the submitted fields and, on success,
    inserts a new row via database.queries.insert_expense and redirects to
    /profile. On any validation failure it re-renders the form (200) with an
    error message and does not touch the database.
  - Validation rules: amount must parse as a positive float > 0; category
    must be one of the 7 fixed values; date must be a valid YYYY-MM-DD date;
    description is optional and stored as NULL when blank.

Field names (amount, category, date, description) and the error-message
container (`class="auth-error"`, from `templates/add_expense.html`'s flash
block) are structural landmarks taken directly from the template markup
created for this step — not from app.py's validation logic — mirroring the
regex-based landmark approach already used in
tests/test_06-date-filter-profile-page.py.

All DB access goes through a per-test temp sqlite file (see
tests/conftest.py) — the real expense_tracker.db is never touched.
"""

import re

import pytest

from database.db import get_db
from database.queries import insert_expense as insert_expense_query


# --------------------------------------------------------------------- #
# HTML-parsing helpers
# --------------------------------------------------------------------- #

FIXED_CATEGORIES = (
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
)


def _category_select_block(body):
    """Return the inner HTML of the <select id="category" ...> element."""
    match = re.search(
        r'<select[^>]*id="category"[^>]*>(.*?)</select>', body, re.DOTALL
    )
    assert match, "Could not locate the category <select> element in response body"
    return match.group(1)


def _form_has_post_method(body):
    return re.search(r'<form[^>]*method="post"', body, re.IGNORECASE) is not None


def _has_error_message(body):
    """The add_expense.html flash block renders errors as `class="auth-error"`."""
    return "auth-error" in body


# --------------------------------------------------------------------- #
# DB helpers (raw, parameterized SQL only)
# --------------------------------------------------------------------- #

def _count_expenses(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def _fetch_expense_by_description(user_id, description):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND description = ?",
            (user_id, description),
        ).fetchone()
    finally:
        conn.close()


def _fetch_latest_expense(user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


VALID_PAYLOAD = {
    "amount": "50.0",
    "category": "Food",
    "date": "2026-03-20",
    "description": "Lunch",
}


# --------------------------------------------------------------------- #
# Unit tests: database.queries.insert_expense
# --------------------------------------------------------------------- #

class TestInsertExpenseQueryHelper:
    def test_insert_expense_valid_data_creates_row(self, seed_user_id):
        insert_expense_query(seed_user_id, 50.0, "Food", "2026-03-20", "Lunch")

        row = _fetch_expense_by_description(seed_user_id, "Lunch")
        assert row is not None, "Expected the new expense row to exist after insert_expense()"
        assert row["user_id"] == seed_user_id
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_insert_expense_with_description_none_stores_null(self, seed_user_id):
        insert_expense_query(seed_user_id, 12.5, "Transport", "2026-03-21", None)

        row = _fetch_latest_expense(seed_user_id)
        assert row is not None
        assert row["amount"] == 12.5
        assert row["category"] == "Transport"
        assert row["date"] == "2026-03-21"
        assert row["description"] is None, "description must be stored as NULL, not empty string"


# --------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------- #

class TestAddExpenseAuthGuard:
    def test_get_add_expense_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_add_expense_unauthenticated_redirects_to_login(self, client):
        response = client.post("/expenses/add", data=VALID_PAYLOAD)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_add_expense_unauthenticated_does_not_insert_row(self, client):
        client.post("/expenses/add", data=VALID_PAYLOAD)
        # No user is logged in, so there is nothing meaningful to look up by
        # user_id; instead assert the table stays empty for a fresh temp DB
        # aside from any seed data (seed_db() runs against the demo user
        # only, and this request carried no session, so no additional row
        # should exist anywhere).
        conn = get_db()
        try:
            total = conn.execute(
                "SELECT COUNT(*) AS cnt FROM expenses WHERE description = ?",
                ("Lunch",),
            ).fetchone()["cnt"]
        finally:
            conn.close()
        assert total == 0, "Unauthenticated POST must not insert any expense row"


# --------------------------------------------------------------------- #
# GET /expenses/add — authenticated
# --------------------------------------------------------------------- #

class TestAddExpenseGet:
    def test_get_add_expense_authenticated_returns_200(self, auth_client):
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200

    def test_get_add_expense_category_select_has_all_seven_options(self, auth_client):
        body = auth_client.get("/expenses/add").data.decode("utf-8")
        select_html = _category_select_block(body)
        for category in FIXED_CATEGORIES:
            assert f">{category}<" in select_html, (
                f"Expected category option {category!r} inside the category <select>"
            )

    def test_get_add_expense_form_uses_post_method(self, auth_client):
        body = auth_client.get("/expenses/add").data.decode("utf-8")
        assert "<form" in body, "Expected a <form> element on the add-expense page"
        assert _form_has_post_method(body), "Expected the add-expense form to use method POST"


# --------------------------------------------------------------------- #
# POST /expenses/add — authenticated, valid data
# --------------------------------------------------------------------- #

class TestAddExpensePostValid:
    def test_post_valid_data_redirects_to_profile(self, auth_client):
        response = auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_valid_data_inserts_row_for_user(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        auth_client.post("/expenses/add", data=VALID_PAYLOAD, follow_redirects=False)
        after = _count_expenses(seed_user_id)
        assert after == before + 1, "Expected exactly one new expense row after a valid POST"

        row = _fetch_expense_by_description(seed_user_id, "Lunch")
        assert row is not None
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"

    def test_post_no_description_redirects_and_stores_null(self, auth_client, seed_user_id):
        payload = {
            "amount": "15.75",
            "category": "Shopping",
            "date": "2026-04-01",
            "description": "",
        }
        response = auth_client.post("/expenses/add", data=payload, follow_redirects=False)
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        row = _fetch_latest_expense(seed_user_id)
        assert row["amount"] == 15.75
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-04-01"
        assert row["description"] is None, "Blank description must be stored as NULL"


# --------------------------------------------------------------------- #
# POST /expenses/add — authenticated, validation failures
# --------------------------------------------------------------------- #

class TestAddExpensePostValidation:
    def test_post_missing_amount_returns_200_with_error(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        payload = {**VALID_PAYLOAD, "amount": "", "description": "MissingAmount"}
        response = auth_client.post("/expenses/add", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is missing"
        assert _count_expenses(seed_user_id) == before, "No row should be inserted on validation failure"

    def test_post_zero_amount_returns_200_with_error(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        payload = {**VALID_PAYLOAD, "amount": "0", "description": "ZeroAmount"}
        response = auth_client.post("/expenses/add", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is zero"
        assert _count_expenses(seed_user_id) == before

    def test_post_negative_amount_returns_200_with_error(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        payload = {**VALID_PAYLOAD, "amount": "-10", "description": "NegativeAmount"}
        response = auth_client.post("/expenses/add", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is negative"
        assert _count_expenses(seed_user_id) == before

    def test_post_non_numeric_amount_returns_200_with_error(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        payload = {**VALID_PAYLOAD, "amount": "not-a-number", "description": "NonNumericAmount"}
        response = auth_client.post("/expenses/add", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is non-numeric"
        assert _count_expenses(seed_user_id) == before

    def test_post_invalid_category_returns_200_with_error(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        payload = {**VALID_PAYLOAD, "category": "NotARealCategory", "description": "InvalidCategory"}
        response = auth_client.post("/expenses/add", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message for an invalid category"
        assert _count_expenses(seed_user_id) == before

    def test_post_invalid_date_returns_200_with_error(self, auth_client, seed_user_id):
        before = _count_expenses(seed_user_id)
        payload = {**VALID_PAYLOAD, "date": "not-a-date", "description": "InvalidDate"}
        response = auth_client.post("/expenses/add", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message for a malformed date"
        assert _count_expenses(seed_user_id) == before
