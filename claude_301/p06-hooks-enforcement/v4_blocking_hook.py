"""
Version 4 — PreToolCall Blocking Hook + Structured Handoff Summary
===================================================================
Two demonstrations:

1. PreToolCall blocking hook
   - $100 refund → passes (below $500 limit)
   - $600 refund → BLOCKED before execution → redirect message sent to LLM
   - LLM receives the block, calls escalate_to_human instead
   - The block is Python code — cannot be bypassed

2. Structured escalation handoff
   When escalation fires, compile a structured summary for the human agent.
   Human agents have ZERO access to conversation history — this summary is
   their entire context. Missing information = bad support outcome.

   Required fields:
     customer_id         → who
     root_cause          → why escalated (policy violation, refund limit, etc.)
     what_was_attempted  → what the agent tried before escalating
     recommended_action  → what the human should do next

── The determinism hierarchy (most important concept in D1) ──────────────────
  DETERMINISTIC (use for financial/legal rules):
    PreToolCall hook  → blocks BEFORE execution
    PostToolUse hook  → normalizes AFTER execution

  PROBABILISTIC (use for guidance only):
    System prompt     → "please escalate refunds over $500"
    Tool descriptions → "requires human approval above limit"

  Exam answer key: when amount > $500 requires human approval →
    ✓ PreToolCall hook
    ✗ "Add clear instructions to the system prompt"
    ✗ "Add few-shot examples showing correct escalation"

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  No API difference. Hooks are Python wrappers.
  CLAUDE SDK: @agent.pre_tool_call decorator
"""

import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_customer",
            "description": "Retrieve customer account by email or customer ID.",
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
            "description": "Process a refund. Autonomous limit: $500. Above that, escalate_to_human first.",
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
                "Escalate to a human agent. Required when refund > $500 "
                "or when the issue cannot be resolved autonomously."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id":         {"type": "string"},
                    "issue_summary":       {"type": "string"},
                    "root_cause":          {"type": "string"},
                    "what_was_attempted":  {"type": "string"},
                    "recommended_action":  {"type": "string"},
                    "priority":            {"type": "string", "enum": ["normal", "high", "urgent"]}
                },
                "required": ["customer_id", "issue_summary", "root_cause",
                             "what_was_attempted", "recommended_action"]
            }
        }
    }
]

FAKE_DB = {
    "customers": {
        "alice@example.com": {"customer_id": "CUST-001", "name": "Alice Chen",
                              "account_status": "active", "loyalty_tier": "gold"},
        "CUST-001":          {"customer_id": "CUST-001", "name": "Alice Chen",
                              "account_status": "active", "loyalty_tier": "gold"},
        "CUST-002":          {"customer_id": "CUST-002", "name": "Bob Smith",
                              "account_status": "active", "loyalty_tier": "silver"},
    },
    "orders": {
        "ORD-12345": {"order_id": "ORD-12345", "status": "delivered",
                      "total_amount": 129.99, "customer_id": "CUST-001"},
        "ORD-67890": {"order_id": "ORD-67890", "status": "processing",
                      "total_amount": 600.00, "customer_id": "CUST-002"},
    }
}


class BlockingAgent:
    """Agent with PreToolCall blocking + structured escalation handoff."""

    def __init__(self):
        self.verified_customer_id: str | None = None
        self.action_log: list[str] = []
        self.escalation_summary: dict | None = None

    def reset(self):
        self.verified_customer_id = None
        self.action_log.clear()
        self.escalation_summary = None

    # ── PreToolCall blocking hook ──────────────────────────────────────────────
    def pre_tool_call(self, tool_name: str, tool_input: dict) -> dict | None:
        """
        Fires BEFORE execution. Returns None to proceed or error dict to block.

        CLAUDE SDK:
            @agent.pre_tool_call
            def gate(tool_name, tool_input): ...
        """
        # Prerequisite gate
        if tool_name in ("lookup_order", "process_refund"):
            if not self.verified_customer_id:
                self.action_log.append(f"BLOCKED:{tool_name}:no_identity")
                return {
                    "isError": True, "errorCategory": "prerequisite_failed",
                    "isRetryable": True,
                    "message": "Call get_customer first to verify identity."
                }

        # Refund limit gate — DETERMINISTIC policy enforcement
        if tool_name == "process_refund":
            amount = tool_input.get("amount", 0)
            if amount > 500:
                self.action_log.append(f"BLOCKED:process_refund:amount={amount}")
                print(f"  [HOOK:pre] BLOCKED process_refund(${amount:.2f}) — "
                      "exceeds $500. LLM must call escalate_to_human.")
                return {
                    "isError": True, "errorCategory": "policy_violation",
                    "isRetryable": False,
                    "message": (
                        f"Refund of ${amount:.2f} exceeds autonomous limit ($500). "
                        f"Policy requires human approval. "
                        f"Call escalate_to_human with customer_id="
                        f"{self.verified_customer_id}, "
                        f"document root_cause, what_was_attempted, and recommended_action."
                    )
                }

        self.action_log.append(f"ALLOWED:{tool_name}")
        return None  # proceed

    # ── Tool execution ─────────────────────────────────────────────────────────
    def execute_tool(self, tool_name: str, args: dict) -> dict:
        blocked = self.pre_tool_call(tool_name, args)
        if blocked:
            return blocked

        if tool_name == "get_customer":
            key    = args.get("customer_email") or args.get("customer_id", "")
            result = FAKE_DB["customers"].get(key, {"isError": True, "message": "not found"})
            if "customer_id" in result:
                self.verified_customer_id = result["customer_id"]
                print(f"  [STATE] customer verified: {self.verified_customer_id}")
            return result

        if tool_name == "lookup_order":
            return FAKE_DB["orders"].get(
                args.get("order_number", ""), {"isError": True, "message": "not found"}
            )

        if tool_name == "process_refund":
            return {"refund_id": "REF-001", "status": "approved",
                    "amount": args.get("amount")}

        if tool_name == "escalate_to_human":
            # Structured handoff — capture for display
            self.escalation_summary = {
                "ticket_id":           f"TKT-{args.get('customer_id', 'UNKNOWN')}-001",
                "customer_id":         args.get("customer_id"),
                "issue_summary":       args.get("issue_summary"),
                "root_cause":          args.get("root_cause"),
                "what_was_attempted":  args.get("what_was_attempted"),
                "recommended_action":  args.get("recommended_action"),
                "priority":            args.get("priority", "normal"),
                "status":              "created",
                "estimated_response":  "1 hour",
            }
            return {"ticket_id": self.escalation_summary["ticket_id"],
                    "status": "created", "estimated_response_time": "1 hour",
                    "message": "Human agent assigned. They will contact the customer shortly."}

        return {}

    def run(self, query: str) -> str:
        self.reset()
        messages = [
            {"role": "system", "content": (
                "You are a customer support agent. "
                "Verify customer identity before accessing orders. "
                "When escalating, provide full context: root_cause, "
                "what_was_attempted, and recommended_action."
            )},
            {"role": "user", "content": query}
        ]

        for _ in range(8):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=512,
                tools=TOOLS,
                tool_choice="auto",        # CLAUDE: tool_choice={"type": "auto"}
                messages=messages
            )
            msg           = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "stop":    # CLAUDE: "end_turn"
                return msg.content or "(done)"

            if finish_reason == "tool_calls":  # CLAUDE: "tool_use"
                messages.append({"role": "assistant", "content": msg.content,
                                 "tool_calls": msg.tool_calls})
                for tc in msg.tool_calls:
                    args   = json.loads(tc.function.arguments)  # CLAUDE: block.input
                    result = self.execute_tool(tc.function.name, args)
                    # CLAUDE: {"role":"user","content":[{"type":"tool_result",...}]}
                    messages.append({"role": "tool", "tool_call_id": tc.id,
                                     "content": json.dumps(result)})

        return "(max turns)"


def main():
    print("=== Version 4: PreToolCall Blocking + Structured Handoff ===\n")

    agent = BlockingAgent()

    # ── Test 1: Refund within limit ────────────────────────────────────────────
    print("=" * 60)
    print("Case 1: $100 refund (below $500 limit — should pass)")
    print("=" * 60)
    answer = agent.run(
        "alice@example.com wants a $100 refund for order ORD-12345. Item was defective."
    )
    print(f"\nAction log: {agent.action_log}")
    print(f"Answer: {answer}\n")

    # ── Test 2: Refund above limit ─────────────────────────────────────────────
    print("=" * 60)
    print("Case 2: $600 refund (above $500 limit — must be blocked → escalated)")
    print("=" * 60)
    agent.reset()
    answer = agent.run(
        "CUST-002 is requesting a full refund of $600 for order ORD-67890. "
        "The product arrived with significant damage."
    )
    print(f"\nAction log: {agent.action_log}")
    print(f"Answer: {answer}\n")

    # ── Show structured handoff summary ───────────────────────────────────────
    if agent.escalation_summary:
        print("=" * 60)
        print("Structured Handoff Summary (human agent's ONLY context)")
        print("=" * 60)
        s = agent.escalation_summary
        print(f"  Ticket ID:           {s['ticket_id']}")
        print(f"  Customer ID:         {s['customer_id']}")
        print(f"  Priority:            {s['priority']}")
        print(f"  Issue:               {s['issue_summary']}")
        print(f"  Root cause:          {s['root_cause']}")
        print(f"  What was attempted:  {s['what_was_attempted']}")
        print(f"  Recommended action:  {s['recommended_action']}")
        print()
        missing = [k for k, v in s.items() if not v and k != "priority"]
        if missing:
            print(f"  ⚠ Missing fields: {missing}")
            print("  Human agent has incomplete context — this degrades support quality.")
        else:
            print("  ✓ All handoff fields populated — human agent has full context.")

    print()
    print("── Key takeaways ──")
    print("  $100 refund : process_refund ALLOWED  (hook passed)")
    print("  $600 refund : process_refund BLOCKED  (hook intercepted) → escalate_to_human")
    print("  Blocking happens in Python BEFORE tool execution — LLM cannot bypass it.")
    print("  Structured handoff: human agent needs all 4 fields to act without history.")

if __name__ == "__main__":
    main()
