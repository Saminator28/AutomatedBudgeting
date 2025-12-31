
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import csv
from collections import defaultdict

app = FastAPI()

# Allow React dev server to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import logging
from fastapi.responses import JSONResponse

from datetime import datetime
import os
# New endpoint for last 12 months income (for bar graph)
@app.get("/api/income-by-month")
def get_income_by_month():
    base_path = Path(__file__).parent.parent.parent.parent / "statements"
    today = datetime.today()
    months = []
    for i in range(12):
        month = (today.month - i - 1) % 12 + 1
        year = today.year if today.month - i > 0 else today.year - 1
        months.append((year, month))
    results = []
    for year, month in reversed(months):
        month_str = f"{year:04d}-{month:02d}"
        income_path = base_path / month_str / "income.csv"
        if not income_path.exists():
            continue
        total_income = 0.0
        with open(income_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    amount = float(row.get("Amount", row.get("amount", 0)))
                except Exception:
                    amount = 0
                total_income += amount
        results.append({
            "month": month_str,
            "income": round(total_income, 2)
        })
    return results

@app.get("/api/expense-categories")
def get_expense_categories():
    # Go up four levels to reach the workspace root from src/ui/backend
    # Use previous month for pie chart
    today = datetime.today()
    prev_month = today.month - 1 or 12
    prev_year = today.year if today.month > 1 else today.year - 1
    prev_month_str = f"{prev_year:04d}-{prev_month:02d}"
    expenses_path = Path(__file__).parent.parent.parent.parent / "statements" / prev_month_str / "expenses.csv"
    category_totals = defaultdict(float)
    try:
        with open(expenses_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                category = row.get("category", "Uncategorized")
                try:
                    amount = float(row.get("Amount", row.get("amount", 0)))
                except Exception:
                    amount = 0
                category_totals[category] += amount
        return [
            {"category": cat, "amount": round(total, 2)}
            for cat, total in category_totals.items()
        ]
    except Exception as e:
        logging.exception("Failed to read expenses.csv")
        return JSONResponse(status_code=500, content={"error": str(e)})


# New endpoint for last 12 months categorized expenses (for line plot)
@app.get("/api/expenses-by-month")
def get_expenses_by_month():
    base_path = Path(__file__).parent.parent.parent.parent / "statements"
    today = datetime.today()
    months = []
    for i in range(12):
        month = (today.month - i - 1) % 12 + 1
        year = today.year if today.month - i > 0 else today.year - 1
        months.append((year, month))
    results = []
    for year, month in reversed(months):
        month_str = f"{year:04d}-{month:02d}"
        expenses_path = base_path / month_str / "expenses.csv"
        if not expenses_path.exists():
            continue
        category_totals = defaultdict(float)
        with open(expenses_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                category = row.get("category", "Uncategorized")
                try:
                    amount = float(row.get("Amount", row.get("amount", 0)))
                except Exception:
                    amount = 0
                category_totals[category] += amount
        for cat, total in category_totals.items():
            results.append({
                "month": month_str,
                "category": cat,
                "amount": round(total, 2)
            })
    return results
