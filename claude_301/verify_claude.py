import anyio
from claude_agent_sdk import query, AssistantMessage, TextBlock

async def main():
    async for msg in query(prompt="Say 'SDK working' and nothing else"):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    print(block.text)

anyio.run(main)