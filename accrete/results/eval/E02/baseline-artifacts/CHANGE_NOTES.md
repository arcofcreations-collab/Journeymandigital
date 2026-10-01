# E02: technician self-dispatch and workload cap

**Interpretation.**
- `claim` is for active technicians at the site of the order's asset (403 otherwise). It only works on `open` orders (409 otherwise). It also gives 409 when the caller already has 3 or more `assigned`/`in_progress` orders. Unknown body keys are a 400, checked after those 403/409 checks. A claim emits the same `assignment` message as `assign`.
- `assign` checks in this order: 403, then 409 (state), then 400 (technician), then 409 (cap).
- One edge case needed a decision. The rule says to count the technician's orders "not counting the order being assigned", and the request also says re-assigning to the current assignee is "always allowed". For the technician who is already above the cap (ravi, 4 orders), those two disagree. I followed the stated intent and the overload policy ("cannot receive *further* orders"): re-assigning to the current assignee never checks the cap. For everyone else this gives the same result as the counting rule.
- `dispatch` is a stored, read-only field. `assign` sets it to `"supervisor"` and `claim` sets it to `"self"`. It can be filtered like other fields.

**Changes.**
- New migration `0003_work_order_dispatch.sql` adds the `dispatch` column and fills it in for existing orders of every status. No other rows change, and the existing overload is kept as it is.
- `repository`: reads and writes `dispatch`, and counts each technician's workload.
- `permissions.can_claim_work_order`.
- `services`: `claim_work_order` / `_authorize_claim`, the cap (`WORKLOAD_CAP`), and a shared `_assign` that `assign` and `claim` both use.
- `validation`: `dispatch` added to the read-only fields.
- New API route and UI route for `claim`.
- Templates: a `claim` form, and `dispatch` shown on the detail page and in the list. The `assign` form now lists only technicians below the cap, plus the current assignee.
- `seed.py` fills in `dispatch` with the same rule as the migration.
- README updated.
- I applied the migration to the committed `data.db` in place, through `app_entry.create_app()`.

**Verification.**
- Added `tests/test_maintenance_dispatch.py` (18 tests). Updated existing tests for the new field, the new `claim` form, and nils now being at the cap. All 97 tests pass, both with plain `pytest` and with `ACCEPT_TARGET`.
- Compared the migrated `data.db` with a fresh `seed.py` rebuild: all tables are identical. Compared it with the pre-change database: staff, assets, parts and every old work order column are unchanged.
- Backfill result: 20 orders `null`, 16 `self`, 46 `supervisor`. The integrity check passes.
