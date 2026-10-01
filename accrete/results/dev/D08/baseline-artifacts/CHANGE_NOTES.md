# Second approval for large claims

**Interpretation.** A claim needs two approvals when `amount > 1000` and the employee's manager has a manager. The "second approver" is that manager's own manager, looked up from the current org chart at request time. The employee's manager's `approve` on such a `submitted` claim records `first_approved_by`/`first_approved_at` and moves the claim to `awaiting_second_approval`. From there the second approver approves (-> `approved`) or rejects with a reason (-> `rejected`). Either way the first-approval fields are kept.

Errors on approve/reject:
- 403 for anyone who is neither the employee's manager nor, while the claim awaits the second approval, its second approver.
- 409 for the employee's manager on any claim that is not `submitted`.
- 400 for a missing reason, checked last.

`pay` still requires `approved`. The second approver can read every claim with a non-null `first_approved_by`.

**Changes.**
- Migration `0002_second_approval.sql`:
  - Rebuilds `claims` with the new status in the CHECK constraint, plus `first_approved_by_id` and `first_approved_at` and an index.
  - Moves approved, unpaid claims over 1000 whose employee's manager has a manager to `awaiting_second_approval`. The old decision becomes the first approval and `decided_*` is set to null. In the seed data these are claims 21, 22 and 44.
- `permissions.py`: adds `is_second_approver`. `can_read_claim` and `can_decide_claim` now also take the claim's manager into account.
- `services.py`: adds the threshold, `_needs_second_approval`, the shared 403/409 check `_check_can_decide` (also used for the UI actions) and the new fields in filtering.
- `repository.py`: new columns and `mark_claim_first_approved`. Employee deletion also checks `first_approved_by`.
- Other code: `validation.py` makes the new fields read-only (400 if a client sends them). The detail template shows the new fields, and `seed.py` inserts them.
- Data and docs: `seed_data.json` now matches the migrated state. The committed `data.db` was migrated in place by starting the app; it is identical to a `seed.py` rebuild. The README is updated.

**Verification.**
- Updated the existing tests for the new fields and readers. Added `tests/test_expenses_second_approval.py`, which covers both approval paths, the 403/409/400 rules, the single-approval cases (including exactly 1000), reading, UI forms, the migrated seed claims, and a migration run on a version-1 database with old-style claims.
- All 43 tests pass when the app is loaded through `app_entry.py`. The tests ran with a minimal local stand-in for `harness/accept_client.py`, because the real harness is outside the work area.

**Note.** If the org chart changes while a claim is awaiting the second approval, the current manager's manager becomes the second approver. If that manager no longer has a manager, nobody can complete the claim.
