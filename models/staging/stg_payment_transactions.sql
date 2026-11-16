-- The payments platform reports minor units (cents, pence). Convert once, here, and nowhere else.
select
    cast(txn_id as varchar)                                   as txn_id,
    cast(txn_type as varchar)                                 as txn_type,
    cast(contract_id as varchar)                              as contract_id,
    cast(merchant_id as varchar)                              as merchant_id,
    cast(currency as varchar)                                 as currency,
    cast(amount_minor as bigint)                              as amount_minor,
    cast(cast(amount_minor as decimal(18, 2)) / 100 as decimal(18, 2)) as amount,
    cast(cast(fee_minor as decimal(18, 2)) / 100 as decimal(18, 2))    as fee_amount,
    cast(created_at as timestamp)                             as created_at,
    cast(_loaded_at as timestamp)                             as _loaded_at
from {{ source('raw', 'payment_transactions') }}
