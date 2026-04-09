"""
Version 1 — Raw Agentic Loop (Manual)
======================================
You drive the loop. You manage history. You execute tools.
finish_reason (OpenAI) == stop_reason (Claude)
  "stop"       == "end_turn"   → PRIMARY termination
  "tool_calls" == "tool_use"   → execute tools and continue

EXERCISE 3 — Break it intentionally:
  Comment out the lines marked [BREAK HERE] below.
  The model gets no new information → loops forever.
  Add them back to fix it.
"""

import json
import pathlib
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

tools = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all Python files in a directory. Returns list of file paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path to search"}
                },
                "required": ["directory"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "count_lines",
            "description": "Count lines in a specific file. Returns integer line count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file"}
                },
                "required": ["filepath"]
            }
        }
    }
]


def execute_tool(name: str, inputs: dict):
    if name == "list_files":
        return [str(p) for p in pathlib.Path(inputs["directory"]).rglob("*.py")]
    elif name == "count_lines":
        with open(inputs["filepath"]) as f:
            return sum(1 for _ in f)


# ── Conversation history — grows with each turn ──────────────────────────────
messages = [{"role": "user", "content": "Analyze Python files in ./src and list top 3 by line count"}]

iteration = 0
print("=== Version 1: Raw Agentic Loop ===\n")

while iteration < 20:           # safety cap — NOT primary termination
    iteration += 1

    response = client.chat.completions.create(
        model="gpt-4o",
        tools=tools,
        messages=messages
    )

    msg = response.choices[0].message
    finish_reason = response.choices[0].finish_reason  # Claude: stop_reason

    print(f"Turn {iteration}: finish_reason={finish_reason} | history length={len(messages)}")

    # ── EXERCISE 2: observe full history after each turn ──────────────────
    # Uncomment to watch tool_use and tool_result blocks accumulate:
    # import pprint; pprint.pprint(messages)

    # ── PRIMARY termination — finish_reason drives the loop ───────────────
    if finish_reason == "stop":          # Claude equivalent: "end_turn"
        print("\n── Final Answer ──")
        print(msg.content)
        break

    elif finish_reason == "tool_calls":  # Claude equivalent: "tool_use"
        # Append assistant message (with tool_calls) to history
        messages.append(msg)

        for tc in msg.tool_calls:
            inputs = json.loads(tc.function.arguments)
            print(f"  [tool] {tc.function.name}({json.dumps(inputs)})")
            result = execute_tool(tc.function.name, inputs)
            print(f"  [result] {str(result)[:120]}")

            # [BREAK HERE] — comment these lines out for Exercise 3
            # Without this, the model never gets tool results → infinite loop
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result)
            })

        print()

    else:
        print(f"Unexpected finish_reason: {finish_reason}")
        break

print(f"\nCompleted in {iteration} turn(s)")
