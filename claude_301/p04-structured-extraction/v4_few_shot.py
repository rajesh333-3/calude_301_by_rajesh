"""
Version 4 — Few-Shot Examples
==============================
Few-shot examples prime the model on edge-case document formats
before it sees the real document. Three shots:
  1. Inline citation style   → date buried mid-sentence
  2. Bibliography format     → amount in different position
  3. No date present         → invoice_date correctly null

Measure: run each example format WITHOUT shots vs WITH shots.
Expect: accuracy on unusual formats improves with shots.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Few-shot  : Same pattern for both — prepend (user/assistant) pairs in messages[].
  OpenAI    : assistant turn uses {"role":"assistant","content":None,"tool_calls":[...]}
              tool result uses {"role":"tool","tool_call_id":...,"content":...}
  CLAUDE    : assistant turn uses {"role":"assistant","content":[block,...]}
              tool result uses {"role":"user","content":[{"type":"tool_result",...}]}
  Args      : json.loads(tc.function.arguments) → response.content[0].input
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
                    "description": "Date in any format found, or null if absent"
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

# ── Few-shot examples ─────────────────────────────────────────────────────────
# Each shot is a (document, expected_extraction) pair.
# We inject them as (user → assistant/tool_result) pairs before the real query.

FEW_SHOT_EXAMPLES = [
    # Shot 1: Date buried in prose
    {
        "document": (
            "Per our agreement dated January 5th 2024, please find enclosed invoice "
            "number SVC-0081 from Cloudbase Technologies for cloud infrastructure "
            "services. Recurring monthly charge: $299.00 USD."
        ),
        "extraction": {
            "invoice_number": "SVC-0081",
            "total_amount": 299.00,
            "vendor_name": "Cloudbase Technologies",
            "invoice_date": "January 5th 2024",
            "currency": "USD",
            "line_items": [
                {"description": "Cloud infrastructure services (monthly)", "amount": 299.00}
            ]
        }
    },
    # Shot 2: Amount appears before description (reversed format)
    {
        "document": (
            "BILL — ref: BIL-2024-44\n"
            "Rapid Design Studio\n"
            "02/28/2024\n\n"
            "$1,200.00 — UI/UX design sprint (week 1)\n"
            "  $800.00 — UI/UX design sprint (week 2)\n"
            "EUR 50.00 — International wire transfer fee\n\n"
            "Total: EUR 2,050.00"
        ),
        "extraction": {
            "invoice_number": "BIL-2024-44",
            "total_amount": 2050.00,
            "vendor_name": "Rapid Design Studio",
            "invoice_date": "02/28/2024",
            "currency": "EUR",
            "line_items": [
                {"description": "UI/UX design sprint (week 1)", "amount": 1200.00},
                {"description": "UI/UX design sprint (week 2)", "amount": 800.00},
                {"description": "International wire transfer fee", "amount": 50.00}
            ]
        }
    },
    # Shot 3: No date present — invoice_date must be null
    {
        "document": (
            "TAX INVOICE\n"
            "Number: TI-9922\n"
            "Issuer: DataStream Analytics Pty Ltd\n\n"
            "Annual subscription — Data pipeline tier    GBP 4,800.00\n\n"
            "Amount due: GBP 4,800.00\n"
            "(Date of service will appear on the accompanying delivery note)"
        ),
        "extraction": {
            "invoice_number": "TI-9922",
            "total_amount": 4800.00,
            "vendor_name": "DataStream Analytics Pty Ltd",
            "invoice_date": None,       # absent → null, not hallucinated
            "currency": "GBP",
            "line_items": [
                {"description": "Annual subscription — Data pipeline tier", "amount": 4800.00}
            ]
        }
    }
]

def build_few_shot_messages(system_instruction: str) -> list[dict]:
    """Build the messages list with injected few-shot examples."""
    messages = [{"role": "system", "content": system_instruction}]

    for shot in FEW_SHOT_EXAMPLES:
        # User turn: the example document
        messages.append({
            "role": "user",
            "content": f"Extract invoice data:\n{shot['document']}"
        })
        # Assistant turn: the tool call (simulated correct extraction)
        # CLAUDE assistant turn:
        #   {"role": "assistant", "content": [
        #       {"type": "tool_use", "id": "toolu_xxx", "name": "extract_invoice",
        #        "input": shot["extraction"]}
        #   ]}
        fake_call_id = f"call_shot_{FEW_SHOT_EXAMPLES.index(shot)}"
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": fake_call_id,
                "type": "function",
                "function": {
                    "name": "extract_invoice",
                    "arguments": json.dumps(shot["extraction"])
                }
            }]
        })
        # Tool result turn: confirm the extraction was accepted
        # CLAUDE tool result:
        #   {"role": "user", "content": [{
        #       "type": "tool_result",
        #       "tool_use_id": "toolu_xxx",
        #       "content": json.dumps(shot["extraction"])
        #   }]}
        messages.append({
            "role": "tool",
            "tool_call_id": fake_call_id,
            "content": json.dumps(shot["extraction"])
        })

    return messages

SYSTEM = (
    "You are an invoice data extraction specialist. "
    "Extract all fields exactly as they appear. "
    "Return null for any field not present in the document — never invent values."
)

# ── Test documents (unusual formats the model might struggle with) ─────────────
TEST_DOCUMENTS = [
    (
        "Inline prose format",
        "As discussed in our meeting on the 15th of March 2024, we are pleased to "
        "issue invoice REF-MARCH-15 to your company from NovaBuild Solutions for "
        "project consulting totalling USD five hundred dollars ($500.00)."
    ),
    (
        "No date, foreign currency",
        "RECHNUNG Nr. INV-DE-0044\n"
        "Anbieter: Müller Softwarelösungen GmbH\n\n"
        "Softwareentwicklung (40h)    EUR 4,000.00\n"
        "Projektmanagement (10h)     EUR 1,000.00\n\n"
        "Gesamtbetrag: EUR 5,000.00"
    ),
    (
        "Amount-first reversed format",
        "PAYMENT REQUEST — PR-2024-88\nFuture Systems Inc  |  April 30 2024\n\n"
        "$3,000.00 Backend API development\n"
        "$1,500.00 QA and testing\n"
        "  $200.00 Deployment and documentation\n\n"
        "TOTAL USD: $4,700.00"
    ),
]

def extract(messages: list[dict], document: str) -> dict:
    """Run extraction using provided message history + the real document."""
    full_messages = messages + [
        {"role": "user", "content": f"Extract invoice data:\n{document}"}
    ]
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "extract_invoice"}},
        # CLAUDE: tool_choice={"type": "tool", "name": "extract_invoice"}
        messages=full_messages
    )
    tc = response.choices[0].message.tool_calls[0]
    # CLAUDE: return response.content[0].input
    return json.loads(tc.function.arguments)

def main():
    print("=== Version 4: Few-Shot Examples ===\n")
    print(f"Injecting {len(FEW_SHOT_EXAMPLES)} few-shot examples before each query.\n")

    zero_shot_messages = [{"role": "system", "content": SYSTEM}]
    few_shot_messages  = build_few_shot_messages(SYSTEM)

    for label, document in TEST_DOCUMENTS:
        print(f"── {label} ──")

        zs = extract(zero_shot_messages, document)
        fs = extract(few_shot_messages,  document)

        print(f"  Zero-shot: invoice={zs.get('invoice_number'):15}  "
              f"vendor={str(zs.get('vendor_name'))[:20]:20}  "
              f"date={zs.get('invoice_date')}")
        print(f"  Few-shot:  invoice={fs.get('invoice_number'):15}  "
              f"vendor={str(fs.get('vendor_name'))[:20]:20}  "
              f"date={fs.get('invoice_date')}")
        print()

    print("── How few-shot works ──")
    print("  Shots are injected as (user → assistant tool_call → tool_result) triples")
    print("  before the real query. The model learns the output format from examples.")
    print("  Best for: unusual document layouts, foreign formats, edge-case field positions.")

if __name__ == "__main__":
    main()
