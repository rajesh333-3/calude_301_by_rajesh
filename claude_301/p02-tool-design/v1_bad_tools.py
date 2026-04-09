"""
Version 1 — Minimal Descriptions (shows the problem)
=====================================================
Tools have vague descriptions. The model must GUESS which tool to call
based on the word "customer" vs "order" in the query — unreliable.

Expected error rate: ~15–30% misrouting.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
This file uses the OpenAI client. To switch to Claude (Anthropic):
  Client   : openai.OpenAI()                 → anthropic.Anthropic()
  Call     : client.chat.completions.create  → client.messages.create
  Tool fmt : {"type":"function","function"}  → {"name":..., "input_schema":...}
  Force    : tool_choice="required"          → tool_choice={"type": "any"}
  Model    : "gpt-4o-mini"                   → "claude-haiku-4-5"
  Response : choices[0].message.tool_calls   → response.content blocks
  Tool name: tc.function.name                → block.name (block.type=="tool_use")
  Args     : json.loads(tc.function.arguments) → block.input (already a dict)
"""

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Fake data ─────────────────────────────────────────────────────────────────
CUSTOMERS = {
    "CUST-001": {"name": "Alice Johnson", "email": "alice@example.com", "account_status": "active", "loyalty_tier": "gold"},
    "CUST-002": {"name": "Bob Smith",     "email": "bob@example.com",   "account_status": "active", "loyalty_tier": "silver"},
    "alice@example.com": "CUST-001",
    "bob@example.com":   "CUST-002",
}
ORDERS = {
    "ORD-12345": {"status": "shipped",    "total_amount": 129.99, "items": ["laptop stand", "USB hub"], "customer_id": "CUST-001"},
    "ORD-67890": {"status": "processing", "total_amount":  49.99, "items": ["keyboard"],               "customer_id": "CUST-002"},
}

# ── Tool implementations ──────────────────────────────────────────────────────
def get_customer(identifier: str) -> dict:
    if identifier in CUSTOMERS:
        cid = CUSTOMERS[identifier] if "@" in identifier else identifier
        return CUSTOMERS.get(cid, {"error": "not found"})
    return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
            "message": f"No customer found for identifier '{identifier}'"}

def lookup_order(identifier: str) -> dict:
    if identifier in ORDERS:
        return ORDERS[identifier]
    return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
            "message": f"No order found for identifier '{identifier}'"}

TOOL_MAP = {"get_customer": get_customer, "lookup_order": lookup_order}

# ── BAD tool definitions — vague, no boundaries ───────────────────────────────
# OpenAI format wraps each tool in {"type": "function", "function": {...}}
# CLAUDE format: {"name": ..., "description": ..., "input_schema": {...}}
BAD_TOOLS = [
    {
        "type": "function",       # CLAUDE: no "type" wrapper — fields go at top level
        "function": {             # CLAUDE: remove this nesting
            "name": "get_customer",
            "description": "Gets information",    # ← vague: causes misrouting
            "parameters": {       # CLAUDE: "input_schema" not "parameters"
                "type": "object",
                "properties": {"identifier": {"type": "string"}},
                "required": ["identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Gets order details",           # ← vague: causes misrouting
            "parameters": {
                "type": "object",
                "properties": {"identifier": {"type": "string"}},
                "required": ["identifier"]
            }
        }
    }
]

# ── 20 test queries — half clearly order-focused, half customer-focused ────────
TEST_QUERIES = [
    # Should route to lookup_order
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
    # Should route to get_customer
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

def run_query(query: str) -> str:
    """Run one query and return which tool was actually called."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",        # CLAUDE: model="claude-haiku-4-5"
                                    # Cheap/fast model chosen because it's more sensitive
                                    # to bad descriptions — makes the misrouting visible
        max_tokens=256,
        tools=BAD_TOOLS,
        tool_choice="required",     # CLAUDE: tool_choice={"type": "any"}
                                    # Force a tool call so we can measure routing accuracy
        messages=[{"role": "user", "content": query}]
    )
    msg = response.choices[0].message
    # CLAUDE:
    #   for block in response.content:
    #       if block.type == "tool_use":
    #           return block.name
    if msg.tool_calls:
        return msg.tool_calls[0].function.name
    return "no_tool"

def main():
    print("=== Version 1: BAD Tool Descriptions ===\n")
    print(f"{'Expected':<16} {'Got':<16} {'OK?':<6} Query")
    print("-" * 80)

    correct = 0
    wrong_cases = []

    for expected_tool, query in TEST_QUERIES:
        called = run_query(query)
        ok = called == expected_tool
        if ok:
            correct += 1
        else:
            wrong_cases.append((expected_tool, called, query))
        status = "✓" if ok else "✗"
        print(f"{expected_tool:<16} {called:<16} {status:<6} {query[:55]}")

    total = len(TEST_QUERIES)
    error_rate = (total - correct) / total * 100

    print(f"\n── Results ──")
    print(f"Correct:    {correct}/{total}")
    print(f"Error rate: {error_rate:.1f}%")

    if wrong_cases:
        print("\n── Wrong routings ──")
        for expected, got, q in wrong_cases:
            print(f"  Expected {expected}, got {got}: \"{q}\"")

    print("\nConclusion: Vague descriptions force the model to guess.")
    print("The word 'order' in a query doesn't guarantee lookup_order is called.")

if __name__ == "__main__":
    main()
