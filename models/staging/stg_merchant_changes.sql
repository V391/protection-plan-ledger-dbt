select
    cast(merchant_id as varchar)          as merchant_id,
    cast(op as varchar)                   as change_op,
    cast(merchant_name as varchar)        as merchant_name,
    cast(vertical as varchar)             as vertical,
    cast(platform as varchar)             as platform,
    cast(currency as varchar)             as currency,
    cast(revenue_share_rate as double)    as revenue_share_rate,
    cast(is_test as boolean)              as is_test_merchant,
    cast(changed_at as timestamp)         as changed_at,
    cast(_loaded_at as timestamp)         as _loaded_at
from {{ source('raw', 'merchant_changes') }}
