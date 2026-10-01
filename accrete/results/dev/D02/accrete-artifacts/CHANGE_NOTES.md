# Change notes: holds (reservations)

Interpretation: new `holds` entity (book, member, placed_at, status waiting|ready|fulfilled|cancelled, ready_at),
readable by librarians or the hold's member; direct create/PATCH/DELETE forbidden (403). `books.status` is
`on_loan` (open loan) > `reserved` (a `ready` hold) > `available`. Queue head = waiting hold with smallest
(placed_at, id).

Changes (all via `accrete apply changes/0002-holds.yaml`, ledger #2):
- `books.hold` action: allow like borrow (member may only hold for self, 403); guard 409 unless book is
  on_loan/reserved, target member active, no waiting/ready hold on the book and no open loan of it. Creates a
  waiting hold, no outbox message.
- `loans.return`: promotes the queue head to `ready` (ready_at = now) and emits `hold_ready {hold, book, member}`.
- `books.borrow`: guard admits a reserved book for librarians or the ready-hold member (so the UI borrow form
  shows to exactly those); a prepended fail effect returns 409 unless the effective borrower is the ready-hold
  member; existing active / 3-loan checks unchanged; success marks the hold `fulfilled` (atomic, so a failed
  borrow leaves it `ready`).
- `holds.cancel` action: hold member or librarian (else 403), only from waiting/ready (else 409); cancelling a
  ready hold promotes the next waiting hold (with hold_ready) or leaves the book available.
- No data migration needed (no holds initially; existing statuses unchanged).

Verification: dry-run replay of 253 recorded requests all identical; 8 expectations in the change file
(permissions, 409 cases, queue order incl. placed_at ordering and id tie-break, reserved borrowing, failed
borrow keeps hold ready, cancel promotion / availability) pass; `accrete check` ok; manual WSGI run through
app_entry.py confirmed outbox payloads and UI forms (hold, borrow on reserved book, cancel).
