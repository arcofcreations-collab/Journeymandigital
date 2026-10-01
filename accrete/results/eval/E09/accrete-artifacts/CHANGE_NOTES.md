# Household guardians: change notes

- **Interpretation:** `members.guardian` is an optional self-reference that only librarians may set. Write access to members stays as it was: librarians, or the member themselves for `name` only. A guardian gets four extra rights over each current dependant: read the member record, read their loans, borrow for them, and return their loans. These rights ignore the `active` flags. The borrow guard still checks the borrower's `active` flag and the 3-open-loan limit. Deleting a member who is still someone's guardian gives 409, because the runtime blocks deleting any member that another record references.
- **Changed:** Applied through `accrete apply` as ledger change #2 (`changes/0002-guardians.yaml`).
  - Added the field `guardian` (ref members, write_if librarian).
  - Added three constraints that return 400: a member cannot be their own guardian; the guardian must not have a guardian; a member who is already a guardian cannot be given one.
  - Extended `members.read`, `loans.read`, the `borrow` allow rule and the `return` allow rule with `... .guardian == user`.
  - Set guardian 5->4, 10->4, 7->6 and 12->11. Every other member is null.
- **Verified:**
  - The dry-run replay showed 41 changes, all intended, and no consequences or unexplained differences. The 32 expectations in the change file pass.
  - `accrete check` passes.
  - A contract-level script (`../verify/check.py`) loads the app through `app_entry.py` using `accept_client`. It covers the data, the `?guardian=` and `?guardian=null` filters, lists and details for guardians and dependants, borrowing for a dependant (including the outbox message, the 409 for a dependant with 3 open loans or who is inactive, and 403 before 409), returns, the 403s for PATCH and DELETE, every validation case, 409 when deleting a guardian, removing access when the guardian is cleared, the UI rows, fields, inputs and return forms, and the existing behaviour. All 58 checks pass.
