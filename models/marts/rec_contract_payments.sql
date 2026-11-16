-- Finance reconciliation: every ledger movement (plan sale, refund) against the payments platform,
-- contract by contract, to the cent. An unmatched row younger than the in-flight window is timing
-- (the other feed has not landed yet). Anything else is a break and fails the build.
with contracts as (
    select * from {{ ref('int_contracts') }}
),

ledger as (
    select contract_id, merchant_id, 'charge' as txn_type, currency, plan_price as amount, purchased_at as occurred_at
    from contracts
    union all
    select contract_id, merchant_id, 'refund' as txn_type, currency, -refund_amount as amount, cancelled_at as occurred_at
    from contracts
    where cancelled_at is not null
),

payments as (
    select contract_id, merchant_id, txn_type, currency, amount, created_at as occurred_at
    from {{ ref('stg_payment_transactions') }}
),

watermark as (
    select least(
        (select max(_loaded_at) from {{ ref('stg_contract_events') }}),
        (select max(_loaded_at) from {{ ref('stg_payment_transactions') }})
    ) as loaded_through
),

joined as (
    select
        coalesce(l.contract_id, p.contract_id)    as contract_id,
        coalesce(l.merchant_id, p.merchant_id)    as merchant_id,
        coalesce(l.txn_type, p.txn_type)          as txn_type,
        l.currency                                as ledger_currency,
        p.currency                                as payment_currency,
        l.amount                                  as ledger_amount,
        p.amount                                  as payment_amount,
        coalesce(l.occurred_at, p.occurred_at)    as occurred_at
    from ledger l
    full outer join payments p
      on p.contract_id = l.contract_id
     and p.txn_type = l.txn_type
)

select
    cast(j.contract_id as varchar)        as contract_id,
    cast(j.merchant_id as varchar)        as merchant_id,
    cast(j.txn_type as varchar)           as txn_type,
    cast(j.ledger_currency as varchar)    as ledger_currency,
    cast(j.payment_currency as varchar)   as payment_currency,
    cast(j.ledger_amount as decimal(18, 2))  as ledger_amount,
    cast(j.payment_amount as decimal(18, 2)) as payment_amount,
    cast(j.occurred_at as timestamp)      as occurred_at,
    cast(case
        when (j.ledger_amount is null or j.payment_amount is null)
             and j.occurred_at > {{ dbt.dateadd('hour', -var('in_flight_hours'), 'w.loaded_through') }}
            then 'in_flight'
        when j.ledger_amount is null then 'missing_in_ledger'
        when j.payment_amount is null then 'missing_in_payments'
        when j.ledger_currency <> j.payment_currency then 'currency_mismatch'
        when j.ledger_amount <> j.payment_amount then 'amount_mismatch'
        else 'matched'
    end as varchar) as match_status
from joined j
cross join watermark w
