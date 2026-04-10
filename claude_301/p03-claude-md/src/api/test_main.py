"""
Tests for src/api/main.py

When Claude Code opens THIS file:
  Loads: .claude/CLAUDE.md (project)
       + .claude/rules/api-conventions.md (path: src/api/**)
       + .claude/rules/testing.md (path: **/test_*.py  ← this file matches)
  All three load simultaneously — path rules stack, they don't override each other.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide a test client for the FastAPI app."""
    return TestClient(app)


def test_get_customer_returns_customer_when_found(client: TestClient) -> None:
    """get_customer should return full customer data for a known customer ID."""
    # Arrange
    customer_id = "CUST-001"

    # Act
    response = client.get(f"/customers/{customer_id}")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "CUST-001"
    assert data["name"] == "Alice Johnson"


def test_get_customer_returns_404_when_not_found(client: TestClient) -> None:
    """get_customer should return 404 when the customer ID does not exist."""
    # Arrange
    customer_id = "CUST-DOES-NOT-EXIST"

    # Act
    response = client.get(f"/customers/{customer_id}")

    # Assert
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
