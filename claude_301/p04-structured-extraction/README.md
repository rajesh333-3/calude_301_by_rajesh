# p04 — Structured Data Extraction Pipeline

Demonstrates the progression from hallucinating extractors to a production-grade
invoice extraction system with nullable fields, semantic validation, few-shot priming,
and confidence-based routing.

---

## Files

| File | What it shows |
|---|---|
| `v1_required_fields.py` | All fields required → model hallucinate vendor to satisfy schema |
| `v2_nullable_fields.py` | Nullable fields → null returned for absent data, zero fabrication |
| `v3_retry_loop.py` | Semantic validator + retry loop (line items ≠ total → retry with error) |
| `v4_few_shot.py` | Few-shot examples for unusual document formats (reversed, foreign, no date) |
| `v5_confidence_scores.py` | Per-field confidence scores → auto-process vs human review queue |

---

## Setup

```bash
cd claude_301/p04-structured-extraction
pip install openai python-dotenv   # if not already installed
echo "OPENAI_API_KEY=sk-..." > .env
```

---

## Run & Explore

### Step 1 — Observe hallucination (`v1_required_fields.py`)

```bash
python v1_required_fields.py
```

**Expected output:**
```
=== Version 1: Required Fields — Hallucination Demo ===

── Document WITH vendor ──
  invoice_number : INV-2024-001
  vendor_name    : Acme Supplies Ltd   ← real data
  total_amount   : 600.0

── Document WITHOUT vendor ──
  invoice_number : INV-2024-002
  vendor_name    : Unknown Vendor      ← HALLUCINATED
  total_amount   : 250.0

Conclusion:
  vendor_name is required → model cannot return null → invents a value.
```

**What to look for:** The `vendor_name` on the second document — it will be
something plausible-sounding but fabricated. Run it 3–4 times; the hallucinated
name changes every run.

**Experiment:** Add `invoice_date` to `required` too, then use the no-vendor doc
which says "date redacted" — watch the model invent a date as well.

---

### Step 2 — Fix with nullable fields (`v2_nullable_fields.py`)

```bash
python v2_nullable_fields.py
```

**Expected output:**
```
── Document WITHOUT vendor ──
  invoice_number : INV-2024-002
  vendor_name    : None
  invoice_date   : March 20, 2024
  total_amount   : 250.0
  null fields    : ['vendor_name']  ← absent in doc, NOT hallucinated

── Document — no date, no vendor, non-USD ──
  invoice_number : INV-2024-003
  vendor_name    : None
  invoice_date   : None
  currency       : EUR
  null fields    : ['vendor_name', 'invoice_date']
```

**What to look for:** `None` values in the output — the model returns null
instead of inventing. The `null fields` line tells you exactly what was absent.

**Experiment:** Run the same document from v1 — vendor is now `None` every time,
not a different fabrication per run. That's the stability improvement.

---

### Step 3 — Retry loop in action (`v3_retry_loop.py`)

```bash
python v3_retry_loop.py
```

**Expected output:**
```
── Case 2: Line items don't sum to total (arithmetic error) ──
  Attempt 1: extracted total=350.0, line_sum=295.0
  → Validation failed: Line items sum (295.0) does not match total_amount (350.0)...
  → Retrying (1/2)...
  Attempt 2: extracted total=350.0, line_sum=350.0
  Result: resolved in 2 attempt(s). total=350.0
  Final line sum: 350.0, total: 350.0, match: True

── Case 3: Missing data (retry cannot invent absent info) ──
  vendor_name: None  ← null, not hallucinated
  invoice_date: None  ← null, not hallucinated
```

**What to look for:**
- Case 2: Attempt 1 fails validation, Attempt 2 corrects itself — retry works.
- Case 3: Even after retries, absent data stays `None` — retry cannot fabricate.

**Experiment:** Change `max_retries=0` in the `extract_with_retry` call for Case 2
and observe the mismatch goes unreported. Then set it back to 2.

---

### Step 4 — Few-shot comparison (`v4_few_shot.py`)

```bash
python v4_few_shot.py
```

**Expected output:**
```
── Inline prose format ──
  Zero-shot: invoice=REF-MARCH-15    vendor=NovaBuild Solutions  date=the 15th of March 2024
  Few-shot:  invoice=REF-MARCH-15    vendor=NovaBuild Solutions  date=15th of March 2024

── No date, foreign currency ──
  Zero-shot: invoice=INV-DE-0044     vendor=Müller Softwarelösung  date=None
  Few-shot:  invoice=INV-DE-0044     vendor=Müller Softwarelösungen GmbH  date=None

── Amount-first reversed format ──
  Zero-shot: invoice=PR-2024-88      vendor=Future Systems Inc   date=April 30 2024
  Few-shot:  invoice=PR-2024-88      vendor=Future Systems Inc   date=April 30 2024
```

**What to look for:** Differences in field accuracy between zero-shot and few-shot
columns — especially on the reversed/foreign-language formats where zero-shot
may truncate vendor names or misread amounts.

**Experiment:** Comment out one of the three shots in `FEW_SHOT_EXAMPLES` and
re-run — accuracy on that shot's format type typically drops.

---

### Step 5 — Confidence routing (`v5_confidence_scores.py`)

```bash
python v5_confidence_scores.py
```

**Expected output:**
```
── DOC-A ──
  invoice_number : INV-2024-100      confidence=high
  vendor_name    : Precision Tools   confidence=high
  invoice_date   : April 10, 2024    confidence=high
  total_amount   : 2240.0            confidence=high
  → Routing: AUTO PROCESSED

── DOC-B ──
  invoice_number : SVC-0055          confidence=high
  vendor_name    : None              confidence=unclear
  invoice_date   : Q1 2024           confidence=low
  total_amount   : 800.0             confidence=low
  → Routing: HUMAN REVIEW — low confidence fields: ['vendor_name', 'invoice_date', 'total_amount']

── Summary ──
  Auto-processed : 1 document(s)
  Human review   : 2 document(s)
```

**What to look for:** DOC-C (conflicting totals: $3,000 billed vs $2,500 paid)
should get `unclear` confidence on `total_amount` and route to human review.

**Experiment:** Change `ROUTE_THRESHOLD` from `{"low", "unclear"}` to just
`{"unclear"}` — DOC-B's `low` confidence fields no longer trigger review.
Observe which documents slip through.

---

### Suggested order for learning

```
v1 → v2   understand the nullable fix (10 min)
v3        understand retry limits (10 min)
v4        optional — run if you have unusual doc formats to test
v5        run last — combines all previous concepts
```

Requires `OPENAI_API_KEY` in `.env`.

---

## Key Concepts

### 1. Required vs Nullable Fields

```python
# v1 — WRONG: required string, no null allowed → model invents a value
"vendor_name": {"type": "string"}
# + "vendor_name" in "required"

# v2 — CORRECT: optional field + null-friendly description
"vendor_name": {
    "type": "string",
    "description": "Vendor name, or null if not present in the document"
}
# vendor_name OMITTED from "required"
```

> **Claude** supports explicit nullable types: `"type": ["string", "null"]`
> **OpenAI** (non-strict): omit from `required` and use the description to signal nullability.

Making a field nullable is the **highest-impact single change** — it eliminates
an entire class of hallucinated data.

---

### 2. Schema vs Semantic Validation

| Error type | Schema catches? | Retry fixes? | Example |
|---|---|---|---|
| Missing required field | ✓ (API error) | N/A | invoice_number absent |
| Wrong type | ✓ (API error) | N/A | amount as string |
| Arithmetic mismatch | ✗ | ✓ | line items ≠ total |
| Absent data | ✗ | ✗ | vendor not in document |

Schema enforcement is structural only. Semantic validation (sum check, date range check,
cross-field consistency) must be coded separately.

---

### 3. Retry Loop Pattern

```python
for attempt in range(max_retries + 1):
    response = client.chat.completions.create(...)
    data = json.loads(tc.function.arguments)

    errors = validate(data)          # semantic checks
    if not errors:
        return data, attempt + 1     # success

    if attempt < max_retries:
        # Append tool call + result to history, add error feedback
        messages.append({"role": "assistant", "content": None, "tool_calls": ...})
        messages.append({"role": "tool", "tool_call_id": ..., "content": ...})
        messages.append({"role": "user", "content": f"Fix these errors: {errors}"})
```

Retry works when the model **has** the data but made an error.
Retry **cannot** fix genuinely absent data.

---

### 4. Few-Shot Injection

Inject `(user → assistant tool_call → tool_result)` triples before the real query:

```
messages = [system] + [shot1_user, shot1_assistant, shot1_tool] + ... + [real_query]
```

Best for: unusual layout, foreign formats, fields in non-standard positions.

---

### 5. Confidence Routing

```python
CONFIDENCE_LEVELS = ["high", "medium", "low", "unclear"]
ROUTE_THRESHOLD   = {"low", "unclear"}   # → human review

# Per-field in schema:
"confidence": {
    "type": "object",
    "properties": {
        "vendor_name":  {"type": "string", "enum": CONFIDENCE_LEVELS},
        "total_amount": {"type": "string", "enum": CONFIDENCE_LEVELS},
        ...
    }
}
```

Any field at `low` or `unclear` → document goes to human review queue.
High/medium → auto-processed.

---

## OpenAI → Claude Translation

```python
# Client
client = OpenAI()                          # → anthropic.Anthropic()

# Tool schema
{"type": "function", "function": {         # → {"name": ...,
    "name": ...,                           #    "description": ...,
    "parameters": {...}}}                  #    "input_schema": {...}}

# Nullable fields
omit from "required" + hint in description # → "type": ["string", "null"]

# Forced tool
tool_choice={"type":"function",            # → {"type":"tool","name":X}
             "function":{"name":X}}

# Get result
json.loads(tc.function.arguments)          # → response.content[0].input

# Retry — append tool result
{"role":"tool","tool_call_id":...}         # → {"role":"user","content":[
                                           #       {"type":"tool_result","tool_use_id":...}]}
```

---

## Learning Objectives

- **D4.1** Forced tool_choice guarantees structured output every time
- **D4.2** Few-shot examples improve accuracy on unusual document formats
- **D4.3** Nullable fields eliminate hallucination for absent data
- **D4.4** Retry works for semantic/arithmetic errors; cannot fix genuinely absent data
- **D4.5** Per-field confidence scores enable human-in-the-loop routing
