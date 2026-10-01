# Change notes: spare parts inventory and atomic part consumption

**Interpretation.**
- `use_parts` checks run in the contract's order: 404, then 403 (only the assignee), then 409 (only `in_progress`), then the stock check (409), then 400.
- A stock 409 applies to any item whose `part` is an existing part at the site of the order's asset and whose `quantity` is a JSON integer >= 1 that exceeds the stock. It wins over every 400 in the request, extra keys included. A part at another site is not a valid part, so asking too much of it is a 400.
- PATCHing a part's stock never emits `low_stock`, because only `use_parts` emits.
- `POST /api/part_usages` returns 403. `PATCH` and `DELETE` on a usage return 404 for an unknown id and 403 otherwise.

**Changes.**
- New migration `0002_spare_parts.sql` adds the `parts` and `part_usages` tables and the 8 starting parts with fixed ids. It has been applied to the committed `data.db`; existing records are byte-for-byte unchanged.
- Validation: `clean_part` and `clean_use_parts_params`; `parts_cost` is read-only.
- Permissions: added parts and part-usage rules.
- Repository: parts and usages; `parts_cost` is a SQL sub-select rounded to 2 decimals; `low_stock` is derived.
- Services: parts CRUD (supervisors only; deleting a part that has usages is 409), read-only usages that follow work order read rules, and the `use_parts` action, which runs in one transaction. `work_completed` now carries `parts_cost`.
- API and UI routes: `/ui/parts`, `/ui/parts/new`, `/ui/part_usages`, and the `use_parts` form on the work order page.
- Updated the README and the `seed.py` docstring.

**Verification.**
- Updated 5 existing tests for the intended changes: `parts_cost` field, `use_parts` action, `work_completed` payload.
- Added `tests/test_maintenance_parts.py` (21 tests): CRUD and validation, permissions and precedence, stock 409 over 400, atomicity, `low_stock` messages, cost snapshot and rounding, cancel and complete, usage read rules, UI pages and forms, migration data.
- Full suite: 79 passed, run through `app_entry.create_app` via the harness `fresh_app`.
- Checked that rebuilding with `seed.py` produces the same data.
