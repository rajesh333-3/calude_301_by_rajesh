"""
Version 3 — tool_choice Configurations + Structured Errors
===========================================================
Experiments with:
  "auto"     → Model decides whether to use a tool at all (may respond in text)
  "required" → Model MUST call at least one tool (no conversational text)
  forced     → Model MUST call a specific tool regardless of input

Also demonstrates the isError / errorCategory / isRetryable pattern
for each error type: not_found, transient, permission, validation.

When to use each:
  auto     → Normal assistant behavior; tool use is optional
  required → You need a structured response every time (e.g., API that parses tool output)
  forced   → Testing a specific tool; onboarding flows that must collect info

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
This file uses the OpenAI client. To switch to Claude (Anthropic):
  Client   : openai.OpenAI()                  → anthropic.Anthropic()
  Call     : client.chat.completions.create   → client.messages.create
  Tool fmt : {"type":"function","function"}   → {"name":..., "input_schema":...}
  auto     : tool_choice="auto"               → tool_choice={"type": "auto"}   (same effect)
  required : tool_choice="required"           → tool_choice={"type": "any"}
  forced   : tool_choice={"type":"function",  → tool_choice={"type": "tool",
               "function":{"name": X}}              "name": X}
  Finish   : choices[0].finish_reason         → response.stop_reason
  Tool use : message.tool_calls               → response.content blocks (type=="tool_use")
  Tool name: tc.function.name                 → block.name
  Args     : json.loads(tc.function.arguments)→ block.input (already a dict)
  Text     : message.content                  → block.text  (block.type=="text")
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Same data + tools as v2 ───────────────────────────────────────────────────
CUSTOMERS = {
    "CUST-001": {"customer_id": "CUST-001", "name": "Alice Johnson",
                 "email": "alice@example.com", "account_status": "active",
                 "loyalty_tier": "gold", "created_date": "2023-01-15"},
}
ORDERS = {
    "ORD-12345": {"order_id": "ORD-12345", "status": "shipped",
                  "total_amount": 129.99, "items": ["laptop stand", "USB hub"],
                  "customer_id": "CUST-001", "created_date": "2024-03-10"},
}

# OpenAI format: {"type": "function", "function": {...}}
# CLAUDE format: {"name": ..., "description": ..., "input_schema": {...}}
TOOLS = [
    {
        "type": "function",       # CLAUDE: no "type" wrapper
        "function": {             # CLAUDE: remove this nesting
            "name": "get_customer",
            "description": (
                "Retrieves customer account data by email address or customer ID.\n"
                "USE WHEN: verifying identity, getting account status, contact details, loyalty tier.\n"
                "INPUT: customer_email (format: user@domain.com) OR customer_id (format: CUST-XXXXX).\n"
                "DO NOT USE to find orders — use lookup_order for that."
            ),
            "parameters": {       # CLAUDE: "input_schema" not "parameters"
                "type": "object",
                "properties": {
                    "customer_email": {"type": "string"},
                    "customer_id":    {"type": "string"}
                    # CLAUDE: supports nullable: "type": ["string", "null"]
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
                "USE WHEN: customer explicitly provides an order number (format: ORD-XXXXX).\n"
                "DO NOT USE to find customer accounts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {"type": "string"}
                },
                "required": ["order_number"]
            }
        }
    }
]

# ── Structured error responses ────────────────────────────────────────────────
def get_customer(customer_email: str = None, customer_id: str = None) -> dict:
    identifier = customer_email or customer_id

    if not identifier:
        return {"isError": True, "errorCategory": "validation", "isRetryable": False,
                "message": "Must provide customer_email or customer_id"}

    if identifier == "CUST-999":      # simulate permission denied
        return {"isError": True, "errorCategory": "permission", "isRetryable": False,
                "message": "Access denied — you lack permission to view this customer record"}

    if identifier == "CUST-SLOW":     # simulate timeout
        return {"isError": True, "errorCategory": "transient", "isRetryable": True,
                "message": "Database timeout — safe to retry"}

    if identifier in CUSTOMERS:
        return CUSTOMERS[identifier]

    return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
            "message": f"No customer found for '{identifier}'"}

def lookup_order(order_number: str) -> dict:
    if not order_number.startswith("ORD-"):
        return {"isError": True, "errorCategory": "validation", "isRetryable": False,
                "message": f"Invalid format '{order_number}' — order numbers must be ORD-XXXXX"}
    if order_number in ORDERS:
        return ORDERS[order_number]
    return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
            "message": f"No order found for '{order_number}'"}

TOOL_MAP = {"get_customer": get_customer, "lookup_order": lookup_order}

def call_tool_if_any(response) -> str:
    """Execute any tool calls in the response; return summary string."""
    parts = []
    msg = response.choices[0].message

    # Text response
    # CLAUDE: for block in response.content:
    #             if block.type == "text": parts.append(f"[text] {block.text[:80]}")
    if msg.content:
        parts.append(f"[text] {msg.content[:80]}")

    # Tool calls
    # CLAUDE: elif block.type == "tool_use":
    #             fn = TOOL_MAP[block.name]
    #             result = fn(**block.input)  ← block.input is already a dict
    if msg.tool_calls:
        for tc in msg.tool_calls:
            fn = TOOL_MAP[tc.function.name]
            inputs = json.loads(tc.function.arguments)  # CLAUDE: block.input (no json.loads)
            result = fn(**inputs)
            if isinstance(result, dict) and result.get("isError"):
                parts.append(
                    f"[tool:{tc.function.name}] isError=True "
                    f"category={result['errorCategory']} "
                    f"retryable={result['isRetryable']} "
                    f"→ {result['message']}"
                )
            else:
                parts.append(f"[tool:{tc.function.name}] → {result}")

    return "\n  ".join(parts) if parts else "(no content)"


# ── Experiment 1: tool_choice = "auto" ───────────────────────────────────────
def demo_auto():
    print("\n" + "=" * 60)
    print("tool_choice='auto'  — model decides whether to use a tool")
    print("=" * 60)

    cases = [
        ("Order question (tool expected)",    "What's the status of order ORD-12345?"),
        ("Conversational (no tool expected)", "Hi! What can you help me with?"),
        ("Ambiguous (could go either way)",   "I have a problem with my account"),
    ]

    for label, query in cases:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=256,
            tools=TOOLS,
            tool_choice="auto",         # CLAUDE: tool_choice={"type": "auto"}
            messages=[{"role": "user", "content": query}]
        )
        finish_reason = resp.choices[0].finish_reason
        # CLAUDE: tool_used = any(b.type == "tool_use" for b in resp.content)
        tool_used = finish_reason == "tool_calls"
        print(f"\n  [{label}]")
        print(f"  Query: {query}")
        print(f"  Tool used: {tool_used}  |  finish_reason: {finish_reason}")
        # CLAUDE: resp.stop_reason instead of finish_reason
        print(f"  {call_tool_if_any(resp)}")


# ── Experiment 2: tool_choice = "required" ───────────────────────────────────
def demo_required():
    print("\n" + "=" * 60)
    print("tool_choice='required'  — MUST call at least one tool, no chat text")
    # CLAUDE: tool_choice={"type": "any"}
    print("=" * 60)

    cases = [
        ("Conversational (forced to use a tool anyway)", "Hello, how are you?"),
        ("Clear order query",                            "Check order ORD-12345"),
        ("Vague query",                                  "I need some help"),
    ]

    for label, query in cases:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=256,
            tools=TOOLS,
            tool_choice="required",     # CLAUDE: tool_choice={"type": "any"}
            messages=[{"role": "user", "content": query}]
        )
        print(f"\n  [{label}]")
        print(f"  Query: {query}")
        print(f"  {call_tool_if_any(resp)}")


# ── Experiment 3: forced tool selection ──────────────────────────────────────
def demo_forced():
    print("\n" + "=" * 60)
    print("tool_choice forced  — pin to a SPECIFIC tool regardless of input")
    print("=" * 60)

    cases = [
        ("Input looks like order — but we force get_customer", "CUST-001",          "get_customer"),
        ("Input looks like customer — but we force lookup_order", "alice@example.com", "lookup_order"),
    ]

    for label, identifier, forced_tool in cases:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=256,
            tools=TOOLS,
            # OpenAI forced tool:
            tool_choice={"type": "function", "function": {"name": forced_tool}},
            # CLAUDE forced tool:
            # tool_choice={"type": "tool", "name": forced_tool}
            messages=[{"role": "user", "content": f"Look up {identifier}"}]
        )
        print(f"\n  [{label}]")
        print(f"  Forced tool: {forced_tool}")
        print(f"  {call_tool_if_any(resp)}")


# ── Experiment 4: structured error responses ──────────────────────────────────
def demo_structured_errors():
    print("\n" + "=" * 60)
    print("Structured errors: isError / errorCategory / isRetryable")
    print("=" * 60)

    error_cases = [
        ("not_found",  get_customer, {"customer_id": "CUST-999X"}),
        ("transient",  get_customer, {"customer_id": "CUST-SLOW"}),
        ("permission", get_customer, {"customer_id": "CUST-999"}),
        ("validation", get_customer, {}),
        ("bad_format", lookup_order, {"order_number": "BADFORMAT"}),
    ]

    for label, fn, kwargs in error_cases:
        result = fn(**kwargs)
        if result.get("isError"):
            print(f"\n  [{label}]")
            print(f"  isError:       {result['isError']}")
            print(f"  errorCategory: {result['errorCategory']}")
            print(f"  isRetryable:   {result['isRetryable']}")
            print(f"  message:       {result['message']}")

    print("\n── When to retry ──")
    print("  transient (isRetryable=True)  → safe to retry with backoff")
    print("  not_found / permission / validation (isRetryable=False) → fix the call first")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Version 3: tool_choice Configurations + Structured Errors ===")

    demo_auto()
    demo_required()
    demo_forced()
    demo_structured_errors()

    print("\n\n── Summary: when to use each tool_choice ──")
    print("  auto     → Default. Tool use is optional; model decides based on query.")
    print("  required → You need structured output every time (API integration, parsers).")
    print("  forced   → Testing, onboarding, or ensuring a specific tool always fires.")
    print()
    print("── OpenAI → Claude translation ──")
    print('  tool_choice="auto"                              → {"type": "auto"}')
    print('  tool_choice="required"                          → {"type": "any"}')
    print('  tool_choice={"type":"function","function":{..}} → {"type":"tool","name":X}')
