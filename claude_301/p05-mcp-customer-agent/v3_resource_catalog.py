"""
Version 3 — Resource Catalog: Read Before You Act
===================================================
MCP resources are readable data catalogs — not executable tools.
The agent reads policy://catalog ONCE before answering policy questions.

Without the resource:
  Agent calls get_customer → lookup_order → escalate_to_human just to
  discover what's possible. 3 exploratory tool calls wasted.

With the resource:
  Agent reads policy://catalog → knows refund limit, return window, escalation
  rules upfront → goes directly to the right action. 0 exploratory calls.

This is the primary value of MCP resources: give the agent visibility into
what's available so it doesn't have to explore via tool calls.

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  Reading resources:
    Both OpenAI and Claude bridge: session.read_resource("policy://catalog")
    The MCP client handles this — same code regardless of LLM provider.

  The difference is in how the resource content is injected:
    Manual bridge (this file): inject as a system message or user context block.
    CLAUDE native MCP: resource content is injected automatically by the SDK
                       before the first turn — no manual injection needed.
"""

import asyncio
import json
import sys
from openai import OpenAI
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
openai_client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Retrieve customer account by email or customer ID.",
            "parameters": {"type": "object", "properties": {
                "customer_email": {"type": "string"},
                "customer_id":    {"type": "string"}
            }}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Retrieve order details by order number (ORD-XXXXX).",
            "parameters": {"type": "object", "properties": {
                "order_number": {"type": "string"}
            }, "required": ["order_number"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process_refund",
            "description": "Process a refund for a verified order. Autonomous limit $500.",
            "parameters": {"type": "object", "properties": {
                "order_number": {"type": "string"},
                "amount":       {"type": "number"},
                "reason":       {"type": "string"}
            }, "required": ["order_number", "amount", "reason"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escalate to human agent. Required for refunds > $500.",
            "parameters": {"type": "object", "properties": {
                "customer_id":   {"type": "string"},
                "issue_summary": {"type": "string"},
                "priority":      {"type": "string", "enum": ["normal", "high", "urgent"]}
            }, "required": ["customer_id", "issue_summary"]}
        }
    }
]

# Fake tool implementations for counting calls
tool_call_log: list[dict] = []

def fake_get_customer(**kwargs) -> dict:
    tool_call_log.append({"tool": "get_customer", "args": kwargs})
    return {"customer_id": "CUST-001", "name": "Alice Chen", "account_status": "active"}

def fake_lookup_order(**kwargs) -> dict:
    tool_call_log.append({"tool": "lookup_order", "args": kwargs})
    return {"order_id": "ORD-12345", "status": "delivered", "total_amount": 129.99}

def fake_process_refund(**kwargs) -> dict:
    tool_call_log.append({"tool": "process_refund", "args": kwargs})
    return {"refund_id": "REF-001", "status": "approved", "amount": kwargs.get("amount")}

def fake_escalate_to_human(**kwargs) -> dict:
    tool_call_log.append({"tool": "escalate_to_human", "args": kwargs})
    return {"ticket_id": "TKT-001", "estimated_response_time": "1 hour"}

FAKE_TOOL_MAP = {
    "get_customer":    fake_get_customer,
    "lookup_order":    fake_lookup_order,
    "process_refund":  fake_process_refund,
    "escalate_to_human": fake_escalate_to_human,
}


def run_agent_without_resource(query: str) -> tuple[str, int]:
    """Run query with NO policy context — agent must explore via tool calls."""
    tool_call_log.clear()

    messages = [
        {"role": "system", "content": "You are a customer support agent."},
        {"role": "user",   "content": query}
    ]
    return _run_loop(messages)


def run_agent_with_resource(query: str, policy_content: str) -> tuple[str, int]:
    """Run query WITH policy catalog pre-loaded — agent knows rules upfront."""
    tool_call_log.clear()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a customer support agent.\n\n"
                "POLICY CATALOG (read this before acting):\n"
                f"{policy_content}\n\n"
                "Use this policy information to answer questions directly without "
                "exploratory tool calls."
            )
        },
        {"role": "user", "content": query}
    ]
    return _run_loop(messages)


def _run_loop(messages: list) -> tuple[str, int]:
    """Shared agentic loop. Returns (final_answer, tool_call_count)."""
    for _ in range(10):
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            max_tokens=512,
            tools=TOOLS,
            tool_choice="auto",    # CLAUDE: tool_choice={"type": "auto"}
            messages=messages
        )
        msg           = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "stop":
            return msg.content, len(tool_call_log)

        if finish_reason == "tool_calls":
            messages.append({
                "role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls
            })
            for tc in msg.tool_calls:
                args   = json.loads(tc.function.arguments)
                result = FAKE_TOOL_MAP[tc.function.name](**args)
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)
                })

    return "Max turns reached", len(tool_call_log)


async def fetch_policy_from_mcp() -> str:
    """Read the policy://catalog resource from the MCP server."""
    server_params = StdioServerParameters(command=sys.executable, args=["mcp_server.py"])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available resources
            resources = await session.list_resources()
            print(f"  [MCP] Available resources: {[r.uri for r in resources.resources]}")

            # Read the policy catalog
            # CLAUDE native MCP: resource content injected automatically — no read_resource() call
            content = await session.read_resource("policy://catalog")
            return content.contents[0].text


async def main():
    print("=== Version 3: Resource Catalog Experiment ===\n")

    # Fetch policy from MCP server
    print("Fetching policy://catalog from MCP server...")
    policy_content = await fetch_policy_from_mcp()
    print(f"  Policy loaded ({len(policy_content)} chars)\n")

    # Policy questions — should NOT require any tool calls when policy is known
    policy_queries = [
        "What is the return policy?",
        "Can I get a refund of $600 autonomously or does it need human approval?",
        "Does the agent handle competitor pricing exceptions?",
    ]

    # Action queries — always require tool calls regardless
    action_queries = [
        "Process a $80 refund for order ORD-12345, the product was defective.",
    ]

    print(f"{'Query':<50} {'Without resource':>17} {'With resource':>14}")
    print("-" * 85)

    total_saved = 0
    for query in policy_queries + action_queries:
        ans_wo, calls_wo = run_agent_without_resource(query)
        ans_wi, calls_wi = run_agent_with_resource(query, policy_content)
        saved = calls_wo - calls_wi
        total_saved += max(0, saved)
        tag = "← exploratory calls saved" if saved > 0 else ""
        print(f"{query[:49]:<50} {calls_wo:>6} tool calls  {calls_wi:>6} tool calls  {tag}")

    print(f"\n  Total exploratory tool calls eliminated: {total_saved}")
    print()
    print("── When to use resources vs tools ──")
    print("  resource → static/slow-changing data the agent needs for decisions")
    print("             (policies, catalogs, config, lookup tables)")
    print("  tool     → actions that change state or require live data")
    print("             (get_customer, process_refund, send_email)")
    print()
    print("  Reading a resource before acting is like reading the manual before calling support.")

if __name__ == "__main__":
    asyncio.run(main())
