# Project Standards — Team Python/React Project
# ================================================
# SCOPE: Project-level (version-controlled, applies to ALL teammates on clone)
# FILE:  p03-claude-md/.claude/CLAUDE.md
#
# This is the CORRECT place for team conventions.
# Exam trap: putting these in ~/.claude/CLAUDE.md means new teammates never get them.

@import ./standards/python.md
@import ./standards/testing.md

## General Rules

- Always use type hints in Python functions
- All public functions need docstrings
- Error messages must be user-friendly — never expose raw exception messages to users
- Commit messages: imperative mood, ≤72 chars ("Add retry logic" not "Added retry logic")
- Never commit secrets, API keys, or credentials

## Project Layout

```
src/api/   → FastAPI backend  (see .claude/rules/api-conventions.md for API-specific rules)
src/ui/    → React frontend   (see .claude/rules/ui-conventions.md for frontend rules)
```

## Workflow

- Run `pytest src/` before every commit
- Open PRs against `main`; at least one reviewer required
