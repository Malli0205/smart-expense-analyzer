from flask import Flask, render_template, request, redirect, jsonify
import urllib.request
import json
import threading
import time
from datetime import datetime, timedelta

from database import (
    get_connection,
    create_table,
    add_deleted_column,
    add_transaction_id_column
)

from analysis_utils import (
    category_expense_analysis,
    monthly_expense_analysis,
    create_category_chart,
    create_monthly_chart,
    create_income_expense_chart
)


app = Flask(__name__)


# =========================================================
# DATABASE SETUP
# =========================================================

create_table()
add_deleted_column()
add_transaction_id_column()


# =========================================================
# DELETE TRANSACTIONS OLDER THAN 2 YEARS
# =========================================================

def clear_old_transactions():

    connection = get_connection()
    cursor = connection.cursor()

    cutoff_date = (
        datetime.today() - timedelta(days=730)
    ).strftime("%Y-%m-%d")

    cursor.execute("""
        DELETE FROM transactions
        WHERE date < ?
    """, (cutoff_date,))

    connection.commit()
    connection.close()


# =========================================================
# AUTOMATIC TRANSACTION CATEGORIZATION
# =========================================================

def categorize_transaction(transaction):

    transaction_type = transaction["type"]
    merchant = transaction["merchant"].lower()

    # -------------------------
    # INCOME
    # -------------------------

    if transaction_type == "Income":

        if "salary" in merchant or "company" in merchant:
            return "Income", "Salary"

        return "Income", "Other"

    # -------------------------
    # EXPENSES
    # -------------------------

    if "biryani" in merchant:
        return "Food", "Restaurant"

    elif "swiggy" in merchant:
        return "Food", "Restaurant"

    elif "zomato" in merchant:
        return "Food", "Restaurant"

    elif "uber" in merchant:
        return "Travel", "Cab"

    elif "amazon" in merchant:
        return "Shopping", "Online Shopping"

    elif "netflix" in merchant:
        return "Entertainment", "OTT Subscription"

    else:
        return "Other", "Other"


# =========================================================
# AUTOMATIC BACKGROUND SYNC
# =========================================================

def automatic_sync():

    print("Automatic transaction sync started.")

    while True:

        try:

            api_url = (
                "http://127.0.0.1:5001/"
                "api/mock-transactions"
            )

            # Get transactions from financial API
            with urllib.request.urlopen(api_url) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

            connection = get_connection()
            cursor = connection.cursor()

            added_count = 0

            for transaction in data:

                transaction_id = transaction["transaction_id"]

                # Check duplicate
                cursor.execute("""
                    SELECT id
                    FROM transactions
                    WHERE transaction_id = ?
                """, (transaction_id,))

                existing_transaction = cursor.fetchone()

                if existing_transaction:

                    continue

                # Automatically categorize
                category, sub_category = (
                    categorize_transaction(transaction)
                )

                # Insert transaction
                cursor.execute("""
                    INSERT INTO transactions
                    (
                        transaction_id,
                        date,
                        type,
                        category,
                        sub_category,
                        amount,
                        description,
                        is_deleted
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,
                    transaction["date"],
                    transaction["type"],
                    category,
                    sub_category,
                    transaction["amount"],
                    transaction["description"],
                    0
                ))

                added_count += 1

            connection.commit()
            connection.close()

            if added_count > 0:

                print(
                    f"Automatic sync: "
                    f"{added_count} new transaction(s) added."
                )

            else:

                print(
                    "Automatic sync: "
                    "No new transactions."
                )

        except Exception as error:

            print(
                "Automatic sync error:",
                error
            )

        # Wait 60 seconds
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

    month_pattern = f"{selected_year}-{selected_month}-%"

    connection = get_connection()
    cursor = connection.cursor()

    # Total income
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE type = 'Income'
        AND date LIKE ?
    """, (month_pattern,))

    total_income = cursor.fetchone()[0]

    # Total expenses
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE type = 'Expense'
        AND date LIKE ?
    """, (month_pattern,))

    total_expenses = cursor.fetchone()[0]

    # Remaining balance
    remaining_balance = (
        total_income - total_expenses
    )

    # Savings
    savings = remaining_balance

    categories = [
        "Food",
        "Travel",
        "Shopping",
        "Education",
        "Bills & Utilities",
        "Health",
        "Entertainment",
        "Home"
    ]

    category_totals = {}

    for category in categories:

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'Expense'
            AND category = ?
            AND date LIKE ?
        """, (category, month_pattern))

        category_totals[category] = cursor.fetchone()[0]

    connection.close()

    return render_template(
        "index.html",
        total_income=total_income,
        total_expenses=total_expenses,
        remaining_balance=remaining_balance,
        savings=savings,
        category_totals=category_totals,
        selected_month=selected_month,
        selected_year=selected_year
    )


# =========================================================
# RECEIVE SINGLE TRANSACTION
# =========================================================

@app.route(
    "/api/receive-transaction",
    methods=["POST"]
)
def receive_transaction():

    data = request.get_json()

    date = data["date"]
    transaction_type = data["type"]
    amount = data["amount"]
    merchant = data["merchant"]
    description = data["description"]

    transaction_id = data.get("transaction_id")

    category, sub_category = (
        categorize_transaction(data)
    )

    connection = get_connection()
    cursor = connection.cursor()

    # Check duplicate transaction
    if transaction_id:

        cursor.execute("""
            SELECT id
            FROM transactions
            WHERE transaction_id = ?
        """, (transaction_id,))

        existing_transaction = cursor.fetchone()

        if existing_transaction:

            connection.close()

            return jsonify({
                "message": "Transaction already exists",
                "transaction_id": transaction_id
            })

    cursor.execute("""
        INSERT INTO transactions
        (
            transaction_id,
            date,
            type,
            category,
            sub_category,
            amount,
            description,
            is_deleted
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        transaction_id,
        date,
        transaction_type,
        category,
        sub_category,
        amount,
        description,
        0
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "message": "Transaction received successfully",
        "transaction_id": transaction_id,
        "date": date,
        "type": transaction_type,
        "amount": amount,
        "merchant": merchant,
        "category": category,
        "sub_category": sub_category
    })


# =========================================================
# MANUAL SYNC API
# =========================================================

@app.route(
    "/api/sync-transactions",
    methods=["POST"]
)
def sync_transactions():

    try:

        api_url = (
            "http://127.0.0.1:5001/"
            "api/mock-transactions"
        )

        with urllib.request.urlopen(api_url) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

        connection = get_connection()
        cursor = connection.cursor()

        added_count = 0
        skipped_count = 0

        for transaction in data:

            transaction_id = transaction["transaction_id"]

            # Check duplicate
            cursor.execute("""
                SELECT id
                FROM transactions
                WHERE transaction_id = ?
            """, (transaction_id,))

            existing_transaction = cursor.fetchone()

            if existing_transaction:

                skipped_count += 1

                continue

            # Categorize
            category, sub_category = (
                categorize_transaction(transaction)
            )

            # Insert
            cursor.execute("""
                INSERT INTO transactions
                (
                    transaction_id,
                    date,
                    type,
                    category,
                    sub_category,
                    amount,
                    description,
                    is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transaction_id,
                transaction["date"],
                transaction["type"],
                category,
                sub_category,
                transaction["amount"],
                transaction["description"],
                0
            ))

            added_count += 1

        connection.commit()
        connection.close()

        return jsonify({
            "message": "Transaction sync completed",
            "added": added_count,
            "skipped_duplicates": skipped_count
        })

    except Exception as error:

        return jsonify({
            "message": "Transaction sync failed",
            "error": str(error)
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
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transactions
            (
                date,
                type,
                category,
                sub_category,
                amount,
                description,
                is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            "Expense",
            category,
            sub_category,
            amount,
            description,
            0
        ))

        connection.commit()
        connection.close()

        selected_year = date[:4]
        selected_month = date[5:7]

        return redirect(
            f"/?month={selected_month}"
            f"&year={selected_year}"
        )

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
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO transactions
            (
                date,
                type,
                category,
                sub_category,
                amount,
                description,
                is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date,
            "Income",
            category,
            sub_category,
            amount,
            description,
            0
        ))

        connection.commit()
        connection.close()

        selected_year = date[:4]
        selected_month = date[5:7]

        return redirect(
            f"/?month={selected_month}"
            f"&year={selected_year}"
        )

    return render_template("add_income.html")


# =========================================================
# TRANSACTION HISTORY
# =========================================================

@app.route("/transactions")
def transactions():

    selected_month = request.args.get("month")
    selected_year = request.args.get("year")

    current_year = datetime.today().year

    years = list(
        range(
            current_year,
            current_year - 10,
            -1
        )
    )

    connection = get_connection()
    cursor = connection.cursor()

    if selected_month and selected_year:

        month_pattern = (
            f"{selected_year}-"
            f"{selected_month.zfill(2)}-%"
        )

        cursor.execute("""
            SELECT
                id,
                date,
                type,
                category,
                sub_category,
                amount,
                description
            FROM transactions
            WHERE date LIKE ?
            AND is_deleted = 0
            ORDER BY date DESC, id DESC
        """, (month_pattern,))

    else:

        cursor.execute("""
            SELECT
                id,
                date,
                type,
                category,
                sub_category,
                amount,
                description
            FROM transactions
            WHERE is_deleted = 0
            ORDER BY date DESC, id DESC
        """)

    transactions = cursor.fetchall()

    if selected_month and selected_year:

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'Income'
            AND date LIKE ?
        """, (month_pattern,))

        monthly_income = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'Expense'
            AND date LIKE ?
        """, (month_pattern,))

        monthly_expenses = cursor.fetchone()[0]

    else:

        monthly_income = 0
        monthly_expenses = 0

    monthly_balance = (
        monthly_income - monthly_expenses
    )

    connection.close()

    return render_template(
        "transaction.html",
        transactions=transactions,
        selected_month=selected_month,
        selected_year=selected_year,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_balance=monthly_balance,
        years=years
    )


# =========================================================
# DELETE / HIDE TRANSACTION
# =========================================================

@app.route(
    "/delete-transaction/<int:transaction_id>",
    methods=["POST"]
)
def delete_transaction(transaction_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE transactions
        SET is_deleted = 1
        WHERE id = ?
    """, (transaction_id,))

    connection.commit()
    connection.close()

    return redirect("/transactions")


# =========================================================
# ANALYSIS
# =========================================================

@app.route("/analysis")
def analysis():

    connection = get_connection()
    cursor = connection.cursor()

    # Total income
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE type = 'Income'
    """)

    total_income = cursor.fetchone()[0]

    # Total expenses
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE type = 'Expense'
    """)

    total_expenses = cursor.fetchone()[0]

    remaining_balance = (
        total_income - total_expenses
    )

    connection.close()

    # Analytics
    category_data = (
        category_expense_analysis()
    )

    monthly_data = (
        monthly_expense_analysis()
    )

    # Charts
    create_category_chart()
    create_monthly_chart()
    create_income_expense_chart()

    # Convert DataFrames
    category_data = category_data.to_dict(
        orient="records"
    )

    monthly_data = monthly_data.to_dict(
        orient="records"
    )

    return render_template(
        "analysis.html",
        total_income=total_income,
        total_expenses=total_expenses,
        remaining_balance=remaining_balance,
        category_data=category_data,
        monthly_data=monthly_data
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    import os

    is_main_process = (
        not app.debug
        or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    )

    if is_main_process:

        sync_thread = threading.Thread(
            target=automatic_sync,
            daemon=True
        )

        sync_thread.start()

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )