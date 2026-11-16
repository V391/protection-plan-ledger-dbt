---
name: review-ai-sql
description: Review SQL or dbt model changes written by a coding agent before merge. Use on every PR that touches models/, tests/ or macros/, and whenever asked to review generated SQL.
---

# Review agent written SQL

Generated SQL usually compiles and usually looks right. The failures are quiet. Check each point and
quote the line for any finding.

1. **Grain.** State the grain of every model touched. Run `select <key>, count(*) ... having count(*) > 1`
   on the result. A join that should be one to one and is not is the most common silent bug.
2. **Fan out before aggregate.** Any `sum()` after a join to a table with many rows per key double counts.
3. **Point in time.** Joins to merchant settings must use `valid_from <= ts < valid_to`, not `is_current`.
4. **Money.** No arithmetic on minor units outside staging. No FX rate other than the documented one.
   Decimals stay decimals until converted to USD.
5. **Incremental logic.** The `is_incremental()` filter must re-read late rows (lookback), and the
   unique_key must be the entity, so a changed entity is rebuilt whole. Run `python run_all.py`: it fails
   if incremental and full refresh differ by a single row.
6. **Event month.** Metrics land in the month of their own event (sale, cancel, paid), never the load month.
7. **Tests moved with the code.** New columns have descriptions (CI fails otherwise), new enums have
   `accepted_values`, new amounts have `in_range`. A test that was loosened needs a reason in the PR.
8. **Nothing was tuned to the answer key.** Diff `tests/` and `data/truth`. Changes there need a human.

Output: approve, or a numbered list of findings with file:line and the query that shows the problem.
