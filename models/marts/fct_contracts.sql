with contracts as (
    select * from {{ ref('int_contracts') }}
),

classified as (
    select
        *,
        case
            when cancelled_at is null then 'active'
            when refund_amount >= plan_price then 'cancelled_full_refund'
            else 'cancelled_prorated'
        end as contract_status,
        -- Revenue is earned over the days actually covered: to coverage end, to the cancel date
        -- on a prorated cancel, and not at all on a full refund.
        case
            when cancelled_at is null then coverage_end_date
            when refund_amount >= plan_price then coverage_start_date
            else cancel_date
        end as earn_end_date
    from contracts
)

select
    cast(contract_id as varchar)                                         as contract_id,
    cast(merchant_id as varchar)                                         as merchant_id,
    cast(order_line_id as varchar)                                       as order_line_id,
    cast(product_category as varchar)                                    as product_category,
    cast(plan_term_months as integer)                                    as plan_term_months,
    cast(currency as varchar)                                            as currency,
    cast(plan_price as decimal(18, 2))                                   as plan_price,
    cast(refund_amount as decimal(18, 2))                                as refund_amount,
    cast(fx_rate_at_purchase as double)                                  as fx_rate_at_purchase,
    cast(plan_price * fx_rate_at_purchase as double)                     as price_usd,
    cast(refund_amount * fx_rate_at_purchase as double)                  as refund_usd,
    cast((plan_price - refund_amount) * fx_rate_at_purchase as double)   as net_usd,
    cast(revenue_share_rate_at_sale as double)                           as revenue_share_rate_at_sale,
    cast(purchased_at as timestamp)                                      as purchased_at,
    cast(purchase_date as date)                                          as purchase_date,
    cast(coverage_start_date as date)                                    as coverage_start_date,
    cast(coverage_end_date as date)                                      as coverage_end_date,
    cast(cancelled_at as timestamp)                                      as cancelled_at,
    cast(cancel_date as date)                                            as cancel_date,
    cast(contract_status as varchar)                                     as contract_status,
    cast(earn_end_date as date)                                          as earn_end_date,
    cast({{ dbt.datediff('coverage_start_date', 'earn_end_date', 'day') }} as integer) as earn_days,
    cast(is_test_merchant as boolean)                                    as is_test_merchant,
    cast(source_loaded_at as timestamp)                                  as source_loaded_at
from classified
