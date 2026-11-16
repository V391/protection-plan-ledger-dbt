# Injected defects: 9 of 9 caught

Each defect is applied alone to clean raw data, then `dbt build` runs.

| Defect | Caught by |
|---|---|
| Payments feed stops loading 3 days before the others | `assert_sources_not_stalled` |
| Payments platform switches 1 week of amounts from minor to major units | `accepted_values_rec_contract_payments_match_status__matched__in_flight` |
| Webhook replay re-sends 3 sales under new event_ids | `unique_int_contracts_contract_id` |
| Integration sends 5 plans with a negative price | `in_range_stg_contract_events_plan_price__0_01` |
| Claims system files a claim against a contract that does not exist | `relationships_fct_claims_contract_id__contract_id__ref_fct_contracts_` |
| Merchant CDC emits two different revenue shares at the same instant | `unique_int_merchant_versions_merchant_version_id` |
| Admin enters a revenue share as a percent (25) instead of a fraction | `in_range_stg_merchant_changes_revenue_share_rate__0_6__0` |
| FX feed misses GBP for one trading day | `assert_fx_rates_complete` |
| Cancellation service refunds 3 prorated cancels in full | `accepted_values_rec_contract_payments_match_status__matched__in_flight`, `assert_refunds_follow_policy` |
