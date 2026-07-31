"""Tests for Step 6: the date-range filter on GET /profile.

Spec: .claude/specs/06-date-filter-profile-page.md

These tests are written strictly from that spec's contract, not from reading
app.py's or database/queries.py's implementations:
  - GET /profile reads optional `date_from` / `date_to` (YYYY-MM-DD) query
    params, inclusive bounds, and applies them to all three data sections
    (summary stats, recent transactions, category breakdown).
  - Four quick-select presets ("This Month", "Last 3 Months",
    "Last 6 Months", "All Time") are rendered as links; the active preset
    (or the custom range) is visually highlighted.
  - Missing/malformed params, or date_from > date_to, silently fall back to
    the unfiltered ("All Time") view; the date_from > date_to case also
    flashes "Start date must be before end date."
  - The "All Time" preset must produce a clean /profile URL (no query
    params).

All DB access goes through a per-test temp sqlite file (see
tests/conftest.py) — the real expense_tracker.db is never touched.

Boundary-testing note: rather than re-deriving app.py's exact month-shift
arithmetic for "Last 3 Months" / "Last 6 Months", these tests seed expenses
at deliberately unambiguous relative offsets (60 / 150 / 400 days before
"today") so preset inclusion/exclusion can be asserted regardless of exactly
how the boundary is computed (calendar months vs. day counts).
"""

import html as html_lib
import re
from datetime import date, timedelta

import pytest

from database.db import create_user
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)


# --------------------------------------------------------------------- #
# HTML-parsing helpers (regex-based, scoped to the profile.html markup
# described in the spec's Templates section)
# --------------------------------------------------------------------- #

PRESET_LINK_RE = re.compile(
    r'<a\s+href="([^"]*)"\s+class="([^"]*)">\s*([^<]*?)\s*</a>'
)


def _preset_links(body):
    """Map preset label -> {"href": unescaped href, "active": bool}.

    Only anchors carrying the profile-filter-preset class are matched, so
    nav-bar / footer links (which lack that class, or contain nested tags)
    are excluded automatically.
    """
    links = {}
    for href, class_attr, label in PRESET_LINK_RE.findall(body):
        if "profile-filter-preset" not in class_attr:
            continue
        links[label.strip()] = {
            "href": html_lib.unescape(href),
            "active": "profile-filter-preset-active" in class_attr,
        }
    return links


def _stat_value(body, label):
    """Extract the rendered value of a profile-stat by its label text."""
    pattern = (
        r'profile-stat-label">' + re.escape(label)
        + r'</span>\s*<span class="profile-stat-value">([^<]*)</span>'
    )
    match = re.search(pattern, body)
    assert match, f"Could not locate stat value for label {label!r} in response body"
    return match.group(1).strip()


def _input_value(body, field_id):
    """Extract the value="" attribute of the date_from / date_to inputs."""
    pattern = r'id="' + re.escape(field_id) + r'"[^>]*value="([^"]*)"'
    match = re.search(pattern, body)
    assert match, f"Could not locate input value for field {field_id!r} in response body"
    return match.group(1)


ALL_PRESET_LABELS = ("This Month", "Last 3 Months", "Last 6 Months", "All Time")


# --------------------------------------------------------------------- #
# Auth guard
# --------------------------------------------------------------------- #

class TestProfileDateFilterAuthGuard:
    def test_bare_profile_unauthenticated_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_profile_with_filter_params_unauthenticated_redirects_to_login(self, client):
        response = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert response.status_code == 302, "Filter query params must not bypass the auth guard"
        assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------- #
# Happy path: bare /profile == Step 5 baseline (unfiltered)
# --------------------------------------------------------------------- #

class TestProfileDateFilterBareRequest:
    def test_bare_profile_matches_unfiltered_step5_baseline(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert _stat_value(body, "Total Spent") == "₹286.45"
        assert _stat_value(body, "Transactions") == "8"
        assert _stat_value(body, "Top Category") == "Bills"

        for category in (
            "Food", "Transport", "Bills", "Health",
            "Entertainment", "Shopping", "Other",
        ):
            assert category in body

        # No filter supplied: custom-range inputs must be empty.
        assert _input_value(body, "date_from") == ""
        assert _input_value(body, "date_to") == ""

    def test_bare_profile_treats_all_time_as_the_active_preset(self, auth_client):
        """Per spec, an absent filter falls back to the 'All Time' (unfiltered)
        view, so the All Time preset should be the one visually highlighted.
        """
        body = auth_client.get("/profile").data.decode("utf-8")
        presets = _preset_links(body)

        assert presets["All Time"]["active"] is True
        for label in ("This Month", "Last 3 Months", "Last 6 Months"):
            assert presets[label]["active"] is False

    def test_all_time_preset_href_has_no_query_params(self, auth_client):
        body = auth_client.get("/profile").data.decode("utf-8")
        href = _preset_links(body)["All Time"]["href"]
        assert href == "/profile", "All Time preset must produce a clean /profile URL"
        assert "?" not in href


# --------------------------------------------------------------------- #
# Presets: This Month / Last 3 Months / Last 6 Months / All Time
# --------------------------------------------------------------------- #

class TestProfileDateFilterPresets:
    @pytest.fixture
    def boundary_expenses(self, empty_user_id, insert_expense):
        """Four expenses at deliberately unambiguous relative dates:
          - this_month: dated today            -> only inside "This Month" and wider windows
          - last_3:     60 days ago (< ~91d)    -> inside "Last 3 Months"
          - last_6:     150 days ago (>91,<181) -> outside 3mo, inside 6mo
          - outside:    400 days ago (>181d)    -> outside every preset but All Time
        """
        today = date.today()
        this_month = today.isoformat()
        last_3 = (today - timedelta(days=60)).isoformat()
        last_6 = (today - timedelta(days=150)).isoformat()
        outside = (today - timedelta(days=400)).isoformat()

        insert_expense(empty_user_id, 10.00, "Food", this_month, "ThisMonthExpense")
        insert_expense(empty_user_id, 20.00, "Transport", last_3, "Last3Expense")
        insert_expense(empty_user_id, 30.00, "Bills", last_6, "Last6Expense")
        insert_expense(empty_user_id, 40.00, "Health", outside, "OutsideExpense")
        return {"this_month": this_month, "last_3": last_3, "last_6": last_6, "outside": outside}

    @staticmethod
    def _follow_preset(client, label):
        bare_body = client.get("/profile").data.decode("utf-8")
        href = _preset_links(bare_body)[label]["href"]
        response = client.get(href)
        assert response.status_code == 200
        return response.data.decode("utf-8"), href

    def test_this_month_preset_shows_only_current_month_expenses(
        self, empty_user_client, boundary_expenses
    ):
        body, _ = self._follow_preset(empty_user_client, "This Month")
        assert "ThisMonthExpense" in body
        for absent in ("Last3Expense", "Last6Expense", "OutsideExpense"):
            assert absent not in body, f"{absent} must be excluded from This Month"

    def test_last_3_months_preset_includes_current_and_recent(
        self, empty_user_client, boundary_expenses
    ):
        body, _ = self._follow_preset(empty_user_client, "Last 3 Months")
        assert "ThisMonthExpense" in body
        assert "Last3Expense" in body
        for absent in ("Last6Expense", "OutsideExpense"):
            assert absent not in body, f"{absent} must be excluded from Last 3 Months"

    def test_last_6_months_preset_includes_up_to_150_days_ago(
        self, empty_user_client, boundary_expenses
    ):
        body, _ = self._follow_preset(empty_user_client, "Last 6 Months")
        for present in ("ThisMonthExpense", "Last3Expense", "Last6Expense"):
            assert present in body
        assert "OutsideExpense" not in body

    def test_all_time_preset_shows_every_expense(self, empty_user_client, boundary_expenses):
        body, href = self._follow_preset(empty_user_client, "All Time")
        for present in ("ThisMonthExpense", "Last3Expense", "Last6Expense", "OutsideExpense"):
            assert present in body
        assert href == "/profile"
        assert "?" not in href

    @pytest.mark.parametrize("label", ALL_PRESET_LABELS)
    def test_only_the_clicked_preset_is_marked_active(
        self, empty_user_client, boundary_expenses, label
    ):
        body, _ = self._follow_preset(empty_user_client, label)
        presets = _preset_links(body)
        assert presets[label]["active"] is True, f"{label} should be active on its own page"
        for other in set(ALL_PRESET_LABELS) - {label}:
            assert presets[other]["active"] is False, f"{other} must not be active while {label} is"


# --------------------------------------------------------------------- #
# Custom date range
# --------------------------------------------------------------------- #

class TestProfileDateFilterCustomRange:
    def test_custom_range_narrows_all_three_sections(
        self, empty_user_client, empty_user_id, insert_expense
    ):
        today = date.today()
        d_range_start = (today - timedelta(days=150)).isoformat()
        d_range_end = (today - timedelta(days=60)).isoformat()
        d_before_range = (today - timedelta(days=400)).isoformat()
        d_after_range = today.isoformat()

        insert_expense(empty_user_id, 30.00, "Bills", d_range_start, "InRangeStart")
        insert_expense(empty_user_id, 20.00, "Transport", d_range_end, "InRangeEnd")
        insert_expense(empty_user_id, 40.00, "Health", d_before_range, "BeforeRange")
        insert_expense(empty_user_id, 10.00, "Food", d_after_range, "AfterRange")

        response = empty_user_client.get(
            f"/profile?date_from={d_range_start}&date_to={d_range_end}"
        )
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert "InRangeStart" in body
        assert "InRangeEnd" in body
        assert "BeforeRange" not in body
        assert "AfterRange" not in body

        assert _stat_value(body, "Total Spent") == "₹50.00"
        assert _stat_value(body, "Transactions") == "2"

    def test_custom_range_inputs_retain_submitted_values(self, empty_user_client):
        response = empty_user_client.get("/profile?date_from=2020-06-01&date_to=2020-06-30")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert _input_value(body, "date_from") == "2020-06-01"
        assert _input_value(body, "date_to") == "2020-06-30"

    def test_custom_range_marks_custom_form_active_and_no_preset_active(self, empty_user_client):
        response = empty_user_client.get("/profile?date_from=2020-06-01&date_to=2020-06-30")
        body = response.data.decode("utf-8")

        assert "profile-filter-custom-active" in body

        presets = _preset_links(body)
        for label, info in presets.items():
            assert info["active"] is False, (
                f"{label} should not be active while a genuinely custom "
                "range is applied"
            )


# --------------------------------------------------------------------- #
# Validation: missing / malformed / inverted params fall back to unfiltered
# --------------------------------------------------------------------- #

class TestProfileDateFilterValidation:
    def test_date_from_after_date_to_falls_back_and_flashes_error(self, auth_client):
        response = auth_client.get("/profile?date_from=2026-08-01&date_to=2026-01-01")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert "Start date must be before end date." in body
        assert _stat_value(body, "Total Spent") == "₹286.45"
        assert _stat_value(body, "Transactions") == "8"

    def test_malformed_date_from_does_not_crash_and_falls_back_unfiltered(self, auth_client):
        response = auth_client.get("/profile?date_from=not-a-date&date_to=2026-01-01")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert "Traceback" not in body
        assert "Internal Server Error" not in body
        assert _stat_value(body, "Total Spent") == "₹286.45"
        assert _stat_value(body, "Transactions") == "8"

    def test_both_dates_malformed_falls_back_unfiltered(self, auth_client):
        response = auth_client.get("/profile?date_from=not-a-date&date_to=also-bad")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert "Traceback" not in body
        assert _stat_value(body, "Total Spent") == "₹286.45"

    def test_only_date_from_present_falls_back_unfiltered(self, auth_client):
        response = auth_client.get("/profile?date_from=2026-01-01")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert _stat_value(body, "Total Spent") == "₹286.45"
        assert _stat_value(body, "Transactions") == "8"

    def test_only_date_to_present_falls_back_unfiltered(self, auth_client):
        response = auth_client.get("/profile?date_to=2026-01-01")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert _stat_value(body, "Total Spent") == "₹286.45"
        assert _stat_value(body, "Transactions") == "8"


# --------------------------------------------------------------------- #
# DB side effects / edge cases
# --------------------------------------------------------------------- #

class TestProfileDateFilterEdgeCases:
    def test_zero_matching_expenses_shows_zero_state_without_errors(self, auth_client):
        # The seeded demo user's expenses are all dated in the current
        # month; a range far in the past matches none of them.
        response = auth_client.get("/profile?date_from=2000-01-01&date_to=2000-01-31")
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        assert _stat_value(body, "Total Spent") == "₹0.00"
        assert _stat_value(body, "Transactions") == "0"
        assert _stat_value(body, "Top Category") == "—"

        assert "profile-progress-row" not in body, "Category breakdown must be empty"
        assert "profile-badge" not in body, "No transaction rows/category badges should render"
        for desc in ("Groceries", "Restaurant dinner", "Electricity bill"):
            assert desc not in body

        assert "Traceback" not in body
        assert "Internal Server Error" not in body

    def test_recent_transactions_limit_of_10_still_applies_when_filtered(
        self, empty_user_client, empty_user_id, insert_expense
    ):
        today = date.today()
        for i in range(12):
            day = (today - timedelta(days=i)).isoformat()
            insert_expense(empty_user_id, 5.00, "Food", day, f"LimitTest{i:02d}")

        date_from = (today - timedelta(days=20)).isoformat()
        response = empty_user_client.get(
            f"/profile?date_from={date_from}&date_to={today.isoformat()}"
        )
        assert response.status_code == 200
        body = response.data.decode("utf-8")

        matches = re.findall(r"LimitTest\d{2}", body)
        assert len(matches) == 10, "Recent transactions must stay capped at 10 rows even when filtered"


# --------------------------------------------------------------------- #
# Direct tests of the date-range contract on the query helpers themselves
# (documented in the spec's "Files to change" section) — exercised
# without going through the Flask route.
# --------------------------------------------------------------------- #

class TestDateFilterQueryHelpers:
    def test_get_summary_stats_unfiltered_when_both_dates_none(self, seed_user_id):
        with_explicit_none = get_summary_stats(seed_user_id, date_from=None, date_to=None)
        without_args = get_summary_stats(seed_user_id)
        assert with_explicit_none == without_args

    def test_get_summary_stats_unfiltered_when_only_one_date_given(self, seed_user_id):
        only_from = get_summary_stats(seed_user_id, date_from="2000-01-01")
        unfiltered = get_summary_stats(seed_user_id)
        assert only_from == unfiltered, (
            "Per spec, the date-range clause only activates when both "
            "date_from and date_to are provided"
        )

    def test_get_summary_stats_date_range_bounds_are_inclusive(self, temp_db, insert_expense):
        user_id = create_user("Boundary Tester", "boundary@example.com", "pw123456")
        insert_expense(user_id, 10.00, "Food", "2026-03-01", "start boundary")
        insert_expense(user_id, 20.00, "Food", "2026-03-15", "middle")
        insert_expense(user_id, 30.00, "Food", "2026-03-31", "end boundary")
        insert_expense(user_id, 40.00, "Food", "2026-02-28", "just before range")
        insert_expense(user_id, 50.00, "Food", "2026-04-01", "just after range")

        stats = get_summary_stats(user_id, date_from="2026-03-01", date_to="2026-03-31")
        assert stats["transaction_count"] == 3
        assert stats["total_spent"] == 60.00

    def test_get_recent_transactions_respects_date_range(self, temp_db, insert_expense):
        user_id = create_user("Range Tester", "range@example.com", "pw123456")
        insert_expense(user_id, 10.00, "Food", "2026-03-01", "in range")
        insert_expense(user_id, 20.00, "Food", "2026-05-01", "out of range")

        txns = get_recent_transactions(user_id, date_from="2026-02-01", date_to="2026-03-31")
        assert len(txns) == 1
        assert txns[0]["description"] == "in range"

    def test_get_category_breakdown_empty_for_no_match_range(self, temp_db, insert_expense):
        user_id = create_user("No Match Tester", "nomatch@example.com", "pw123456")
        insert_expense(user_id, 10.00, "Food", "2026-03-01", "outside filter")

        breakdown = get_category_breakdown(user_id, date_from="2020-01-01", date_to="2020-01-31")
        assert breakdown == []

    def test_get_category_breakdown_percentages_sum_to_100_within_filtered_subset(
        self, temp_db, insert_expense
    ):
        user_id = create_user("Filtered Pct Tester", "filteredpct@example.com", "pw123456")

        # Three equal-amount categories inside the filter window (33/33/33
        # rounds down to 99 without a remainder-adjustment step) plus one
        # expense clearly outside the window that must not skew the result.
        insert_expense(user_id, 10.00, "Food", "2026-03-01", "in range a")
        insert_expense(user_id, 10.00, "Transport", "2026-03-02", "in range b")
        insert_expense(user_id, 10.00, "Bills", "2026-03-03", "in range c")
        insert_expense(user_id, 999.00, "Health", "2020-01-01", "far outside range")

        breakdown = get_category_breakdown(user_id, date_from="2026-03-01", date_to="2026-03-31")

        assert len(breakdown) == 3
        assert {c["name"] for c in breakdown} == {"Food", "Transport", "Bills"}
        assert sum(c["pct"] for c in breakdown) == 100
