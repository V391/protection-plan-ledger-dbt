---
name: debug-recon-break
description: Diagnose a failing reconciliation between the contracts ledger and the payments platform (rec_contract_payments accepted_values test fails). Use when the build reports amount_mismatch, missing_in_payments, missing_in_ledger or currency_mismatch rows.
---

# Debug a reconciliation break

Do not change the reconciliation model or widen the in-flight window to make the test pass. Find the cause.

1. **Size it.**
   ```sql
   select match_status, txn_type, count(*), sum(ledger_amount), sum(payment_amount)
   from marts.rec_contract_payments
   where match_status not in ('matched', 'in_flight')
   group by 1, 2;
   ```
2. **Look for a shape.** Group the breaks by `merchant_id`, `date_trunc('day', occurred_at)` and currency.
   One day or one merchant points at a feed. Every row points at a model change.
3. **Classify against known causes:**
   | Pattern | Likely cause | Where to look |
   |---|---|---|
   | payment = ledger / 100 or x 100 | provider changed units | `stg_payment_transactions` raw `amount_minor` |
   | missing_in_payments, all recent | payments feed stalled | `assert_sources_not_stalled`, raw `_loaded_at` |
   | missing_in_ledger, refunds | cancel webhook lost or not deduplicated | `stg_contract_events` |
   | refund amount differs | refund policy bug upstream | `assert_refunds_follow_policy` |
   | currency_mismatch | merchant settlement currency changed | `int_merchant_versions` |
4. **Confirm on raw rows.** Pull three example `contract_id`s through every layer, raw to mart.
5. **Fix at the source layer**, add or tighten a test that would have caught it earlier than the reconciliation,
   and add the case to `checks/inject_defects.py`.

Report: count and value of breaks, root cause with example ids, the fix, and the new test.
