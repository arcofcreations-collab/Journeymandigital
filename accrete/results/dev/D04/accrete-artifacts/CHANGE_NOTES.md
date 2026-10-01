# D04 Late-return fines

Interpretation: `loans.fine` is computed as min(5.00, 0.50 * max(0, days late)), with days late = (date of `returned_at`, or today if the loan is still out) - current `due_at`. `loans.fine_paid` is a stored system bool (default false). `members.fines_due` is computed as the sum of `fine` over the member's returned loans that have `fine_paid` false. Guards: borrow and hold require `(params.member or user).fines_due <= 0`, and renew requires `record.member.fines_due <= 0`. All three return 409 before any effect runs, so a ready hold stays ready.

Changes (changes/0004-fines.yaml, ledger #4, applied with `accrete apply`):
- Added the fields `loans.fine`, `loans.fine_paid` and `members.fines_due`.
- Added the fines condition to the borrow, hold and renew guards.
- `return` now emits `fine_charged {loan, member, amount}` when the loan's fine is greater than 0.
- New action `loans.pay_fine`. Only librarians may run it. Its guard requires the loan to be returned, with fine > 0 and not yet paid. It sets `fine_paid` and emits `fine_paid {loan, member, amount}`.
- Migration: existing loans returned with fine > 0 are backfilled with `fine_paid` = true (12 loans). Every other loan gets false, so no member has `fines_due` > 0 after the change.

Verification:
- The accrete pipeline passed: 997 replayed requests, 125 changed as intended, 0 unexplained, 0 consequences.
- The 18 expectations in the change file passed. They cover fine values and the cap, the backfill, blocks on borrow, librarian-lend, renew and hold, the ready hold surviving a failed borrow, pay_fine returning 403, 409 and 200, outbox payloads, the calendar-date rule and a fine after a renewal.
- Manual checks through `app_entry.create_app()` on a copy of the app: the UI shows the `pay_fine` form only to librarians, and only for a returned loan with an unpaid fine. The borrow, hold and renew forms are hidden while the member owes and come back after payment.
