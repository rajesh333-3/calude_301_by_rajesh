# p03 — CLAUDE.md Hierarchy Mastery

Demonstrates the full CLAUDE.md configuration hierarchy for a multi-developer project
with a FastAPI backend and React frontend.

---

## Project Structure

```
p03-claude-md/
├── src/
│   ├── api/
│   │   ├── main.py          ← FastAPI backend (opens: project + api-conventions rules)
│   │   └── test_main.py     ← Tests (opens: project + api-conventions + testing rules)
│   └── ui/
│       └── App.tsx          ← React frontend (opens: project rules only)
│
├── .claude/
│   ├── CLAUDE.md            ← Project-level: team contract, version-controlled ✓
│   ├── standards/
│   │   ├── python.md        ← @imported by CLAUDE.md
│   │   └── testing.md       ← @imported by CLAUDE.md
│   ├── rules/
│   │   ├── api-conventions.md   ← path-scoped: src/api/**/*
│   │   └── testing.md           ← path-scoped: **/test_*.py, **/*.spec.ts
│   ├── commands/
│   │   └── review.md        ← /review slash command (available to all teammates)
│   └── skills/
│       └── analyze-codebase/
│           └── SKILL.md     ← context:fork skill (isolated context)
│
└── wrong_config_example.md  ← explains the Step 2 exam trap
```

---

## Explore & Verify

This module has no standalone Python scripts — it's a live configuration for Claude Code itself.
Open this project in Claude Code (VS Code extension or CLI) to see the hierarchy in action.

### Step 1 — Verify project-level config loads

Open `src/api/main.py` in Claude Code and run:
```
/memory
```
You should see `.claude/CLAUDE.md` listed as a loaded context source.
The imported standards (python.md, testing.md) are merged into it at load time.

---

### Step 2 — Verify path-scoped rules load only for matching files

Open `src/api/main.py` → run `/memory` → note loaded rules.
Open `src/api/test_main.py` → run `/memory` → **two** rule files should now appear:
  - `api-conventions.md` (path: `src/api/**/*`)
  - `testing.md` (path: `**/test_*.py`)

Open `src/ui/App.tsx` → run `/memory` → only project CLAUDE.md loads,
no api or testing rules. This is the context-window saving in action.

---

### Step 3 — Test the /review slash command

Open any Python file in the project, then type:
```
/review
```
Claude runs the checklist from `.claude/commands/review.md` against the open file.
Try it on `src/api/main.py` (should pass most checks) and then create a quick
test file without docstrings to see failures reported.

---

### Step 4 — Run the analyze-codebase skill

In Claude Code chat:
```
/analyze-codebase src/
```
Because `context: fork` is set in the skill's frontmatter, the output appears
in an isolated context — it won't flood your main conversation history.
Notice the `allowed-tools` restriction: the skill can Read/Grep/Glob but
cannot run Bash commands.

---

### Step 5 — Simulate the "new teammate" bug

1. Temporarily move `.claude/CLAUDE.md` out of the project folder.
2. Open Claude Code fresh — run `/memory`. Team standards are gone.
3. Move it back. Standards return immediately on the next Claude Code open.

This is the exam trap: user-level config stays on your machine;
project-level config travels with the repo.

---

### Step 6 — Inspect the @import resolution

Open `.claude/CLAUDE.md`. The `@import` lines pull in:
- `.claude/standards/python.md` — type hints, docstrings, error handling
- `.claude/standards/testing.md` — pytest rules, naming, mocking

These are merged at load time. Claude sees one unified context,
not separate files. Split them for maintainability, not for Claude's benefit.

---

## The Hierarchy

```
~/.claude/CLAUDE.md           user-level    personal only, NEVER in git
.claude/CLAUDE.md             project-level team contract, version-controlled
src/api/CLAUDE.md             directory     scoped to one subsystem
.claude/rules/*.md            path-scoped   loads only for matching file patterns
```

More specific always wins on conflicts. User-level is for personal preferences only.

---

## What Loads When

| File you open | Rules loaded |
|---|---|
| `src/api/main.py` | project CLAUDE.md + `api-conventions.md` |
| `src/api/test_main.py` | project CLAUDE.md + `api-conventions.md` + `testing.md` |
| `src/ui/App.tsx` | project CLAUDE.md only |
| Any `*.spec.ts` | project CLAUDE.md + `testing.md` |

Path-scoped rules reduce context window usage — backend rules don't load for frontend files.

---

## Key Concepts

### 1. Exam Trap — User-level vs Project-level

**Wrong:** `~/.claude/CLAUDE.md` — on your machine only, new teammates never see it.
**Right:** `.claude/CLAUDE.md` — version-controlled, every teammate gets it on clone.

See `wrong_config_example.md` for the full breakdown.

### 2. @import

Split large CLAUDE.md files into focused standards files:
```markdown
@import ./standards/python.md
@import ./standards/testing.md
```
Each file stays focused. The imports are resolved at load time.

### 3. Path-scoped Rules

Frontmatter `paths:` glob patterns control which files trigger a rule file:
```yaml
---
paths: ["src/api/**/*"]
---
```
No match → rule file is never loaded → context window stays lean.

### 4. Skills with `context: fork`

```yaml
---
context: fork
allowed-tools: [Read, Grep, Glob]
---
```
`context: fork` runs the skill in an isolated context — verbose output (e.g., scanning
thousands of files) doesn't fill or pollute the main conversation history.
`allowed-tools` is a security boundary — omitting `Bash` means the skill can't run shell commands.

### 5. Shared Slash Commands

`.claude/commands/review.md` → available as `/review` to every teammate who has pulled
the repo. No installation needed — Claude Code auto-discovers command files.

---

## Learning Objectives

- **D3.1** CLAUDE.md hierarchy: user → project → directory → path-scoped
- **D3.2** Skills frontmatter: `context:fork`, `allowed-tools`, `argument-hint`
- **D3.3** Path-scoped rules with glob patterns in `paths:` frontmatter
- **Exam trap:** Team conventions in user-level config = teammates never get them
