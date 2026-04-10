/**
 * React frontend — sample source file for p03.
 *
 * When Claude Code opens THIS file:
 *   Loads: .claude/CLAUDE.md (project)
 *   Skips: .claude/rules/api-conventions.md (path: src/api/** — doesn't match src/ui/)
 *   Skips: .claude/rules/testing.md (path: **\/*.test.py — .tsx doesn't match)
 *
 * Only the project-level rules load here — no backend noise, no test noise.
 */

import { useState, useEffect } from "react";

interface Customer {
  customer_id: string;
  name: string;
  email: string;
  account_status: string;
  loyalty_tier: string;
}

export default function App() {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/customers/CUST-001")
      .then((res) => {
        if (!res.ok) throw new Error("Customer not found");
        return res.json();
      })
      .then(setCustomer)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) return <p>Error: {error}</p>;
  if (!customer) return <p>Loading...</p>;

  return (
    <div>
      <h1>{customer.name}</h1>
      <p>Status: {customer.account_status}</p>
      <p>Tier: {customer.loyalty_tier}</p>
    </div>
  );
}
