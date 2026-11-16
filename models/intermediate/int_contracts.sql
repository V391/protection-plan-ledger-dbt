-- One row per contract: the created event, its cancellation if any, the FX rate on the purchase
-- date and the merchant revenue share that was in force at the moment of sale (point in time).
with events as (
    select * from {{ ref('stg_contract_events') }}
),

created as (
    select * from events where event_type = 'contract.created'
),

cancelled as (
    select contract_id, occurred_at as cancelled_at, refund_amount, _loaded_at
    from events
    where event_type = 'contract.cancelled'
),

merchant_versions as (
    select * from {{ ref('int_merchant_versions') }}
),

fx as (
    select * from {{ ref('stg_fx_rates') }}
)

select
    c.contract_id,
    c.merchant_id,
    c.order_line_id,
    c.product_category,
    c.plan_term_months,
    c.currency,
    c.plan_price,
    c.occurred_at                                   as purchased_at,
    cast(c.occurred_at as date)                     as purchase_date,
    c.coverage_start_date,
    c.coverage_end_date,
    x.cancelled_at,
    cast(x.cancelled_at as date)                    as cancel_date,
    coalesce(x.refund_amount, 0)                    as refund_amount,
    fx.usd_per_unit                                 as fx_rate_at_purchase,
    mv.revenue_share_rate                           as revenue_share_rate_at_sale,
    mv.is_test_merchant,
    greatest(c._loaded_at, coalesce(x._loaded_at, c._loaded_at)) as source_loaded_at
from created c
left join cancelled x
    on x.contract_id = c.contract_id
left join fx
    on fx.currency = c.currency
   and fx.rate_date = cast(c.occurred_at as date)
left join merchant_versions mv
    on mv.merchant_id = c.merchant_id
   and c.occurred_at >= mv.valid_from
   and (c.occurred_at < mv.valid_to or mv.valid_to is null)
