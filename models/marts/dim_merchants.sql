select
    cast(merchant_version_id as varchar)   as merchant_version_id,
    cast(merchant_id as varchar)           as merchant_id,
    cast(merchant_name as varchar)         as merchant_name,
    cast(vertical as varchar)              as vertical,
    cast(platform as varchar)              as platform,
    cast(currency as varchar)              as currency,
    cast(revenue_share_rate as double)     as revenue_share_rate,
    cast(is_test_merchant as boolean)      as is_test_merchant,
    cast(valid_from as timestamp)          as valid_from,
    cast(valid_to as timestamp)            as valid_to,
    cast(is_current as boolean)            as is_current
from {{ ref('int_merchant_versions') }}
