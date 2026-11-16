-- Relative freshness: every transactional feed must be within max_source_lag_hours of the
-- freshest one. Catches a feed that silently stops loading while the others keep going.
with feeds as (
    select 'orders' as feed, max(_loaded_at) as loaded_through from {{ ref('stg_orders') }}
    union all select 'order_lines', max(_loaded_at) from {{ ref('stg_order_lines') }}
    union all select 'contract_events', max(_loaded_at) from {{ ref('stg_contract_events') }}
    union all select 'payment_transactions', max(_loaded_at) from {{ ref('stg_payment_transactions') }}
    union all select 'claim_status_history', max(_loaded_at) from {{ ref('stg_claim_status_history') }}
),

freshest as (
    select max(loaded_through) as loaded_through from feeds
)

select f.feed, f.loaded_through, x.loaded_through as freshest_feed_loaded_through
from feeds f
cross join freshest x
where {{ dbt.datediff('f.loaded_through', 'x.loaded_through', 'hour') }} > {{ var('max_source_lag_hours') }}
