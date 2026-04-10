"""
Version 1 — Demonstrates why -p is required in CI
===================================================
Without -p, Claude Code waits for a human's next input after every response.
In CI, there's no human — the subprocess blocks indefinitely.

This script shows:
  1. What happens without -p  → process hangs (we use timeout to show it)
  2. What happens with -p     → process exits cleanly with output
  3. Why this is the #1 CI exam question

── No OpenAI equivalent for this version ─────────────────────────────────────
  -p is a Claude Code CLI flag (the `claude` terminal tool).
  There is no `openai -p` equivalent.
  The OpenAI approach to non-interactive review = call the API directly in Python
  (see ci_review.py which uses openai.OpenAI() as the OpenAI-compatible fallback).

  Exam question framing:
    "Your CI pipeline runs `claude 'Review this file'` and the job hangs."
    Answer: add -p flag → `claude -p 'Review this file'`
    Wrong answers: --no-interactive, --ci-mode, --headless (these don't exist)
"""

import subprocess
import sys
import time


SAMPLE_PROMPT = "Review sample_pr/auth.py for security issues. List top 3 bugs."


def try_without_p_flag(timeout_seconds: int = 5) -> None:
    """
    Run claude WITHOUT -p. The process will hang waiting for stdin.
    We kill it after timeout_seconds to demonstrate the hang.
    """
    print(f"── Without -p (timeout after {timeout_seconds}s) ──")
    print(f"  Command: claude '{SAMPLE_PROMPT[:40]}...'")
    print(f"  Starting process...")

    start = time.time()
    try:
        result = subprocess.run(
            ["claude", SAMPLE_PROMPT],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,    # we add timeout to prevent actual hang in demo
            cwd="."
        )
        elapsed = time.time() - start
        print(f"  Process exited in {elapsed:.1f}s (unexpected — would normally hang)")
        print(f"  stdout: {result.stdout[:200]}")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"  ✗ TIMED OUT after {elapsed:.1f}s — process was HANGING")
        print(f"  In a real CI job: this job runs forever until it's killed by the runner.")
    except FileNotFoundError:
        print(f"  [Note] `claude` CLI not found — install Claude Code to run this demo.")
        print(f"  Expected behavior: process hangs indefinitely waiting for stdin.")


def try_with_p_flag() -> None:
    """
    Run claude WITH -p. Non-interactive mode: outputs result and exits.
    """
    print(f"\n── With -p flag ──")
    print(f"  Command: claude -p '{SAMPLE_PROMPT[:40]}...'")
    print(f"  Starting process...")

    start = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", SAMPLE_PROMPT],
            capture_output=True,
            text=True,
            timeout=60,     # generous timeout — model needs time to respond
            cwd="."
        )
        elapsed = time.time() - start
        if result.returncode == 0:
            print(f"  ✓ Process exited cleanly in {elapsed:.1f}s")
            print(f"  Output preview: {result.stdout[:300]}...")
        else:
            print(f"  Process exited with code {result.returncode} in {elapsed:.1f}s")
            print(f"  stderr: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timed out — check that claude CLI is installed and ANTHROPIC_API_KEY is set")
    except FileNotFoundError:
        print(f"  [Note] `claude` CLI not found.")
        print(f"  Install: npm install -g @anthropic-ai/claude-code")
        print(f"  Then set ANTHROPIC_API_KEY in your environment.")
        _show_expected_behavior()


def _show_expected_behavior() -> None:
    """Show what the output would look like if claude CLI were installed."""
    print("""
  Expected behavior with -p:
    $ claude -p 'Review sample_pr/auth.py for security issues. List top 3 bugs.'

    1. SQL Injection (line 22): `get_user_by_email` uses an f-string directly in
       SQL query. An attacker can pass email=" OR 1=1--" to dump all users.
       Fix: use parameterized queries with `?` placeholders.

    2. Hardcoded secret (line 8): SECRET_KEY is a string literal in source code.
       Fix: use os.getenv("SECRET_KEY") and add SECRET_KEY to .env.

    3. Plaintext password storage (line 35): `create_user` stores passwords as-is.
       Fix: hash with bcrypt before storing, compare hashes on login.

    [Process exits with code 0]
""")


def explain_the_difference() -> None:
    print("\n── Why -p matters ──")
    print("""
  Without -p:
    Claude Code is designed for interactive sessions.
    After each response it prompts "> " waiting for your next input.
    In CI there is no human — the process blocks on stdin forever.
    The CI job runs until the runner's job timeout kills it (often 6 hours).

  With -p (print mode):
    Claude Code runs the prompt, outputs the result to stdout, and exits.
    Return code 0 = success, non-zero = error.
    The CI job proceeds normally.

  Common exam traps (flags that do NOT exist):
    ✗  claude --no-interactive   (not a real flag)
    ✗  claude --ci-mode          (not a real flag)
    ✗  claude --headless         (not a real flag)
    ✓  claude -p                 (correct — print mode)
    ✓  claude --print            (same as -p, long form)
""")


def main():
    print("=== Version 1: Why -p is Required in CI ===\n")

    try_without_p_flag(timeout_seconds=5)
    try_with_p_flag()
    explain_the_difference()

    print("\n── Other useful CI flags ──")
    print("  --output-format json   → machine-parseable output (see v2)")
    print("  --model claude-opus-4-6 → specify model")
    print("  --max-tokens 4096      → cap output length")
    print("  -p is ALWAYS required in CI — remember this for the exam.")


if __name__ == "__main__":
    main()
