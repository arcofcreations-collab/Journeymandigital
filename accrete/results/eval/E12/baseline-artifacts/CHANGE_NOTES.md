# Change notes: atomic employee offboarding

**Interpretation.** Implemented as specified. Every write permission (create/patch/delete of any
record, every claim action and offboard) now also requires an active caller, so inactive users get
403 in the usual 404 → 403 → 409 → 400 order while their read rights are unchanged. One extension:
the spec rejects a successor whose *direct* manager is the offboarded employee because re-managing
the reports under them would form a loop; an *indirect* report causes the same loop (and the app
already forbids reporting loops), so it is rejected with 400 too.

**Changes.** Migration `0002_add_employee_active.sql` adds `employees.active` (NOT NULL DEFAULT 1, so
every existing employee is active; nothing else changes) and was applied to `data.db`.
`repository` exposes `active` and the offboarding queries; `validation` makes `active` read-only and
parses `{"successor"}`; `permissions` requires an active caller for writes; `services.offboard_employee`
does checks + reassign reports + delete drafts + deactivate + outbox in one transaction; employee
`manager` must be active; `active` is filterable. API/UI route `/employees/{id}/offboard`; the employee
detail page shows `active` and an `offboard` form (with successor select) when allowed. Seed
data/`seed.py` carry `active`; README updated.

**Verification.** Updated two existing tests for the new field and added `tests/test_expenses_offboarding.py`
plus a UI form test (effects, outbox payload, approval hand-over, precedence, every successor rule,
no-trace failures, inactive read/write rules, UI form visibility). `pytest` via the harness: 46 passed.
