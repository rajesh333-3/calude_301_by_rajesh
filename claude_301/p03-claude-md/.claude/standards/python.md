# Python Coding Standards
# Imported by .claude/CLAUDE.md — applies project-wide

## Type Hints
- Every function parameter and return value must be type-annotated
- Use `Optional[X]` (or `X | None` in Python 3.10+) for nullable values
- Prefer built-in generics: `list[str]` not `List[str]`

## Docstrings
- All public functions, classes, and modules need docstrings
- Format: Google style
  ```python
  def fn(x: int) -> str:
      """One-line summary.

      Args:
          x: Description of x.

      Returns:
          Description of return value.
      """
  ```

## Error Handling
- Never let raw exception messages reach the user
- Log the original exception internally; return a clean message externally
- Use custom exception classes for domain errors (e.g., `CustomerNotFoundError`)

## Imports
- Standard library → third-party → local (blank line between each group)
- No wildcard imports (`from module import *`)
