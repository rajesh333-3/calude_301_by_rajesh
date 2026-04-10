"""
auth.py — partially fixed (SQL injection resolved, other bugs remain)
"""

import os
import sqlite3

# BUG STILL PRESENT: hardcoded secret — should be os.getenv("SECRET_KEY")
SECRET_KEY = "super-secret-key-1234"


def get_db():
    return sqlite3.connect("users.db")


def get_user_by_email(email: str) -> dict | None:
    db = get_db()
    # FIXED: parameterized query — no longer vulnerable to SQL injection
    cursor = db.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    return {"id": row[0], "email": row[1], "password": row[2]} if row else None


def create_user(email: str, password: str) -> dict:
    db = get_db()
    # BUG STILL PRESENT: password stored as plaintext
    db.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
    db.commit()
    return {"email": email, "status": "created"}


def verify_password(email: str, password: str) -> bool:
    user = get_user_by_email(email)
    if not user:
        return False
    return user["password"] == password


def generate_token(user_id: int) -> str:
    import hashlib
    return hashlib.sha256(f"{user_id}{SECRET_KEY}".encode()).hexdigest()
