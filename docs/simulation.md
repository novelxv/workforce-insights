# Simulation

`pipeline/simulate.py` steps a fictional insurer's workforce forward one month at a time for
36 months ending October 2026. Each month: ratings (February), pay review and promotions (April),
transfers, manager changes, overtime, exits, then hiring to backfill most leavers and grow the
bancassurance and agency channels.

Each active employee's monthly chance of resigning is a department base rate multiplied by:

| Factor | Multiplier |
|---|---|
| pay below 90pct of midpoint | 1.8 |
| pay 90 to 100pct of midpoint | 1.25 |
| pay above 110pct of midpoint | 0.8 |
| no promotion 36 months | 1.5 |
| manager changed last 6 months | 1.4 |
| overtime over 30h 3m avg | 1.6 |
| high performer paid below midpoint | 1.5 |
| low performer | 1.3 |
| tenure under 12 months | 1.6 |
| tenure 3 to 10 years | 0.7 |
| tenure over 10 years | 0.5 |
| april may after bonus | 1.3 |
| personal factor lognormal sigma | 0.45 |

Retirement happens at 58.5 years; involuntary exits depend on a rating of 1; PKWT staff can leave
when a contract anniversary passes unrenewed.

## Rows loaded

| Table | Rows |
|---|---|
| `dim_department` | 17 |
| `dim_location` | 5 |
| `dim_grade` | 7 |
| `dim_month` | 36 |
| `dim_employee` | 1,567 |
| `fact_headcount_monthly` | 26,628 |
| `fact_movement` | 1,298 |
| `fact_attrition_score` | 743 |
