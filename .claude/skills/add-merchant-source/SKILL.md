---
name: add-merchant-source
description: Add a new raw feed from a merchant platform, payment provider or partner API to the ledger. Use when a new integration (for example a WooCommerce orders feed or a second payments processor) needs to land in the warehouse and reach the marts.
---

# Add a merchant or partner source

1. **Land it raw.** Add the feed to `generator/` (or the real extractor) so every row carries `_loaded_at`.
   Register it in `models/staging/_sources.yml` with a one line description of how it is delivered
   (webhook at least once, CDC, daily file, API poll).
2. **Stage it.** One `stg_<source>.sql`: rename, cast every column explicitly, convert units (minor to major,
   percent to fraction) here and only here. Deduplicate at-least-once feeds with
   `qualify row_number() over (partition by <natural id> order by received_at) = 1`.
3. **Contract the edges.** In the staging YAML add `unique` + `not_null` on the natural key,
   `accepted_values` on every enum, `in_range` on every amount and rate. A feed without range tests is not done.
4. **Add it to freshness.** Add the feed to `tests/assert_sources_not_stalled.sql`.
5. **Join point in time.** Anything that depends on merchant settings joins `int_merchant_versions` on the
   event timestamp, never the current row.
6. **Reconcile.** If the feed moves money, add its movements to `rec_contract_payments` (or a new `rec_` model)
   with the same match statuses, so a break fails the build.
7. **Prove it.** Add one defect for the new feed to `checks/inject_defects.py` (the failure you most expect from
   this provider) and confirm it is caught. Then `python run_all.py` must exit 0.

Report back: the grain of each new model, the tests added, and the defect you injected and what caught it.
