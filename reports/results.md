# Results

Simulation: 40 merchants (plus 2 sandbox stores), Jan 2024 to Dec 2025, USD, CAD and GBP.

| Metric | Value |
|---|---|
| Protection plans sold | 30,773 |
| Attach rate on eligible lines | 24.2% |
| Gross written premium | $2,533,713 |
| Refunds on cancellations | $149,618 |
| Earned revenue | $819,204 |
| Deferred (unearned) at Dec 2025 | $1,564,891 |
| Claims paid | $322,370 |
| Loss ratio (claims paid / earned) | 39.4% |
| Merchant revenue share payable | $518,611 |

## Proof

- **Answer key:** `mrt_merchant_monthly` matches the simulator's independent answer key on all 894 merchant months, 7 metrics each, counts exact and money to the cent.
- **Finance reconciliation:** 33,942 of 33,942 ledger and payment movements matched to the cent; 0 in flight at the cutoff; 0 breaks.
- **Incremental == full refresh:** built in two batches (cutoff 2025-11-01 00:00:00), then compared with a from-scratch build: 0 differing rows across fct_contracts, fct_contract_earnings_monthly, fct_claims, mrt_merchant_monthly.
- **Traps handled:** 998 redelivered webhook events, 151 claim status rows landing over a day late, 23 mid-stream revenue share changes, payments in minor units, 3 currencies, 2 sandbox stores.
- **Injected defects: 9 of 9 caught**: see [defects.md](defects.md).
