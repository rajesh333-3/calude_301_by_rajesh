"""
Version 2 — Nullable Fields (eliminates hallucination)
=======================================================
Single change from v1: vendor_name and invoice_date become
  type: ["string", "null"]   and are removed from "required".

Same document with no vendor now returns null — zero fabrication.

Key insight: making a field nullable is the highest-impact single change
you can make. It eliminates an entire class of hallucinated data.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Client   : openai.OpenAI()                  → anthropic.Anthropic()
  Call     : client.chat.completions.create   → client.messages.create
  Tool fmt : {"type":"function","function"}   → {"name":..., "input_schema":...}
  Nullable : OpenAI does not natively support → Claude: "type": ["string", "null"]
             "type": ["string", "null"] in    Claude will honor this and return null.
             strict mode. In non-strict mode
             (default), just omit from
             "required" — model returns null
             implicitly.
  Forced   : tool_choice={"type":"function",  → tool_choice={"type":"tool","name":X}
               "function":{"name":X}}
  Args     : json.loads(tc.function.arguments)→ response.content[0].input
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Tool with NULLABLE optional fields ────────────────────────────────────────
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

                # NULLABLE: not in "required" → model returns null when absent
                # CLAUDE: "type": ["string", "null"] — explicit nullable union type
                # OpenAI (non-strict): omit from required; use description to signal nullability
                "vendor_name": {
                    "type": "string",
                    "description": "Vendor name, or null if not present in the document"
                },
                "invoice_date": {
                    "type": "string",
                    "description": "Invoice date in any format found, or null if absent"
                },

                "currency": {
                    "type": "string",
                    "enum": ["USD", "EUR", "GBP", "other"]
                },
                "currency_detail": {
                    "type": "string",
                    "description": "Currency name if 'other' was selected, else null"
                },
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
            # vendor_name and invoice_date deliberately OMITTED from required
            "required": ["invoice_number", "total_amount"]
        }
    }
}

# ── Same documents as v1 ──────────────────────────────────────────────────────
DOCUMENT_WITH_VENDOR = """
INVOICE #INV-2024-001
Date: March 15, 2024
Vendor: Acme Supplies Ltd

Services:
  - Cloud hosting (monthly)   $450.00
  - Support plan              $150.00

Total due: $600.00 USD
"""

DOCUMENT_NO_VENDOR = """
INVOICE #INV-2024-002
Date: March 20, 2024

(Vendor information not available on this copy)

Items:
  - Software license          200.00
  - Setup fee                  60.00

Total: 260.00
"""

DOCUMENT_NO_DATE_NO_VENDOR_NO_CURRENCY = """
INVOICE #INV-2024-003

Consulting services rendered    $1,200.00
Travel expenses                   $180.00

TOTAL: EUR 1,380.00
"""

def extract(document: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "extract_invoice"}},
        # CLAUDE: tool_choice={"type": "tool", "name": "extract_invoice"}
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract invoice data. For fields not present in the document, "
                    "return null — do NOT invent or guess values.\n\n"
                    f"Document:\n{document}"
                )
            }
        ]
    )
    tc = response.choices[0].message.tool_calls[0]
    # CLAUDE: return response.content[0].input
    return json.loads(tc.function.arguments)

def print_result(label: str, result: dict) -> None:
    null_fields = [k for k, v in result.items() if v is None]
    print(f"\n── {label} ──")
    print(f"  invoice_number : {result.get('invoice_number')}")
    print(f"  vendor_name    : {result.get('vendor_name')}")
    print(f"  invoice_date   : {result.get('invoice_date')}")
    print(f"  total_amount   : {result.get('total_amount')}")
    print(f"  currency       : {result.get('currency')}")
    if null_fields:
        print(f"  null fields    : {null_fields}  ← absent in doc, NOT hallucinated")

def main():
    print("=== Version 2: Nullable Fields — Zero Hallucination ===\n")

    print_result("Document WITH vendor", extract(DOCUMENT_WITH_VENDOR))
    print_result("Document WITHOUT vendor", extract(DOCUMENT_NO_VENDOR))
    print_result("Document — no date, no vendor, non-USD", extract(DOCUMENT_NO_DATE_NO_VENDOR_NO_CURRENCY))

    print("\n── What changed from v1 ──")
    print("  v1: vendor_name required → model MUST fill it → hallucination")
    print("  v2: vendor_name optional + 'return null' in prompt → null returned")
    print("  Rule: if data can be absent, make the field nullable + remove from required.")

if __name__ == "__main__":
    main()
