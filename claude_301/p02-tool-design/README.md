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

## Run

```bash
python v1_bad_tools.py      # see misrouting in action
python v2_good_tools.py     # see explicit descriptions fix it
python v3_tool_choice.py    # explore tool_choice modes + structured errors
```

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
