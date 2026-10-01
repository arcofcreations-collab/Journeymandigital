# E06: site-scoped supervisors and the `manager` role

**Interpretation.** `staff.role` gains `manager`. "Supervisor rights" (read every order, assign,
cancel from open/assigned/in_progress, PATCH title/description/priority while unfinished, manage
assets and parts) now belong to managers on every site and to supervisors only on their own site
(an order's site = its asset's site; an asset's/part's = its own `site`). Elsewhere a supervisor has
only the rights of any staff member (requester/assignee), so e.g. priority is 403 and a requested
order is editable/cancellable only while open. Supervisors create work orders only for own-site
assets; only managers manage staff. Asset/part writes by a supervisor: another site in a create body,
a record currently at another site, or a PATCH moving it to another site is 403 (before the retire 409
and any 400); a missing or `null` `site` on create is left to validation (400). Reads of staff,
assets and parts are unchanged.

**Changes.** `permissions.py` (`is_manager`, `supervises_site`, `supervises_work_order`,
`can_create_assets/parts`, `can_manage_assets_at/parts_at`, `can_manage_staff` = managers; work order
rules take the asset), `services.py` (authorizers receive the order's asset; site checks for
asset/part create, PATCH, DELETE via `_ensure_manages_site`), `validation.STAFF_ROLES`, UI (staff/new
managers only, assets/new and parts/new for managers and supervisors with the supervisor's site preset,
"New ..." links from permissions). Migration `0007_manager_role.sql` rebuilds `staff` with the new
CHECK (keeping ids and the id counter) and makes sofia (id 1) `manager` (site North unchanged);
`seed.py` applies the same (`seed_role`). Committed `data.db` upgraded by starting the app once.
README updated.

**Verification.** Full suite (143 tests) passes both from `app/` and as the evaluators run it
(`cd harness && ACCEPT_TARGET=../baseline/app pytest`). Existing tests that relied on cross-site
supervisor rights or supervisor staff management were updated; new `tests/test_maintenance_sites.py`
covers reads, assign/cancel/PATCH scoping, the requester fallback, create rules, asset/part/staff
rights and 403-before-409/400 precedence, the UI pages, and migration 0007 on a pre-0007 database.
The upgraded `data.db` equals a fresh `python seed.py` rebuild, and only sofia's role differs from the
pre-change database.
