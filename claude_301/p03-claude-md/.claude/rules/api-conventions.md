---
paths: ["src/api/**/*"]
---
# API Conventions
# ONLY loaded when editing files under src/api/ — not loaded elsewhere.
# This keeps context window lean: frontend devs don't see backend rules.

## FastAPI Patterns

- Route handlers must be async
- Always declare response_model on every endpoint
- Use Pydantic models for request body and response — never raw dicts
- Group routes by resource using APIRouter, not a flat list in main.py

```python
# Good
router = APIRouter(prefix="/customers", tags=["customers"])

@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str) -> CustomerResponse:
    """Retrieve a customer by ID."""
    ...
```

## Status Codes

| Situation | Code |
|---|---|
| Success (read) | 200 |
| Created | 201 |
| Not found | 404 |
| Bad input | 422 (FastAPI auto) |
| Server error | 500 |

## Error Responses

Always return structured errors — never a bare string:
```python
{"detail": "Customer CUST-999 not found"}   # FastAPI HTTPException format
```

## No Business Logic in Route Handlers

Route handlers call service functions. Business logic lives in `services/`.
