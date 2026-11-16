select
    cast(order_id as varchar)       as order_id,
    cast(merchant_id as varchar)    as merchant_id,
    cast(ordered_at as timestamp)   as ordered_at,
    cast(currency as varchar)       as currency,
    cast(_loaded_at as timestamp)   as _loaded_at
from {{ source('raw', 'orders') }}
