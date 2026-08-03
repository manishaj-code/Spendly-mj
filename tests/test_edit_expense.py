"""Tests for Step 8: Edit Expense (GET/POST /expenses/<id>/edit).

Spec: .claude/specs/08-edit-expense.md

These tests are written strictly from that spec's contract, not from reading
app.py's route-handling implementation:
  - GET /expenses/<id>/edit loads the expense via
    database.queries.get_expense_by_id (scoped to id AND user_id) and renders
    a form pre-filled with its current amount, category, date, and
    description — logged-in only. If the expense does not exist, or exists
    but belongs to a different user, the route returns 404.
  - POST /expenses/<id>/edit validates the submitted fields (identical rules
    to add expense) and, on success, calls database.queries.update_expense
    and redirects to /profile. On any validation failure it re-renders the
    form (200) with an error message and does not mutate the database. A
    POST to another user's expense returns 404 without mutating the row.
  - Validation rules: amount must parse as a positive float > 0; category
    must be one of the 7 fixed values; date must be a valid YYYY-MM-DD date;
    description is optional and stored as NULL when blank.

Field names (amount, category, date, description) and the error-message
container (`class="auth-error"`, from `templates/edit_expense.html`'s flash
block) are structural landmarks taken directly from the template markup
created for this step — not from app.py's validation logic — mirroring the
regex-based landmark approach already used in tests/test_add_expense.py.

All DB access goes through a per-test temp sqlite file (see
tests/conftest.py) — the real expense_tracker.db is never touched.
"""

import re

import pytest

from database.db import get_db
from database.queries import get_expense_by_id, update_expense


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


def _selected_option(select_html, category):
    """Return the <option> tag for a given category, or None if not present."""
    match = re.search(
        rf'<option[^>]*value="{re.escape(category)}"[^>]*>', select_html
    )
    return match.group(0) if match else None


def _form_has_post_method(body):
    return re.search(r'<form[^>]*method="post"', body, re.IGNORECASE) is not None


def _has_error_message(body):
    """The edit_expense.html flash block renders errors as `class="auth-error"`."""
    return "auth-error" in body


# --------------------------------------------------------------------- #
# DB helpers (raw, parameterized SQL only)
# --------------------------------------------------------------------- #

def _fetch_expense_by_description(user_id, description):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND description = ?",
            (user_id, description),
        ).fetchone()
    finally:
        conn.close()


def _fetch_expense_by_id(expense_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


VALID_PAYLOAD = {
    "amount": "75.0",
    "category": "Bills",
    "date": "2026-04-15",
    "description": "Updated Bill",
}


# --------------------------------------------------------------------- #
# Unit tests: database.queries.get_expense_by_id
# --------------------------------------------------------------------- #

class TestGetExpenseByIdQueryHelper:
    def test_get_expense_by_id_valid_owner_returns_row(self, seed_user_id, insert_expense):
        insert_expense(seed_user_id, 30.0, "Food", "2026-02-01", "OwnerLookup")
        seeded = _fetch_expense_by_description(seed_user_id, "OwnerLookup")

        row = get_expense_by_id(seeded["id"], seed_user_id)

        assert row is not None, "Expected a matching row for the correct owner"
        assert row["id"] == seeded["id"]
        assert row["amount"] == 30.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-02-01"
        assert row["description"] == "OwnerLookup"

    def test_get_expense_by_id_wrong_user_returns_none(
        self, seed_user_id, empty_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 30.0, "Food", "2026-02-01", "WrongUserLookup")
        seeded = _fetch_expense_by_description(seed_user_id, "WrongUserLookup")

        row = get_expense_by_id(seeded["id"], empty_user_id)

        assert row is None, "Expected None when the expense belongs to a different user"

    def test_get_expense_by_id_nonexistent_id_returns_none(self, seed_user_id):
        row = get_expense_by_id(9999999, seed_user_id)
        assert row is None, "Expected None for a non-existent expense id"


# --------------------------------------------------------------------- #
# Unit tests: database.queries.update_expense
# --------------------------------------------------------------------- #

class TestUpdateExpenseQueryHelper:
    def test_update_expense_valid_owner_persists_changes(self, seed_user_id, insert_expense):
        insert_expense(seed_user_id, 10.0, "Food", "2026-02-01", "ToUpdate")
        seeded = _fetch_expense_by_description(seed_user_id, "ToUpdate")

        update_expense(
            seeded["id"], seed_user_id, 99.0, "Health", "2026-05-05", "UpdatedDescription"
        )

        row = _fetch_expense_by_id(seeded["id"])
        assert row["amount"] == 99.0
        assert row["category"] == "Health"
        assert row["date"] == "2026-05-05"
        assert row["description"] == "UpdatedDescription"

    def test_update_expense_wrong_user_leaves_row_unchanged_no_exception(
        self, seed_user_id, empty_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 10.0, "Food", "2026-02-01", "NotYours")
        seeded = _fetch_expense_by_description(seed_user_id, "NotYours")

        # Attempting to update as the wrong user must not raise, and must
        # not mutate the row (0 rows affected due to the user_id guard).
        update_expense(seeded["id"], empty_user_id, 999.0, "Other", "2026-06-06", "Hacked")

        row = _fetch_expense_by_id(seeded["id"])
        assert row["amount"] == 10.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-02-01"
        assert row["description"] == "NotYours"


# --------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------- #

class TestEditExpenseAuthGuard:
    def test_get_edit_expense_unauthenticated_redirects_to_login(
        self, client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 20.0, "Food", "2026-02-01", "AuthGuardGet")
        seeded = _fetch_expense_by_description(seed_user_id, "AuthGuardGet")

        response = client.get(f"/expenses/{seeded['id']}/edit")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_post_edit_expense_unauthenticated_redirects_to_login(
        self, client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 20.0, "Food", "2026-02-01", "AuthGuardPost")
        seeded = _fetch_expense_by_description(seed_user_id, "AuthGuardPost")

        response = client.post(f"/expenses/{seeded['id']}/edit", data=VALID_PAYLOAD)
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# Not found / ownership enforcement
# --------------------------------------------------------------------- #

class TestEditExpenseNotFoundOrOwnership:
    def test_get_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.get("/expenses/9999999/edit")
        assert response.status_code == 404

    def test_get_other_users_expense_returns_404(
        self, auth_client, empty_user_id, insert_expense
    ):
        insert_expense(empty_user_id, 45.0, "Shopping", "2026-03-10", "NotYourExpenseGet")
        seeded = _fetch_expense_by_description(empty_user_id, "NotYourExpenseGet")

        response = auth_client.get(f"/expenses/{seeded['id']}/edit")
        assert response.status_code == 404

    def test_post_other_users_expense_returns_404_and_does_not_mutate(
        self, auth_client, empty_user_id, insert_expense
    ):
        insert_expense(empty_user_id, 45.0, "Shopping", "2026-03-10", "NotYourExpensePost")
        seeded = _fetch_expense_by_description(empty_user_id, "NotYourExpensePost")

        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=VALID_PAYLOAD)
        assert response.status_code == 404

        row = _fetch_expense_by_id(seeded["id"])
        assert row["amount"] == 45.0
        assert row["category"] == "Shopping"
        assert row["date"] == "2026-03-10"
        assert row["description"] == "NotYourExpensePost"


# --------------------------------------------------------------------- #
# GET /expenses/<id>/edit — authenticated, owned expense
# --------------------------------------------------------------------- #

class TestEditExpenseGet:
    def test_get_edit_expense_owned_returns_200(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 60.0, "Entertainment", "2026-01-15", "GetOwned200")
        seeded = _fetch_expense_by_description(seed_user_id, "GetOwned200")

        response = auth_client.get(f"/expenses/{seeded['id']}/edit")
        assert response.status_code == 200

    def test_get_edit_expense_prefills_amount_date_description(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 60.5, "Entertainment", "2026-01-15", "PrefilledFields")
        seeded = _fetch_expense_by_description(seed_user_id, "PrefilledFields")

        body = auth_client.get(f"/expenses/{seeded['id']}/edit").data.decode("utf-8")

        assert "60.5" in body, "Expected the current amount to be pre-filled in the form"
        assert "2026-01-15" in body, "Expected the current date to be pre-filled in the form"
        assert "PrefilledFields" in body, "Expected the current description to be pre-filled in the form"

    def test_get_edit_expense_category_option_is_selected(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 60.0, "Entertainment", "2026-01-15", "SelectedCategory")
        seeded = _fetch_expense_by_description(seed_user_id, "SelectedCategory")

        body = auth_client.get(f"/expenses/{seeded['id']}/edit").data.decode("utf-8")
        select_html = _category_select_block(body)

        option_tag = _selected_option(select_html, "Entertainment")
        assert option_tag is not None, "Expected an <option> for the current category (Entertainment)"
        assert "selected" in option_tag, (
            f"Expected the current category's <option> to be marked selected, got: {option_tag!r}"
        )

        # Sanity: all 7 fixed categories should still be present as options.
        for category in FIXED_CATEGORIES:
            assert f">{category}<" in select_html, (
                f"Expected category option {category!r} inside the category <select>"
            )

    def test_get_edit_expense_form_uses_post_method(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 60.0, "Entertainment", "2026-01-15", "FormMethodCheck")
        seeded = _fetch_expense_by_description(seed_user_id, "FormMethodCheck")

        body = auth_client.get(f"/expenses/{seeded['id']}/edit").data.decode("utf-8")
        assert "<form" in body, "Expected a <form> element on the edit-expense page"
        assert _form_has_post_method(body), "Expected the edit-expense form to use method POST"


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — authenticated, valid data
# --------------------------------------------------------------------- #

class TestEditExpensePostValid:
    def test_post_valid_data_redirects_to_profile_and_updates_db(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 10.0, "Food", "2026-01-01", "BeforeUpdate")
        seeded = _fetch_expense_by_description(seed_user_id, "BeforeUpdate")

        response = auth_client.post(
            f"/expenses/{seeded['id']}/edit", data=VALID_PAYLOAD, follow_redirects=False
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        row = _fetch_expense_by_id(seeded["id"])
        assert row["amount"] == 75.0
        assert row["category"] == "Bills"
        assert row["date"] == "2026-04-15"
        assert row["description"] == "Updated Bill"

    def test_post_no_description_redirects_and_stores_null(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 10.0, "Food", "2026-01-01", "BeforeNullDescription")
        seeded = _fetch_expense_by_description(seed_user_id, "BeforeNullDescription")

        payload = {**VALID_PAYLOAD, "description": ""}
        response = auth_client.post(
            f"/expenses/{seeded['id']}/edit", data=payload, follow_redirects=False
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        row = _fetch_expense_by_id(seeded["id"])
        assert row["amount"] == 75.0
        assert row["category"] == "Bills"
        assert row["date"] == "2026-04-15"
        assert row["description"] is None, "Blank description must be stored as NULL"


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — authenticated, validation failures
# --------------------------------------------------------------------- #

class TestEditExpensePostValidation:
    def _seed_and_get(self, seed_user_id, insert_expense, description):
        insert_expense(seed_user_id, 22.0, "Food", "2026-01-10", description)
        return _fetch_expense_by_description(seed_user_id, description)

    def test_post_missing_amount_returns_200_with_error_and_row_unchanged(
        self, auth_client, seed_user_id, insert_expense
    ):
        seeded = self._seed_and_get(seed_user_id, insert_expense, "ValidationMissingAmount")
        before = _fetch_expense_by_id(seeded["id"])

        payload = {**VALID_PAYLOAD, "amount": ""}
        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is missing"

        after = _fetch_expense_by_id(seeded["id"])
        assert dict(after) == dict(before), "Row must be unchanged after a failed validation POST"

    def test_post_zero_amount_returns_200_with_error_and_row_unchanged(
        self, auth_client, seed_user_id, insert_expense
    ):
        seeded = self._seed_and_get(seed_user_id, insert_expense, "ValidationZeroAmount")
        before = _fetch_expense_by_id(seeded["id"])

        payload = {**VALID_PAYLOAD, "amount": "0"}
        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is zero"

        after = _fetch_expense_by_id(seeded["id"])
        assert dict(after) == dict(before)

    def test_post_negative_amount_returns_200_with_error_and_row_unchanged(
        self, auth_client, seed_user_id, insert_expense
    ):
        seeded = self._seed_and_get(seed_user_id, insert_expense, "ValidationNegativeAmount")
        before = _fetch_expense_by_id(seeded["id"])

        payload = {**VALID_PAYLOAD, "amount": "-10"}
        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is negative"

        after = _fetch_expense_by_id(seeded["id"])
        assert dict(after) == dict(before)

    def test_post_non_numeric_amount_returns_200_with_error_and_row_unchanged(
        self, auth_client, seed_user_id, insert_expense
    ):
        seeded = self._seed_and_get(seed_user_id, insert_expense, "ValidationNonNumericAmount")
        before = _fetch_expense_by_id(seeded["id"])

        payload = {**VALID_PAYLOAD, "amount": "not-a-number"}
        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message when amount is non-numeric"

        after = _fetch_expense_by_id(seeded["id"])
        assert dict(after) == dict(before)

    def test_post_invalid_category_returns_200_with_error_and_row_unchanged(
        self, auth_client, seed_user_id, insert_expense
    ):
        seeded = self._seed_and_get(seed_user_id, insert_expense, "ValidationInvalidCategory")
        before = _fetch_expense_by_id(seeded["id"])

        payload = {**VALID_PAYLOAD, "category": "NotARealCategory"}
        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message for an invalid category"

        after = _fetch_expense_by_id(seeded["id"])
        assert dict(after) == dict(before)

    def test_post_invalid_date_returns_200_with_error_and_row_unchanged(
        self, auth_client, seed_user_id, insert_expense
    ):
        seeded = self._seed_and_get(seed_user_id, insert_expense, "ValidationInvalidDate")
        before = _fetch_expense_by_id(seeded["id"])

        payload = {**VALID_PAYLOAD, "date": "not-a-date"}
        response = auth_client.post(f"/expenses/{seeded['id']}/edit", data=payload)

        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert _has_error_message(body), "Expected an error message for a malformed date"

        after = _fetch_expense_by_id(seeded["id"])
        assert dict(after) == dict(before)
