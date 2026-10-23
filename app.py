from flask import Flask, render_template, request, redirect, jsonify, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import threading
import time
from flask import send_file
from werkzeug.utils import secure_filename
from pypdf import PdfReader
import io
import re
import hashlib

from database import (
    get_connection,
    create_table,
    add_deleted_column,
    add_transaction_id_column,
    add_user_id_column,
    create_users_table,
)

from analysis_utils import (
    category_expense_analysis,
    monthly_expense_analysis,
    create_category_chart,
    create_monthly_chart,
    create_income_expense_chart,
)

from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-this-key")

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return view_function(*args, **kwargs)
    return wrapped_view


# =========================================================
# DATABASE SETUP
# =========================================================


create_table()
add_deleted_column()
add_transaction_id_column()
create_users_table()
add_user_id_column()


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
    pass


# =========================================================
# AUTOMATIC TRANSACTION CATEGORIZATION
# =========================================================




def categorize_transaction(transaction):
    text = (
        str(transaction.get("merchant", "")) + " " +
        str(transaction.get("description", ""))
    ).lower().strip()

    transaction_type = str(transaction.get("type", "")).lower().strip()

    # Income transactions
    if transaction_type == "income":
        return "Income", "Other"

    # Healthcare — check before general merchant rules
    if any(word in text for word in [
        "pharmacy", "medical", "hospital", "medicine",
        "doctor", "clinic", "apollo", "lab test",
        "diagnostic", "health centre", "health center"
    ]):
        return "Health", "Medical"

    # ATM / cash withdrawal
    if any(word in text for word in [
        "atm cash withdrawal", "cash withdrawal",
        "atm withdrawal"
    ]):
        return "Cash & ATM", "Cash Withdrawal"

    # Education
    if any(word in text for word in [
        "college", "school", "tuition", "education",
        "exam fee", "course fee", "online course",
        "textbook", "stationery", "university",
        "institute", "institution", "iit",
        "educational"
    ]):
        return "Education", "Education"

    # Bills and utilities
    if any(word in text for word in [
        "electricity", "water bill", "gas bill",
        "recharge", "broadband", "internet bill",
        "phone bill", "mobile bill", "rent payment",
        "upi/rent", "utility bill"
    ]):
        if "rent" in text or "rent payment" in text:
            return "Home", "Household"
        return "Bills & Utilities", "Bills"

    # Travel
    if any(word in text for word in [
        "uber", "ola", "rapido", "cab", "auto fare",
        "petrol", "diesel", "fuel", "bus", "train",
        "metro", "irctc", "transport", "ola cabs",
        "toll"
    ]):
        return "Travel", "Transport"

    # Entertainment
    if any(word in text for word in [
        "netflix", "prime video", "hotstar",
        "movie", "cinema", "spotify", "gaming",
        "jiosaavn", "movie tickets"
    ]):
        return "Entertainment", "Entertainment"

    # Shopping, flowers and personal care
    if any(word in text for word in [
        "fancy", "bangles", "earrings", "jewellery",
        "jewelry", "clothing", "clothes", "dress",
        "shoes", "footwear", "amazon", "flipkart",
        "shopping", "cosmetics", "shampoo", "perfume",
        "flower shop", "flowers", "saree", "garments",
        "boutique", "gift shop"
    ]):
        return "Shopping", "Personal Shopping"

    # Food, groceries, bakeries and restaurants
    if any(word in text for word in [
        "food", "restaurant", "biryani", "swiggy",
        "zomato", "coffee", "cafe", "tea shop",
        "bakery", "milk", "curd", "vegetable",
        "fruit", "grocery", "groceries", "kirana",
        "general stores", "supermarket", "zepto",
        "blinkit", "bigbasket", "instamart",
        "ice cream", "ice creams", "icecream",
        "chopsticks", "hotel", "mill",
        "tiffin", "meals", "sweets", "juice",
        "provision store", "fruits shop"
    ]):
        return "Food", "Groceries/Food"

    # Home and household
    if any(word in text for word in [
        "rent", "furniture", "household",
        "cleaning supplies", "kitchen items",
        "home appliance"
    ]):
        return "Home", "Household"

    # Do not guess a category for incomplete descriptions.
    # Keep unknown merchants available for manual review.
    return "Other", "Needs Review"




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

# USER REGISTRATION

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or len(password) < 8:
            flash("Enter valid details. Password must be at least 8 characters.")
            return redirect("/register")

        connection = get_connection()
        try:
            cursor = connection.cursor()

            cursor.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            )

            if cursor.fetchone():
                flash("This email is already registered.")
                return redirect("/register")

            password_hash = generate_password_hash(password)

            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (?, ?, ?)
                """,
                (name, email, password_hash)
            )

            connection.commit()

        finally:
            connection.close()

        flash("Registration successful! Please log in.")
        return redirect("/login")

    return render_template("register.html")
    
# USER LOGIN

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = ?",
                (email,)
            )
            user = cursor.fetchone()
        finally:
            connection.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect("/")

        flash("Invalid email or password.")
        return redirect("/login")

    return render_template("login.html")


# USER LOGOUT

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect("/login")



@app.route("/")
@login_required
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

        # Total income for the logged-in user
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Income'
              AND date LIKE ?
              AND is_deleted = 0
            """,
            (session["user_id"], month_pattern),
        )
        total_income = cursor.fetchone()[0]

        # Total expenses for the logged-in user
        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND date LIKE ?
              AND is_deleted = 0
            """,
            (session["user_id"], month_pattern),
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
            "Cash & ATM",
            "Other",
        ]

        category_totals = {}

        # Category totals for the logged-in user only
        for category in categories:
            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM transactions
                WHERE user_id = ?
                  AND type = 'Expense'
                  AND category = ?
                  AND date LIKE ?
                  AND is_deleted = 0
                """,
                (session["user_id"], category, month_pattern),
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
@login_required
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
                    user_id, date, type, category, sub_category,
                    amount, description, is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    session["user_id"],
                    date,
                    "Expense",
                    category,
                    sub_category,
                    amount,
                    description,
                ),
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
@login_required
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
                    user_id, date, type, category, sub_category,
                    amount, description, is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    session["user_id"],
                    date,
                    "Income",
                    category,
                    sub_category,
                    amount,
                    description,
                ),
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
@login_required
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
                WHERE user_id = ? AND date LIKE ? AND is_deleted = 0
                ORDER BY date DESC, id DESC
                """,
                (session["user_id"], month_pattern),
            )
            transaction_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM transactions
                WHERE user_id = ? AND type = 'Income' AND date LIKE ?
                """,
                (session["user_id"], month_pattern),
            )
            monthly_income = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)
                FROM transactions
               WHERE user_id = ? AND type = 'Expense' AND date LIKE ?
                """,
               (session["user_id"], month_pattern),
            )
            monthly_expenses = cursor.fetchone()[0]
        else:
            cursor.execute(
                """
                SELECT id, date, type, category, sub_category, amount, description
                FROM transactions
                WHERE user_id = ? AND is_deleted = 0
                ORDER BY date DESC, id DESC
                """ ,
                (session["user_id"],)

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
@login_required
def delete_transaction(transaction_id):
    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE transactions
            SET is_deleted = 1
            WHERE id = ? AND user_id = ? AND is_deleted = 0
            """,
            (transaction_id, session["user_id"]),
        )
        connection.commit()
    finally:
        connection.close()

    return redirect("/transactions")



# =========================================================
# ANALYSIS
# =========================================================



@app.route("/analysis")
@login_required
def analysis():
    connection = get_connection()

    try:
        cursor = connection.cursor()
        user_id = session["user_id"]

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Income'
              AND is_deleted = 0
            """,
            (user_id,)
        )
        total_income = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND is_deleted = 0
            """,
            (user_id,)
        )
        total_expenses = cursor.fetchone()[0]

    finally:
        connection.close()

    remaining_balance = total_income - total_expenses

    category_data = category_expense_analysis(user_id)
    monthly_data = monthly_expense_analysis(user_id)

    create_category_chart(user_id)
    create_monthly_chart(user_id)
    create_income_expense_chart(user_id)

    return render_template(
        "analysis.html",
        total_income=total_income,
        total_expenses=total_expenses,
        remaining_balance=remaining_balance,
        category_data=category_data.to_dict(orient="records"),
        monthly_data=monthly_data.to_dict(orient="records"),
        category_chart=f"category_expenses_{user_id}.png",
        monthly_chart=f"monthly_expenses_{user_id}.png",
        income_expense_chart=f"income_vs_expense_{user_id}.png",
    )
    
@app.route("/upload-statement", methods=["GET", "POST"])
@login_required
def upload_statement():
    if request.method == "POST":
        uploaded_file = request.files.get("statement")

        if not uploaded_file or not uploaded_file.filename:
            flash("Please select a PDF file.")
            return redirect("/upload-statement")

        if not uploaded_file.filename.lower().endswith(".pdf"):
            flash("Please upload a PDF file only.")
            return redirect("/upload-statement")

        try:
            pdf_bytes = uploaded_file.read()

            if not pdf_bytes.startswith(b"%PDF-"):
                flash("The selected file is not a valid PDF.")
                return redirect("/upload-statement")

            reader = PdfReader(io.BytesIO(pdf_bytes))

            if reader.is_encrypted:
                flash("Encrypted PDFs are not supported yet.")
                return redirect("/upload-statement")

            extracted_text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

            if not extracted_text.strip():
                flash(
                    "No selectable text found. "
                    "This may be a scanned PDF; OCR support is needed."
                )
                return redirect("/upload-statement")

            return render_template(
                "statement_preview.html",
                extracted_text=extracted_text[:50000]
            )

        except Exception:
            flash("Could not read this PDF. Please try another statement.")
            return redirect("/upload-statement")

    return render_template("upload_statement.html")

@app.route("/recategorize", methods=["POST"])
@login_required
def recategorize_existing_transactions():
    connection = get_connection()

    try:
        cursor = connection.cursor()
        user_id = session["user_id"]

        cursor.execute("""
            SELECT id, type, description, category, sub_category
            FROM transactions
            WHERE user_id = ?
              AND is_deleted = 0
        """, (user_id,))

        rows = cursor.fetchall()
        updated = 0

        for row in rows:
            description = (row["description"] or "").strip()

            new_category, new_sub_category = categorize_transaction({
                "type": row["type"],
                "merchant": "",
                "description": description
            })

            # Update only when the category actually changes
            if (
                new_category != row["category"]
                or new_sub_category != row["sub_category"]
            ):
                cursor.execute("""
                    UPDATE transactions
                    SET category = ?, sub_category = ?
                    WHERE id = ? AND user_id = ? AND is_deleted = 0
                """, (
                    new_category,
                    new_sub_category,
                    row["id"],
                    user_id
                ))

                updated += cursor.rowcount

        connection.commit()
        flash(f"Successfully updated categories for {updated} transactions.")

    except Exception:
        connection.rollback()
        app.logger.exception("Category update failed")
        flash("Category update failed. Please check the application log.")

    finally:
        connection.close()

    return redirect("/transactions")
  



@app.route("/import-statement", methods=["POST"])
@login_required
def import_statement():
    extracted_text = request.form.get("extracted_text", "")

    if not extracted_text.strip():
        flash("No statement text found. Please upload the PDF again.")
        return redirect("/upload-statement")

    # Parser for our sample bank statement PDF
    sample_pattern = re.compile(
        r"(?m)^(\d{2}-\d{2}-\d{4})\s+"
        r"(.+?)\s+"
        r"(Debit|Credit)\s+"
        r"[₹]?\s*([\d,]+(?:\.\d{1,2})?)\s*$",
        re.IGNORECASE
    )

    transactions_to_import = []

    # First, recognize the sample PDF format
    for match in sample_pattern.finditer(extracted_text):
        date_text, description, txn_type, amount_text = match.groups()

        transactions_to_import.append({
            "date": date_text,
            "description": description.strip(),
            "type": txn_type.title(),
            "amount": amount_text,
            "transaction_id": None,
            "date_format": "%d-%m-%Y"
        })

    # If it is not our sample format, try a text-based PhonePe statement
    if not transactions_to_import:
        date_pattern = re.compile(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{1,2},\s+\d{4}\b",
            re.IGNORECASE
        )

        date_matches = list(date_pattern.finditer(extracted_text))

        for index, date_match in enumerate(date_matches):
            block_start = date_match.start()
            block_end = (
                date_matches[index + 1].start()
                if index + 1 < len(date_matches)
                else len(extracted_text)
            )
            block = extracted_text[block_start:block_end]

            type_match = re.search(
                r"\b(DEBIT|CREDIT)\b", block, re.IGNORECASE
            )
            id_match = re.search(
                r"(?:Transaction\s*ID|UPI\s*Transaction\s*ID|UTR)"
                r"\s*[:#]?\s*([A-Za-z0-9_-]+)",
                block,
                re.IGNORECASE
            )
            amount_match = re.search(
                r"₹\s*([\d,]+(?:\.\d{1,2})?)",
                block
            )

            if not type_match or not amount_match:
                continue

            # Try to extract the payment description
            description_match = re.search(
                r"\b(Paid to|Received from|Received from|"
                r"Paid by|Refund from)\s+(.+?)(?=\s+"
                r"(?:DEBIT|CREDIT)\b|₹|\n|$)",
                block,
                re.IGNORECASE
            )

            if description_match:
                description = (
                    description_match.group(1) + " " +
                    description_match.group(2)
                ).strip()
            else:
                description = "PhonePe transaction"

            transactions_to_import.append({
                "date": date_match.group(0),
                "description": description,
                "type": type_match.group(1).title(),
                "amount": amount_match.group(1),
                "transaction_id": id_match.group(1) if id_match else None,
                "date_format": "%b %d, %Y"
            })

    if not transactions_to_import:
        flash(
            "No transactions recognized. Please check the PDF text format."
        )
        return redirect("/upload-statement")
        
    # Identify a previously imported statement for this user
    statement_hash = hashlib.sha256(
        " ".join(extracted_text.split()).encode("utf-8")
    ).hexdigest()

    check_conn = get_connection()
    try:
        check_conn.execute("""
            CREATE TABLE IF NOT EXISTS statement_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                statement_hash TEXT NOT NULL,
                imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, statement_hash)
            )
        """)

        already_imported = check_conn.execute("""
            SELECT 1 FROM statement_imports
            WHERE user_id = ? AND statement_hash = ?
            LIMIT 1
        """, (session["user_id"], statement_hash)).fetchone()

        if already_imported:
            flash("This statement was already imported. No duplicate import made.")
            return redirect("/transactions")

    finally:
        check_conn.close()



    imported = 0
    duplicates = 0
    invalid = 0
    connection = get_connection()

    try:
        cursor = connection.cursor()

        for txn in transactions_to_import:
            try:
                transaction_date = datetime.strptime(
                    txn["date"].strip(),
                    txn["date_format"]
                ).strftime("%Y-%m-%d")

                amount = float(txn["amount"].replace(",", ""))

            except (ValueError, TypeError):
                invalid += 1
                continue

            if amount <= 0:
                invalid += 1
                continue

            description = txn["description"].strip()
            transaction_type = txn["type"].lower()
            text_to_check = description.lower()

            
            if transaction_type == "credit":
                db_type = "Income"
            else:
                db_type = "Expense"

            category, sub_category = categorize_transaction({
                "type": db_type,
                "merchant": "",
                "description": description
            })


            # Use the original PhonePe transaction ID when available.
            # For sample statements, create a stable ID from row details.
            transaction_id = txn["transaction_id"]

            if not transaction_id:
                
                stable_text = (
                    f'{session["user_id"]}|{transaction_date}|'
                    f'{db_type}|{amount:.2f}|{description.lower()}'
                )
                transaction_id = "PDF-" + hashlib.sha256(
                    stable_text.encode("utf-8")
                ).hexdigest()[:32]
                
            # Skip an already-imported active transaction with identical details
            
            


            cursor.execute(
                """
                SELECT 1
                FROM transactions
                WHERE user_id = ? AND transaction_id = ?
                LIMIT 1
                """,
                (session["user_id"], transaction_id)
            )

            if cursor.fetchone():
                duplicates += 1
                continue

            cursor.execute(
                """
                INSERT OR IGNORE INTO transactions (
                    transaction_id, user_id, date, type,
                    category, sub_category, amount, description,
                    is_deleted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    transaction_id,
                    session["user_id"],
                    transaction_date,
                    db_type,
                    category,
                    sub_category,
                    amount,
                    description
                )
            )

            if cursor.rowcount == 1:
                imported += 1
            else:
                duplicates += 1

        connection.commit()

    except Exception:
        connection.rollback()
        app.logger.exception("Statement import failed")
        flash("Import failed. Please check the application logs.")
        return redirect("/upload-statement")

    finally:
        connection.close()
        
    mark_conn = get_connection()
    try:
        mark_conn.execute("""
            INSERT OR IGNORE INTO statement_imports
                (user_id, statement_hash)
            VALUES (?, ?)
        """, (session["user_id"], statement_hash))
        mark_conn.commit()
    finally:
        mark_conn.close()


    flash(
        f"Import complete: {imported} imported, "
        f"{duplicates} duplicates skipped, "
        f"{invalid} invalid rows skipped."
    )
    return redirect("/transactions")





@app.route("/ai-coach")
@login_required
def ai_coach():
    connection = get_connection()

    try:
        cursor = connection.cursor()
        user_id = session["user_id"]

        from calendar import monthrange

        # Current and previous month date ranges
        today = datetime.today().date()
        current_start = today.replace(day=1)

        if today.month == 1:
            previous_year = today.year - 1
            previous_month = 12
        else:
            previous_year = today.year
            previous_month = today.month - 1

        previous_start = datetime(
            previous_year, previous_month, 1
        ).date()

        previous_end = previous_start.replace(
            day=min(
                today.day,
                monthrange(previous_year, previous_month)[1]
            )
        )

        current_start_str = current_start.isoformat()
        today_str = today.isoformat()
        previous_start_str = previous_start.isoformat()
        previous_end_str = previous_end.isoformat()

        # All-time income
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Income'
              AND is_deleted = 0
        """, (user_id,))
        total_income = cursor.fetchone()[0]

        # All-time expenses
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND is_deleted = 0
        """, (user_id,))
        total_expenses = cursor.fetchone()[0]

        # Current month expenses
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND is_deleted = 0
              AND date >= ? AND date <= ?
        """, (user_id, current_start_str, today_str))
        current_expenses = cursor.fetchone()[0]

        # Previous month expenses for the same number of days
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND is_deleted = 0
              AND date >= ? AND date <= ?
        """, (user_id, previous_start_str, previous_end_str))
        previous_expenses = cursor.fetchone()[0]

        # Current month category totals
        cursor.execute("""
            SELECT category, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND is_deleted = 0
              AND date >= ? AND date <= ?
            GROUP BY category
            ORDER BY total DESC
        """, (user_id, current_start_str, today_str))
        category_rows = cursor.fetchall()

        # Previous month category totals
        cursor.execute("""
            SELECT category, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = ?
              AND type = 'Expense'
              AND is_deleted = 0
              AND date >= ? AND date <= ?
            GROUP BY category
        """, (user_id, previous_start_str, previous_end_str))
        previous_category_rows = cursor.fetchall()

        previous_category_totals = {
            row["category"]: row["total"]
            for row in previous_category_rows
        }

        insights = []

        # Exclude Other from category recommendations
        meaningful_categories = [
            row for row in category_rows
            if row["category"]
            and row["category"].strip().lower() != "other"
        ]

        # Highest spending category
        if meaningful_categories:
            highest = meaningful_categories[0]
            insights.append(
                f"Your highest spending category this month is "
                f"{highest['category']} (₹{highest['total']:.2f}). "
                f"Review this category to find possible savings."
            )
        else:
            insights.append(
                "Add categorized expenses to receive category-wise "
                "saving suggestions."
            )

        # Compare current and previous month in rupees only
        difference = current_expenses - previous_expenses

        if previous_expenses > 0:
            if difference > 0:
                insights.append(
                    f"Your expenses are ₹{difference:.2f} higher "
                    f"than the same period last month. "
                    f"Try a realistic savings goal of ₹5,000 next month "
                    f"by reducing non-essential purchases."
                )
            elif difference < 0:
                insights.append(
                    f"Great work! You have spent "
                    f"₹{abs(difference):.2f} less than the same "
                    f"period last month. Try maintaining this habit."
                )
            else:
                insights.append(
                    "Your expenses are the same as the equivalent "
                    "period last month. Try saving more by reducing "
                    "non-essential purchases."
                )
        elif current_expenses > 0:
            insights.append(
                f"You have spent ₹{current_expenses:.2f} this month. "
                f"There is no previous-period spending to compare."
            )
        else:
            insights.append(
                "No expenses have been recorded for the current "
                "month so far."
            )

        # Compare category spending, excluding Other
        category_changes = []

        for row in meaningful_categories:
            category = row["category"]
            current_amount = row["total"]
            previous_amount = previous_category_totals.get(
                category, 0
            )

            if current_amount > previous_amount:
                category_changes.append((
                    category,
                    current_amount - previous_amount,
                    current_amount
                ))

        category_changes.sort(
            key=lambda item: item[1],
            reverse=True
        )

        if category_changes:
            category, increase, current_amount = category_changes[0]

            insights.append(
                f"{category} spending increased by ₹{increase:.2f} "
                f"compared with the same period last month. "
                f"Reducing this category by ₹{increase:.2f} would "
                f"bring it back to last month's spending level."
            )

        # All-time balance and savings information
        savings = total_income - total_expenses

        if total_income > 0:
            if savings < 0:
                insights.append(
                    f"Your recorded expenses exceed your recorded "
                    f"income by ₹{abs(savings):.2f}. Prioritize "
                    f"essential expenses and review your budget."
                )
            else:
                insights.append(
                    f"Your recorded balance is ₹{savings:.2f}. "
                    f"Try setting aside a fixed amount from "
                    f"your future income for savings."
                )
        else:
            insights.append(
                "Record your income to calculate your balance "
                "and plan your savings."
            )

        # Suggest saving 10% of the highest non-Other category
        if meaningful_categories:
            highest = meaningful_categories[0]
            current_amount = highest["total"]

            if current_amount > 0:
                target = round(current_amount * 0.10, 2)

                insights.append(
                    f"Suggested saving goal: reduce spending in "
                    f"{highest['category']} by ₹{target:.2f}. "
                    f"This is a practical starting target based "
                    f"on your current spending."
                )

        return render_template(
            "ai_coach.html",
            insights=insights,
            total_income=total_income,
            total_expenses=total_expenses,
            category_rows=category_rows
        )

    finally:
        connection.close()



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
