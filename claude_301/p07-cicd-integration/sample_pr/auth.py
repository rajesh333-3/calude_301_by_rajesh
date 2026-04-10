"""
Sample file for CI review — intentionally contains bugs for detection.
Bug list (for verifying review catches them):
  1. SQL injection in get_user_by_email (line 22)
  2. Hardcoded secret key (line 8)
  3. Password stored as plaintext (line 35)
  4. No rate limiting on login endpoint
  5. Missing input validation on email parameter
"""

SECRET_KEY = "super-secret-key-1234"   # BUG: hardcoded secret — should be env var

import sqlite3
import hashlib


def get_db():
    return sqlite3.connect("users.db")


def get_user_by_email(email: str) -> dict | None:
    db = get_db()
    # BUG: SQL injection — never use f-strings in SQL queries
    cursor = db.execute(f"SELECT * FROM users WHERE email = '{email}'")
    row = cursor.fetchone()
    return {"id": row[0], "email": row[1], "password": row[2]} if row else None


def create_user(email: str, password: str) -> dict:
    db = get_db()
    # BUG: password stored as plaintext — should be hashed with bcrypt/argon2
    db.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
    db.commit()
    return {"email": email, "status": "created"}


def verify_password(email: str, password: str) -> bool:
    user = get_user_by_email(email)
    if not user:
        return False
    # BUG: comparing plaintext password
    return user["password"] == password


def generate_token(user_id: int) -> str:
    # BUG: uses SECRET_KEY which is hardcoded above
    return hashlib.sha256(f"{user_id}{SECRET_KEY}".encode()).hexdigest()
