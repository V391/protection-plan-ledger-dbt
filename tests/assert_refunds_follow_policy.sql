-- Refund policy: full refund inside the free look window or before coverage starts,
-- otherwise prorated by days of coverage remaining. Rounding tolerance one cent.
with c as (
    select
        *,
        case
            when {{ dbt.datediff('purchase_date', 'cancel_date', 'day') }} < {{ var('free_look_days') }}
                 or cancel_date <= coverage_start_date
                then plan_price
            else plan_price
                 * {{ dbt.datediff('cancel_date', 'coverage_end_date', 'day') }}
                 / {{ dbt.datediff('coverage_start_date', 'coverage_end_date', 'day') }}
        end as expected_refund
    from {{ ref('fct_contracts') }}
    where cancelled_at is not null
)

select contract_id, plan_price, refund_amount, expected_refund
from c
where abs(refund_amount - expected_refund) > 0.01
