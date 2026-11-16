-- The merchant monthly mart against the simulator's answer key, every merchant, every month,
-- every metric. Counts must match exactly and money to the cent.
{{ config(tags=['truth']) }}

with m as (
    select * from {{ ref('mrt_merchant_monthly') }}
),

t as (
    select * from {{ source('truth', 'merchant_monthly') }}
),

j as (
    select
        coalesce(m.merchant_id, t.merchant_id)          as merchant_id,
        coalesce(m.month_start, cast(t.month_start as date)) as month_start,
        coalesce(m.eligible_lines, 0)        - coalesce(t.eligible_lines, 0)       as d_eligible_lines,
        coalesce(m.contracts_sold, 0)        - coalesce(t.contracts_sold, 0)       as d_contracts_sold,
        coalesce(m.gwp_usd, 0)               - coalesce(t.gwp_usd, 0)              as d_gwp_usd,
        coalesce(m.refunds_usd, 0)           - coalesce(t.refunds_usd, 0)          as d_refunds_usd,
        coalesce(m.earned_usd, 0)            - coalesce(t.earned_usd, 0)           as d_earned_usd,
        coalesce(m.claims_paid_usd, 0)       - coalesce(t.claims_paid_usd, 0)      as d_claims_paid_usd,
        coalesce(m.merchant_payable_usd, 0)  - coalesce(t.merchant_payable_usd, 0) as d_merchant_payable_usd
    from m
    full outer join t
      on t.merchant_id = m.merchant_id
     and cast(t.month_start as date) = m.month_start
)

select *
from j
where d_eligible_lines <> 0
   or d_contracts_sold <> 0
   or abs(d_gwp_usd) > 0.01
   or abs(d_refunds_usd) > 0.01
   or abs(d_earned_usd) > 0.01
   or abs(d_claims_paid_usd) > 0.01
   or abs(d_merchant_payable_usd) > 0.01
