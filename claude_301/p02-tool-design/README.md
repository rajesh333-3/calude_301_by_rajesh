# p02 — Tool Design Studio: From Vague to Precise

Demonstrates how tool description quality and `tool_choice` configuration
directly control LLM routing accuracy and output guarantees.

---

## Files

| File | What it shows |
|---|---|
| `v1_bad_tools.py` | Vague descriptions → model guesses → ~15–30% misrouting |
| `v2_good_tools.py` | Explicit USE WHEN / DO NOT USE → deterministic routing, ~0% errors |
| `v3_tool_choice.py` | `auto` / `required` / forced tool_choice + all 4 error categories |

---

## Setup

```bash
cd claude_301/p02-tool-design
pip install openai python-dotenv   # if not already installed
echo "OPENAI_API_KEY=sk-..." > .env
```

---

## Run & Explore

### Step 1 — See the problem (`v1_bad_tools.py`)

```bash
python v1_bad_tools.py
```

**Expected output** (results vary run-to-run — that's the point):
```
=== Version 1: BAD Tool Descriptions ===

Expected         Got              OK?    Query
--------------------------------------------------------------------------------
lookup_order     lookup_order     ✓      What's the status of order #ORD-12345?
lookup_order     get_customer     ✗      Can you check order ORD-67890 for me?
get_customer     get_customer     ✓      Look up customer CUST-001
...

── Results ──
Correct:    17/20
Error rate: 15.0%
```

**What to look for:** The `✗` rows — queries that clearly say "order" but got
routed to `get_customer`, or vice versa. Error rate is non-deterministic;
re-run a few times to see it fluctuate between 5–30%.

**Experiment:** Edit `BAD_TOOLS` descriptions to be even vaguer (e.g., `"Gets info"`)
and re-run — misrouting gets worse.

---

### Step 2 — See the fix (`v2_good_tools.py`)

```bash
python v2_good_tools.py
```

**Expected output:**
```
=== Version 2: GOOD Tool Descriptions ===

Expected         Got              OK?    Query
--------------------------------------------------------------------------------
lookup_order     lookup_order     ✓      What's the status of order #ORD-12345?
lookup_order     lookup_order     ✓      Can you check order ORD-67890 for me?
...

── Results ──
Correct:    20/20
Error rate: 0.0%

✓ Zero misroutings — explicit descriptions eliminated all ambiguity.
```

**What to look for:** Every row shows `✓`. The error rate should be 0% consistently.

**Experiment:** Remove just the `DO NOT USE` clause from one tool description and
re-run — misrouting reappears. This shows every clause is load-bearing.

---

### Step 3 — Explore tool_choice modes (`v3_tool_choice.py`)

```bash
python v3_tool_choice.py
```

**Expected output (condensed):**
```
============================================================
tool_choice='auto'  — model decides whether to use a tool
============================================================

  [Order question (tool expected)]
  Query: What's the status of order ORD-12345?
  Tool used: True  |  finish_reason: tool_calls
  [tool:lookup_order] → {'order_id': 'ORD-12345', 'status': 'shipped', ...}

  [Conversational (no tool expected)]
  Query: Hi! What can you help me with?
  Tool used: False  |  finish_reason: stop
  [text] I can help you with customer account lookups and order status checks...

============================================================
tool_choice='required'  — MUST call at least one tool
============================================================

  [Conversational (forced to use a tool anyway)]
  Query: Hello, how are you?
  [tool:get_customer] isError=True category=validation retryable=False → ...

============================================================
Structured errors: isError / errorCategory / isRetryable
============================================================

  [transient]
  isError:       True
  errorCategory: transient
  isRetryable:   True
  message:       Database timeout — safe to retry
```

**What to look for:**
- `auto`: conversational query → no tool call (`finish_reason: stop`)
- `required`: even "Hello" forces a tool call — model picks the least-wrong tool
- Forced: the wrong tool is called for the input — demonstrates pinning
- Errors: notice `transient` is the only one with `isRetryable: True`

**Experiment:** In `demo_forced()`, swap which tool is forced and observe the model
trying to make sense of a mismatched identifier.

---

### Summary: what error rate to expect

| File | Runs | Expected error rate |
|---|---|---|
| `v1_bad_tools.py` | multiple | 5–30% (non-deterministic) |
| `v2_good_tools.py` | multiple | 0% consistently |

Requires `OPENAI_API_KEY` in `.env`.

---

## Key Concepts

### 1. Tool description is routing logic

The model reads your description to decide which tool to call.
Vague descriptions → the model guesses from surface words in the query.
Explicit descriptions → deterministic, testable routing.

**Bad (v1):**
```
"description": "Gets customer information"
```

**Good (v2):**
```
"description": (
    "Retrieves customer account data by email address or customer ID.\n"
    "USE WHEN: verifying identity, getting account status, contact details, loyalty tier.\n"
    "INPUT: customer_email (format: user@domain.com) OR customer_id (format: CUST-XXXXX).\n"
    "DO NOT USE to find orders — use lookup_order for that."
)
```

Every clause is load-bearing. The improvement comes from removing ambiguity, not adding tokens.

---

### 2. tool_choice modes

| Mode | OpenAI | Claude | When to use |
|---|---|---|---|
| Model decides | `"auto"` | `{"type": "auto"}` | Normal assistant — tool use optional |
| Must use a tool | `"required"` | `{"type": "any"}` | API that always parses tool output |
| Specific tool | `{"type":"function","function":{"name":X}}` | `{"type":"tool","name":X}` | Testing, onboarding flows |

---

### 3. Structured error pattern (isError)

Return errors as structured dicts instead of raising exceptions.
The model can then decide how to respond based on `isRetryable`.

```python
# not_found — fix the identifier, don't retry
{"isError": True, "errorCategory": "not_found",  "isRetryable": False, "message": "..."}

# transient — safe to retry with backoff
{"isError": True, "errorCategory": "transient",   "isRetryable": True,  "message": "..."}

# permission — don't retry, escalate
{"isError": True, "errorCategory": "permission",  "isRetryable": False, "message": "..."}

# validation — caller sent bad input, fix the call
{"isError": True, "errorCategory": "validation",  "isRetryable": False, "message": "..."}
```

---

## OpenAI → Claude Translation

These files use the OpenAI client. Every Claude-specific equivalent is marked
with a `# CLAUDE:` comment inline. Summary:

```python
# Client
client = OpenAI()                          # → anthropic.Anthropic()

# API call
client.chat.completions.create(...)        # → client.messages.create(...)

# Tool schema
{"type": "function", "function": {         # → {"name": ...,
    "name": ...,                           #    "description": ...,
    "description": ...,                    #    "input_schema": {...}}
    "parameters": {...}}}

# tool_choice
tool_choice="auto"                         # → {"type": "auto"}
tool_choice="required"                     # → {"type": "any"}
tool_choice={"type":"function",            # → {"type": "tool", "name": X}
             "function":{"name": X}}

# Response — tool call detection
resp.choices[0].finish_reason == "tool_calls"   # → resp.stop_reason == "tool_use"
msg.tool_calls[0].function.name                 # → block.name  (block.type=="tool_use")
json.loads(tc.function.arguments)               # → block.input  (already a dict)
msg.content                                     # → block.text   (block.type=="text")
```

---

## Learning Objectives

- **D2.1** Tool descriptions are routing logic — write them like API contracts
- **D2.2** `tool_choice` controls output guarantees (`auto` → optional, `required` → always, forced → specific)
- **D2.3** Return errors as structured data (`isError` / `errorCategory` / `isRetryable`) so the model can act on them
