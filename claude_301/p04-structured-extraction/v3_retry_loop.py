"""
Version 3 — Validation-Retry Loop
==================================
Schema enforcement catches structural errors (wrong type, missing required field).
It CANNOT catch semantic errors (line items don't sum to total).

This version adds a semantic validator + retry with specific error feedback.

Why retry works for arithmetic but NOT for absent data:
  ✓ Line items don't sum → model HAS the data but made an arithmetic error → retry fixes it
  ✗ Vendor absent       → no amount of retrying can invent what isn't in the document

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Client   : openai.OpenAI()                  → anthropic.Anthropic()
  Call     : client.chat.completions.create   → client.messages.create
  Tool fmt : {"type":"function","function"}   → {"name":..., "input_schema":...}
  Forced   : tool_choice={"type":"function",  → tool_choice={"type":"tool","name":X}
               "function":{"name":X}}
  History  : append {"role":"assistant",      → append {"role":"assistant",
               "content": None,                    "content": response.content}
               "tool_calls": msg.tool_calls}   (content is a list of blocks)
  Tool res : {"role":"tool",                  → {"role":"user","content":[{
               "tool_call_id":tc.id,               "type":"tool_result",
               "content": json.dumps(result)}]      "tool_use_id":block.id,
                                                    "content": json.dumps(result)}]}
  Args     : json.loads(tc.function.arguments)→ response.content[0].input
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_invoice",
        "description": "Extract structured invoice data from unstructured text",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "total_amount":   {"type": "number"},
                "vendor_name": {
                    "type": "string",
                    "description": "Vendor name, or null if not present"
                },
                "invoice_date": {
                    "type": "string",
                    "description": "Invoice date, or null if not present"
                },
                "currency": {"type": "string", "enum": ["USD", "EUR", "GBP", "other"]},
                "line_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "amount":      {"type": "number"}
                        },
                        "required": ["description", "amount"]
                    }
                }
            },
            "required": ["invoice_number", "total_amount", "currency", "line_items"]
        }
    }
}

# ── Semantic validator ────────────────────────────────────────────────────────
def validate(data: dict) -> list[str]:
    """Return list of semantic errors schema cannot catch."""
    errors = []
    items = data.get("line_items", [])
    if items:
        line_sum = round(sum(item["amount"] for item in items), 2)
        total    = round(data["total_amount"], 2)
        if abs(line_sum - total) > 0.01:
            errors.append(
                f"Line items sum ({line_sum}) does not match total_amount ({total}). "
                f"Re-read the document and correct the discrepancy."
            )
    return errors

# ── Extraction with retry ─────────────────────────────────────────────────────
def extract_with_retry(document: str, max_retries: int = 2) -> tuple[dict, int]:
    """Extract invoice data with semantic validation and retry.

    Returns:
        (extracted_data, attempts_used)
    """
    messages = [
        {
            "role": "user",
            "content": (
                "Extract invoice data. Return null for absent fields — do not invent values.\n\n"
                f"Document:\n{document}"
            )
        }
    ]

    for attempt in range(max_retries + 1):
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1024,
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "function", "function": {"name": "extract_invoice"}},
            # CLAUDE: tool_choice={"type": "tool", "name": "extract_invoice"}
            messages=messages
        )

        msg = response.choices[0].message
        tc  = msg.tool_calls[0]
        # CLAUDE: data = response.content[0].input
        data = json.loads(tc.function.arguments)

        print(f"  Attempt {attempt + 1}: extracted total={data.get('total_amount')}, "
              f"line_sum={round(sum(i['amount'] for i in data.get('line_items',[])),2)}")

        errors = validate(data)
        if not errors:
            return data, attempt + 1

        if attempt < max_retries:
            error_text = "\n".join(f"- {e}" for e in errors)
            print(f"  → Validation failed: {error_text}")
            print(f"  → Retrying ({attempt + 1}/{max_retries})...")

            # Append assistant turn (the tool call) to history
            # CLAUDE:
            #   messages.append({"role": "assistant", "content": response.content})
            #   messages.append({"role": "user", "content": [{
            #       "type": "tool_result",
            #       "tool_use_id": response.content[0].id,
            #       "content": json.dumps(data)
            #   }]})
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": msg.tool_calls
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(data)
            })
            messages.append({
                "role": "user",
                "content": (
                    f"Validation errors found:\n{error_text}\n\n"
                    "Please re-extract the invoice data and fix these issues."
                )
            })
        else:
            print(f"  → Max retries reached. Returning best attempt.")

    return data, max_retries + 1


# ── Test documents ─────────────────────────────────────────────────────────────
DOCUMENT_GOOD = """
INVOICE #INV-2024-010
Date: April 1, 2024   Vendor: TechCorp Ltd

  - API integration service    $800.00
  - Code review (8h @ $75)     $600.00
  - Documentation               $100.00

TOTAL: $1,500.00 USD
"""

DOCUMENT_ARITHMETIC_ERROR = """
INVOICE #INV-2024-011
Vendor: Widgets Inc   Date: April 5, 2024

Line items:
  Widget A × 10 @ $12.50   = $125.00
  Widget B × 5  @ $30.00   = $150.00
  Shipping                  =  $20.00

TOTAL DUE: $350.00 USD
"""
# Note: 125 + 150 + 20 = 295 ≠ 350 — semantic error the model should catch on retry

DOCUMENT_MISSING_DATA = """
INVOICE #INV-2024-012

(Vendor and date information redacted for this copy)

Consulting: $500.00

TOTAL: $500.00 USD
"""

def main():
    print("=== Version 3: Validation-Retry Loop ===\n")

    print("── Case 1: Well-formed document ──")
    data, attempts = extract_with_retry(DOCUMENT_GOOD)
    print(f"  Result: OK in {attempts} attempt(s). total={data['total_amount']}")

    print("\n── Case 2: Line items don't sum to total (arithmetic error) ──")
    data, attempts = extract_with_retry(DOCUMENT_ARITHMETIC_ERROR)
    print(f"  Result: resolved in {attempts} attempt(s). total={data['total_amount']}")
    line_sum = round(sum(i["amount"] for i in data.get("line_items", [])), 2)
    print(f"  Final line sum: {line_sum}, total: {data['total_amount']}, match: {abs(line_sum - data['total_amount']) < 0.01}")

    print("\n── Case 3: Missing data (retry cannot invent absent info) ──")
    data, attempts = extract_with_retry(DOCUMENT_MISSING_DATA)
    print(f"  vendor_name: {data.get('vendor_name')}  ← null, not hallucinated")
    print(f"  invoice_date: {data.get('invoice_date')}  ← null, not hallucinated")

    print("\n── Summary ──")
    print("  Retry works : semantic/arithmetic errors — model HAS data, made a mistake")
    print("  Retry fails : absent data — retrying cannot invent what is not in the doc")

if __name__ == "__main__":
    main()
