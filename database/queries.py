"""Pure DB query helpers for the profile page. No Flask imports here."""

from datetime import datetime

from database.db import get_db


# --- Subagent 2 begin --- #
def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": datetime.strptime(
            row["created_at"], "%Y-%m-%d %H:%M:%S"
        ).strftime("%B %Y"),
    }
# --- Subagent 2 end --- #


# --- Subagent 2 begin --- #
def get_summary_stats(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        total_spent = round(float(row["total"]), 2)
        transaction_count = row["cnt"]

        if transaction_count == 0:
            top_category = "—"
        else:
            top_row = conn.execute(
                "SELECT category FROM expenses WHERE user_id = ? "
                "GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
                (user_id,),
            ).fetchone()
            top_category = top_row["category"]
    finally:
        conn.close()

    return {
        "total_spent": total_spent,
        "transaction_count": transaction_count,
        "top_category": top_category,
    }
# --- Subagent 2 end --- #


# --- Subagent 1 begin --- #
def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    transactions = []
    for row in rows:
        transactions.append(
            {
                "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%b %d, %Y"),
                "description": row["description"] or "",
                "category": row["category"],
                "amount": round(float(row["amount"]), 2),
            }
        )
    return transactions
# --- Subagent 1 end --- #


# --- Subagent 3 begin --- #
def get_category_breakdown(user_id):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)
    pcts = [round(row["total"] / grand_total * 100) for row in rows]
    remainder = 100 - sum(pcts)
    pcts[0] += remainder

    categories = []
    for row, pct in zip(rows, pcts):
        categories.append(
            {
                "name": row["category"],
                "amount": round(float(row["total"]), 2),
                "pct": pct,
            }
        )
    return categories
# --- Subagent 3 end --- #
