select
    cast(currency as varchar)        as currency,
    cast(rate_date as date)          as rate_date,
    cast(usd_per_unit as double)     as usd_per_unit,
    cast(_loaded_at as timestamp)    as _loaded_at
from {{ source('raw', 'fx_rates') }}
