# E03: priority scale p1-p4

**Interpretation.** `priority` is exactly `p1`..`p4` (anything else, including the old values and
`P1`, is a 400 on create/PATCH; old values as list filters just match nothing). `due_date` =
`created_at` date + 1/3/7/30 days. Setting `p4` on an order whose asset currently has criticality
`high` is a 400 on create and PATCH (also when the order already is `p4`), checked after the
existing 403/409 rules. `claim` is allowed only for orders whose current priority is `p3`/`p4`; this
is part of the claim permission, so it is a 403 that beats the open-state and workload 409s (and any
400). `assign` is unchanged.

**Changes.**
- `migrations/0004_work_order_priority_scale.sql`: rebuilds `work_orders` with the new CHECK
  constraint (create-copy-drop-rename, indexes and id counter kept) and maps every order:
  urgent->p1, normal->p2 (high-criticality asset) / p3, low->p4 (also on high assets; kept).
  No other column changes. `data.db` is migrated (schema version 4).
- `db.migrate`: runs migrations with foreign keys off (needed to rebuild a referenced table) and
  refuses to commit a migration that leaves `PRAGMA foreign_key_check` violations.
- `validation.WORK_ORDER_PRIORITIES`, `services.DUE_DAYS`, `services._ensure_priority_allowed`
  (create + PATCH), `permissions.SELF_DISPATCH_PRIORITIES` in `can_claim_work_order` (so the UI claim
  form follows automatically), `new.html` default `p3`, `seed.py` maps the seed's old priorities
  like the migration (`seed_priority`); README updated.

**Verification.** Updated the existing tests to the new scale (claim tests now use p3/p4 orders) and
added `tests/test_maintenance_priority.py` (values, due dates, p4 rule and its precedence, claim
restriction and its precedence, UI forms, migration). 114 tests pass (also run the evaluators' way
from `harness/`). Checked the migrated `data.db` row by row against the pre-migration copy (only
`priority` differs, exactly per the mapping; other tables identical), that `python seed.py` produces
the same data, and that the migration also works when part usages reference work orders.
