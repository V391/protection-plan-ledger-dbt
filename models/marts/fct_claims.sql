{{
  config(
    materialized='incremental',
    unique_key='claim_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
  )
}}
-- One row per claim, rebuilt from its full status history. Incremental runs pick up any claim
-- with a status row loaded inside the lookback window, which catches statuses that land late.
with history as (
    select * from {{ ref('stg_claim_status_history') }}
),

{% if is_incremental() %}
changed as (
    select distinct claim_id
    from history
    where _loaded_at > (
        select {{ dbt.dateadd('hour', -var('incremental_lookback_hours'), 'max(source_loaded_at)') }} from {{ this }}
    )
),

in_scope as (
    select h.* from history h join changed c on c.claim_id = h.claim_id
),
{% else %}
in_scope as (
    select * from history
),
{% endif %}

rolled as (
    select
        claim_id,
        max(contract_id)                                                       as contract_id,
        min(case when status = 'filed' then changed_at end)                    as filed_at,
        max(case when status in ('approved', 'denied') then status end)        as decision,
        max(case when status in ('approved', 'denied') then changed_at end)    as decided_at,
        max(case when status = 'paid' then changed_at end)                     as paid_at,
        max(case when status = 'paid' then amount end)                         as paid_amount,
        max(resolution)                                                        as resolution,
        max(currency)                                                          as currency,
        max(_loaded_at)                                                        as source_loaded_at
    from in_scope
    group by claim_id
),

latest as (
    select claim_id, status as current_status
    from in_scope
    qualify row_number() over (partition by claim_id order by changed_at desc) = 1
)

select
    cast(r.claim_id as varchar)                 as claim_id,
    cast(r.contract_id as varchar)              as contract_id,
    cast(k.merchant_id as varchar)              as merchant_id,
    cast(k.product_category as varchar)         as product_category,
    cast(l.current_status as varchar)           as current_status,
    cast(r.decision as varchar)                 as decision,
    cast(r.resolution as varchar)               as resolution,
    cast(r.filed_at as timestamp)               as filed_at,
    cast(r.decided_at as timestamp)             as decided_at,
    cast(r.paid_at as timestamp)                as paid_at,
    cast(cast(r.paid_at as date) as date)       as paid_date,
    cast(r.currency as varchar)                 as currency,
    cast(r.paid_amount as decimal(18, 2))       as paid_amount,
    cast(r.paid_amount * fx.usd_per_unit as double) as paid_usd,
    cast(k.is_test_merchant as boolean)         as is_test_merchant,
    cast(r.source_loaded_at as timestamp)       as source_loaded_at
from rolled r
join latest l on l.claim_id = r.claim_id
left join {{ ref('fct_contracts') }} k on k.contract_id = r.contract_id
left join {{ ref('stg_fx_rates') }} fx
  on fx.currency = r.currency
 and fx.rate_date = cast(r.paid_at as date)
