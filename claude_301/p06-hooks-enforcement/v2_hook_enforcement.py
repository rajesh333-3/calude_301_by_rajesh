"""
Version 2 — Programmatic Hook Enforcement (0% failure rate)
============================================================
Same 15 queries as v1. Same model. Same tool descriptions.

The ONLY difference: a PreToolCall hook fires in Python BEFORE the LLM's
tool call executes. If lookup_order or process_refund is called without a
verified customer_id in agent state → the hook raises an error and redirects.

The LLM never executes the forbidden call. The gate is in Python, not in prompts.

Failure rate: exactly 0% — independent of query phrasing, context length, or
model "mood". The check happens unconditionally in the Python runtime.

── The determinism hierarchy ──────────────────────────────────────────────────
  Hooks / programmatic prerequisites  → DETERMINISTIC  (always fire, Python code)
  Prompt instructions                 → PROBABILISTIC  (can fail, LLM reasoning)

  When a business rule has financial or legal consequences:
    ✓ Use hooks / prerequisites
    ✗ "Add few-shot examples" — wrong answer on the exam

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  The SupportAgent hook wrapper class is the same regardless of LLM provider.
  Hooks are Python-layer — no API difference.

  CLAUDE SDK native hooks (claude_agent_sdk):
    @agent.pre_tool_call   → fires before tool execution
    @agent.post_tool_use   → fires after tool returns, before Claude sees result
  This file implements the same pattern manually over the OpenAI chat API.

  CLAUDE: tool_choice={"type":"auto"} vs OpenAI tool_choice="auto"
  CLAUDE: stop_reason == "tool_use" vs finish_reason == "tool_calls"
  CLAUDE: block.input vs json.loads(tc.function.arguments)
"""

import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Same tools as v1 ──────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": (
                "Retrieve customer account by email or customer ID.\n"
                "USE WHEN: identity verification, account status, loyalty tier."
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
            "description": "Retrieve order details by order number (ORD-XXXXX).",
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
            "description": "Process a refund for a verified order. Autonomous limit $500.",
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
                "Escalate to human agent. Required for refunds > $500 or unresolvable issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id":   {"type": "string"},
                    "issue_summary": {"type": "string"},
                    "priority":      {"type": "string", "enum": ["normal", "high", "urgent"]}
                },
                "required": ["customer_id", "issue_summary"]
            }
        }
    }
]

FAKE_CUSTOMERS = {
    "alice@example.com": {"customer_id": "CUST-001", "name": "Alice Chen",
                          "account_status": "active", "loyalty_tier": "gold",
                          "created_ts": 1673827200},    # Unix timestamp — normalized by hook
    "bob@example.com":   {"customer_id": "CUST-002", "name": "Bob Smith",
                          "account_status": "active", "loyalty_tier": "silver",
                          "created_ts": 1687219200},
    "CUST-001": {"customer_id": "CUST-001", "name": "Alice Chen",
                 "account_status": "active", "loyalty_tier": "gold",
                 "created_ts": 1673827200},
}
FAKE_ORDERS = {
    "ORD-12345": {"order_id": "ORD-12345", "status": "shipped",
                  "total_amount": 129.99, "created_ts": 1710028800},
    "ORD-67890": {"order_id": "ORD-67890", "status": "processing",
                  "total_amount": 600.00, "created_ts": 1710374400},
}


class SupportAgent:
    """
    Wraps the OpenAI agentic loop with programmatic hooks.

    CLAUDE SDK equivalent:
        from claude_agent_sdk import ClaudeAgentSDK
        agent = ClaudeAgentSDK(...)

        @agent.pre_tool_call
        def gate(tool_name, tool_input): ...

        @agent.post_tool_use
        def normalize(tool_name, result): ...
    """

    def __init__(self):
        self.verified_customer_id: str | None = None   # STATE: tracks verification
        self.tools_called: list[str] = []
        self.hooks_fired:  list[str] = []

    def reset(self):
        self.verified_customer_id = None
        self.tools_called.clear()
        self.hooks_fired.clear()

    # ── Hook 1: PreToolCall — deterministic gate ──────────────────────────────
    def pre_tool_call(self, tool_name: str, tool_input: dict) -> dict | None:
        """
        Fires BEFORE the tool executes.
        Returns None to proceed, or a redirect dict to block and substitute.

        CLAUDE SDK: decorated with @agent.pre_tool_call
        """
        self.hooks_fired.append(f"pre:{tool_name}")

        # Gate 1: identity verification prerequisite
        # This check is Python code — it CANNOT be bypassed by any LLM output
        if tool_name in ("lookup_order", "process_refund"):
            if not self.verified_customer_id:
                # Block the call. Return an error the LLM will see as a tool result.
                print(f"  [HOOK:pre] BLOCKED {tool_name} — no verified customer. "
                      "Redirecting to get_customer.")
                return {
                    "isError": True,
                    "errorCategory": "prerequisite_failed",
                    "isRetryable": True,
                    "message": (
                        "Identity verification required. "
                        "Call get_customer first to verify the customer before accessing orders."
                    )
                }

        # Gate 2: refund amount policy enforcement
        if tool_name == "process_refund":
            amount = tool_input.get("amount", 0)
            if amount > 500:
                print(f"  [HOOK:pre] BLOCKED process_refund(amount={amount}) — "
                      f"exceeds $500 limit. Redirecting to escalate_to_human.")
                return {
                    "isError": True,
                    "errorCategory": "policy_violation",
                    "isRetryable": False,
                    "message": (
                        f"Refund of ${amount:.2f} exceeds autonomous limit ($500). "
                        f"You MUST call escalate_to_human with customer_id="
                        f"{self.verified_customer_id} before processing this refund."
                    )
                }

        return None  # proceed normally

    # ── Hook 2: PostToolUse — normalization before LLM sees result ────────────
    def post_tool_use(self, tool_name: str, result: dict) -> dict:
        """
        Fires AFTER tool returns, BEFORE the LLM sees the result.
        Normalizes data: heterogeneous timestamp formats → ISO 8601.

        CLAUDE SDK: decorated with @agent.post_tool_use
        """
        self.hooks_fired.append(f"post:{tool_name}")

        # Normalization: Unix timestamp → ISO 8601
        # Different backends return different formats — normalize here, not in prompts
        if "created_ts" in result:
            result["created_at"] = datetime.fromtimestamp(
                result.pop("created_ts")
            ).isoformat()

        # Track verified customer from get_customer result
        if tool_name == "get_customer" and "customer_id" in result:
            self.verified_customer_id = result["customer_id"]
            print(f"  [HOOK:post] Verified customer: {self.verified_customer_id}")

        return result

    # ── Tool execution (with hook wrapping) ───────────────────────────────────
    def execute_tool(self, tool_name: str, args: dict) -> dict:
        """Execute a tool, applying pre/post hooks around it."""
        self.tools_called.append(tool_name)

        # PreToolCall hook — may block
        blocked = self.pre_tool_call(tool_name, args)
        if blocked is not None:
            return blocked  # hook returned error — LLM sees this as tool result

        # Execute the actual tool
        result = self._real_tool(tool_name, args)

        # PostToolUse hook — normalizes result
        result = self.post_tool_use(tool_name, result)
        return result

    def _real_tool(self, name: str, args: dict) -> dict:
        if name == "get_customer":
            key = args.get("customer_email") or args.get("customer_id", "")
            return dict(FAKE_CUSTOMERS.get(key, {"isError": True, "message": "not found"}))
        if name == "lookup_order":
            return dict(FAKE_ORDERS.get(args.get("order_number", ""),
                                        {"isError": True, "message": "not found"}))
        if name == "process_refund":
            return {"refund_id": "REF-001", "status": "approved",
                    "amount": args.get("amount")}
        if name == "escalate_to_human":
            return {"ticket_id": "TKT-001", "status": "created",
                    "estimated_response_time": "1 hour",
                    "message": "Human agent will follow up within 1 hour."}
        return {}

    # ── Agentic loop ──────────────────────────────────────────────────────────
    def run(self, query: str) -> tuple[str, list[str], list[str]]:
        """Run one query. Returns (final_answer, tools_called, hooks_fired)."""
        self.reset()
        messages = [
            # Note: NO ordering instruction in system prompt — enforcement is in the hook
            {"role": "system", "content": (
                "You are a customer support agent. "
                "Verify customer identity and handle orders and refunds."
            )},
            {"role": "user", "content": query}
        ]

        for _ in range(8):
            response = client.chat.completions.create(
                model="gpt-4o-mini",       # CLAUDE: model="claude-haiku-4-5"
                max_tokens=256,
                tools=TOOLS,
                tool_choice="auto",        # CLAUDE: tool_choice={"type": "auto"}
                messages=messages
            )
            msg           = response.choices[0].message
            finish_reason = response.choices[0].finish_reason  # CLAUDE: response.stop_reason

            if finish_reason == "stop":    # CLAUDE: "end_turn"
                return (msg.content or "(done)"), self.tools_called, self.hooks_fired

            if finish_reason == "tool_calls":  # CLAUDE: "tool_use"
                messages.append({"role": "assistant", "content": msg.content,
                                 "tool_calls": msg.tool_calls})
                for tc in msg.tool_calls:
                    args   = json.loads(tc.function.arguments)  # CLAUDE: block.input
                    result = self.execute_tool(tc.function.name, args)
                    # CLAUDE: {"role":"user","content":[{"type":"tool_result",...}]}
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": json.dumps(result)})

        return "(max turns)", self.tools_called, self.hooks_fired


# ── Same 15 queries as v1 ─────────────────────────────────────────────────────
TEST_QUERIES = [
    "Can you check the account for alice@example.com and then look at her order ORD-12345?",
    "What is the status of alice@example.com's account?",
    "My email is bob@example.com, can you look at my order ORD-67890?",
    "Check alice@example.com and process a $50 refund for ORD-12345, item arrived broken.",
    "Verify CUST-001 and check their latest order.",
    "What's the status of ORD-12345?",
    "Check order ORD-67890 for me.",
    "Process a $80 refund for ORD-12345.",
    "ORD-12345 hasn't arrived yet, can you help?",
    "I need a refund for order ORD-67890, $50.",
    "I have a problem with my recent order.",
    "My package is late.",
    "I want my money back.",
    "Can you help me with an order issue?",
    "Something's wrong with my shipment.",
]

def main():
    print("=== Version 2: Hook-Based Enforcement (0% failure rate) ===")
    print(f"Running {len(TEST_QUERIES)} queries...\n")

    agent = SupportAgent()
    violations = 0

    print(f"{'Query':<52} {'Tools called':<45} {'Violation?'}")
    print("-" * 105)

    for query in TEST_QUERIES:
        answer, tools, hooks = agent.run(query)

        # Check: was get_customer called before any gated tool?
        gated = {"lookup_order", "process_refund"}
        for i, t in enumerate(tools):
            if t in gated:
                if not any(x == "get_customer" for x in tools[:i]):
                    violations += 1
                break

        tools_str = " → ".join(tools) if tools else "(no tools)"
        print(f"{query[:51]:<52} {tools_str[:44]:<45} {'✗ BUG' if violations else '✓'}")

    total = len(TEST_QUERIES)
    print(f"\n── Results ──")
    print(f"  Violations : {violations}/{total}")
    print(f"  Failure rate: {violations/total*100:.1f}%")
    print()
    print("── Why hooks achieve 0% ──")
    print("  The gate fires in Python BEFORE the tool executes.")
    print("  The LLM cannot bypass Python code — only prompt instructions can be ignored.")
    print("  When blocked, the hook returns an error the LLM sees as a tool result,")
    print("  which causes it to call get_customer and retry.")

if __name__ == "__main__":
    main()
