-- Every currency must have a rate for every day trading has reached. Checked directly rather than
-- through sales, so a gap on a quiet day fails today instead of on the first sale that hits it.
with recursive trading_through as (
    select max(cast(ordered_at as date)) as last_day from {{ ref('stg_orders') }}
),

days (rate_date) as (
    select cast('{{ var("horizon_start") }}' as date)
    union all
    select cast({{ dbt.dateadd('day', 1, 'rate_date') }} as date)
    from days
    where rate_date < (select last_day from trading_through)
),

currencies as (
    select distinct currency from {{ ref('stg_fx_rates') }}
)

select c.currency, d.rate_date
from days d
cross join currencies c
left join {{ ref('stg_fx_rates') }} fx
  on fx.currency = c.currency
 and fx.rate_date = d.rate_date
where fx.usd_per_unit is null
