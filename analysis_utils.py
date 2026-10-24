
import os

import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from database import get_connection


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CHART_FOLDER = os.path.join(BASE_DIR, "static", "charts")


def load_transactions(user_id):
    """Load active transactions belonging only to the requested user."""

    connection = get_connection()

    query = """
        SELECT
            id,
            date,
            type,
            category,
            sub_category,
            amount,
            description
        FROM transactions
        WHERE user_id = %s
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY date DESC, id DESC
    """

    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()

            columns = [
                column.name
                for column in cursor.description
            ]

        df = pd.DataFrame(
            [tuple(row) for row in rows],
            columns=columns
        )

    finally:
        connection.close()

    return df


def category_expense_analysis(user_id):
    df = load_transactions(user_id)

    expenses = df[df["type"] == "Expense"].copy()

    if expenses.empty:
        return pd.DataFrame(columns=["category", "total"])

    result = (
        expenses
        .groupby("category", dropna=False)["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total"})
        .sort_values("total", ascending=False)
    )

    return result


def monthly_expense_analysis(user_id):
    df = load_transactions(user_id)

    expenses = df[df["type"] == "Expense"].copy()

    if expenses.empty:
        return pd.DataFrame(columns=["month", "total"])

    expenses["date"] = pd.to_datetime(
        expenses["date"],
        errors="coerce"
    )

    expenses = expenses.dropna(subset=["date"])

    if expenses.empty:
        return pd.DataFrame(columns=["month", "total"])

    expenses["month"] = (
        expenses["date"]
        .dt.to_period("M")
        .astype(str)
    )

    result = (
        expenses
        .groupby("month")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total"})
        .sort_values("month")
    )

    return result


def create_category_chart(user_id):
    data = category_expense_analysis(user_id)

    os.makedirs(CHART_FOLDER, exist_ok=True)

    chart_path = os.path.join(
        CHART_FOLDER,
        f"category_expenses_{user_id}.png"
    )

    plt.figure(figsize=(9, 5))

    if data.empty:
        plt.text(
            0.5, 0.5,
            "No Expense Data Available",
            ha="center",
            va="center"
        )
        plt.axis("off")
    else:
        plt.bar(
            data["category"].fillna("Uncategorized").astype(str),
            data["total"]
        )
        plt.title("Category-wise Expenses")
        plt.xlabel("Category")
        plt.ylabel("Amount (₹)")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()

    plt.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close()

    return chart_path


def create_monthly_chart(user_id):
    data = monthly_expense_analysis(user_id)

    os.makedirs(CHART_FOLDER, exist_ok=True)

    chart_path = os.path.join(
        CHART_FOLDER,
        f"monthly_expenses_{user_id}.png"
    )

    plt.figure(figsize=(9, 5))

    if data.empty:
        plt.text(
            0.5, 0.5,
            "No Monthly Data Available",
            ha="center",
            va="center"
        )
        plt.axis("off")
    else:
        plt.plot(
            data["month"],
            data["total"],
            marker="o"
        )
        plt.title("Monthly Expense Trend")
        plt.xlabel("Month")
        plt.ylabel("Amount (₹)")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()

    plt.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close()

    return chart_path


def create_income_expense_chart(user_id):
    df = load_transactions(user_id)

    os.makedirs(CHART_FOLDER, exist_ok=True)

    chart_path = os.path.join(
        CHART_FOLDER,
        f"income_vs_expense_{user_id}.png"
    )

    income = df.loc[
        df["type"] == "Income", "amount"
    ].sum()

    expense = df.loc[
        df["type"] == "Expense", "amount"
    ].sum()

    labels = ["Income", "Expenses"]
    values = [income, expense]

    plt.figure(figsize=(7, 5))
    plt.bar(labels, values)
    plt.title("Income vs Expenses")
    plt.ylabel("Amount (₹)")
    plt.tight_layout()

    plt.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close()

    return chart_path
