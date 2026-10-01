# Second approval for large claims

Interpretation: the "second approver" is the claim employee's manager's manager (resolved via the current
manager chain, like the existing manager rules). A claim needs two approvals when amount > 1000 and that
second approver exists.

Changed (via `accrete apply`, changes/0002-second-approval.yaml, ledger #2):
- `claims.status` gains `awaiting_second_approval`; new system fields `first_approved_by` (ref employees),
  `first_approved_at` (datetime) - clients setting them get 400.
- `approve`: manager on a submitted two-approval claim -> awaiting_second_approval + first_approved_by/at;
  otherwise (single-approval claim, or second approver on awaiting) -> approved + decided_by/at.
- `approve`/`reject` allow = employee's manager, or the second approver while awaiting (else 403);
  guard = manager only on `submitted`, second approver only on `awaiting_second_approval` (else 409);
  reject reason still 400 after 403/409. `pay` unchanged (requires approved).
- read rule: also the second approver when `first_approved_by` is set (also after decision).
- Data: approved claims 21, 22, 44 (amount > 1000, manager has a manager) migrated to
  awaiting_second_approval with first_approved_* = former decided_*, decided_* = null; all others untouched.

Verification: dry-run + commit passed replay (0 unexplained / unacknowledged) and 33 expectations
(migration values, 403/409/400 matrix, two-step flow, single-approval paths, pay 409, read access,
system-field 400s). UI checked through app_entry.py on a copy: on an awaiting claim only the second approver
gets approve/reject forms, first approver and finance get none; pay appears only once approved.
