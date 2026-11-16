# Protection plan ledger in dbt

A dbt project that turns the raw feeds of a post-purchase protection business (merchant orders, protection plan sales, cancellations, claims, payment platform transactions) into the tables Finance and Merchant Success run on. It proves those tables are right instead of asserting it.

**Result:** all 70 dbt checks pass. The merchant monthly mart matches an independent answer key on **all 894 merchant months**, **33,942 of 33,942** ledger and payment movements reconcile to the cent, the incremental build equals a full refresh row for row, and **9 of 9** deliberately injected data defects fail the build.

## Why this exists

Selling protection plans at checkout produces data that is easy to get almost right. A plan is cash on day one but revenue over years, sometimes starting only after the manufacturer warranty ends. Cancellations refund in full or prorated depending on timing. Merchants are paid a revenue share that changes over time. The payments platform reports in cents. Webhooks arrive twice. Each of those is a quiet way for a Finance number to drift. This repo models them explicitly and puts a test on every one.

## The data, and the traps in it

`generator/generate.py` simulates two years (Jan 2024 to Dec 2025) for 40 merchants plus 2 sandbox stores across electronics, appliances, furniture, bikes, jewelry and apparel, selling in USD, CAD and GBP. It lands raw files the way an S3 landing zone would, each row stamped with `_loaded_at`, and writes a separate answer key computed in plain Python, independent of dbt.

| Trap | Wrong answer if you miss it |
|---|---|
| Contract webhook delivered at least once (same `event_id` twice) | Plan sales double counted |
| Payments platform amounts in minor units | Reconciliation off by 100x |
| Coverage starts after a 12 month manufacturer warranty on electronics and appliances | Revenue earned a year early |
| Free look cancellations (full refund) vs prorated refunds | Revenue earned on plans that were refunded |
| Merchant revenue share changes mid-stream (CDC log) | Merchant payable computed at today's rate |
| Claim statuses that land days after they happen | Incremental model misses paid claims |
| Three currencies, daily FX | Totals in mixed currencies |
| Sandbox stores with real looking sales | Fake revenue in Finance numbers |

## Models

```
raw (S3 landing -> warehouse, _loaded_at on every row)
  -> staging        typed, units converted once, webhook redeliveries removed
  -> intermediate   int_merchant_versions (SCD2 from CDC), int_contracts (point in time share, FX)
  -> marts          contracts enforced, every column documented
       dim_merchants                    Type 2, valid_from / valid_to
       fct_contracts                    one row per plan, status, net price, earning window
       fct_contract_earnings_monthly    incremental, delete+insert by contract
       fct_claims                       incremental, rebuilt from status history with a lookback
       mrt_merchant_monthly             attach rate, GWP, refunds, earned, claims, loss ratio, merchant payable
       rec_contract_payments            ledger vs payments platform, contract by contract, to the cent
```

Design choices worth reading:

- **Earned revenue** spreads the net price (price less refund) evenly over the days actually covered: to coverage end, to the cancel date on a prorated cancel, nothing on a full refund. A test checks no contract ever earns more than its net price and a closed contract earns exactly that.
- **Incremental by entity.** `fct_contract_earnings_monthly` deletes and rebuilds every month of any contract touched since the last run. A free look cancellation that lands late therefore wipes months already earned, instead of leaving them behind. A contract with nothing to earn still gets one zero row so the delete reaches it.
- **Point in time.** Merchant payable uses the revenue share in force at the moment of sale, joined on `valid_from <= purchased_at < valid_to`.
- **Reconciliation with timing.** An unmatched movement younger than 24 hours is `in_flight`, not a break. Anything else fails the build.
- **Relative freshness.** A feed more than 48 hours behind the freshest feed fails the build, so a silently stalled integration is caught even though the data is historical.

## Proof

`python run_all.py` does all of this and fails on any miss. CI runs the same script on every pull request.

1. **Two batch incremental build.** Loads data up to 1 Nov 2025 and builds, then loads the rest and runs incrementally. Compares every row of the four facts and marts with a from-scratch full refresh: **0 differing rows**.
2. **Answer key.** `tests/assert_marts_match_truth.sql` compares `mrt_merchant_monthly` to the simulator on every merchant, month and metric: **894 of 894 merchant months match**, 7 metrics each, counts exact and money to the cent.
3. **Finance reconciliation.** **33,942 of 33,942** plan sales and refunds match the payments platform to the cent, 0 breaks.
4. **Injected defects.** `checks/inject_defects.py` breaks the raw data nine ways, one at a time, and runs the build: **9 of 9 caught** ([which test caught which](reports/defects.md)).
5. **Docs gate.** `checks/check_docs.py` fails CI if any mart model or column lacks a description.

## Results

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

## Working with coding agents

The repo is set up so an agent picks up the conventions without being told:

- [`CLAUDE.md`](CLAUDE.md): grain, money handling, point in time joins, incremental rules, and the definition of done (`run_all.py` exits 0, not just `dbt build`).
- [`.claude/skills/add-merchant-source`](.claude/skills/add-merchant-source/SKILL.md): onboarding a new integration feed, ending with a new injected defect that must be caught.
- [`.claude/skills/debug-recon-break`](.claude/skills/debug-recon-break/SKILL.md): diagnosing a reconciliation failure from its shape, fixing at the source layer.
- [`.claude/skills/review-ai-sql`](.claude/skills/review-ai-sql/SKILL.md): the review checklist for SQL an agent wrote (grain, fan out, point in time, incremental logic, tests moved with the code).

## Run it

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run_all.py
```

Runs on DuckDB in a few minutes. `profiles.yml` also defines a Snowflake target; the SQL uses dbt cross-database macros (`dateadd`, `datediff`, `date_trunc`) and `qualify`, so the models run on both.
