"""
Version 3 — PostToolUse Normalization Hook
==========================================
Different backends (legacy DB, modern API, cache layer) return timestamps
in different formats:
  Legacy DB   : Unix timestamp (int)          e.g. 1673827200
  Modern API  : ISO 8601 string               e.g. "2024-03-10T14:30:00"
  Cache layer : Relative string               e.g. "3 days ago"

Without normalization, the LLM receives inconsistent data and may:
  - Misinterpret "3 days ago" as a date
  - Fail to compare Unix timestamps with ISO strings
  - Generate incorrect time-based reasoning

The PostToolUse hook normalizes ALL formats to ISO 8601 BEFORE the LLM
sees the result. The LLM always sees clean, consistent data.

Key principle: normalize at the boundary, not in the prompt.
  Prompt: "Interpret these timestamp formats correctly" → probabilistic
  Hook:   normalize() runs on every result             → deterministic

── OpenAI vs Claude API diff ─────────────────────────────────────────────────
  No API difference. Hooks are a Python wrapper layer over any LLM client.
  CLAUDE SDK: @agent.post_tool_use decorator
  This file: post_tool_use() called manually in the agentic loop.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# CLAUDE: client = anthropic.Anthropic()
client = OpenAI()

# ── Mock backends returning heterogeneous timestamp formats ────────────────────
def backend_legacy_db(order_id: str) -> dict:
    """Legacy database — returns Unix timestamps."""
    return {
        "order_id":    order_id,
        "status":      "shipped",
        "total_amount": 129.99,
        "created_ts":  1673827200,          # Unix — int
        "updated_ts":  1710028800,          # Unix — int
    }

def backend_modern_api(order_id: str) -> dict:
    """Modern REST API — returns ISO 8601 strings."""
    return {
        "order_id":    order_id,
        "status":      "delivered",
        "total_amount": 49.99,
        "created_at":  "2024-03-10T14:30:00",   # ISO 8601 — already correct
        "updated_at":  "2024-03-15T09:00:00",
    }

def backend_cache_layer(order_id: str) -> dict:
    """Cache layer — returns human-readable relative timestamps."""
    return {
        "order_id":    order_id,
        "status":      "processing",
        "total_amount": 200.00,
        "created_at":  "3 days ago",        # relative — unusable for date math
        "updated_at":  "2 hours ago",
    }

# Simulated routing: different orders come from different backends
BACKEND_MAP = {
    "ORD-11111": backend_legacy_db,
    "ORD-22222": backend_modern_api,
    "ORD-33333": backend_cache_layer,
}


# ── PostToolUse normalization hook ────────────────────────────────────────────
def normalize_timestamps(result: dict) -> dict:
    """
    PostToolUse hook: normalize all timestamp fields to ISO 8601.

    Handles:
      - Unix int/float → datetime.fromtimestamp().isoformat()
      - ISO 8601 string → pass through unchanged
      - Relative string ("3 days ago") → compute absolute time
      - Unknown format → tag as "unknown_format:{original}"

    CLAUDE SDK equivalent:
        @agent.post_tool_use
        def normalize(tool_name, result):
            return normalize_timestamps(result)
    """
    result = dict(result)   # don't mutate original

    # Field name patterns that contain timestamps
    ts_patterns = [
        (re.compile(r'_ts$'),      'unix'),         # created_ts, updated_ts
        (re.compile(r'_at$'),      'detect'),       # created_at, updated_at
        (re.compile(r'_date$'),    'detect'),       # invoice_date
        (re.compile(r'^date_'),    'detect'),       # date_created
    ]

    now = datetime.now(timezone.utc)

    for key, value in list(result.items()):
        format_hint = next(
            (hint for pattern, hint in ts_patterns if pattern.search(key)), None
        )
        if format_hint is None:
            continue

        normalized = None

        # Unix timestamp (int or float)
        if isinstance(value, (int, float)) or format_hint == 'unix':
            try:
                normalized = datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
            except (ValueError, OSError, OverflowError):
                pass

        # ISO 8601 string — already correct, pass through
        elif isinstance(value, str) and re.match(
            r'\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?', value
        ):
            normalized = value   # already ISO 8601

        # Relative timestamp ("3 days ago", "2 hours ago")
        elif isinstance(value, str):
            m = re.match(r'(\d+)\s+(second|minute|hour|day|week)s?\s+ago', value)
            if m:
                n, unit = int(m.group(1)), m.group(2)
                delta_map = {
                    "second": timedelta(seconds=n),
                    "minute": timedelta(minutes=n),
                    "hour":   timedelta(hours=n),
                    "day":    timedelta(days=n),
                    "week":   timedelta(weeks=n),
                }
                normalized = (now - delta_map[unit]).isoformat()
            else:
                normalized = f"unknown_format:{value}"

        if normalized is not None and normalized != value:
            # Rename _ts → _at for consistency, replace value with ISO 8601
            new_key = re.sub(r'_ts$', '_at', key)
            if new_key != key:
                del result[key]
            result[new_key] = normalized

    return result


# ── Demo: show before/after for each backend ──────────────────────────────────
def demo_normalization():
    print("=== Version 3: PostToolUse Normalization Hook ===\n")
    print("Showing raw backend output vs normalized output:\n")

    for order_id, backend_fn in BACKEND_MAP.items():
        raw    = backend_fn(order_id)
        normed = normalize_timestamps(raw)

        backend_name = backend_fn.__name__
        print(f"── {backend_name} ({order_id}) ──")

        ts_keys = [k for k in set(list(raw.keys()) + list(normed.keys()))
                   if any(p in k for p in ['_ts', '_at', '_date', 'date_'])]

        for key in sorted(set(ts_keys)):
            raw_val   = raw.get(key,   "(removed)")
            normd_val = normed.get(key, "(removed)")
            raw_val   = raw.get(re.sub(r'_at$', '_ts', key), raw_val)  # handle renamed keys
            changed   = "← normalized" if str(raw_val) != str(normd_val) else "← unchanged"
            print(f"  {key:<15} raw: {str(raw_val):<30} normed: {normd_val}  {changed}")
        print()

    print("── What the LLM sees ──")
    print("  All three backends → consistent ISO 8601 timestamps.")
    print("  The LLM can now compare dates, compute durations, and reason correctly")
    print("  without needing to understand multiple timestamp formats.")
    print()
    print("── Why this is better than a prompt ──")
    print("  Prompt: 'Interpret Unix timestamps as dates' → probabilistic, can fail")
    print("  Hook:   normalize() runs on every result    → deterministic, always fires")


# ── Live agent run showing hook in loop ───────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up an order by order number (ORD-XXXXX).",
            "parameters": {
                "type": "object",
                "properties": {"order_number": {"type": "string"}},
                "required": ["order_number"]
            }
        }
    }
]

def run_agent_with_normalization(query: str) -> str:
    """Run a query, applying the normalization hook on every tool result."""
    messages = [
        {"role": "system",
         "content": "You are a support agent. Report the order creation date in your response."},
        {"role": "user", "content": query}
    ]

    for _ in range(4):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=256,
            tools=TOOLS,
            tool_choice="auto",        # CLAUDE: tool_choice={"type": "auto"}
            messages=messages
        )
        msg           = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "stop":    # CLAUDE: "end_turn"
            return msg.content or ""

        if finish_reason == "tool_calls":  # CLAUDE: "tool_use"
            messages.append({"role": "assistant", "content": msg.content,
                             "tool_calls": msg.tool_calls})
            for tc in msg.tool_calls:
                args     = json.loads(tc.function.arguments)  # CLAUDE: block.input
                order_id = args.get("order_number", "")

                # Raw result from whichever backend serves this order
                backend  = BACKEND_MAP.get(order_id, backend_legacy_db)
                raw      = backend(order_id)

                # ── PostToolUse hook fires here ───────────────────────────────
                normalized = normalize_timestamps(raw)
                normalized = raw
                # ─────────────────────────────────────────────────────────────

                print(f"  [hook:post] {order_id} raw_ts keys: "
                      f"{[k for k in raw if '_ts' in k or '_at' in k]} → "
                      f"{[k for k in normalized if '_at' in k]}")

                # CLAUDE: {"role":"user","content":[{"type":"tool_result",...}]}
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(normalized)})

    return "(max turns)"


def demo_live_agent():
    print("\n── Live agent run (normalization in loop) ──\n")
    queries = [
        ("Legacy DB (Unix ts)", "When was order ORD-11111 created?"),
        ("Modern API (ISO)",    "When was order ORD-22222 created?"),
        ("Cache layer (relative)", "When was order ORD-33333 created?"),
    ]
    for label, query in queries:
        print(f"Query [{label}]: {query}")
        answer = run_agent_with_normalization(query)
        print(f"Answer: {answer}\n")


if __name__ == "__main__":
    demo_normalization()
    demo_live_agent()
