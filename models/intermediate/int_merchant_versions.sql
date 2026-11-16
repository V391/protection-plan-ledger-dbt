-- Type 2 history built straight from the CDC log: each change opens a version, the next one closes it.
with changes as (
    select * from {{ ref('stg_merchant_changes') }}
)

select
    merchant_id || '@' || cast(changed_at as varchar)                        as merchant_version_id,
    merchant_id,
    merchant_name,
    vertical,
    platform,
    currency,
    revenue_share_rate,
    is_test_merchant,
    changed_at                                                               as valid_from,
    lead(changed_at) over (partition by merchant_id order by changed_at)     as valid_to,
    lead(changed_at) over (partition by merchant_id order by changed_at) is null as is_current
from changes
