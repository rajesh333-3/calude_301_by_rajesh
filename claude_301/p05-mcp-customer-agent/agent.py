"""
MCP Customer Support Agent
===========================
Connects to mcp_server.py via stdio transport.
Discovers all tools automatically at connection time.
Converts MCP tool schemas → OpenAI format and runs an agentic loop.

Architecture:
  User query
      ↓
  OpenAI (sees MCP tools as regular function specs)
      ↓
  tool_calls in response
      ↓
  MCP client routes call to MCP server subprocess
      ↓
  MCP server executes tool, returns result
      ↓
  Result appended to history → next OpenAI call

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  MCP connection:
    OpenAI: no native MCP support — manually bridge via MCP Python SDK client.
            Discover tools → convert schema → route calls back to MCP session.
    CLAUDE: native MCP support via claude_desktop_config.json or SDK beta.
            client.beta.messages.create(mcp_servers=[...]) handles discovery
            and routing automatically — no manual bridging code needed.

  Agentic loop:
    OpenAI  : finish_reason == "tool_calls" / "stop"
    CLAUDE  : stop_reason == "tool_use" / "end_turn"

  Tool result:
    OpenAI  : {"role":"tool","tool_call_id":tc.id,"content":str}
    CLAUDE  : {"role":"user","content":[{"type":"tool_result","tool_use_id":...}]}

  Args:
    OpenAI  : json.loads(tc.function.arguments)
    CLAUDE  : block.input  (already a dict)
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

SYSTEM_PROMPT = """You are a customer support agent with access to customer and order tools.

Before answering any policy question, read the policy://catalog resource.

Decision rules:
- Always verify customer identity before processing any action
- For refunds > $600: escalate_to_human FIRST, then inform customer
- For competitor pricing: always escalate_to_human — never handle autonomously
- After escalating: do NOT attempt further resolution, inform customer a human will follow up
"""


def mcp_tool_to_openai(tool) -> dict:
    """Convert an MCP tool definition to OpenAI function schema.

    CLAUDE: This conversion is not needed — Claude's SDK handles MCP tools natively.
    With Claude, you'd pass mcp_servers config directly to client.beta.messages.create().
    """
    return {
        "type": "function",              # CLAUDE: no "type" wrapper in tool schema
        "function": {                    # CLAUDE: fields go at top level
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema  # CLAUDE: "input_schema" not "parameters"
        }
    }


async def run_agent(user_query: str, session: ClientSession) -> str:
    """Run one full agentic turn: query → tool calls → final response."""

    # Discover tools from MCP server at connection time
    tools_response = await session.list_tools()
    openai_tools   = [mcp_tool_to_openai(t) for t in tools_response.tools]

    print(f"\n  [MCP] Discovered {len(openai_tools)} tools: "
          f"{[t.name for t in tools_response.tools]}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_query}
    ]

    turn = 0
    max_turns = 10

    while turn < max_turns:
        turn += 1

        # CLAUDE: response = client.messages.create(model=..., tools=..., messages=...)
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1024,
            tools=openai_tools,
            tool_choice="auto",      # CLAUDE: tool_choice={"type": "auto"}
            messages=messages
        )

        msg           = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        # CLAUDE: finish_reason → response.stop_reason  ("end_turn" / "tool_use")

        print(f"  [turn {turn}] finish_reason={finish_reason}")

        if finish_reason == "stop":           # CLAUDE: stop_reason == "end_turn"
            return msg.content

        if finish_reason == "tool_calls":     # CLAUDE: stop_reason == "tool_use"
            # Append assistant message with tool calls
            # CLAUDE: messages.append({"role":"assistant","content": response.content})
            messages.append({
                "role":    "assistant",
                "content": msg.content,
                "tool_calls": msg.tool_calls
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                # CLAUDE: args = block.input  (already a dict — no json.loads needed)
                args      = json.loads(tc.function.arguments)

                print(f"  [tool] {tool_name}({json.dumps(args)})")

                # Route call to MCP server
                # CLAUDE: also uses session.call_tool() if using SDK MCP client,
                # or the native MCP integration handles this automatically.
                result = await session.call_tool(tool_name, args)

                # MCP returns content blocks — extract text
                result_text = (result.content[0].text
                               if result.content else json.dumps({"status": "ok"}))

                print(f"  [result] {result_text[:120]}")

                # Append tool result to history
                # CLAUDE:
                #   messages.append({"role":"user","content":[{
                #       "type":"tool_result",
                #       "tool_use_id": block.id,
                #       "content": result_text
                #   }]})
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result_text
                })

    return "Max turns reached without resolution"


async def main():
    """Connect to MCP server and run demo queries."""
    server_params = StdioServerParameters(
        command=sys.executable,   # use the same python that's running this script
        args=["mcp_server.py"],   # "python" doesn't exist on macOS — sys.executable always works
        # env vars injected here (or from .mcp.json when using Claude Code)
        env={
            "SUPPORT_DB_URL":  "sqlite:///support.db",   # would be ${SUPPORT_DB_URL} in .mcp.json
            "SUPPORT_API_KEY": "demo-key"
        }
    )

    print("=== MCP Customer Support Agent ===\n")
    print("Connecting to MCP server...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Connected.\n")

            queries = [
                ("Identity lookup",
                 "Can you check the account status for alice@example.com?"),

                ("Order + policy question",
                 "What's the status of order ORD-12345, and what's the return policy?"),

                ("Refund within limit",
                 "Customer alice@example.com wants a refund of $80 for order ORD-12345. "
                 "The item arrived damaged."),

                ("Refund above limit — must escalate",
                 "Customer CUST-002 wants a $600 refund for order ORD-67890. Process it."),
            ]

            for label, query in queries:
                print(f"\n{'='*60}")
                print(f"Query: [{label}]")
                print(f"  {query}")
                answer = await run_agent(query, session)
                print(f"\n  ── Final Answer ──")
                print(f"  {answer}")

if __name__ == "__main__":
    asyncio.run(main())
