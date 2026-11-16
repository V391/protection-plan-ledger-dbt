select
    cast(order_line_id as varchar)        as order_line_id,
    cast(order_id as varchar)             as order_id,
    cast(sku as varchar)                  as sku,
    cast(product_category as varchar)     as product_category,
    cast(unit_price as decimal(18, 2))    as unit_price,
    cast(is_eligible as boolean)          as is_protection_eligible,
    cast(_loaded_at as timestamp)         as _loaded_at
from {{ source('raw', 'order_lines') }}
