from flask import Flask, jsonify

app = Flask(__name__)

MOCK_TRANSACTIONS = [
    {
        "transaction_id": "TXN001",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 500,
        "merchant": "Biryani Restaurant",
        "description": "Biryani"
    },
    {
        "transaction_id": "TXN002",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 250,
        "merchant": "Uber",
        "description": "Cab ride"
    },
    {
        "transaction_id": "TXN003",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 1200,
        "merchant": "Amazon",
        "description": "Shopping"
    },
    {
        "transaction_id": "TXN004",
        "date": "2026-10-05",
        "type": "Expense",
        "amount": 649,
        "merchant": "Netflix",
        "description": "OTT subscription"
    },
    {
        "transaction_id": "TXN005",
        "date": "2026-10-05",
        "type": "Income",
        "amount": 30000,
        "merchant": "Company Salary",
        "description": "Monthly salary"
    }
]

@app.route("/api/mock-transactions", methods=["GET"])
def mock_transactions():
    return jsonify(MOCK_TRANSACTIONS)

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=True
    )