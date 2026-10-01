# Change: payment runs

**Interpretation.** New collection `payment_runs` (`claims` in given order, `total` = rounded sum,
`created_by`, `created_at`) and a derived claim field `payment_run`. `POST /api/payment_runs` is
finance-only (403 before any body check); 409 if any listed *existing* claim is not `approved`
(checked before, and winning over, every 400); 400 for a missing/non-list/empty list, non-integer
ids, duplicates, unknown claim ids, unknown or read-only body fields, or a rounded total above
10000.00 (exactly 10000.00 is allowed). Success pays each claim exactly like `pay` (claim event +
`payment` outbox message, list order), then emits one `payment_run` message, all in one
transaction. Runs: finance-only reads; PATCH/DELETE 403 for everyone (404 first for unknown ids).
The single `pay` action is unchanged (its claims keep `payment_run` = null).

**Changes.** Migration `0003_payment_runs.sql` (tables `payment_runs` and
`payment_run_claims(run_id, position, claim_id UNIQUE)`; a claim's `payment_run` is derived from
the link table, so all existing claims read null — no data rewrite needed); repository, validation
(`payment_run` read-only on claims, `clean_payment_run`, `MAX_PAYMENT_RUN_TOTAL`), permissions,
services (`create_payment_run`, shared `_pay` used by `pay_claim`), API routes, UI pages
(`/ui/payment_runs`, detail, `new` form) plus `payment_run` on the claim detail page; employees who
created a run cannot be deleted (409). Filters on a list field match by membership. The committed
`data.db` was upgraded by starting the app (schema_version 3; existing claims/events untouched).

**Verification.** Updated three existing tests for the new claim field and added
`tests/test_expenses_payment_runs.py` (ordering, outbox/events, rounding and the 10000 limit,
403/409/400 precedence, all-or-nothing snapshots, visibility, read-only runs, filters, UI, migration).
Full suite: 60 passed, run against the app loaded through `app_entry.py`.
