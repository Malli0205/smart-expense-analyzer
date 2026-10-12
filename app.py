from flask import Flask, render_template, request, redirect, jsonify
from datetime import datetime, timedelta
import os
import threading
import time

from database import (
    get_connection,
    create_table,
    add_deleted_column,
    add_transaction_id_column,
)

from analysis_utils import (
    category_expense_analysis,
    monthly_expense_analysis,
    create_category_chart,
    create_monthly_chart,
    create_income_expense_chart,
)

app = Flask(__name__)

# =========================================================
# DATABASE SETUP
# =========================================================

create_table()
add_deleted_column()
add_transaction_id_column()

# =========================================================
# MOCK FINANCIAL DATA
# Demo data only. This is NOT connected to a real bank.
# Keep this list in the main app so it works without a
# separate mock_api.py server during local testing.
# =========================================================

MOCK_TRANSACTIONS = [
    {
        "transaction_id": "TXN001",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 500,
        "merchant": "Biryani Restaurant",
        "description": "Biryani",
    },
    {
        "transaction_id": "TXN002",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 250,
        "merchant": "Uber",
        "description": "Cab ride",
    },
    {
        "transaction_id": "TXN003",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 1200,
        "merchant": "Amazon",
        "description": "Shopping",
    },
    {
        "transaction_id": "TXN004",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 649,
        "merchant": "Netflix",
        "description": "OTT subscription",
    },
    {
        "transaction_id": "TXN005",
        "date": "2026-10-05",
        "type": "Income",
        "amount": 30000,
        "merchant": "Company Salary",
        "description": "Monthly salary",
    },
]

# =========================================================
# DELETE TRANSACTIONS OLDER THAN TWO YEARS
# =========================================================

def clear_old_transactions():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cutoff_date = (
            datetime.today() - timedelta(days=730)
        ).strftime("%Y-%m-%d")
        cursor.execute(
            "DELETE FROM transactions WHERE date < ?",
            (cutoff_date,),
        )
        connection.commit()
    finally:
        connection.close()


# =========================================================
# AUTOMATIC TRANSACTION CATEGORIZATION
# =========================================================

def categorize_transaction(transaction):
    transaction_type = transaction.get("type", "Expense")
    merchant = str(transaction.get("merchant", "")).lower()

    if transaction_type == "Income":
        if "salary" in merchant or "company" in merchant:
            return "Income", "Salary"
        return "Income", "Other"

    if any(word in merchant for word in ("biryani", "swiggy", "zomato")):
        return "Food", "Restaurant"
    if "uber" in merchant:
        return "Travel", "Cab"
    if "amazon" in merchant:
        return "Shopping", "Online Shopping"
    if "netflix" in merchant:
        return "Entertainment", "OTT Subscription"

    return "Other", "Other"


# =========================================================
# TRANSACTION SYNC HELPER
# =========================================================

def sync_transaction_data(transactions):
    """Insert unseen transactions and skip IDs already in the database."""
    added_count = 0
    skipped_count = 0

    connection = get_connection()
    try:
        cursor = connection.cursor()

        for transaction in transactions:
            transaction_id = transaction.get("transaction_id")
            if not transaction_id:
                # An external transaction ID is required for safe deduplication.
                skipped_count += 1
                continue

            cursor.execute(
                "SELECT id FROM transactions WHERE transaction_id = ?",
                (transaction_id,),
            )
            if cursor.fetchone():
                skipped_count += 1
                continue

            date = transaction.get("date")
            transaction_type = transaction.get("type")
            amount = transaction.get("amount")
            merchant = transaction.get("merchant", "")
            description = transaction.get("description", "")

            if not date or transaction_type not in ("Income", "Expense"):
                skipped_count += 1
                continue

            try:
                amount = float(amount)
            except (TypeError, ValueError):
                skipped_count += 1
                continue

            if amount < 0:
                skipped_count += 1
                continue

            category, sub_category = categorize_transaction(transaction)

            cursor.execute(
                """
                INSERT INTO transactions (
                    transaction_id, date, type, category, sub_category,
                    amount, description, is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    transaction_id,
                    date,
                    transaction_type,
                    category,
                    sub_category,
                    amount,
                    description,
                ),
            )
            added_count += 1

        connection.commit()
    finally:
        connection.close()

    return added_count, skipped_count


# =========================================================
# MOCK API ENDPOINT
# =========================================================

@app.route("/api/mock-transactions", methods=["GET"])
def mock_transactions():
    return jsonify(MOCK_TRANSACTIONS)


# =========================================================
# AUTOMATIC BACKGROUND SYNC
# =========================================================

def automatic_sync():
    """Demo sync loop. It checks the mock feed once every 60 seconds."""
    print("Automatic transaction sync started.")

    while True:
        try:
            added_count, skipped_count = sync_transaction_data(
                MOCK_TRANSACTIONS
            )
            if added_count:
                print(
                    f"Automatic sync: {added_count} transaction(s) added; "
                    f"{skipped_count} skipped."
                )
            else:
                print(
                    "Automatic sync: No new transactions; "
                    f"{skipped_count} already processed or invalid."
                )
        except Exception as error:
            print(f"Automatic sync error: {error}")

        time.sleep(60)


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def home():
    clear_old_transactions()

    selected_month = request.args.get("month")
    selected_year = request.args.get("year")

    if not selected_month or not selected_year:
        current_date = datetime.today()
        selected_month = current_date.strftime("%m")
        selected_year = current_date.strftime("%Y")

    month_pattern = f"{selected_year}-{selected_month.zfill(2)}-%"

    connection = get_connection()
    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'Income' AND date LIKE ?
            """,
            (month_pattern,),
        )
        total_income = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'Expense' AND date LIKE ?
            """,
            (month_pattern,),
        )
        total_expenses = cursor.fetchone()[0]

        remaining_balance = total_income - total_expenses
        savings = remaining_balance

        categories = [
            "Food",
            "Travel",
            "Shopping",
            "Education",
            "Bills & Utilities",
            "Health",
            "Entertainment",
            "Home",
        ]
        category_totals = {}

        for category in categories:
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM transactions
                WHERE type = 'Expense'
                  AND category = ?
                  AND date LIKE ?
                """,
                (category, month_pattern),
            )
            category_totals[category] = cursor.fetchone()[0]
    finally:
        connection.close()

    return render_template(
        "index.html",
        total_income=total_income,
        total_expenses=total_expenses,
        remaining_balance=remaining_balance,
        savings=savings,
        category_totals=category_totals,
        selected_month=selected_month,
        selected_year=selected_year,
    )


# =========================================================
# RECEIVE A SINGLE TRANSACTION
# =========================================================

@app.route("/api/receive-transaction", methods=["POST"])
def receive_transaction():
    data = request.get_json(silent=True) or {}

    required_fields = ("date", "type", "amount", "merchant", "description")
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({
            "message": "Missing required fields",
            "missing_fields": missing,
        }), 400

    transaction_type = data["type"]
    if transaction_type not in ("Income", "Expense"):
        return jsonify({"message": "type must be Income or Expense"}), 400

    transaction_id = data.get("transaction_id")

    if transaction_id:
        connection = get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id FROM transactions WHERE transaction_id = ?",
                (transaction_id,),
            )
            if cursor.fetchone():
                return jsonify({
                    "message": "Transaction already exists",
                    "transaction_id": transaction_id,
                    "duplicate": True,
                }), 200
        finally:
            connection.close()

    category, sub_category = categorize_transaction(data)

    try:
        amount = float(data["amount"])
        if amount < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"message": "amount must be a non-negative number"}), 400

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO transactions (
                transaction_id, date, type, category, sub_category,
                amount, description, is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                transaction_id,
                data["date"],
                transaction_type,
                category,
                sub_category,
                amount,
                data["description"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return jsonify({
        "message": "Transaction received successfully",
        "transaction_id": transaction_id,
        "date": data["date"],
        "type": transaction_type,
        "amount": amount,
        "merchant": data["merchant"],
        "category": category,
        "sub_category": sub_category,
    }), 201


# =========================================================
# MANUAL SYNC API
# =========================================================

@app.route("/api/sync-transactions", methods=["POST"])
def sync_transactions():
    try:
        added_count, skipped_count = sync_transaction_data(MOCK_TRANSACTIONS)
        return jsonify({
            "message": "Transaction sync completed",
            "added": added_count,
            "skipped_duplicates_or_invalid": skipped_count,
        })
    except Exception as error:
        app.logger.exception("Transaction sync failed")
        return jsonify({
            "message": "Transaction sync failed",
            "error": str(error),
        }), 500


# =========================================================
# ADD EXPENSE
# =========================================================

@app.route("/add-expense", methods=["GET", "POST"])
def add_expense():
    if request.method == "POST":
        date = request.form["date"]
        category = request.form["category"]
        sub_category = request.form["sub_category"]
        amount = request.form["amount"]
        description = request.form["description"]

        connection = get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO transactions (
                    date, type, category, sub_category,
                    amount, description, is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (date, "Expense", category, sub_category, amount, description),
            )
            connection.commit()
        finally:
            connection.close()

        return redirect(f"/?month={date[5:7]}&year={date[:4]}")

    return render_template("add_expense.html")


# =========================================================
# ADD INCOME
# =========================================================

@app.route("/add-income", methods=["GET", "POST"])
def add_income():
    if request.method == "POST":
        date = request.form["date"]
        category = request.form["category"]
        sub_category = request.form["sub_category"]
        amount = request.form["amount"]
        description = request.form["description"]

        connection = get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO transactions (
                    date, type, category, sub_category,
                    amount, description, is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (date, "Income", category, sub_category, amount, description),
            )
            connection.commit()
        finally:
            connection.close()

        return redirect(f"/?month={date[5:7]}&year={date[:4]}")

    return render_template("add_income.html")


# =========================================================
# TRANSACTION HISTORY
# =========================================================

@app.route("/transactions")
def transactions():
    selected_month = request.args.get("month")
    selected_year = request.args.get("year")
    current_year = datetime.today().year
    years = list(range(current_year, current_year - 10, -1))

    connection = get_connection()
    try:
        cursor = connection.cursor()

        if selected_month and selected_year:
            month_pattern = f"{selected_year}-{selected_month.zfill(2)}-%"
            cursor.execute(
                """
                SELECT id, date, type, category, sub_category, amount, description
                FROM transactions
                WHERE date LIKE ? AND is_deleted = 0
                ORDER BY date DESC, id DESC
                """,
                (month_pattern,),
            )
            transaction_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM transactions
                WHERE type = 'Income' AND date LIKE ?
                """,
                (month_pattern,),
            )
            monthly_income = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM transactions
                WHERE type = 'Expense' AND date LIKE ?
                """,
                (month_pattern,),
            )
            monthly_expenses = cursor.fetchone()[0]
        else:
            cursor.execute(
                """
                SELECT id, date, type, category, sub_category, amount, description
                FROM transactions
                WHERE is_deleted = 0
                ORDER BY date DESC, id DESC
                """
            )
            transaction_rows = cursor.fetchall()
            monthly_income = 0
            monthly_expenses = 0
    finally:
        connection.close()

    monthly_balance = monthly_income - monthly_expenses

    return render_template(
        "transaction.html",
        transactions=transaction_rows,
        selected_month=selected_month,
        selected_year=selected_year,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_balance=monthly_balance,
        years=years,
    )


# =========================================================
# DELETE / HIDE TRANSACTION
# =========================================================

@app.route("/delete-transaction/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE transactions SET is_deleted = 1 WHERE id = ?",
            (transaction_id,),
        )
        connection.commit()
    finally:
        connection.close()

    return redirect("/transactions")


# =========================================================
# ANALYSIS
# =========================================================

@app.route("/analysis")
def analysis():
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'Income'"
        )
        total_income = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'Expense'"
        )
        total_expenses = cursor.fetchone()[0]
    finally:
        connection.close()

    remaining_balance = total_income - total_expenses
    category_data = category_expense_analysis()
    monthly_data = monthly_expense_analysis()

    create_category_chart()
    create_monthly_chart()
    create_income_expense_chart()

    return render_template(
        "analysis.html",
        total_income=total_income,
        total_expenses=total_expenses,
        remaining_balance=remaining_balance,
        category_data=category_data.to_dict(orient="records"),
        monthly_data=monthly_data.to_dict(orient="records"),
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":
    # Start one background sync thread when running locally.
    # For Render/Gunicorn, use a separate worker or scheduler
    # instead of starting background loops in each web worker.
    sync_thread = threading.Thread(target=automatic_sync, daemon=True)
    sync_thread.start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
