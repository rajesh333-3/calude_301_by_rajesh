# p05 — MCP Customer Support Agent

Builds a real MCP server, connects it to an OpenAI agent via a manual bridge,
and demonstrates tool distribution and resource catalog patterns.

---

## Files

| File | What it shows |
|---|---|
| `mcp_server.py` | MCP server — 4 tools + 1 resource (provider-agnostic) |
| `agent.py` | Full agent: MCP client bridge + OpenAI agentic loop |
| `v2_over_provision.py` | 4 tools vs 18 tools — accuracy degradation experiment |
| `v3_resource_catalog.py` | Resource read before acting — exploratory call elimination |
| `.mcp.json` | Project-scoped MCP config with env var expansion |

---

## Setup

```bash
cd claude_301/p05-mcp-customer-agent

# Install MCP SDK + dependencies
pip install mcp openai python-dotenv anyio

# Set env vars (referenced in .mcp.json)
export SUPPORT_DB_URL="sqlite:///support.db"
export SUPPORT_API_KEY="your-key"
echo "OPENAI_API_KEY=sk-..." >> .env
```

---

## Architecture

```
User query
    ↓
OpenAI API  ←── sees MCP tools as regular function specs
    ↓
tool_calls in response
    ↓
MCP client (agent.py)  ←── routes call via stdio transport
    ↓
MCP server (mcp_server.py subprocess)  ←── executes tool
    ↓
Result → appended to history → next OpenAI call
```

**MCP is provider-agnostic.** `mcp_server.py` does not import OpenAI or Anthropic.
The bridge code in `agent.py` converts MCP schemas ↔ OpenAI format.
With Claude, this bridge is built into the SDK — no manual conversion needed.

---

## Run & Explore

### Step 1 — Verify the MCP server starts

```bash
python mcp_server.py
```

The server starts and waits on stdio. Press `Ctrl+C` to stop.
You should see no errors — this confirms FastMCP and your environment are working.

---

### Step 2 — Run the full agent (`agent.py`)

```bash
python agent.py
```

**Expected output:**
```
=== MCP Customer Support Agent ===

Connecting to MCP server...
Connected.

  [MCP] Discovered 4 tools: ['get_customer', 'lookup_order', 'process_refund', 'escalate_to_human']

============================================================
Query: [Identity lookup]
  Can you check the account status for alice@example.com?
  [turn 1] finish_reason=tool_calls
  [tool] get_customer({"customer_email": "alice@example.com"})
  [result] {"customer_id": "CUST-001", "name": "Alice Chen", "account_status": "active", ...}
  [turn 2] finish_reason=stop

  ── Final Answer ──
  Alice Chen (CUST-001) is an active account with gold loyalty tier.

============================================================
Query: [Refund above limit — must escalate]
  Customer CUST-002 wants a $600 refund for order ORD-67890. Process it.
  [turn 1] finish_reason=tool_calls
  [tool] escalate_to_human({"customer_id": "CUST-002", "issue_summary": "...", "priority": "high"})
  [result] {"ticket_id": "TKT-002", "estimated_response_time": "1 hour", ...}
  [turn 2] finish_reason=stop

  ── Final Answer ──
  This refund exceeds the $500 autonomous limit. I've escalated to our team —
  a human agent will contact you within 1 hour.
```

**What to look for:**
- Tool discovery happens once at connection: `Discovered 4 tools`
- For the $600 refund: agent calls `escalate_to_human` directly (not `process_refund`)
  — the decision rule in the system prompt is applied without being explicitly triggered
- Each `[turn N]` shows one round-trip to the LLM

**Experiment:** Remove the "refunds > $500 → escalate" rule from `SYSTEM_PROMPT`
in `agent.py` and re-run the $600 query. The model will try `process_refund`, get
a permission error, then (hopefully) escalate — but it might also just give up.
This shows why decision rules in the prompt matter.

---

### Step 3 — Tool over-provisioning (`v2_over_provision.py`)

```bash
python v2_over_provision.py
```

**Expected output:**
```
============================================================
CORRECT (4 tools)
============================================================
Expected               Got                    OK?   Query
--------------------------------------------------------------------------------
get_customer           get_customer           ✓     What is the account status for...
lookup_order           lookup_order           ✓     Get me the details on order ORD-12345
process_refund         process_refund         ✓     Process a $50 refund for order...
escalate_to_human      escalate_to_human      ✓     Customer CUST-001 wants a $700...

  Accuracy: 6/6 = 100%

============================================================
OVER-PROVISIONED (18 tools)
============================================================
get_customer           get_customer           ✓     What is the account status for...
lookup_order           lookup_order           ✓     Get me the details on order ORD-12345
process_refund         create_support_ticket  ✗     Process a $50 refund for order...
escalate_to_human      create_support_ticket  ✗     Customer CUST-001 wants a $700...

  Accuracy: 4/6 = 67%

============================================================
TRIMMED BACK (4 tools)
============================================================
  Accuracy: 6/6 = 100%
```

**What to look for:** Which specific noise tools the model picks instead of the
correct ones. `create_support_ticket` and `flag_fraudulent_order` are the common
traps — they sound plausibly related to the query.

**Experiment:** Remove the 10 most semantically distant noise tools (inventory,
supplier, warehouse) and keep only the 4 most plausible (create_support_ticket,
log_customer_feedback, archive_customer_account, flag_fraudulent_order).
Re-run — accuracy will be worse than with all 14, because closer noise is
harder to distinguish.

---

### Step 4 — Resource catalog (`v3_resource_catalog.py`)

```bash
python v3_resource_catalog.py
```

**Expected output:**
```
Fetching policy://catalog from MCP server...
  [MCP] Available resources: ['policy://catalog']
  Policy loaded (847 chars)

Query                                              Without resource   With resource
----------------------------------------------------------------------------------
What is the return policy?                               0 tool calls        0 tool calls
Can I get a refund of $600 autonomously...               2 tool calls        0 tool calls  ← exploratory calls saved
Does the agent handle competitor pricing...              1 tool calls        0 tool calls  ← exploratory calls saved
Process a $80 refund for order ORD-12345...              2 tool calls        2 tool calls

  Total exploratory tool calls eliminated: 3
```

**What to look for:**
- Policy questions: `without resource` may call `get_customer` or `lookup_order`
  just to discover what operations are possible — pure exploration, zero value
- The action query (process_refund) calls tools regardless — the resource helps
  with *what* to do, not *whether* to call tools
- The `total_saved` line quantifies the cost reduction

**Experiment:** Replace the policy catalog with an empty dict `{}` and re-run.
All queries will trigger exploratory tool calls — shows why catalog content quality matters.

---

### Step 5 — User-scoped personal server (`~/.claude.json`)

This step is Claude Code–specific (not runnable as a Python script).

Add a personal experimental server to `~/.claude.json`:

```json
{
  "mcpServers": {
    "my-dev-tools": {
      "command": "python",
      "args": ["/path/to/my_personal_mcp_server.py"],
      "env": {
        "DEV_API_KEY": "${DEV_API_KEY}"
      }
    }
  }
}
```

When you open this project in Claude Code, **both** servers are available simultaneously:
- `customer-support` (from `.mcp.json` — project-scoped, shared via git)
- `my-dev-tools` (from `~/.claude.json` — personal, never committed)

Run `/tools` in Claude Code to see all discovered tools from both servers listed together.

**Scoping rule:** `.mcp.json` = team tools (committed). `~/.claude.json` = personal tools (private).

---

## Key Concepts

### MCP vs Tool Use

| | Tool Use | MCP |
|---|---|---|
| Definition | Inline JSON in API call | External server via protocol |
| Discovery | Manual — you write the schema | Automatic — server exposes it |
| Scope | One LLM call | Persistent server process |
| Credentials | Hardcoded (bad) or env (good) | `${ENV_VAR}` expansion in .mcp.json |
| Reuse | Per-call | Any client that speaks MCP |

### .mcp.json vs ~/.claude.json

| File | Scope | In git? | Use for |
|---|---|---|---|
| `.mcp.json` | Project | ✓ Yes | Team tools, shared servers |
| `~/.claude.json` | User | ✗ Never | Personal/experimental servers |

### Resource vs Tool

| | Resource | Tool |
|---|---|---|
| Execution | Read-only | Executable (can mutate state) |
| When to use | Policies, catalogs, config | Actions, lookups, mutations |
| Call cost | One read, cached | One API round-trip per call |

---

## OpenAI → Claude Translation

```python
# MCP server (mcp_server.py) — NO CHANGE between OpenAI and Claude
# The MCP server is provider-agnostic.

# MCP client bridge (agent.py)
# OpenAI: manual schema conversion + manual tool routing
mcp_tool_to_openai(tool)          # convert MCP schema → OpenAI function spec
json.loads(tc.function.arguments)  # parse args
{"role":"tool","tool_call_id":...} # tool result format

# CLAUDE: native MCP support — no bridge code needed
# client.beta.messages.create(
#     mcp_servers=[{"type":"stdio","command":"python","args":["mcp_server.py"]}],
#     ...
# )
# Claude SDK handles discovery, routing, and result injection automatically.

# tool_choice
tool_choice="auto"      # → {"type": "auto"}
tool_choice="required"  # → {"type": "any"}
```

---

## Learning Objectives

- **D2.4** `.mcp.json` project scope vs `~/.claude.json` user scope
- **D2.4** `${ENV_VAR}` expansion — never hardcode credentials in config
- **D2.4** MCP resources for policy/catalog data (read before acting)
- **D2.1** Tool distribution — 4 focused tools outperforms 18 noisy tools
- **D2.3** Decision rules in system prompt override default model behavior
