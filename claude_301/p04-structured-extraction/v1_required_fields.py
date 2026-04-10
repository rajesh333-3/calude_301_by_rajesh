"""
Version 1 — Required Fields Everywhere (shows the hallucination problem)
========================================================================
vendor_name is required. When the document has no vendor, the model
INVENTS one to satisfy the schema. Print the hallucinated value.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Client   : openai.OpenAI()                  → anthropic.Anthropic()
  Call     : client.chat.completions.create   → client.messages.create
  Tool fmt : {"type":"function","function"}   → {"name":..., "input_schema":...}
  Forced   : tool_choice={"type":"function",  → tool_choice={"type":"tool",
               "function":{"name":X}}               "name": X}
  Args     : json.loads(tc.function.arguments)→ response.content[0].input (already dict)
  Model    : "gpt-4o"                         → "claude-sonnet-4-6"
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Tool with ALL fields required ─────────────────────────────────────────────
# CLAUDE format: {"name": ..., "description": ..., "input_schema": {...}}
EXTRACTION_TOOL = {
    "type": "function",           # CLAUDE: no "type" wrapper
    "function": {                 # CLAUDE: remove this nesting
        "name": "extract_invoice",
        "description": "Extract structured invoice data from unstructured text",
        "parameters": {           # CLAUDE: "input_schema" not "parameters"
            "type": "object",
            "properties": {
                "invoice_number": {"type": "string"},
                "total_amount":   {"type": "number"},
                "vendor_name":    {"type": "string"},   # ← REQUIRED string, no null allowed
                "invoice_date":   {"type": "string"},   # ← same problem
                "currency": {
                    "type": "string",
                    "enum": ["USD", "EUR", "GBP", "other"]
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
            # ALL fields required → model must hallucinate when data is absent
            "required": ["invoice_number", "total_amount", "vendor_name",
                         "invoice_date", "currency"]
        }
    }
}

# ── Test documents ─────────────────────────────────────────────────────────────
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
  - Software license          $200.00
  - Setup fee                  $50.00

Total: $250.00 USD
"""

def extract(document: str, label: str) -> dict:
    """Call the extraction tool and return parsed result."""
    response = client.chat.completions.create(
        model="gpt-4o",               # CLAUDE: model="claude-sonnet-4-6"
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={                  # CLAUDE: tool_choice={"type":"tool","name":"extract_invoice"}
            "type": "function",
            "function": {"name": "extract_invoice"}
        },
        messages=[{"role": "user", "content": f"Extract invoice data:\n{document}"}]
    )
    tc = response.choices[0].message.tool_calls[0]
    # CLAUDE: data = response.content[0].input  (already a dict — no json.loads needed)
    return json.loads(tc.function.arguments)

def main():
    print("=== Version 1: Required Fields — Hallucination Demo ===\n")

    print("── Document WITH vendor ──")
    result = extract(DOCUMENT_WITH_VENDOR, "with_vendor")
    print(f"  invoice_number : {result.get('invoice_number')}")
    print(f"  vendor_name    : {result.get('vendor_name')}   ← real data")
    print(f"  total_amount   : {result.get('total_amount')}")

    print("\n── Document WITHOUT vendor ──")
    result = extract(DOCUMENT_NO_VENDOR, "no_vendor")
    print(f"  invoice_number : {result.get('invoice_number')}")
    print(f"  vendor_name    : {result.get('vendor_name')}   ← HALLUCINATED")
    print(f"  total_amount   : {result.get('total_amount')}")

    print("\nConclusion:")
    print("  vendor_name is required → model cannot return null → invents a value.")
    print("  Fix: make vendor_name nullable (see v2).")

if __name__ == "__main__":
    main()
