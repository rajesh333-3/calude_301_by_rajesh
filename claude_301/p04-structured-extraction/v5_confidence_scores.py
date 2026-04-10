"""
Version 5 — Field-Level Confidence Scores + Human Review Queue
==============================================================
Extends the schema with per-field confidence: "high" | "medium" | "low" | "unclear".
Low or unclear confidence → routed to human review queue instead of auto-processing.

Use cases:
  high    → field is unambiguous in the document
  medium  → field present but formatting is non-standard
  low     → field inferred, not explicitly stated
  unclear → document is contradictory or field is illegible

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Same as v3/v4. Key addition: nested confidence objects in schema.
  OpenAI  : nested objects work the same way in "parameters"
  CLAUDE  : nested objects work the same way in "input_schema"
  No diff in schema nesting — the translation is purely client/call syntax.
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

CONFIDENCE_LEVELS = ["high", "medium", "low", "unclear"]

# ── Extended schema with per-field confidence ──────────────────────────────────
EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_invoice",
        "description": "Extract structured invoice data with per-field confidence scores",
        "parameters": {           # CLAUDE: "input_schema"
            "type": "object",
            "properties": {
                # ── Core fields ───────────────────────────────────────────────
                "invoice_number": {"type": "string"},
                "total_amount":   {"type": "number"},
                "vendor_name": {
                    "type": "string",
                    "description": "Vendor name, or null if not present"
                },
                "invoice_date": {
                    "type": "string",
                    "description": "Invoice date in any format, or null if absent"
                },
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
                },

                # ── Per-field confidence scores ────────────────────────────────
                # One confidence enum per extractable field.
                # "high"    → field unambiguous in document
                # "medium"  → field present, non-standard format
                # "low"     → field inferred, not explicitly stated
                # "unclear" → document contradictory or field illegible
                "confidence": {
                    "type": "object",
                    "description": "Per-field confidence in the extraction",
                    "properties": {
                        "invoice_number": {"type": "string", "enum": CONFIDENCE_LEVELS},
                        "total_amount":   {"type": "string", "enum": CONFIDENCE_LEVELS},
                        "vendor_name":    {"type": "string", "enum": CONFIDENCE_LEVELS},
                        "invoice_date":   {"type": "string", "enum": CONFIDENCE_LEVELS},
                        "line_items":     {"type": "string", "enum": CONFIDENCE_LEVELS},
                    },
                    "required": ["invoice_number", "total_amount", "vendor_name",
                                 "invoice_date", "line_items"]
                }
            },
            "required": ["invoice_number", "total_amount", "currency",
                         "line_items", "confidence"]
        }
    }
}

# ── Human review queue ────────────────────────────────────────────────────────
REVIEW_QUEUE: list[dict] = []
AUTO_PROCESSED: list[dict] = []

ROUTE_THRESHOLD = {"low", "unclear"}   # these confidence levels trigger human review

def route(data: dict, document_id: str) -> str:
    """Route extraction to auto-process or human review based on confidence."""
    conf = data.get("confidence", {})
    low_conf_fields = [
        field for field, level in conf.items()
        if level in ROUTE_THRESHOLD
    ]

    if low_conf_fields:
        REVIEW_QUEUE.append({"document_id": document_id, "data": data,
                             "review_reason": low_conf_fields})
        return f"HUMAN REVIEW — low confidence fields: {low_conf_fields}"
    else:
        AUTO_PROCESSED.append({"document_id": document_id, "data": data})
        return "AUTO PROCESSED"

def extract(document: str, document_id: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "extract_invoice"}},
        # CLAUDE: tool_choice={"type": "tool", "name": "extract_invoice"}
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract invoice data with honest per-field confidence scores.\n"
                    "high=unambiguous, medium=present but non-standard, "
                    "low=inferred, unclear=contradictory.\n"
                    "Return null for absent fields — do not invent values."
                )
            },
            {
                "role": "user",
                "content": f"Document ID: {document_id}\n\n{document}"
            }
        ]
    )
    tc = response.choices[0].message.tool_calls[0]
    # CLAUDE: return response.content[0].input
    return json.loads(tc.function.arguments)

# ── Test documents ─────────────────────────────────────────────────────────────
DOCUMENTS = {
    "DOC-A": """
    INVOICE #INV-2024-100
    Date: April 10, 2024
    Vendor: Precision Tools Ltd

    CNC machining (20h @ $95)    $1,900.00
    Material costs               $  340.00

    TOTAL: $2,240.00 USD
    """,

    "DOC-B": """
    ref: SVC-0055
    (Vendor information unavailable — filed without cover sheet)

    The attached services were rendered sometime in Q1 2024.
    Approximate total: around $800 USD
    Exact breakdown not provided.
    """,

    "DOC-C": """
    INVOICE XZ-9901   GlobalOps Inc   March 2024

    Service package A    $1,000
    Service package B    $2,000
    Discount applied      -$500

    TOTAL BILLED: $3,000 USD
    TOTAL PAID:   $2,500 USD
    """,
}

def main():
    print("=== Version 5: Field-Level Confidence + Human Review Queue ===\n")

    for doc_id, document in DOCUMENTS.items():
        print(f"── {doc_id} ──")
        data = extract(document, doc_id)
        conf = data.get("confidence", {})
        routing = route(data, doc_id)

        print(f"  invoice_number : {data.get('invoice_number'):15}  confidence={conf.get('invoice_number')}")
        print(f"  vendor_name    : {str(data.get('vendor_name'))[:20]:20}  confidence={conf.get('vendor_name')}")
        print(f"  invoice_date   : {str(data.get('invoice_date'))[:15]:15}  confidence={conf.get('invoice_date')}")
        print(f"  total_amount   : {data.get('total_amount'):10}  confidence={conf.get('total_amount')}")
        print(f"  line_items     :              confidence={conf.get('line_items')}")
        print(f"  → Routing: {routing}")
        print()

    print(f"── Summary ──")
    print(f"  Auto-processed : {len(AUTO_PROCESSED)} document(s)")
    print(f"  Human review   : {len(REVIEW_QUEUE)} document(s)")
    if REVIEW_QUEUE:
        for item in REVIEW_QUEUE:
            print(f"    {item['document_id']}: review fields → {item['review_reason']}")

    print("\n── When to use confidence routing ──")
    print("  Use in any pipeline where incorrect data is costly")
    print("  (billing, legal, medical records).")
    print("  Low/unclear → human reviews the source document directly.")
    print("  High/medium → auto-process, optionally spot-check.")

if __name__ == "__main__":
    main()
