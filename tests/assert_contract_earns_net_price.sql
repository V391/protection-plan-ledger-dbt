-- A contract never earns more than its net price, and one whose earning window closed inside
-- the horizon has earned exactly its net price.
with earned as (
    select contract_id, sum(earned_usd) as earned_usd
    from {{ ref('fct_contract_earnings_monthly') }}
    group by 1
)

select c.contract_id, c.net_usd, e.earned_usd
from {{ ref('fct_contracts') }} c
join earned e on e.contract_id = c.contract_id
where e.earned_usd > c.net_usd + 0.000001
   or (c.earn_end_date <= cast('{{ var("horizon_end") }}' as date)
       and c.earn_days > 0
       and abs(e.earned_usd - c.net_usd) > 0.000001)
