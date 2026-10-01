# Cost centres with budgets

Interpretation: new `cost_centres` collection (code unique, name, department unique among non-null,
budget >= 0, computed `committed` = approved+paid claim amounts rounded to cents, `remaining` =
budget - committed). Read by everyone; create/PATCH/DELETE finance only (403 first). PATCHing a valid
budget below `committed` -> 409 (a negative budget is an invalid value -> 400). Deleting a cost centre
with any claim -> 409. Claims get a required `cost_centre` ref defaulting to the cost centre of the
creator's department (null / unknown id -> 400), editable by the employee while draft. `approve`
additionally requires committed + amount <= budget (to the cent), else 409 with no change. The
`payment` payload now includes `cost_centre`.

Changes (via `accrete apply`): changes/0002-cost-centres.yaml (entity, 4 seed cost centres with ids
1-4, claims.cost_centre backfilled from the employee's department: Sales -> 2, others -> 1, approve
guard, pay payload); changes/0003-cost-centre-ids-in-ui.yaml (UI shows cost centre refs as ids, like
other references).

Verification: 60+ expectations in 0002 (permissions, validation, duplicates, 409 budget patch with no
side effects, delete conflicts, defaults, draft-only edits, budget-limited approvals, outbox payload)
passed; replay showed 0 unexplained differences. UI checked with the harness client: /ui/cost_centres
list/detail, /new 403 for non-finance and inputs code/name/department/budget for finance, claim form
has cost_centre input, approve form hidden when the budget would be exceeded.
