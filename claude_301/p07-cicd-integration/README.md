# p07 — Claude Code CI/CD Integration

Non-interactive review pipelines, structured output, duplicate prevention,
multi-pass analysis, and independent review instances.

---

## Files

| File | What it shows |
|---|---|
| `v1_no_p_flag.py` | Why `-p` is required in CI — subprocess hangs without it |
| `ci_review.py` | Core pipeline: Claude CLI + OpenAI fallback, JSON schema output, PR comments |
| `v3_duplicate_prevention.py` | Prior findings in context → no re-reporting of fixed issues |
| `v4_multi_pass.py` | Pass 1 (per-file) + Pass 2 (cross-file integration) vs single pass |
| `v5_independent_review.py` | Fresh instance reviews generated code — catches generation context bias |
| `review_schema.json` | JSON schema enforcing structured finding format |
| `sample_pr/` | Auth + orders code with intentional bugs for review |

---

## Setup

```bash
cd claude_301/p07-cicd-integration
pip install openai python-dotenv

# For OpenAI fallback (works without claude CLI)
echo "OPENAI_API_KEY=sk-..." > .env

# For Claude CLI (preferred — uses real -p flag)
# Install: npm install -g @anthropic-ai/claude-code
# Then:  export ANTHROPIC_API_KEY=sk-ant-...
```

`ci_review.py` auto-detects which backend to use:
- Claude CLI available + `ANTHROPIC_API_KEY` set → uses `claude -p`
- Otherwise → falls back to OpenAI API

---

## Run & Explore

### Step 1 — Understand why `-p` is required (`v1_no_p_flag.py`)

```bash
python3 v1_no_p_flag.py
```

**Expected output:**
```
=== Version 1: Why -p is Required in CI ===

── Without -p (timeout after 5s) ──
  Command: claude 'Review sample_pr/auth.py...'
  Starting process...
  ✗ TIMED OUT after 5.0s — process was HANGING
  In a real CI job: this job runs forever until it's killed by the runner.

── With -p flag ──
  Command: claude -p 'Review sample_pr/auth.py...'
  ✓ Process exited cleanly in 8.3s
  Output preview: 1. SQL Injection (line 22)...

── Why -p matters ──
  Without -p: Claude Code prompts "> " waiting for next input — blocks indefinitely in CI
  With -p:    Outputs result to stdout and exits with code 0
```

**If `claude` CLI is not installed**, the script shows expected behavior and explains the flag.

**What to look for:** The timeout on the without-`-p` run. In real CI this isn't 5s — it runs until the job timeout (often hours), burning runner minutes.

**Exam trap:** These flags do NOT exist: `--no-interactive`, `--ci-mode`, `--headless`.
The correct flag is `-p` or `--print`.

---

### Step 2 — Run the core review pipeline (`ci_review.py`)

```bash
python3 ci_review.py
```

**Expected output:**
```
=== CI Review Pipeline ===

Reviewing 2 file(s): ['auth.py', 'orders.py']

  [mode] OpenAI API fallback (claude CLI not available)

Found 7 issue(s):

## Automated Code Review

### 🔴 CRITICAL (1)
**auth.py:22** `[NEW]`
**Issue:** SQL injection via f-string interpolation in SQL query
**Fix:** Use parameterized query: db.execute("SELECT * FROM users WHERE email = ?", (email,))

### 🟠 HIGH (3)
**auth.py:8** `[NEW]`
**Issue:** SECRET_KEY hardcoded in source — will be committed to git
**Fix:** SECRET_KEY = os.getenv("SECRET_KEY") and add to .env

---
❌ FAIL — 7 finding(s), 1 critical, 3 high

[saved] prior_findings.json — use in v3_duplicate_prevention.py
```

**What to look for:**
- Severity grouping: CRITICAL → HIGH → MEDIUM → LOW
- `[NEW]` tag on first run (all findings are new)
- `prior_findings.json` saved — needed for Step 3
- `❌ FAIL` when critical or high findings exist

**Experiment:** Edit `review_schema.json` — change `"critical"` to `"blocker"` in the severity enum. Re-run — the model will now use "blocker" in its output. Schema shapes the output format.

---

### Step 3 — Duplicate prevention (`v3_duplicate_prevention.py`)

```bash
# Must run ci_review.py first to generate prior_findings.json
python3 ci_review.py
python3 v3_duplicate_prevention.py
```

**Expected output:**
```
=== Version 3: Duplicate Comment Prevention ===

Prior findings loaded: 7 issue(s)
  [critical] auth.py:22 — SQL injection via f-string...
  [high] auth.py:8 — SECRET_KEY hardcoded in source...
  [high] auth.py:35 — Password stored as plaintext...

Simulating partial fix commit...
  [sim] Fixed: SQL injection
  [sim] Remaining: hardcoded secret, plaintext password

Running second review with prior findings injected...

── Classification ──
  Resolved (fixed since last review) : 1
    ✓ auth.py:22 [security]
  Persisting (still present)         : 2
    ⚠ auth.py:8 — SECRET_KEY hardcoded...
    ⚠ auth.py:35 — Password stored as plaintext...
  New (introduced in this commit)    : 0
```

**What to look for:** SQL injection (line 22) no longer appears in the second review output — it was fixed and the model correctly doesn't re-report it. The two remaining bugs persist.

**Experiment:** Modify `sample_pr_fixed/auth.py` to also fix the hardcoded secret. Re-run — it should now show as resolved too, and `persisting` drops to 1.

---

### Step 4 — Multi-pass review (`v4_multi_pass.py`)

```bash
python3 v4_multi_pass.py
```

**Expected output:**
```
── Single-pass review (all files together) ──
  Found 7 issue(s)

── Multi-pass review ──

  Pass 1: per-file analysis...
    Reviewing auth.py... → 5 issue(s)
    Reviewing orders.py... → 3 issue(s)
  Pass 1 total: 8 local issue(s)

  Pass 2: cross-file integration analysis...
  Pass 2 total: 2 integration issue(s)

── Comparison ──
  Single-pass  : 7 finding(s)
  Multi-pass   : 8 local + 2 integration = 10 finding(s)

  Issues caught ONLY by multi-pass integration pass:
    [high] orders.py:? — process_refund trusts customer identity not verified in auth layer
    [medium] auth.py:? — token format incompatible with orders.py ownership check
```

**What to look for:** The integration pass findings — issues that span both files and only appear when both are analyzed together.

**Experiment:** Remove the `integration_prompt_addition` instructions from Pass 2 (the IMPORTANT block). Re-run — Pass 2 will re-report local issues instead of focusing on cross-file patterns. This shows why the scoping instruction matters.

---

### Step 5 — Independent review (`v5_independent_review.py`)

```bash
python3 v5_independent_review.py
```

**Expected output:**
```
── Step 2a: Self-review (same session)...
  Self-review found 3 issue(s):
  [high] SHA-256 token lacks HMAC — timing attack possible
  [medium] Secret key not validated for minimum length
  [low] No token expiry mechanism

── Step 2b: Independent review (fresh instance)...
  Independent review found 5 issue(s):
  [critical] Token construction is predictable — hash(user_id + secret) is guessable
  [high] SHA-256 token lacks HMAC — timing attack possible
  [high] No token revocation mechanism
  [medium] Missing input validation on user_id (negative values, overflow)
  [low] No token expiry mechanism

── Comparison ──
  Shared (both found)          : 2
  Only self-review found       : 1
  Only independent found       : 3  ← missed by self-review
```

**What to look for:** The "Only independent found" section — issues the generator's own review skipped because it "knew" why it made those decisions.

**Experiment:** Run `v5_independent_review.py` twice. The generated code will differ slightly each run. Observe whether the set of "only independent found" issues changes — it often does, because bias is context-specific.

---

## The `-p` Flag — Exam Reference

```bash
# CORRECT — non-interactive, exits after output
claude -p "Review auth.py for bugs" --output-format json

# WRONG — process blocks waiting for human input
claude "Review auth.py for bugs"

# WRONG — these flags don't exist
claude --no-interactive "..."
claude --ci-mode "..."
claude --headless "..."
```

`-p` = `--print` (same flag, long form).
Always required in CI. Most-tested CI/CD question in the exam.

---

## Architecture: Claude CLI vs OpenAI API in CI

```
Claude CLI (preferred):
  subprocess.run(["claude", "-p", prompt, "--output-format", "json"])
  ↓
  Native file-system tools (Read, Grep, Glob on repo files)
  Structured JSON output
  Fresh context per subprocess = independent review by default
  Exit code 0 = success, non-zero = error

OpenAI API (fallback in this module):
  client.chat.completions.create(response_format={"type":"json_object"})
  ↓
  Files must be embedded as text content (no native file access)
  JSON mode via response_format (no schema enforcement)
  Fresh messages[] = independent review
```

---

## OpenAI → Claude Translation

```python
# Non-interactive execution
subprocess.run(["openai", ...])          # no equivalent CLI
                                         # → subprocess.run(["claude", "-p", ...])

# Structured output
response_format={"type":"json_object"}   # JSON mode (no schema)
                                         # → --output-format json + --json-schema file

# Independent review
new messages[] list                      # same approach
                                         # → new claude -p subprocess (always fresh)

# Self-review (same session)
append to messages[]                     # same concept
                                         # → claude -p with --continue flag (resume session)
```

---

## Learning Objectives

- **D3.6** `-p` flag is required in CI — without it, the process hangs indefinitely
- **D3.6** `--output-format json` makes CI output machine-parseable
- **D4.6** Prior findings in context prevents duplicate PR comments
- **D4.6** Multi-pass: Pass 1 (per-file) + Pass 2 (integration) catches cross-file issues
- **D4.6** Independent review instance has no generation context bias
- **Exam trap:** `--no-interactive`, `--ci-mode`, `--headless` do not exist
