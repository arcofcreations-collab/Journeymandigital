# Change: atomic employee offboarding

Interpretation: `employees.active` is a system (read-only, 400 if sent) bool defaulting to true; all 15
existing employees backfilled to true, nothing else touched. Every write rule (create/update/delete on
employees and claims) and every action allow (submit/approve/reject/pay/offboard) now also requires
`user.active`, so inactive callers keep read access but get 403 on writes and create forms. A constraint
`manager_active` makes an inactive manager a 400 on employee create/patch.

`POST /api/employees/{id}/offboard {successor}`: allow = active finance caller (403); guard = employee
active and no submitted/approved claims (409); `successor` param is a required ref (missing/unknown
-> 400), then a 400 `fail` effect checks active / role manager / not self / not managed by the employee
before anything changes. Effects: emit `employee_offboarded` {employee, successor, reassigned (asc),
deleted_claims (asc)}, re-manage direct reports to the successor, delete the employee's drafts, set
active = false — all in one atomic action.

Changed via `accrete apply` of changes/0002-offboarding.yaml (ledger #2; replay: 0 unexplained / 0
unacknowledged consequences; 15 expectations pass). Verified additionally through app_entry.py with the
harness client (verify_e12.py next to the app directory): UI offboard form visibility, draft deletion + payload ids, re-managing,
all-or-nothing on 400, 404/403/409/400 order, inactive finance read-all but 403 on pay/patch/offboard/
create forms, payment payload unchanged.
