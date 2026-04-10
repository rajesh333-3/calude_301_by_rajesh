"""
Sample file for CI review — intentionally contains bugs.
Bug list:
  1. Refund processed without order ownership verification (line 38)
  2. No check that refund amount <= order total (line 41)
  3. Race condition in process_refund (no transaction / locking)
  4. Error details leaked to caller (line 55)
"""

from typing import Optional


ORDERS_DB: dict = {
    "ORD-001": {"order_id": "ORD-001", "customer_id": "CUST-001",
                "total": 129.99, "status": "delivered"},
    "ORD-002": {"order_id": "ORD-002", "customer_id": "CUST-002",
                "total": 600.00, "status": "processing"},
}

REFUNDS_DB: dict = {}


def get_order(order_id: str) -> Optional[dict]:
    return ORDERS_DB.get(order_id)


def process_refund(order_id: str, amount: float, requesting_customer_id: str) -> dict:
    order = get_order(order_id)
    if not order:
        return {"isError": True, "message": f"Order {order_id} not found"}

    # BUG: no ownership check — any customer can refund any order
    # Should verify: order["customer_id"] == requesting_customer_id

    # BUG: no check that amount <= order["total"]
    # A customer could request a $10,000 refund on a $10 order

    # BUG: race condition — two concurrent requests can both pass these checks
    # and both receive refunds. Needs DB-level locking or idempotency key.

    refund_id = f"REF-{order_id}-{int(amount*100)}"
    REFUNDS_DB[refund_id] = {
        "refund_id": refund_id,
        "order_id":  order_id,
        "amount":    amount,
        "status":    "approved",
    }
    return {"refund_id": refund_id, "status": "approved", "amount": amount}


def get_order_history(customer_id: str) -> list:
    try:
        # Simulate a DB error
        raise ConnectionError("DB connection pool exhausted at host db-primary:5432")
    except Exception as e:
        # BUG: raw exception message (including host/port) leaked to caller
        return {"isError": True, "message": str(e)}
