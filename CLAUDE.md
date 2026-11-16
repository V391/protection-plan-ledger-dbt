# Working in this repo (for coding agents)

dbt project for a post-purchase protection ledger. DuckDB locally, Snowflake target in `profiles.yml`.

## Run
- Everything: `python run_all.py` (generate, two batch incremental build, full refresh compare, defects, docs).
- Just the models: `python load_raw.py --db warehouse/dev.duckdb` then `dbt build` with `DBT_PROFILES_DIR=.`.
- A change is done when `python run_all.py` exits 0. Green `dbt build` alone is not enough: the incremental
  comparison and the defect suite run outside dbt.

## Rules that are easy to break
- **Grain first.** Every model states its grain in the first comment. `fct_contracts` is one row per contract,
  `fct_contract_earnings_monthly` one per contract per month, `mrt_merchant_monthly` one per merchant per month.
- **Money.** Payments arrive in minor units. Convert in `stg_payment_transactions` and nowhere else. Plan prices and
  refunds stay `decimal(18,2)` in sale currency; USD amounts use the purchase date FX rate (claims: paid date).
- **Point in time.** Merchant revenue share comes from `int_merchant_versions` at the sale timestamp. Never join
  `dim_merchants where is_current` for anything that happened in the past.
- **Incremental models rebuild whole entities.** Earnings are delete+insert by `contract_id`, claims by `claim_id`.
  If you add a column that can change after first load, make sure it moves `source_loaded_at`.
- **Event month.** Sales book in the purchase month, refunds in the cancel month, claims in the paid month.
- **Test merchants** (`is_test_merchant`) are excluded from marts but kept in the reconciliation.
- Do not edit `tests/assert_marts_match_truth.sql` or the answer key to make a build pass. A mismatch is a bug.

## Skills
- `.claude/skills/add-merchant-source/` onboarding a new integration feed.
- `.claude/skills/debug-recon-break/` when `rec_contract_payments` fails.
- `.claude/skills/review-ai-sql/` checklist to run on any SQL an agent wrote before it is merged.
