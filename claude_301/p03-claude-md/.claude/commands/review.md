# /review — Team Code Review Checklist
# =====================================
# Shared slash command — version-controlled so every teammate gets it via git.
# Usage: /review  (run on the current file open in the editor)
#
# Claude Code loads commands from .claude/commands/ automatically.
# No installation step — just pull and it appears.

Review the current file against the team checklist below.
For each item, output: ✓ pass | ✗ fail | — not applicable, then a one-line reason if fail.

## Checklist

### Python (skip if not a .py file)
- [ ] All functions have type hints on parameters and return value
- [ ] All public functions have a Google-style docstring
- [ ] No raw exception messages exposed to callers
- [ ] No wildcard imports (`from x import *`)
- [ ] Imports ordered: stdlib → third-party → local

### FastAPI routes (skip if not in src/api/)
- [ ] Handler is `async def`
- [ ] `response_model` declared on every endpoint
- [ ] Request body uses a Pydantic model, not a raw dict
- [ ] No business logic inside the route handler — delegates to a service

### Tests (skip if not a test file)
- [ ] File named `test_{module}.py`
- [ ] Every test has a docstring
- [ ] External services are mocked
- [ ] Tests use pytest fixtures, not setUp/tearDown

### General (always checked)
- [ ] No TODO comments left in code
- [ ] No hardcoded credentials, API keys, or secrets
- [ ] Commit-ready: would pass `pytest` and linting

## Output Format

```
File: src/api/customers.py

✓ Type hints on all functions
✗ Missing docstring on `get_customer_by_email` — add Google-style docstring
✓ No raw exceptions exposed
— FastAPI checks: not applicable (not a route file)
...

Summary: 1 issue found. Fix before merging.
```
