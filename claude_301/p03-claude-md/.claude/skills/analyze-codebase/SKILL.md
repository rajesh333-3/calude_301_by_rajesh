---
context: fork
# ↑ ISOLATED — this skill runs in a forked context so verbose codebase output
#   does not pollute or fill the main session's context window.
#   Without context:fork a 10,000-token analysis would crowd out your conversation history.

allowed-tools:
  - Read
  - Grep
  - Glob
  # Bash is intentionally NOT listed — this skill cannot run arbitrary shell commands.
  # allowed-tools is a security boundary: keep it minimal.

argument-hint: "Enter the directory to analyze (default: src/)"
---

Analyze the codebase in the specified directory (or `src/` if none given).

Report the following:

1. **Module count** — total number of Python (`.py`) and TypeScript (`.ts`, `.tsx`) files
2. **Average file size** — mean lines across all discovered files
3. **Top 5 largest files** — filename + line count, sorted descending
4. **TODO count** — total occurrences of `# TODO` or `// TODO` across all files
5. **Test coverage estimate** — count of `test_*.py` / `*.spec.ts` files vs total source files

Format output as a compact markdown table where appropriate.
Flag any file over 500 lines as a refactor candidate.
