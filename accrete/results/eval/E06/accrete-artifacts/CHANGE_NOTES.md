# E06: site-scoped supervisors and the `manager` role

**Interpretation.** `manager` keeps every right supervisors had before, on all sites. A supervisor
is now limited to their own site. For a work order that is the site of its asset; for an asset or
part it is the record's own `site`. On other sites a supervisor only has the rights any
`requested_by` has (title/description while open, cancel while open), otherwise 403. Work-order
create: managers can use any site. Everyone else, supervisors included, needs an asset at their
own site; this 403 wins over 400, and a missing or unknown asset is still a 400. Assets and parts:
a supervisor creates only with `site` = own site. A missing or null `site` is left to the
required-field 400. They can PATCH/DELETE only records whose stored site is their own, and a
PATCH sending any other non-null `site` is a 403. Only managers can create, PATCH or DELETE
staff. Reads of staff, assets and parts are unchanged.

**Changes** (`changes/0007-site-scoped-supervisors.yaml`, ledger #7, applied with `accrete apply`):
- Added `manager` to the `staff.role` enum.
- Data migration: sofia (id 1) is now `manager`. Her site stays North, and no other record changed.
- Rewrote the staff, asset and part create/update/delete rules.
- Rewrote the work_orders read/create/update/update_guard rules and the `assign` allow rule. Also
  rewrote `cancel` (allow + guard).
- Rewrote the part_usages and time_entries read rules to match the new work-order read rule.
- The UI comes from these rules, so `/ui/staff/new` is for managers only and `/ui/assets/new` and
  `/ui/parts/new` are for managers and supervisors. Lists and action forms follow the new rights.

**Verification.** The change has about 70 expectations (data, staff, work-order read, assign,
cancel and PATCH for own and other sites, a supervisor moved to another site, create, assets and
parts). Replay of 775 requests found 0 unexplained differences and 0 unacknowledged
consequences. I also ran a script against `app_entry.py` with `accept_client.py`. It checked UI
create forms per role, list rows in the UI vs the API, action forms on detail pages, a new
manager acting immediately, and that E01 (`use_parts`) and E04 (`log_time`) still work, along with
the assignment outbox and the workload cap.
