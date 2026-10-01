# Change notes: cost centres with budgets

**Interpretation.** New `cost_centres` collection (readable by everyone, managed by finance) with
derived `committed` (approved + paid claim amounts) and `remaining`, rounded to the cent. Claims
gain a required `cost_centre` reference. When it is omitted on create, it defaults to the cost
centre of the creator's department. If that department has none, the result is 400, so every claim
stays charged to a cost centre. Approving fails with 409 when it would push `committed` above
`budget` (compared to the cent; reaching the budget exactly is allowed). The check runs after the
403 and status-409 checks and before parameter validation. A PATCH with a valid `budget` below
`committed` is 409, which beats other 400s in the body. The `payment` outbox payload carries
`cost_centre`.

**Changes.** Migration `0002_cost_centres.sql` creates the table and the four required cost
centres. It rebuilds `claims` with a NOT NULL `cost_centre_id` FK, charges each existing claim to
the cost centre of its employee's current department (Sales → 2, everything else → 1; a department
with no cost centre also falls back to 1), and keeps the claims AUTOINCREMENT high-water mark.
Updated: `repository.py`, `validation.py`, `permissions.py`, `services.py` (CRUD, default/reference
checks, budget rule, `claim_actions` hides approve when it would fail), `routes_api.py`,
`routes_ui.py`, new `money.py`, templates (cost centre list/detail/new, claim cost centre
field/column/select, nav), `seed.py` and `seed_data.json` (claims carry `cost_centre`), and the
README. The committed `data.db` was migrated in place by starting the app.

**Verification.** I updated the existing tests (claim shape, UI fields and inputs, outbox
payload) and added `tests/test_expenses_cost_centres.py` plus a UI form-post test. All 52 tests
pass, both from the app directory and from `harness/` with `ACCEPT_TARGET`. I also checked:
- the in-place migrated DB is identical to a `seed.py` rebuild (rows, schema, sequences, no FK
  violations);
- an extra employee in an unmapped department migrates to cost centre 1;
- the AUTOINCREMENT sequence is preserved.
