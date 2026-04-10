"""
Version 5 — Independent Review Instance
=========================================
When Claude generates code and then reviews it in the same session,
it has "generation context bias": it subconsciously validates the decisions
it just made rather than questioning them.

An independent review instance starts fresh with no generation context.
It sees only the code, not the reasoning behind each line.

This file demonstrates both approaches:
  Generator   → writes a piece of auth code (with deliberate subtle bugs)
  Self-review → same session reviews it (may miss context-tied decisions)
  Independent → fresh instance reviews the same code (no bias)

The independent instance typically catches:
  - Assumptions the generator encoded silently ("I'll add rate limiting later")
  - "Obvious" choices that aren't actually obvious (SHA-256 for tokens vs HMAC)
  - Missing edge cases the generator hand-waved during generation

── OpenAI vs Claude CLI ──────────────────────────────────────────────────────
  Self-review:    continue the same openai session (append to messages[])
  Independent:    new OpenAI() call with fresh messages[], no prior context

  CLAUDE CLI self-review:     claude -p "review the code you just wrote" (same session)
  CLAUDE CLI independent:     separate `claude -p` subprocess invocation
                              Each subprocess is a fresh context — no memory of prior runs.
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Step 1: Generate auth code (with subtle intentional bugs) ─────────────────
GENERATION_PROMPT = """Write a Python function `create_session_token(user_id: int) -> str`
that:
- Takes a user_id integer
- Returns a session token string
- Uses a secret key from environment for signing
- Token should be non-guessable

Also write a companion `verify_session_token(token: str, user_id: int) -> bool`.

Keep it concise — under 30 lines. No external libraries, stdlib only."""

def generate_code() -> tuple[str, list[dict]]:
    """Generate auth code. Returns (generated_code, message_history)."""
    messages = [
        {"role": "system", "content": "You are a backend Python developer."},
        {"role": "user",   "content": GENERATION_PROMPT}
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        messages=messages
    )
    code = response.choices[0].message.content
    # Append to history for self-review
    messages.append({"role": "assistant", "content": code})
    return code, messages


# ── Step 2a: Self-review (same session, generation context present) ────────────
REVIEW_PROMPT = """Review the code you just wrote for security issues.
List ALL security vulnerabilities and missing best practices.
Be critical — do not be lenient because you wrote it.
Return a JSON object:
{
  "findings": [
    {"issue": "description", "severity": "critical|high|medium|low",
     "recommendation": "specific fix"}
  ],
  "self_review": true
}"""

def self_review(messages: list[dict]) -> list[dict]:
    """
    Review in the SAME session — generator has context of its own decisions.
    CLAUDE CLI: claude -p "review the code you just wrote" (continuation)
    """
    review_messages = messages + [{"role": "user", "content": REVIEW_PROMPT}]
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        response_format={"type": "json_object"},
        messages=review_messages
    )
    try:
        data = json.loads(response.choices[0].message.content)
        for f in data.get("findings", []):
            f["reviewer"] = "self"
        return data.get("findings", [])
    except json.JSONDecodeError:
        return []


# ── Step 2b: Independent review (fresh instance, no generation context) ────────
INDEPENDENT_REVIEW_PROMPT_TEMPLATE = """Review the following Python code for security issues.
You have no prior context about why it was written this way.
Be critical and thorough. List ALL vulnerabilities and missing best practices.
Return a JSON object:
{{
  "findings": [
    {{"issue": "description", "severity": "critical|high|medium|low",
     "recommendation": "specific fix"}}
  ],
  "self_review": false
}}

Code to review:
{code}"""

def independent_review(code: str) -> list[dict]:
    """
    Review with a FRESH instance — no generation context whatsoever.
    CLAUDE CLI: new `claude -p` subprocess = completely fresh context.
    """
    prompt = INDEPENDENT_REVIEW_PROMPT_TEMPLATE.format(code=code)
    # Fresh messages — no history of how the code was generated
    fresh_messages = [
        {"role": "system",
         "content": "You are an independent security auditor with no prior context."},
        {"role": "user", "content": prompt}
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=512,
        response_format={"type": "json_object"},
        messages=fresh_messages  # ← FRESH context, not the generator's session
    )
    try:
        data = json.loads(response.choices[0].message.content)
        for f in data.get("findings", []):
            f["reviewer"] = "independent"
        return data.get("findings", [])
    except json.JSONDecodeError:
        return []


def main():
    print("=== Version 5: Independent Review Instance ===\n")

    # Step 1: generate
    print("── Step 1: Generating auth code...")
    code, history = generate_code()
    print(f"Generated {len(code)} chars of code.\n")
    print("Generated code:")
    print("-" * 50)
    print(code)
    print("-" * 50)

    # Step 2a: self-review
    print("\n── Step 2a: Self-review (same session, has generation context)...")
    self_findings = self_review(history)
    print(f"  Self-review found {len(self_findings)} issue(s):")
    for f in self_findings:
        print(f"  [{f.get('severity','?')}] {f.get('issue','')[:70]}")

    # Step 2b: independent review
    print(f"\n── Step 2b: Independent review (fresh instance, no context)...")
    indep_findings = independent_review(code)
    print(f"  Independent review found {len(indep_findings)} issue(s):")
    for f in indep_findings:
        print(f"  [{f.get('severity','?')}] {f.get('issue','')[:70]}")

    # Compare
    print(f"\n── Comparison ──")
    self_issues  = {f.get("issue", "")[:50] for f in self_findings}
    indep_issues = {f.get("issue", "")[:50] for f in indep_findings}

    only_indep = indep_issues - self_issues
    only_self  = self_issues  - indep_issues
    shared     = self_issues  & indep_issues

    print(f"  Shared (both found)          : {len(shared)}")
    print(f"  Only self-review found       : {len(only_self)}")
    print(f"  Only independent found       : {len(only_indep)}  ← missed by self-review")

    if only_indep:
        print(f"\n  Issues the independent reviewer caught that self-review missed:")
        for issue in only_indep:
            print(f"    • {issue}")

    print(f"\n── Why independent review catches more ──")
    print("  Self-review: generator recalls its decisions ('I chose SHA-256 intentionally')")
    print("               and validates them rather than questioning them.")
    print("  Independent: no context of intent — evaluates code purely on its own merits.")
    print("               'Why SHA-256? HMAC-SHA256 with a proper secret would be safer.'")
    print()
    print("── In CI: how to implement independent review ──")
    print("  CLAUDE CLI:  each `claude -p` subprocess is a fresh instance by default.")
    print("               Generate in one subprocess, review in a second subprocess.")
    print("  OPENAI API:  start with empty messages[] — do not pass generation history.")
    print("               A new messages list = an independent context.")

if __name__ == "__main__":
    main()
