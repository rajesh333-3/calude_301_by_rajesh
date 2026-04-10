"""
Version 3 — Duplicate Comment Prevention
=========================================
Problem: PR review runs on every commit. Without deduplication, the same
bugs are re-reported on every push, flooding the PR with repeated comments.

Solution: include prior findings in context. Instruct the model to report
ONLY new or still-unaddressed issues.

How it works:
  1. First review: run normally, save findings to prior_findings.json
  2. Developer makes a partial fix (fixes SQL injection, leaves hardcoded key)
  3. Second review: load prior_findings.json, inject into prompt
  4. Model compares current code state vs prior findings
  5. Fixed issues → not re-reported  |  Remaining issues → re-reported as is_new=false

── OpenAI vs Claude CLI ──────────────────────────────────────────────────────
  Same as ci_review.py — routes to whichever backend is available.
  The deduplication logic is identical regardless of LLM backend.
"""

import json
from pathlib import Path
from ci_review import run_review, format_as_pr_comments

SAMPLE_PR     = Path(__file__).parent / "sample_pr"
PRIOR_FILE    = Path(__file__).parent / "prior_findings.json"
FIXED_PR_DIR  = Path(__file__).parent / "sample_pr_fixed"


def simulate_partial_fix() -> None:
    """
    Write a 'fixed' version of auth.py where SQL injection is resolved
    but the hardcoded secret and plaintext password remain.
    This simulates a commit that fixes some but not all issues.
    """
    FIXED_PR_DIR.mkdir(exist_ok=True)

    fixed_auth = '''"""
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
'''

    (FIXED_PR_DIR / "auth.py").write_text(fixed_auth)
    # orders.py unchanged
    import shutil
    shutil.copy(SAMPLE_PR / "orders.py", FIXED_PR_DIR / "orders.py")
    print(f"  [sim] Partial fix applied to {FIXED_PR_DIR}/")
    print("  [sim] Fixed: SQL injection")
    print("  [sim] Remaining: hardcoded secret, plaintext password")


def load_prior_findings() -> list[dict]:
    """Load prior findings from previous review run."""
    if not PRIOR_FILE.exists():
        print(f"  [warn] {PRIOR_FILE} not found — run ci_review.py first.")
        print(f"  [sim] Using mock prior findings for demo...")
        return [
            {"file": "auth.py", "line": 22, "severity": "critical",
             "category": "security", "issue": "SQL injection via f-string in query",
             "recommendation": "Use parameterized query with ? placeholder"},
            {"file": "auth.py", "line": 8, "severity": "high",
             "category": "security", "issue": "Hardcoded SECRET_KEY in source",
             "recommendation": "Use os.getenv('SECRET_KEY')"},
            {"file": "auth.py", "line": 35, "severity": "high",
             "category": "security", "issue": "Password stored as plaintext",
             "recommendation": "Hash with bcrypt before storing"},
        ]
    return json.loads(PRIOR_FILE.read_text())


def compare_findings(prior: list[dict], current: list[dict]) -> dict:
    """Classify current findings as new, persisting, or resolved."""
    prior_issues = {(f.get("file"), f.get("line"), f.get("category"))
                    for f in prior}
    current_issues = {(f.get("file"), f.get("line"), f.get("category"))
                      for f in current}

    resolved    = prior_issues - current_issues
    new_issues  = current_issues - prior_issues
    persisting  = prior_issues & current_issues

    return {
        "new":       [f for f in current if (f.get("file"), f.get("line"), f.get("category"))
                      in new_issues],
        "persisting": [f for f in current if (f.get("file"), f.get("line"), f.get("category"))
                       in persisting],
        "resolved":  list(resolved),
    }


def main():
    print("=== Version 3: Duplicate Comment Prevention ===\n")

    # Step 1: load prior findings
    prior = load_prior_findings()
    print(f"Prior findings loaded: {len(prior)} issue(s)")
    for f in prior:
        print(f"  [{f['severity']}] {f['file']}:{f.get('line','?')} — {f['issue'][:60]}")

    # Step 2: simulate a partial fix (developer fixed SQL injection only)
    print("\nSimulating partial fix commit...")
    simulate_partial_fix()

    # Step 3: run review on fixed files WITH prior findings in context
    print("\nRunning second review with prior findings injected...")
    fixed_files = sorted(FIXED_PR_DIR.glob("*.py"))
    current_findings = run_review(fixed_files, prior_findings=prior,
                                  pass_label="post-fix-review")

    # Step 4: classify findings
    classification = compare_findings(prior, current_findings)

    print(f"\n── Classification ──")
    print(f"  Resolved (fixed since last review) : {len(classification['resolved'])}")
    for r in classification["resolved"]:
        print(f"    ✓ {r[0]}:{r[1]} [{r[2]}]")

    print(f"  Persisting (still present)         : {len(classification['persisting'])}")
    for f in classification["persisting"]:
        print(f"    ⚠ {f['file']}:{f.get('line','?')} — {f['issue'][:60]}")

    print(f"  New (introduced in this commit)    : {len(classification['new'])}")
    for f in classification["new"]:
        print(f"    ✗ {f['file']}:{f.get('line','?')} — {f['issue'][:60]}")

    print(f"\n── PR Comment (only new + persisting, no duplicates) ──")
    print(format_as_pr_comments(current_findings))

    print(f"\n── What prevents duplicates ──")
    print("  Prior findings are injected into the prompt:")
    print('  "do NOT re-report these unless still present"')
    print("  The model sees what was already flagged and skips resolved issues.")
    print("  is_new=false marks persisting issues so CI can suppress them if desired.")


if __name__ == "__main__":
    main()
