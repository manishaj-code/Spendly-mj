"""Tests for Step 9: Delete Expense (POST /expenses/<id>/delete).

Spec: .claude/specs/09-delete-expense.md

These tests are written strictly from that spec's contract, not from reading
app.py's route-handling implementation:
  - POST /expenses/<id>/delete verifies ownership via
    database.queries.get_expense_by_id (scoped to id AND user_id), then
    deletes the row via database.queries.delete_expense and redirects to
    /profile — logged-in only. If the expense does not exist, or exists but
    belongs to a different user, the route returns 404 without mutating the
    database.
  - The route only accepts POST — a bare GET must return 405 (Flask's
    native behavior when a route declares methods=["POST"] only).
  - Unauthenticated access redirects to /login (302).

All DB access goes through a per-test temp sqlite file (see
tests/conftest.py) — the real expense_tracker.db is never touched.
"""

from database.db import get_db
from database.queries import delete_expense


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


# --------------------------------------------------------------------- #
# Unit tests: database.queries.delete_expense
# --------------------------------------------------------------------- #

class TestDeleteExpenseQueryHelper:
    def test_delete_expense_valid_owner_removes_row(self, seed_user_id, insert_expense):
        insert_expense(seed_user_id, 30.0, "Food", "2026-02-01", "ToDelete")
        seeded = _fetch_expense_by_description(seed_user_id, "ToDelete")

        delete_expense(seeded["id"], seed_user_id)

        assert _fetch_expense_by_id(seeded["id"]) is None, "Expected the row to be removed"

    def test_delete_expense_wrong_user_leaves_row_intact_no_exception(
        self, seed_user_id, empty_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 30.0, "Food", "2026-02-01", "NotYoursToDelete")
        seeded = _fetch_expense_by_description(seed_user_id, "NotYoursToDelete")

        # Attempting to delete as the wrong user must not raise, and must
        # not remove the row (0 rows affected due to the user_id guard).
        delete_expense(seeded["id"], empty_user_id)

        row = _fetch_expense_by_id(seeded["id"])
        assert row is not None, "Expected the row to remain when deleted by the wrong user"
        assert row["amount"] == 30.0
        assert row["category"] == "Food"
        assert row["description"] == "NotYoursToDelete"

    def test_delete_expense_nonexistent_id_no_error_db_unchanged(
        self, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 30.0, "Food", "2026-02-01", "UnaffectedByNonexistentDelete")
        seeded = _fetch_expense_by_description(seed_user_id, "UnaffectedByNonexistentDelete")

        delete_expense(9999999, seed_user_id)

        row = _fetch_expense_by_id(seeded["id"])
        assert row is not None, "Deleting a non-existent id must not affect unrelated rows"


# --------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------- #

class TestDeleteExpenseAuthGuard:
    def test_post_delete_expense_unauthenticated_redirects_to_login(
        self, client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 20.0, "Food", "2026-02-01", "AuthGuardDelete")
        seeded = _fetch_expense_by_description(seed_user_id, "AuthGuardDelete")

        response = client.post(f"/expenses/{seeded['id']}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

        assert _fetch_expense_by_id(seeded["id"]) is not None, (
            "Row must not be deleted when the request is unauthenticated"
        )


# --------------------------------------------------------------------- #
# Not found / ownership enforcement
# --------------------------------------------------------------------- #

class TestDeleteExpenseNotFoundOrOwnership:
    def test_post_delete_nonexistent_expense_returns_404(self, auth_client):
        response = auth_client.post("/expenses/9999999/delete")
        assert response.status_code == 404

    def test_post_delete_other_users_expense_returns_404_and_does_not_mutate(
        self, auth_client, empty_user_id, insert_expense
    ):
        insert_expense(empty_user_id, 45.0, "Shopping", "2026-03-10", "NotYourExpenseDelete")
        seeded = _fetch_expense_by_description(empty_user_id, "NotYourExpenseDelete")

        response = auth_client.post(f"/expenses/{seeded['id']}/delete")
        assert response.status_code == 404

        row = _fetch_expense_by_id(seeded["id"])
        assert row is not None, "Row must still exist after a 404 delete attempt"
        assert row["amount"] == 45.0
        assert row["category"] == "Shopping"
        assert row["description"] == "NotYourExpenseDelete"


# --------------------------------------------------------------------- #
# POST /expenses/<id>/delete — authenticated, valid
# --------------------------------------------------------------------- #

class TestDeleteExpensePostValid:
    def test_post_delete_own_expense_redirects_to_profile_and_removes_row(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 10.0, "Food", "2026-01-01", "OwnedExpenseToDelete")
        seeded = _fetch_expense_by_description(seed_user_id, "OwnedExpenseToDelete")

        response = auth_client.post(
            f"/expenses/{seeded['id']}/delete", follow_redirects=False
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]
        assert _fetch_expense_by_id(seeded["id"]) is None, "Expected the row to be removed"


# --------------------------------------------------------------------- #
# GET /expenses/<id>/delete — method not allowed
# --------------------------------------------------------------------- #

class TestDeleteExpenseMethodNotAllowed:
    def test_get_delete_expense_unauthenticated_returns_405(
        self, client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 20.0, "Food", "2026-02-01", "MethodCheckUnauth")
        seeded = _fetch_expense_by_description(seed_user_id, "MethodCheckUnauth")

        response = client.get(f"/expenses/{seeded['id']}/delete")
        assert response.status_code == 405

    def test_get_delete_expense_authenticated_returns_405(
        self, auth_client, seed_user_id, insert_expense
    ):
        insert_expense(seed_user_id, 20.0, "Food", "2026-02-01", "MethodCheckAuth")
        seeded = _fetch_expense_by_description(seed_user_id, "MethodCheckAuth")

        response = auth_client.get(f"/expenses/{seeded['id']}/delete")
        assert response.status_code == 405
