import sqlite3


DATABASE_NAME = "expense.db"


def get_connection():

    connection = sqlite3.connect(DATABASE_NAME)

    connection.row_factory = sqlite3.Row

    return connection


def create_table():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            transaction_id TEXT UNIQUE,

            date TEXT NOT NULL,

            type TEXT NOT NULL,

            category TEXT NOT NULL,

            sub_category TEXT NOT NULL,

            amount REAL NOT NULL,

            description TEXT,

            is_deleted INTEGER DEFAULT 0

        )
    """)

    connection.commit()
    connection.close()


def add_deleted_column():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        PRAGMA table_info(transactions)
    """)

    columns = [
        row["name"]
        for row in cursor.fetchall()
    ]

    if "is_deleted" not in columns:

        cursor.execute("""
            ALTER TABLE transactions
            ADD COLUMN is_deleted INTEGER DEFAULT 0
        """)

    connection.commit()
    connection.close()


def add_transaction_id_column():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        PRAGMA table_info(transactions)
    """)

    columns = [
        row["name"]
        for row in cursor.fetchall()
    ]

    if "transaction_id" not in columns:

        cursor.execute("""
            ALTER TABLE transactions
            ADD COLUMN transaction_id TEXT
        """)

    connection.commit()
    connection.close()


if __name__ == "__main__":

    create_table()

    add_deleted_column()

    add_transaction_id_column()

    print("Database created successfully!")

    print("Transactions table ready!")

    print("Transaction ID support ready!")