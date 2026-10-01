# E07: preventive maintenance schedules

**Interpretation.** New `schedules` collection. Everyone can read it. Managers can create, PATCH, DELETE and `generate` on any schedule; supervisors only on schedules whose asset is at their site. Error precedence is 404, 403, 409, 400. On create, a supervisor naming an existing asset at another site gets 403, even if the asset is retired. `generate` copies the schedule's priority as it is. If the asset has since become high-criticality and the schedule still has p4, the order keeps p4, the same way the p4 rule only refuses *setting* p4. A schedule of a retired asset can be reactivated by PATCH, but `generate` then returns 409. The body for `generate` must be `{}`.

**Changes.**
- Added migration `0008_maintenance_schedules.sql`. It creates the `schedules` table and the 5 required schedules (ids 1-5, so new ids continue from 6), and adds a nullable `work_orders.schedule_id` (null for all existing orders) plus indexes.
- `db.migrate` takes a new `up_to` argument. `seed.py` uses it to load the seed at schema 7 and then apply 0008, because the schedules reference seed assets. I checked that the rebuilt database matches the migrated `data.db`.
- Added schedule logic in validation, permissions, repository, services and the API and UI routes. That includes the `generate` action and its `preventive_generated` outbox message.
- Work orders have a new read-only `schedule` field. Sending it in a create or PATCH body is a 400.
- Deleting an asset that has schedules is a 409. Retiring an asset deactivates its schedules in the same transaction.
- New UI templates under `templates/schedules/`, a Schedules link in the nav, and the `schedule` field on the work order detail page.
- Updated the README.

**Verification.** Added `tests/test_maintenance_schedules.py` with 22 tests. They cover the data, the migration on a pre-0008 database, create/PATCH/DELETE rules and precedence, asset delete and retire, `generate` (success, conflicts, lateness, atomicity, outbox) and the generated-order workflow including the workload cap. They also cover the UI list, detail, generate form and create form. I updated 5 existing tests for the new `schedule` field, the new index and the migration list. All 165 tests pass when run through `app_entry.py` with the harness.
