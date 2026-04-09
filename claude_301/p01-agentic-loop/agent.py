import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

tools = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a basic math expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A math expression to evaluate, e.g. '15 * 7 + 42'"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city (simulated)",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name"
                    }
                },
                "required": ["city"]
            }
        }
    }
]

my_new_tool = {
    "type": "function",
    "function": {
        "name": "get_national_anthem",
        "description": "Get the national anthem in text for a country pronounced in English",
        "parameters": {
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "Country name"
                }
            },
            "required": ["country"]
        }
    }
}
tools.append(my_new_tool)

def run_tool(name: str, inputs: dict) -> str:
    if name == "calculator":
        try:
            result = eval(inputs["expression"], {"__builtins__": {}})
            return str(result)
        except Exception as e:
            return f"Error: {e}"
    elif name == "get_weather":
        simulated = {"Paris": "Sunny, 18°C", "Tokyo": "Cloudy, 22°C", "New York": "Rainy, 14°C"}
        return simulated.get(inputs["city"], f"Partly cloudy, 20°C in {inputs['city']}")
    elif name == "get_national_anthem":
        national_anthems = {
            "India": "Jana Gana Mana",
            "USA": "The Star-Spangled Banner",
            "UK": "God Save the King",
            "France": "La Marseillaise",
            "Germany": "Das Lied der Deutschen",
            "Japan": "Kimigayo",
            "China": "March of the Volunteers",
            "Russia": "State Anthem of the Russian Federation",
            "Brazil": "Hino Nacional Brasileiro",
            "Canada": "O Canada",
        }
        return national_anthems.get(inputs["country"], f"National anthem not found for {inputs['country']}")    
    return f"Unknown tool: {name}"


def run_agent(user_message: str):
    messages = [{"role": "user", "content": user_message}]
    print(f"\nUser: {user_message}")
    print("-" * 50)

    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            tools=tools,
            messages=messages
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "stop":
            print(f"\nAgent: {msg.content}")
            break

        elif finish_reason == "tool_calls":
            messages.append(msg)
            for tc in msg.tool_calls:
                inputs = json.loads(tc.function.arguments)
                result = run_tool(tc.function.name, inputs)
                print(f"  [tool] {tc.function.name}({json.dumps(inputs)}) → {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result
                })

        else:
            print(f"Unexpected finish reason: {finish_reason}")
            break


if __name__ == "__main__":
    run_agent("What is 15 * 7 + 42? Also, what's the weather like in Paris and Tokyo? lastly get national anthem of India and USA")
