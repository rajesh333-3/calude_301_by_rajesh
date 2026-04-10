"""
FastAPI backend — sample source file for p03.

When Claude Code opens THIS file:
  Loads: .claude/CLAUDE.md (project) + .claude/rules/api-conventions.md (path-scoped)
  Skips: .claude/rules/testing.md (path doesn't match **/*.test.py or **/test_*.py)
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Customer API")


class CustomerResponse(BaseModel):
    customer_id: str
    name: str
    email: str
    account_status: str
    loyalty_tier: str


CUSTOMERS: dict[str, CustomerResponse] = {
    "CUST-001": CustomerResponse(
        customer_id="CUST-001",
        name="Alice Johnson",
        email="alice@example.com",
        account_status="active",
        loyalty_tier="gold",
    )
}


@app.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str) -> CustomerResponse:
    """Retrieve a customer by ID.

    Args:
        customer_id: Customer identifier in format CUST-XXXXX.

    Returns:
        CustomerResponse with account details.

    Raises:
        HTTPException: 404 if customer not found.
    """
    if customer_id not in CUSTOMERS:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    return CUSTOMERS[customer_id]
