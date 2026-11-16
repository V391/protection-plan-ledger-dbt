select
    cast(claim_status_id as varchar)    as claim_status_id,
    cast(claim_id as varchar)           as claim_id,
    cast(contract_id as varchar)        as contract_id,
    cast(status as varchar)             as status,
    cast(resolution as varchar)         as resolution,
    cast(amount as decimal(18, 2))      as amount,
    cast(currency as varchar)           as currency,
    cast(changed_at as timestamp)       as changed_at,
    cast(_loaded_at as timestamp)       as _loaded_at
from {{ source('raw', 'claim_status_history') }}
