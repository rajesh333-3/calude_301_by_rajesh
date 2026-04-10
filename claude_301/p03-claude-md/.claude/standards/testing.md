# Testing Standards
# Imported by .claude/CLAUDE.md — applies project-wide

## Framework
- Use pytest; do NOT use unittest
- Fixtures over setUp/tearDown
- One assertion concept per test (multiple asserts are fine if they test one idea)

## Naming
- Files:      `test_{module_name}.py`
- Functions:  `test_{what_it_does}_{expected_outcome}`
- Example:    `test_get_customer_returns_404_when_not_found`

## Coverage
- All public functions must have at least one happy-path test
- All error branches must have at least one sad-path test

## External Services
- Mock ALL external services — never call real APIs in tests
- Use `pytest-mock` or `unittest.mock.patch`
- Database: use an in-memory SQLite or test fixtures, never prod DB
