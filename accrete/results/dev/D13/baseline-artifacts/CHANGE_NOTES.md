# Change notes: approval delegation

**Interpretation.** New `delegations` collection (`delegator` = creator, `delegate`, `starts_on`,
`ends_on`). Only managers create; the delegate must be another existing manager; `ends_on` >=
`starts_on`. Readable by delegator, delegate and finance; only the delegator deletes; PATCH is
always 403 (after the 404 check). Active on `starts_on`..`ends_on` inclusive, using the `X-Now`
date. While active the delegate reads, approves and rejects claims of the delegator's *direct
reports* (`decided_by` = delegate); the delegator keeps all rights. Nobody decides their own claim
(also via delegation). Rights come only from the delegator's direct reports, so they never chain.
An employee referenced by a delegation cannot be deleted (409, as for claims/reports).

**Changes.** Migration `0002_add_delegations.sql` (new empty table; existing data untouched;
committed `data.db` migrated). `repository.py` (delegation CRUD, `active_delegator_ids`,
reference check), `permissions.py` (`acts_as_manager_of`, delegation rights, self-decision ban in
`can_decide_claim`), `validation.py` (`clean_delegation`, date checks), `services.py` (delegation
operations; claim read/approve/reject/actions honour active delegations), `routes_api.py`,
`routes_ui.py` + `templates/delegations/*` (list, detail, new, delete) and a nav link; README.

**Verification.** New `tests/test_expenses_delegations.py` (15 tests: validation and 403/400
precedence, visibility, PATCH/DELETE rules, date boundaries, deletion, self-approval, no chaining,
UI actions and pages); the full suite (50 tests) passes, run through `app_entry.create_app()`
on fresh copies of the instance.
