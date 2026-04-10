"""
MCP Customer Support Server
============================
Exposes 4 tools + 1 resource via the MCP protocol.
Provider-agnostic — this file does NOT change between OpenAI and Claude.
The MCP protocol is a separate layer from the LLM API.

Run standalone to verify server starts:
    python mcp_server.py

Or connect via the agent:
    python agent.py

── What MCP exposes ──────────────────────────────────────────────────────────
  tools     → executable functions the agent can call
  resources → readable data catalogs (agent reads before answering)
  prompts   → reusable templates (not used here)

── Env vars (never hardcode credentials) ────────────────────────────────────
  SUPPORT_DB_URL    → injected from .mcp.json env block
  SUPPORT_API_KEY   → injected from .mcp.json env block
"""

import json
import os
from mcp.server.fastmcp import FastMCP

app = FastMCP("customer-support")

# ── Fake data (replace with real DB calls using os.getenv("SUPPORT_DB_URL")) ──
CUSTOMERS = {
    "CUST-001": {"customer_id": "CUST-001", "name": "Alice Chen",
                 "email": "alice@example.com", "account_status": "active",
                 "loyalty_tier": "gold", "created_date": "2023-01-15"},
    "CUST-002": {"customer_id": "CUST-002", "name": "Bob Smith",
                 "email": "bob@example.com",  "account_status": "active",
                 "loyalty_tier": "silver", "created_date": "2023-06-20"},
    "alice@example.com": "CUST-001",
    "bob@example.com":   "CUST-002",
}
ORDERS = {
    "ORD-12345": {"order_id": "ORD-12345", "status": "shipped",
                  "total_amount": 129.99, "items": ["laptop stand", "USB hub"],
                  "customer_id": "CUST-001", "created_date": "2024-03-10"},
    "ORD-67890": {"order_id": "ORD-67890", "status": "processing",
                  "total_amount": 600.00,  "items": ["keyboard"],
                  "customer_id": "CUST-002", "created_date": "2024-03-15"},
}
REFUNDS = {}   # track processed refunds in memory


# ── Tool 1: get_customer ──────────────────────────────────────────────────────
@app.tool()
def get_customer(customer_email: str = None, customer_id: str = None) -> dict:
    """Retrieve customer account by email or customer ID.

    Use for: identity verification, account status, loyalty tier.
    INPUT: customer_email (format: user@domain.com) OR customer_id (format: CUST-XXXXX).
    OUTPUT: {customer_id, name, email, account_status, loyalty_tier}
    Use BEFORE lookup_order when no order number is available.
    DO NOT USE to find orders.
    """
    identifier = customer_email or customer_id
    if not identifier:
        return {"isError": True, "errorCategory": "validation", "isRetryable": False,
                "message": "Provide customer_email or customer_id"}

    # Resolve email → customer_id
    if identifier in CUSTOMERS and isinstance(CUSTOMERS[identifier], str):
        identifier = CUSTOMERS[identifier]

    if identifier in CUSTOMERS and isinstance(CUSTOMERS[identifier], dict):
        return CUSTOMERS[identifier]

    return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
            "message": f"No customer found for '{identifier}'"}


# ── Tool 2: lookup_order ──────────────────────────────────────────────────────
@app.tool()
def lookup_order(order_number: str) -> dict:
    """Retrieve order details by order number.

    Use WHEN: customer explicitly provides an order number.
    INPUT: order_number (format: ORD-XXXXX).
    OUTPUT: {order_id, status, items, total_amount, created_date}
    DO NOT USE without an exact order number. Call get_customer first if no order number.
    """
    if not order_number.startswith("ORD-"):
        return {"isError": True, "errorCategory": "validation", "isRetryable": False,
                "message": f"Invalid format '{order_number}' — must be ORD-XXXXX"}
    if order_number in ORDERS:
        return ORDERS[order_number]
    return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
            "message": f"Order '{order_number}' not found"}


# ── Tool 3: process_refund ────────────────────────────────────────────────────
@app.tool()
def process_refund(order_number: str, amount: float, reason: str) -> dict:
    """Process a refund for a given order.

    Use WHEN: customer requests refund and order is verified.
    INPUT: order_number (ORD-XXXXX), amount (float, ≤ order total), reason (string).
    LIMIT: autonomous approval ≤ $600. Amounts > $600 require escalate_to_human first.
    DO NOT CALL without verifying order exists via lookup_order first.
    """
    if amount > 600:
        return {"isError": True, "errorCategory": "permission", "isRetryable": False,
                "message": f"Refund of ${amount:.2f} exceeds autonomous limit ($600). "
                           "Call escalate_to_human before processing."}

    if order_number not in ORDERS:
        return {"isError": True, "errorCategory": "not_found", "isRetryable": False,
                "message": f"Order '{order_number}' not found — verify before refunding"}

    order = ORDERS[order_number]
    if amount > order["total_amount"]:
        return {"isError": True, "errorCategory": "validation", "isRetryable": False,
                "message": f"Refund amount ${amount:.2f} exceeds order total "
                           f"${order['total_amount']:.2f}"}

    refund_id = f"REF-{order_number}-{int(amount*100)}"
    REFUNDS[refund_id] = {"refund_id": refund_id, "order_number": order_number,
                          "amount": amount, "reason": reason, "status": "approved"}
    return {"refund_id": refund_id, "status": "approved", "amount": amount,
            "message": f"Refund of ${amount:.2f} approved for {order_number}"}


# ── Tool 4: escalate_to_human ──────────────────────────────────────────────────
@app.tool()
def escalate_to_human(customer_id: str, issue_summary: str, priority: str = "normal") -> dict:
    """Escalate a case to a human support agent.

    Use WHEN: refund > $600, competitor pricing exceptions, or issue cannot be resolved.
    INPUT: customer_id, issue_summary (clear description), priority ("normal"|"high"|"urgent").
    OUTPUT: {ticket_id, estimated_response_time, assigned_team}
    This is a terminal action — do NOT attempt to resolve the issue after escalating.
    """
    if priority not in ("normal", "high", "urgent"):
        return {"isError": True, "errorCategory": "validation", "isRetryable": False,
                "message": f"Invalid priority '{priority}' — use normal/high/urgent"}

    ticket_id = f"TKT-{customer_id}-{hash(issue_summary) % 10000:04d}"
    response_times = {"normal": "4 hours", "high": "1 hour", "urgent": "15 minutes"}

    return {"ticket_id": ticket_id, "status": "created", "priority": priority,
            "estimated_response_time": response_times[priority],
            "assigned_team": "tier-2-support",
            "message": f"Case escalated. Agent will contact customer within "
                       f"{response_times[priority]}."}


# ── Resource: policy catalog ──────────────────────────────────────────────────
@app.resource("policy://catalog")
def policy_catalog() -> str:
    """Policy summaries — agent reads this BEFORE answering any policy questions.

    Reading this resource eliminates exploratory tool calls: instead of calling
    get_customer + lookup_order to discover what's possible, the agent reads the
    policy catalog once and knows the rules upfront.
    """
    policies = {
        "return_policy": {
            "summary": "30-day return window from purchase date",
            "conditions": ["Receipt or order number required",
                           "Original packaging preferred but not mandatory",
                           "Items must be unused and undamaged"],
            "exceptions": ["Digital downloads non-refundable",
                           "Customized/personalized items non-refundable"]
        },
        "refund_policy": {
            "summary": "Refunds processed within 5-7 business days",
            "autonomous_limit": 600.00,
            "approval_required_above": 600.00,
            "methods": ["Original payment method", "Store credit (+10% bonus)"],
            "escalation_trigger": "Amount > $600 → escalate_to_human before processing"
        },
        "competitor_pricing": {
            "summary": "Price matching not standard policy",
            "rule": "NOT covered by autonomous agents — always escalate_to_human",
            "exception_process": "Human agent discretion only"
        },
        "loyalty_tiers": {
            "gold":   {"benefits": "Free shipping, priority support, 10% discount"},
            "silver": {"benefits": "Free shipping on orders >$50, 5% discount"},
            "bronze": {"benefits": "Standard shipping rates"}
        }
    }
    return json.dumps(policies, indent=2)


if __name__ == "__main__":
    # Run the MCP server (stdio transport — agent connects via subprocess)
    app.run()
