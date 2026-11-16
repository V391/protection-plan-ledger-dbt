{{ config(materialized='table') }}
-- Month spine for the reporting horizon. Recursive CTE so it runs on DuckDB and Snowflake alike.
with recursive months (month_start) as (
    select cast('{{ var("horizon_start") }}' as date)
    union all
    select cast({{ dbt.dateadd('month', 1, 'month_start') }} as date)
    from months
    where cast({{ dbt.dateadd('month', 1, 'month_start') }} as date) <= cast('{{ var("horizon_end") }}' as date)
)

select
    month_start,
    cast({{ dbt.dateadd('month', 1, 'month_start') }} as date) as next_month_start
from months
