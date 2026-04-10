# p06 — Hooks, Prerequisites & Deterministic Enforcement

The most-tested conceptual distinction in the exam:
**Hooks are deterministic. Prompt instructions are probabilistic.**

When a business rule has financial or legal consequences, only deterministic enforcement is acceptable.

---

## Files

| File | What it shows |
|---|---|
| `v1_prompt_enforcement.py` | Prompt says "always verify identity first" — ~10–20% failure rate |
| `v2_hook_enforcement.py` | PreToolCall hook enforces the same rule — exactly 0% failure rate |
| `v3_normalization_hook.py` | PostToolUse hook: 3 timestamp formats → ISO 8601 before LLM sees result |
| `v4_blocking_hook.py` | PreToolCall blocks `process_refund > $500` + structured escalation handoff |

---

## Setup

```bash
cd claude_301/p06-hooks-enforcement
pip install openai python-dotenv
echo "OPENAI_API_KEY=sk-..." > .env
```

---

## Run & Explore

### Step 1 — See prompt enforcement fail (`v1_prompt_enforcement.py`)

```bash
python3 v1_prompt_enforcement.py
```

**Expected output:**
```
=== Version 1: Prompt-Based Enforcement ===
Running 15 queries...

Expected               Got                               OK?
----------------------------------------------------------------------------------------------------
...
What's the status of ORD-12345?          lookup_order              ✗ VIOLATION
Check order ORD-67890 for me.            lookup_order              ✗ VIOLATION
Process a $80 refund for ORD-12345.      process_refund            ✗ VIOLATION
...

── Results ──
  Violations : 3/15
  Failure rate: 20.0%
```

**What to look for:** The adversarial queries (order number given directly, no email)
are where violations appear. The model "sees" the order number prominently and jumps
straight to `lookup_order`, skipping identity verification.

**Experiment:** Strengthen the system prompt further — add `"THIS IS MANDATORY"`,
caps, repetition. Re-run. Violation rate drops slightly but never reaches zero.
This is the ceiling of prompt-based enforcement.

---

### Step 2 — See hook enforcement achieve 0% (`v2_hook_enforcement.py`)

```bash
python3 v2_hook_enforcement.py
```

**Expected output:**
```
=== Version 2: Hook-Based Enforcement (0% failure rate) ===

  [HOOK:pre] BLOCKED lookup_order — no verified customer. Redirecting to get_customer.
  [HOOK:pre] BLOCKED lookup_order — no verified customer. Redirecting to get_customer.
  [HOOK:post] Verified customer: CUST-001

Query                                                Tools called                                    Violation?
---------------------------------------------------------------------------------------------------------
What's the status of ORD-12345?      get_customer → lookup_order              ✓
Check order ORD-67890 for me.        get_customer → lookup_order              ✓
Process a $80 refund for ORD-12345.  get_customer → process_refund            ✓

── Results ──
  Violations : 0/15
  Failure rate: 0.0%
```

**What to look for:**
- `[HOOK:pre] BLOCKED` lines — the gate firing before execution
- The tools_called column: even for adversarial queries, `get_customer` always appears first
- The `[HOOK:post] Verified customer` line — state is tracked after each `get_customer` result

**Experiment:** Comment out the `pre_tool_call` method body (make it always return `None`).
Re-run — you get v1's failure rate back immediately. This proves hooks, not prompts, are responsible for the 0%.

**Compare v1 vs v2 side by side:**
```bash
python3 v1_prompt_enforcement.py 2>&1 | tail -5
python3 v2_hook_enforcement.py   2>&1 | tail -5
```

---

### Step 3 — PostToolUse normalization (`v3_normalization_hook.py`)

```bash
python3 v3_normalization_hook.py
```

**Expected output:**
```
=== Version 3: PostToolUse Normalization Hook ===

── backend_legacy_db (ORD-11111) ──
  created_ts      raw: 1673827200                   normed: 2023-01-16T00:00:00+00:00  ← normalized
  updated_ts      raw: 1710028800                   normed: 2024-03-10T00:00:00+00:00  ← normalized

── backend_modern_api (ORD-22222) ──
  created_at      raw: 2024-03-10T14:30:00          normed: 2024-03-10T14:30:00        ← unchanged
  updated_at      raw: 2024-03-15T09:00:00          normed: 2024-03-15T09:00:00        ← unchanged

── backend_cache_layer (ORD-33333) ──
  created_at      raw: 3 days ago                   normed: 2026-04-07T...+00:00       ← normalized
  updated_at      raw: 2 hours ago                  normed: 2026-04-10T...+00:00       ← normalized

── Live agent run (normalization in loop) ──

Query [Legacy DB (Unix ts)]: When was order ORD-11111 created?
  [hook:post] ORD-11111 raw_ts keys: ['created_ts', 'updated_ts'] → ['created_at', 'updated_at']
Answer: Order ORD-11111 was created on January 16, 2023.

Query [Cache layer (relative)]: When was order ORD-33333 created?
  [hook:post] ORD-33333 raw_ts keys: ['created_at', 'updated_at'] → ['created_at', 'updated_at']
Answer: Order ORD-33333 was created approximately 3 days ago (April 7, 2026).
```

**What to look for:**
- Raw values (Unix ints, relative strings) vs normalized ISO 8601 values
- The `_ts` suffix renamed to `_at` — consistency across field names
- The live agent correctly reports the date for all 3 backends without knowing their formats

**Experiment:** Remove the `normalize_timestamps()` call from `run_agent_with_normalization()`
and re-run the cache layer query. The LLM receives `"3 days ago"` and either guesses
the wrong date or asks the user to clarify.

---

### Step 4 — PreToolCall blocking + handoff (`v4_blocking_hook.py`)

```bash
python3 v4_blocking_hook.py
```

**Expected output:**
```
============================================================
Case 1: $100 refund (below $500 limit — should pass)
============================================================
  [STATE] customer verified: CUST-001

Action log: ['ALLOWED:get_customer', 'ALLOWED:lookup_order', 'ALLOWED:process_refund']
Answer: I've processed a $100 refund for order ORD-12345. Refund ID: REF-001.

============================================================
Case 2: $600 refund (above $500 limit — must be blocked → escalated)
============================================================
  [STATE] customer verified: CUST-002
  [HOOK:pre] BLOCKED process_refund($600.00) — exceeds $500. LLM must call escalate_to_human.

Action log: ['ALLOWED:get_customer', 'ALLOWED:lookup_order', 'BLOCKED:process_refund:amount=600.0', 'ALLOWED:escalate_to_human']

============================================================
Structured Handoff Summary (human agent's ONLY context)
============================================================
  Ticket ID:           TKT-CUST-002-001
  Customer ID:         CUST-002
  Priority:            high
  Issue:               Customer requesting $600 refund for damaged product
  Root cause:          Refund amount ($600) exceeds autonomous limit ($500)
  What was attempted:  Verified customer identity, looked up order ORD-67890
  Recommended action:  Approve $600 refund if damage is verified; request photos if needed

  ✓ All handoff fields populated — human agent has full context.
```

**What to look for:**
- Case 1 action log: three `ALLOWED` entries — hook passed all calls
- Case 2 action log: `BLOCKED:process_refund` appears, then `ALLOWED:escalate_to_human`
  — the LLM received the block error, understood it, and pivoted to escalation
- The handoff summary: 4 required fields populated — human agent has everything they need

**Experiment:** Remove `root_cause`, `what_was_attempted`, and `recommended_action`
from the `escalate_to_human` tool's `required` list. Re-run — some fields will be
missing from the handoff summary, flagged as `⚠ Missing fields`.
This shows why all 4 handoff fields must be required in the schema.

---

## The Determinism Hierarchy

```
DETERMINISTIC (financial/legal rules → always use these)
  ├── PreToolCall hook   → fires BEFORE execution, can block or redirect
  └── PostToolUse hook   → fires AFTER execution, normalizes before LLM sees result

PROBABILISTIC (guidance only → never rely on for compliance)
  ├── System prompt      → "always verify identity first"
  ├── Tool descriptions  → "requires human approval above limit"
  └── Few-shot examples  → "see how to handle high-value refunds"
```

**Exam pattern:** When a question involves a financial limit, legal requirement,
or compliance rule → the answer is always a programmatic gate, never a prompt instruction.

---

## Hook Pattern (Python)

```python
class SupportAgent:
    def __init__(self):
        self.verified_customer_id = None   # STATE

    # ── PreToolCall: fires BEFORE execution ─────────────────────────────────
    # CLAUDE SDK: @agent.pre_tool_call
    def pre_tool_call(self, tool_name, tool_input):
        if tool_name in ("lookup_order", "process_refund"):
            if not self.verified_customer_id:
                return {"isError": True, "message": "Call get_customer first"}
        if tool_name == "process_refund":
            if tool_input.get("amount", 0) > 500:
                return {"isError": True, "message": "Exceeds limit — escalate_to_human"}
        return None   # proceed

    # ── PostToolUse: fires AFTER execution, BEFORE LLM sees result ──────────
    # CLAUDE SDK: @agent.post_tool_use
    def post_tool_use(self, tool_name, result):
        if "created_ts" in result:
            result["created_at"] = datetime.fromtimestamp(result.pop("created_ts")).isoformat()
        if tool_name == "get_customer" and "customer_id" in result:
            self.verified_customer_id = result["customer_id"]
        return result
```

---

## OpenAI → Claude Translation

```python
# No API difference for hooks — they are Python wrappers over any LLM client.
# The hook logic is identical regardless of provider.

# The only differences are the standard call/response patterns:
tool_choice="auto"          # → {"type": "auto"}
finish_reason="tool_calls"  # → stop_reason == "tool_use"
finish_reason="stop"        # → stop_reason == "end_turn"
json.loads(tc.function.arguments)  # → block.input (already dict)
{"role":"tool","tool_call_id":...} # → {"role":"user","content":[{"type":"tool_result",...}]}

# CLAUDE SDK native hooks (claude_agent_sdk):
@agent.pre_tool_call
def gate(tool_name, tool_input): ...

@agent.post_tool_use
def normalize(tool_name, result): ...
# These replace the manual hook calling in the agentic loop.
```

---

## Learning Objectives

- **D1.4** Programmatic prerequisites vs prompt guidance — deterministic vs probabilistic
- **D1.5** PreToolCall blocking hook — intercepts before execution
- **D1.5** PostToolUse normalization hook — cleans data before LLM sees it
- **D1.4** Structured escalation handoff — 4 required fields for zero-context human agents
- **Exam trap:** "Add few-shot examples" is always wrong for financial/legal enforcement
