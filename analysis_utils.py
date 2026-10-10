import sqlite3
import os
import pandas as pd
import matplotlib.pyplot as plt


DATABASE_NAME = "expense.db"
CHART_FOLDER = "static/charts"


def load_transactions():

    connection = sqlite3.connect(DATABASE_NAME)

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
    """

    df = pd.read_sql_query(query, connection)

    connection.close()

    return df


def category_expense_analysis():

    df = load_transactions()

    expenses = df[df["type"] == "Expense"].copy()

    if expenses.empty:
        return pd.DataFrame(
            columns=["category", "total"]
        )

    result = (
        expenses
        .groupby("category")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "total"})
        .sort_values("total", ascending=False)
    )

    return result


def monthly_expense_analysis():

    df = load_transactions()

    expenses = df[df["type"] == "Expense"].copy()

    if expenses.empty:
        return pd.DataFrame(
            columns=["month", "total"]
        )

    expenses["date"] = pd.to_datetime(
        expenses["date"],
        errors="coerce"
    )

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


def create_category_chart():

    data = category_expense_analysis()

    os.makedirs(CHART_FOLDER, exist_ok=True)

    chart_path = os.path.join(
        CHART_FOLDER,
        "category_expenses.png"
    )

    plt.figure(figsize=(9, 5))

    if data.empty:

        plt.text(
            0.5,
            0.5,
            "No Expense Data Available",
            ha="center",
            va="center"
        )

        plt.axis("off")

    else:

        plt.bar(
            data["category"],
            data["total"]
        )

        plt.title("Category-wise Expenses")
        plt.xlabel("Category")
        plt.ylabel("Amount (₹)")

        plt.xticks(
            rotation=30,
            ha="right"
        )

        plt.tight_layout()

    plt.savefig(
        chart_path,
        dpi=120
    )

    plt.close()

    return chart_path


def create_monthly_chart():

    data = monthly_expense_analysis()

    os.makedirs(CHART_FOLDER, exist_ok=True)

    chart_path = os.path.join(
        CHART_FOLDER,
        "monthly_expenses.png"
    )

    plt.figure(figsize=(9, 5))

    if data.empty:

        plt.text(
            0.5,
            0.5,
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

        plt.xticks(
            rotation=30,
            ha="right"
        )

        plt.tight_layout()

    plt.savefig(
        chart_path,
        dpi=120
    )

    plt.close()

    return chart_path


def create_income_expense_chart():

    df = load_transactions()

    os.makedirs(CHART_FOLDER, exist_ok=True)

    chart_path = os.path.join(
        CHART_FOLDER,
        "income_vs_expense.png"
    )

    income = df[
        df["type"] == "Income"
    ]["amount"].sum()

    expense = df[
        df["type"] == "Expense"
    ]["amount"].sum()

    labels = [
        "Income",
        "Expenses"
    ]

    values = [
        income,
        expense
    ]

    plt.figure(figsize=(7, 5))

    plt.bar(
        labels,
        values
    )

    plt.title("Income vs Expenses")
    plt.ylabel("Amount (₹)")

    plt.tight_layout()

    plt.savefig(
        chart_path,
        dpi=120
    )

    plt.close()

    return chart_path