---
paths: ["**/*.test.py", "**/test_*.py", "**/*.spec.ts"]
---
# Testing Conventions
# ONLY loaded when editing test files — not loaded for src/api/*.py or src/ui/*.tsx.
# Path-scoped rules save context: you don't see these when writing production code.

## pytest Rules

- Use fixtures, not setUp/tearDown
- Mark slow tests: `@pytest.mark.slow`
- Mark integration tests: `@pytest.mark.integration`
- Parametrize repeated similar tests with `@pytest.mark.parametrize`

## What Every Test Must Have

1. A docstring explaining WHAT is being tested and WHY it matters
2. Arrange / Act / Assert comment blocks for clarity
3. A single conceptual assertion (multiple asserts OK if they validate one thing)

```python
def test_get_customer_returns_404_when_not_found(client):
    """get_customer should return 404 when the customer ID does not exist in the DB."""
    # Arrange
    customer_id = "CUST-DOES-NOT-EXIST"

    # Act
    response = client.get(f"/customers/{customer_id}")

    # Assert
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
```

## Mocking

- Always mock external HTTP calls (`httpx`, `requests`)
- Always mock database calls in unit tests — use fixtures for integration tests
- Never mock the system under test itself

## TypeScript / Vitest (*.spec.ts)

- Use `vi.mock()` for module mocks
- Use `describe` blocks to group related tests
- Test file co-located with source: `Button.tsx` → `Button.spec.ts`
