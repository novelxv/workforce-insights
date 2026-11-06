# Arunika Life workforce extract for Power BI

Synthetic data for a fictional insurer, exported from the workforce insights app.

The extract is pseudonymous:

- Employees appear by employee number only. Names and dates of birth stay in the app.
- Pay appears only as `pay_ratio` (salary relative to the grade-band midpoint).
- Individual attrition scores are not exported.

## Files

| File | Grain |
|---|---|
| `fact_headcount_monthly.csv` | One employee in one month they were employed, with that month's attributes and 0/1 flags (`active_eom`, `hired`, `exited`, `promoted`, `transferred`) |
| `fact_movement.csv` | One hire, exit, promotion or transfer |
| `dim_employee.csv` | Type-2 history: one row per spell in a department, office and grade |
| `dim_department.csv`, `dim_location.csv`, `dim_grade.csv`, `dim_month.csv` | Lookups |
| `measures.dax` | The app's metric definitions as DAX measures |

## Model setup (about ten minutes)

1. **Get data > Text/CSV**, load all seven CSVs. In Power Query, check these types:
   - `month`, `date`, `hire_date`, `exit_date`, `valid_from`, `valid_to`: **Date**.
   - `pay_ratio`, `overtime_hours`: **Decimal number**.
   - The 0/1 flags: **Whole number**.
2. **Relationships** (Model view). All are many-to-one and single direction, from the fact to the dimension:
   - `fact_headcount_monthly[month]` → `dim_month[month]`
   - `fact_headcount_monthly[department_code]` → `dim_department[code]`
   - `fact_headcount_monthly[location_code]` → `dim_location[code]`
   - `fact_headcount_monthly[grade]` → `dim_grade[code]`
   - `fact_headcount_monthly[employee_key]` → `dim_employee[employee_key]`
   - `fact_movement[month]` → `dim_month[month]`
3. Sort `dim_month[label]` by `dim_month[month]` so months appear in calendar order. `dim_month` has one row per month. That is enough for these measures, which filter months explicitly, but it cannot be marked as a date table (Power BI wants one row per day).
4. Add the measures from `measures.dax`. Format the rates and shares as percentages, and Compa-ratio with two decimals.

## Checking against the app

With no filters and `dim_month[month]` limited to the last 12 months, `Voluntary Turnover Rate` should equal the dashboard's figure for the same months. The app computes each metric in `api/app/metrics.py`, and the DAX follows the same formulas:

- Annualised rates are `12 × events / sum of month-end headcounts`.
- Point-in-time metrics use the last month in context.

## Before sharing a report

The app withholds any figure that rests on fewer than five people, so that a small team's resignations or pay cannot be read off a chart. Power BI does not do this by itself. Use the `(published)` measures on any page that slices by department, gender, age band or grade. Also keep row-level security in mind if HRBPs should see only their departments.
