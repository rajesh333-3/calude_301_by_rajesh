"""
Version 2 — Explicit Descriptions (shows the fix)
==================================================
Same 20 queries as v1. Only the tool descriptions change.
Explicit USE WHEN / DO NOT USE / INPUT FORMAT boundaries give
the model deterministic routing criteria → error rate drops to ~0%.

Key insight: the error rate improvement comes from removing ambiguity,
not from adding more tokens. Every added clause is load-bearing.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
This file uses the OpenAI client. To switch to Claude (Anthropic):
  Client   : openai.OpenAI()                 → anthropic.Anthropic()
  Call     : client.chat.completions.create  → client.messages.create
  Tool fmt : {"type":"function","function"}  → {"name":..., "input_schema":...}
  Force    : tool_choice="required"          → tool_choice={"type": "any"}
  Model    : "gpt-4o-mini"                   → "claude-haiku-4-5"
  Response : choices[0].message.tool_calls   → response.content blocks
  Tool name: tc.function.name                → block.name
  Args     : json.loads(tc.function.arguments) → block.input (already a dict)
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Same fake data as v1 ───────────────────────────────────────────────────────
CUSTOMERS = {
    "CUST-001": {"customer_id": "CUST-001", "name": "Alice Johnson", "email": "alice@example.com",
                 "account_status": "active", "loyalty_tier": "gold", "created_date": "2023-01-15"},
    "CUST-002": {"customer_id": "CUST-002", "name": "Bob Smith", "email": "bob@example.com",
                 "account_status": "active", "loyalty_tier": "silver", "created_date": "2023-06-20"},
    "alice@example.com": "CUST-001",
    "bob@example.com":   "CUST-002",
}
ORDERS = {
    "ORD-12345": {"order_id": "ORD-12345", "status": "shipped",    "total_amount": 129.99,
                  "items": ["laptop stand", "USB hub"], "customer_id": "CUST-001",
                  "created_date": "2024-03-10", "shipping_address": "123 Main St"},
    "ORD-67890": {"order_id": "ORD-67890", "status": "processing", "total_amount":  49.99,
                  "items": ["keyboard"], "customer_id": "CUST-002",
                  "created_date": "2024-03-15", "shipping_address": "456 Oak Ave"},
}

# ── Structured error responses (isError pattern) ──────────────────────────────
def get_customer(customer_email: str = None, customer_id: str = None) -> dict:
    identifier = customer_email or customer_id
    try:
        if not identifier:
            return {"isError": True, "errorCategory": "validation",
                    "isRetryable": False, "message": "Provide customer_email or customer_id"}
        # resolve email → ID
        if identifier in CUSTOMERS and isinstance(CUSTOMERS[identifier], str):
            identifier = CUSTOMERS[identifier]
        if identifier in CUSTOMERS and isinstance(CUSTOMERS[identifier], dict):
            return CUSTOMERS[identifier]
        return {"isError": True, "errorCategory": "not_found",
                "isRetryable": False, "message": f"No customer for '{identifier}'"}
    except TimeoutError:
        return {"isError": True, "errorCategory": "transient",
                "isRetryable": True, "message": "Database timeout, try again"}
    except PermissionError:
        return {"isError": True, "errorCategory": "permission",
                "isRetryable": False, "message": "Access denied to customer records"}

def lookup_order(order_number: str) -> dict:
    try:
        if order_number in ORDERS:
            return ORDERS[order_number]
        return {"isError": True, "errorCategory": "not_found",
                "isRetryable": False, "message": f"No order found for '{order_number}'"}
    except TimeoutError:
        return {"isError": True, "errorCategory": "transient",
                "isRetryable": True, "message": "Database timeout, try again"}

TOOL_MAP = {"get_customer": get_customer, "lookup_order": lookup_order}

# ── GOOD tool definitions — explicit, boundaries enforced ─────────────────────
# OpenAI format: {"type": "function", "function": {name, description, parameters}}
# CLAUDE format: {"name": ..., "description": ..., "input_schema": {...}}
GOOD_TOOLS = [
    {
        "type": "function",       # CLAUDE: no "type" wrapper
        "function": {             # CLAUDE: remove this nesting
            "name": "get_customer",
            "description": (
                "Retrieves customer account data by email address or customer ID.\n"
                "USE WHEN: verifying identity, getting account status, contact details, loyalty tier.\n"
                "INPUT: customer_email (format: user@domain.com) OR customer_id (format: CUST-XXXXX). "
                "At least one must be provided.\n"
                "OUTPUT: {customer_id, name, email, account_status, loyalty_tier, created_date}\n"
                "DO NOT USE to find orders — use lookup_order for that.\n"
                "ALWAYS call this BEFORE lookup_order when customer hasn't provided an order number."
            ),
            "parameters": {       # CLAUDE: "input_schema" not "parameters"
                "type": "object",
                "properties": {
                    "customer_email": {"type": "string",
                                       "description": "Customer email, format: user@domain.com"},
                    "customer_id":    {"type": "string",
                                       "description": "Customer ID, format: CUST-XXXXX"}
                    # CLAUDE supports nullable types as: "type": ["string", "null"]
                    # OpenAI: just omit "required" to make fields optional
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "Retrieves order details by order number ONLY.\n"
                "USE WHEN: customer explicitly provides an order number.\n"
                "INPUT: order_number (format: ORD-XXXXX) — must be an exact order number.\n"
                "OUTPUT: {order_id, status, items, total_amount, created_date, shipping_address}\n"
                "DO NOT USE to find customer accounts. DO NOT use with just a customer name or email.\n"
                "If no order number is available, call get_customer first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {"type": "string",
                                     "description": "Exact order number, format: ORD-XXXXX"}
                },
                "required": ["order_number"]
            }
        }
    }
]

# ── Same 20 test queries as v1 ─────────────────────────────────────────────────
TEST_QUERIES = [
    ("lookup_order", "What's the status of order #ORD-12345?"),
    ("lookup_order", "Can you check order ORD-67890 for me?"),
    ("lookup_order", "I need details on my recent order ORD-12345"),
    ("lookup_order", "Track my order number ORD-67890"),
    ("lookup_order", "Show me order ORD-12345 information"),
    ("lookup_order", "What items are in order ORD-67890?"),
    ("lookup_order", "Is order ORD-12345 shipped yet?"),
    ("lookup_order", "Pull up order ORD-67890"),
    ("lookup_order", "Get order details for ORD-12345"),
    ("lookup_order", "Check the status for ORD-67890"),
    ("get_customer", "Look up customer CUST-001"),
    ("get_customer", "What's the account status for alice@example.com?"),
    ("get_customer", "Find customer info for CUST-002"),
    ("get_customer", "Get the loyalty tier for bob@example.com"),
    ("get_customer", "Show me the customer profile for CUST-001"),
    ("get_customer", "Is CUST-002 an active customer?"),
    ("get_customer", "Retrieve account details for alice@example.com"),
    ("get_customer", "What's the loyalty tier of CUST-001?"),
    ("get_customer", "Look up account CUST-002"),
    ("get_customer", "Find the email on file for CUST-001"),
]

def run_query(query: str) -> tuple[str, dict]:
    """Run one query, execute the tool, return (tool_name, result)."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",        # CLAUDE: model="claude-haiku-4-5"
        max_tokens=256,
        tools=GOOD_TOOLS,
        tool_choice="required",     # CLAUDE: tool_choice={"type": "any"}
        messages=[{"role": "user", "content": query}]
    )
    msg = response.choices[0].message
    # CLAUDE:
    #   for block in response.content:
    #       if block.type == "tool_use":
    #           fn = TOOL_MAP[block.name]
    #           result = fn(**block.input)   ← block.input is already a dict
    #           return block.name, result
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        fn = TOOL_MAP[tc.function.name]
        inputs = json.loads(tc.function.arguments)   # CLAUDE: block.input (no json.loads needed)
        result = fn(**inputs)
        return tc.function.name, result
    return "no_tool", {}

def main():
    print("=== Version 2: GOOD Tool Descriptions ===\n")
    print(f"{'Expected':<16} {'Got':<16} {'OK?':<6} Query")
    print("-" * 80)

    correct = 0
    wrong_cases = []

    for expected_tool, query in TEST_QUERIES:
        called, result = run_query(query)
        ok = called == expected_tool
        if ok:
            correct += 1
        else:
            wrong_cases.append((expected_tool, called, query))
        status = "✓" if ok else "✗"
        error_flag = " [isError]" if isinstance(result, dict) and result.get("isError") else ""
        print(f"{expected_tool:<16} {called:<16} {status:<6} {query[:50]}{error_flag}")

    total = len(TEST_QUERIES)
    error_rate = (total - correct) / total * 100

    print(f"\n── Results ──")
    print(f"Correct:    {correct}/{total}")
    print(f"Error rate: {error_rate:.1f}%")

    if wrong_cases:
        print("\n── Wrong routings ──")
        for expected, got, q in wrong_cases:
            print(f"  Expected {expected}, got {got}: \"{q}\"")
    else:
        print("\n✓ Zero misroutings — explicit descriptions eliminated all ambiguity.")

    print("\n── What changed ──")
    print("  v1: 'Gets customer information'  →  model guesses from query words")
    print("  v2: USE WHEN / INPUT FORMAT / DO NOT USE  →  deterministic routing")

if __name__ == "__main__":
    main()
