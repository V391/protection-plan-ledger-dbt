-- Merchant by month: attach rate, written and earned revenue, claims, loss ratio, merchant payable.
-- Test merchants are excluded. Every metric sits in the month its event happened.
with contracts as (
    select * from {{ ref('fct_contracts') }} where not is_test_merchant
),

current_merchants as (
    select * from {{ ref('dim_merchants') }} where is_current
),

sales as (
    select
        merchant_id,
        cast({{ dbt.date_trunc('month', 'purchase_date') }} as date)  as month_start,
        count(*)                                                     as contracts_sold,
        sum(price_usd)                                               as gwp_usd,
        sum(price_usd * revenue_share_rate_at_sale)                  as payable_on_sales_usd
    from contracts
    group by 1, 2
),

refunds as (
    select
        merchant_id,
        cast({{ dbt.date_trunc('month', 'cancel_date') }} as date)    as month_start,
        sum(refund_usd)                                              as refunds_usd,
        sum(refund_usd * revenue_share_rate_at_sale)                 as payable_clawback_usd
    from contracts
    where cancelled_at is not null
    group by 1, 2
),

earned as (
    select merchant_id, month_start, sum(earned_usd) as earned_usd
    from {{ ref('fct_contract_earnings_monthly') }}
    where not is_test_merchant
    group by 1, 2
),

claims as (
    select
        merchant_id,
        cast({{ dbt.date_trunc('month', 'paid_date') }} as date)      as month_start,
        sum(paid_usd)                                                as claims_paid_usd,
        count(*)                                                     as claims_paid
    from {{ ref('fct_claims') }}
    where paid_at is not null and not is_test_merchant
    group by 1, 2
),

eligible as (
    select
        o.merchant_id,
        cast({{ dbt.date_trunc('month', 'o.ordered_at') }} as date)   as month_start,
        sum(case when l.is_protection_eligible then 1 else 0 end)    as eligible_lines
    from {{ ref('stg_order_lines') }} l
    join {{ ref('stg_orders') }} o on o.order_id = l.order_id
    join current_merchants cm on cm.merchant_id = o.merchant_id and not cm.is_test_merchant
    group by 1, 2
),

keys as (
    select merchant_id, month_start from sales
    union select merchant_id, month_start from refunds
    union select merchant_id, month_start from earned
    union select merchant_id, month_start from claims
    union select merchant_id, month_start from eligible
)

select
    cast(k.merchant_id as varchar)                                               as merchant_id,
    cast(k.month_start as date)                                                  as month_start,
    cast(cm.merchant_name as varchar)                                            as merchant_name,
    cast(cm.vertical as varchar)                                                 as vertical,
    cast(cm.platform as varchar)                                                 as platform,
    cast(coalesce(e.eligible_lines, 0) as bigint)                                as eligible_lines,
    cast(coalesce(s.contracts_sold, 0) as bigint)                                as contracts_sold,
    cast(coalesce(s.contracts_sold, 0) * 1.0 / nullif(e.eligible_lines, 0) as double) as attach_rate,
    cast(coalesce(s.gwp_usd, 0) as double)                                       as gwp_usd,
    cast(coalesce(r.refunds_usd, 0) as double)                                   as refunds_usd,
    cast(coalesce(s.gwp_usd, 0) - coalesce(r.refunds_usd, 0) as double)          as net_written_usd,
    cast(coalesce(ea.earned_usd, 0) as double)                                   as earned_usd,
    cast(coalesce(c.claims_paid, 0) as bigint)                                   as claims_paid,
    cast(coalesce(c.claims_paid_usd, 0) as double)                               as claims_paid_usd,
    cast(coalesce(c.claims_paid_usd, 0) / nullif(ea.earned_usd, 0) as double)    as loss_ratio,
    cast(coalesce(s.payable_on_sales_usd, 0) - coalesce(r.payable_clawback_usd, 0) as double) as merchant_payable_usd
from keys k
left join current_merchants cm on cm.merchant_id = k.merchant_id
left join sales s    on s.merchant_id = k.merchant_id  and s.month_start = k.month_start
left join refunds r  on r.merchant_id = k.merchant_id  and r.month_start = k.month_start
left join earned ea  on ea.merchant_id = k.merchant_id and ea.month_start = k.month_start
left join claims c   on c.merchant_id = k.merchant_id  and c.month_start = k.month_start
left join eligible e on e.merchant_id = k.merchant_id  and e.month_start = k.month_start
