# E14 Lost copies

Interpretation: a loan is open when `returned_at` and `lost_at` are both null. `loans.lost_at` is a system
(read-only) datetime, `copies.lost` a system bool defaulting to false, so sending it on create/PATCH gives 400
(non-librarians still get 403 first). Copy status is `lost` / `on_loan` (has an open loan) / `available`;
book status is `unavailable` when no non-lost copy exists. A loan with `lost_at` set is never overdue,
doesn't count towards the 3-loan limit, and can't be returned (409).

Changes (one accrete change, `changes/0003-lost-copies.yaml`, ledger #3): added the fields with backfill (loans 46/50
lost_at = 2026-02-28T10:00:00, copies 4/16 lost = true, nothing emitted); updated the computed copy/book status and
loan overdue fields; changed the borrow guard (open-loan count also requires lost_at=None) and the return guard; added
`loans.declare_lost` (librarian; open loan; sets lost_at=now, marks the copy lost, emits `copy_lost`
{loan, copy, book, member}) and `copies.found` (librarian; lost copies only; lost=false). Copy delete_guard is unchanged
(any loan blocks delete).

Verification: the dry run and apply passed: 973 replayed requests, 0 unexplained differences, 28 expectations
covering the migration, 400/403/409 cases, declare_lost/found flows, outbox payload, the open-loan limit for jo, lost
copies skipped by borrow, and delete blocked. I also checked the UI through app_entry.py with the harness client:
the declare_lost/return/found forms appear only when they should, and the new fields are shown.
