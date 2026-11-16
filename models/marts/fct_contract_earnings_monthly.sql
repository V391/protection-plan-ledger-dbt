{{
  config(
    materialized='incremental',
    unique_key='contract_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
  )
}}
-- Earned revenue per contract per month. Incremental by contract: any contract touched since the
-- last run (new sale, cancellation) is deleted and rebuilt whole, so a cancellation that shortens
-- the earning window cannot leave stale months behind.
with contracts as (
    select * from {{ ref('fct_contracts') }}
    {% if is_incremental() %}
    where source_loaded_at > (
        select {{ dbt.dateadd('hour', -var('incremental_lookback_hours'), 'max(source_loaded_at)') }} from {{ this }}
    )
    {% endif %}
),

months as (
    select * from {{ ref('util_months') }}
),

earning as (
    select
        c.contract_id,
        c.merchant_id,
        c.is_test_merchant,
        m.month_start,
        {{ dbt.datediff(
            'greatest(c.coverage_start_date, m.month_start)',
            'least(c.earn_end_date, m.next_month_start)',
            'day') }}                                        as earned_days,
        c.net_usd,
        c.earn_days,
        c.source_loaded_at
    from contracts c
    join months m
      on m.month_start < c.earn_end_date
     and m.next_month_start > c.coverage_start_date
    where c.earn_days > 0
),

-- A contract with nothing to earn in the horizon (full refund, coverage not started yet) still
-- gets one zero row, so delete+insert clears months it may have earned in an earlier run.
placeholder as (
    select
        c.contract_id,
        c.merchant_id,
        c.is_test_merchant,
        cast({{ dbt.date_trunc('month', 'c.purchase_date') }} as date) as month_start,
        0 as earned_days,
        c.net_usd,
        c.earn_days,
        c.source_loaded_at
    from contracts c
    where not exists (select 1 from earning e where e.contract_id = c.contract_id)
)

select
    cast(contract_id as varchar)                                       as contract_id,
    cast(merchant_id as varchar)                                       as merchant_id,
    cast(is_test_merchant as boolean)                                  as is_test_merchant,
    cast(month_start as date)                                          as month_start,
    cast(earned_days as integer)                                       as earned_days,
    cast(case when earn_days > 0 then net_usd * earned_days / earn_days else 0 end as double) as earned_usd,
    cast(source_loaded_at as timestamp)                                as source_loaded_at
from (
    select * from earning
    union all
    select * from placeholder
) all_rows
