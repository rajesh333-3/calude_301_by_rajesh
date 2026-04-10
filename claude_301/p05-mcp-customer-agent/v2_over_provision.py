"""
Version 2 — Tool Over-Provisioning Experiment
==============================================
Demonstrates how adding irrelevant tools degrades the model's tool selection.

The spec: give the agent 4 correct tools, then add 14 irrelevant ones (18 total).
Observe: the model may call the wrong tool, ask for clarification, or refuse.
Then trim back to 4. Observe: routing accuracy recovers.

Why this happens:
  The model reads ALL tool descriptions when deciding which to call.
  More tools → more surface area for confusion → higher misrouting rate.
  It's the same problem as p02 v1 (vague descriptions) but caused by volume, not clarity.

Rule: only expose tools the agent can plausibly need for the current task.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Same as agent.py. Tool over-provisioning is a model behavior problem,
  not an API difference — affects both OpenAI and Claude equally.
  CLAUDE: tool_choice={"type":"any"} instead of tool_choice="required"
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── The 4 correct tools ────────────────────────────────────────────────────────
CORRECT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": (
                "Retrieve customer account by email or customer ID.\n"
                "USE WHEN: identity verification, account status, loyalty tier.\n"
                "INPUT: customer_email OR customer_id.\n"
                "DO NOT USE to find orders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_email": {"type": "string"},
                    "customer_id":    {"type": "string"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "Retrieve order details by order number.\n"
                "USE WHEN: customer provides an order number (ORD-XXXXX).\n"
                "DO NOT USE without an exact order number."
            ),
            "parameters": {
                "type": "object",
                "properties": {"order_number": {"type": "string"}},
                "required": ["order_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process_refund",
            "description": (
                "Process a refund for a verified order.\n"
                "USE WHEN: customer requests refund and order is verified.\n"
                "LIMIT: autonomous ≤ $500. Above that, escalate_to_human first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {"type": "string"},
                    "amount":       {"type": "number"},
                    "reason":       {"type": "string"}
                },
                "required": ["order_number", "amount", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Escalate to a human support agent.\n"
                "USE WHEN: refund > $500, competitor pricing, or unresolvable issue.\n"
                "Terminal action — do NOT continue resolving after escalating."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id":    {"type": "string"},
                    "issue_summary":  {"type": "string"},
                    "priority":       {"type": "string", "enum": ["normal", "high", "urgent"]}
                },
                "required": ["customer_id", "issue_summary"]
            }
        }
    }
]

# ── 14 irrelevant tools that pollute the selection space ──────────────────────
NOISE_TOOLS = [
    {"type": "function", "function": {"name": "send_marketing_email",
     "description": "Send a promotional email to a customer segment.",
     "parameters": {"type": "object", "properties": {"segment": {"type": "string"},
      "template_id": {"type": "string"}}, "required": ["segment", "template_id"]}}},
    {"type": "function", "function": {"name": "update_inventory",
     "description": "Update stock levels for a product SKU.",
     "parameters": {"type": "object", "properties": {"sku": {"type": "string"},
      "quantity": {"type": "number"}}, "required": ["sku", "quantity"]}}},
    {"type": "function", "function": {"name": "generate_invoice",
     "description": "Generate a PDF invoice for an order.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}},
      "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "get_product_details",
     "description": "Retrieve product catalog entry by SKU.",
     "parameters": {"type": "object", "properties": {"sku": {"type": "string"}},
      "required": ["sku"]}}},
    {"type": "function", "function": {"name": "apply_discount_code",
     "description": "Apply a discount code to an active cart.",
     "parameters": {"type": "object", "properties": {"cart_id": {"type": "string"},
      "code": {"type": "string"}}, "required": ["cart_id", "code"]}}},
    {"type": "function", "function": {"name": "schedule_delivery",
     "description": "Schedule a delivery window for a shipment.",
     "parameters": {"type": "object", "properties": {"shipment_id": {"type": "string"},
      "window": {"type": "string"}}, "required": ["shipment_id", "window"]}}},
    {"type": "function", "function": {"name": "request_supplier_quote",
     "description": "Request a pricing quote from a registered supplier.",
     "parameters": {"type": "object", "properties": {"supplier_id": {"type": "string"},
      "product_list": {"type": "array", "items": {"type": "string"}}},
      "required": ["supplier_id", "product_list"]}}},
    {"type": "function", "function": {"name": "archive_customer_account",
     "description": "Archive (soft-delete) a customer account.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"},
      "reason": {"type": "string"}}, "required": ["customer_id"]}}},
    {"type": "function", "function": {"name": "flag_fraudulent_order",
     "description": "Flag an order for fraud review.",
     "parameters": {"type": "object", "properties": {"order_id": {"type": "string"},
      "evidence": {"type": "string"}}, "required": ["order_id", "evidence"]}}},
    {"type": "function", "function": {"name": "sync_crm_contact",
     "description": "Synchronise a customer record with the CRM system.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}},
      "required": ["customer_id"]}}},
    {"type": "function", "function": {"name": "create_support_ticket",
     "description": "Create a new support ticket in the helpdesk system.",
     "parameters": {"type": "object", "properties": {"subject": {"type": "string"},
      "body": {"type": "string"}, "priority": {"type": "string"}},
      "required": ["subject", "body"]}}},
    {"type": "function", "function": {"name": "log_customer_feedback",
     "description": "Log qualitative feedback from a customer interaction.",
     "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"},
      "feedback": {"type": "string"}, "rating": {"type": "number"}},
      "required": ["customer_id", "feedback"]}}},
    {"type": "function", "function": {"name": "export_order_report",
     "description": "Export order data to CSV for a date range.",
     "parameters": {"type": "object", "properties": {"start_date": {"type": "string"},
      "end_date": {"type": "string"}}, "required": ["start_date", "end_date"]}}},
    {"type": "function", "function": {"name": "get_warehouse_location",
     "description": "Get the warehouse location for a product SKU.",
     "parameters": {"type": "object", "properties": {"sku": {"type": "string"},
      "warehouse_id": {"type": "string"}}, "required": ["sku"]}}},
]

OVERPROVISIONED_TOOLS = CORRECT_TOOLS + NOISE_TOOLS   # 18 tools total

# ── Test queries — should always route to a specific correct tool ─────────────
TEST_CASES = [
    ("get_customer",      "What is the account status for alice@example.com?"),
    ("lookup_order",      "Get me the details on order ORD-12345"),
    ("process_refund",    "Process a $50 refund for order ORD-12345, item was broken"),
    ("escalate_to_human", "Customer CUST-001 wants a $700 refund, please escalate"),
    ("get_customer",      "Is CUST-002 an active customer?"),
    ("lookup_order",      "Check the shipping status of ORD-67890"),
]

def run_single_turn(query: str, tools: list) -> str:
    """Run one query, return the first tool called."""
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=256,
        tools=tools,
        tool_choice="required",     # CLAUDE: tool_choice={"type": "any"}
        messages=[{"role": "user", "content": query}]
    )
    msg = response.choices[0].message
    if msg.tool_calls:
        return msg.tool_calls[0].function.name
    return "no_tool"

def measure_accuracy(tools: list, label: str) -> float:
    print(f"\n{'='*60}")
    print(f"{label}  ({len(tools)} tools)")
    print(f"{'='*60}")
    print(f"{'Expected':<22} {'Got':<22} {'OK?':<5} Query")
    print("-" * 80)

    correct = 0
    for expected, query in TEST_CASES:
        called = run_single_turn(query, tools)
        ok = called == expected
        if ok:
            correct += 1
        status = "✓" if ok else "✗"
        print(f"{expected:<22} {called:<22} {status:<5} {query[:40]}")

    rate = correct / len(TEST_CASES) * 100
    print(f"\n  Accuracy: {correct}/{len(TEST_CASES)} = {rate:.0f}%")
    return rate

def main():
    print("=== Version 2: Tool Over-Provisioning Experiment ===")
    print("Same 6 queries, same model. Only the tool count changes.\n")

    acc_4  = measure_accuracy(CORRECT_TOOLS,       "CORRECT (4 tools)")
    acc_18 = measure_accuracy(OVERPROVISIONED_TOOLS, "OVER-PROVISIONED (18 tools)")
    acc_4b = measure_accuracy(CORRECT_TOOLS,       "TRIMMED BACK (4 tools)")

    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print(f"  4 tools (correct)     : {acc_4:.0f}% accuracy")
    print(f"  18 tools (noise added): {acc_18:.0f}% accuracy  ← degraded")
    print(f"  4 tools (trimmed)     : {acc_4b:.0f}% accuracy  ← recovered")
    print()
    print("Rule: only expose tools the agent can plausibly need for the current task.")
    print("Each irrelevant tool is a distractor — more distractors = more misrouting.")

if __name__ == "__main__":
    main()
