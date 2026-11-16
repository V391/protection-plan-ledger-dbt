-- The webhook is at-least-once: a redelivery carries the same event_id with a later received_at.
-- Keep the first delivery of each event.
select
    cast(event_id as varchar)                 as event_id,
    cast(event_type as varchar)               as event_type,
    cast(contract_id as varchar)              as contract_id,
    cast(merchant_id as varchar)              as merchant_id,
    cast(order_line_id as varchar)            as order_line_id,
    cast(product_category as varchar)         as product_category,
    cast(plan_term_months as integer)         as plan_term_months,
    cast(plan_price as decimal(18, 2))        as plan_price,
    cast(currency as varchar)                 as currency,
    cast(coverage_start_date as date)         as coverage_start_date,
    cast(coverage_end_date as date)           as coverage_end_date,
    cast(refund_amount as decimal(18, 2))     as refund_amount,
    cast(occurred_at as timestamp)            as occurred_at,
    cast(received_at as timestamp)            as received_at,
    cast(_loaded_at as timestamp)             as _loaded_at
from {{ source('raw', 'contract_events') }}
qualify row_number() over (partition by event_id order by received_at) = 1
