"""
Version 2 — Agent SDK (Abstracted Loop)
========================================
The while loop disappears. History management is handled by the SDK.
Tool execution is registered via a dispatch table.
max_turns is the safety cap — NOT primary termination.

What the SDK does for you automatically:
  - Appends assistant messages to history
  - Appends tool results to history
  - Drives the loop until finish_reason == "stop"
  - Enforces max_turns as a safety net
"""

import json
import pathlib
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


# ── Minimal Agent SDK — wraps the manual loop from v1 ────────────────────────
class AgentSDK:
    def __init__(self, model="gpt-4o"):
        self.client = OpenAI()
        self.model = model
        self.tools = []
        self._handlers = {}

    def tool(self, name: str, description: str, parameters: dict):
        """Register a tool with its schema and handler."""
        def decorator(fn):
            self.tools.append({
                "type": "function",
                "function": {"name": name, "description": description, "parameters": parameters}
            })
            self._handlers[name] = fn
            return fn
        return decorator

    def run(self, prompt: str, max_turns: int = 10) -> str:
        messages = [{"role": "user", "content": prompt}]
        turn = 0

        while turn < max_turns:          # safety cap — NOT primary termination
            turn += 1
            response = self.client.chat.completions.create(
                model=self.model,
                tools=self.tools,
                messages=messages
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            print(f"Turn {turn}: finish_reason={finish_reason}")

            if finish_reason == "stop":  # PRIMARY termination
                return msg.content

            elif finish_reason == "tool_calls":
                messages.append(msg)
                for tc in msg.tool_calls:
                    inputs = json.loads(tc.function.arguments)
                    print(f"  [tool] {tc.function.name}({json.dumps(inputs)})")
                    result = self._handlers[tc.function.name](**inputs)
                    print(f"  [result] {str(result)[:120]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result)
                    })

        return "Max turns reached without completion"


# ── Create agent and register tools ──────────────────────────────────────────
agent = AgentSDK()

@agent.tool(
    name="list_files",
    description="List all Python files in a directory.",
    parameters={
        "type": "object",
        "properties": {"directory": {"type": "string"}},
        "required": ["directory"]
    }
)
def list_files(directory: str):
    return [str(p) for p in pathlib.Path(directory).rglob("*.py")]


@agent.tool(
    name="count_lines",
    description="Count lines in a specific file.",
    parameters={
        "type": "object",
        "properties": {"filepath": {"type": "string"}},
        "required": ["filepath"]
    }
)
def count_lines(filepath: str):
    with open(filepath) as f:
        return sum(1 for _ in f)


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Version 2: Agent SDK (Abstracted Loop) ===\n")
    result = agent.run(
        prompt="Analyze Python files in ./src and list top 3 by line count",
        max_turns=10
    )
    print(f"\n── Final Answer ──\n{result}")
