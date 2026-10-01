# Change notes: loan renewals

**Interpretation.** `POST /api/loans/{id}/renew` (body `{}`) can be called by the borrower or any librarian; any other member gets 403. It moves `due_at` forward 14 days from the current `due_at` and increments `renewals`. It returns 409 when the loan is returned, overdue (today > `due_at`; renewing on the due date itself is allowed), already renewed twice, or when the book has a `waiting` hold. The checks run in contract order 404 → 403 → 409 → 400, so a non-empty body is a 400 only on a loan that could otherwise be renewed. A successful renewal emits one `loan_renewed` message `{"loan", "due_at"}`. Holds are never touched. `ready` holds don't block a renewal, because a book with an open loan can't have one. `renewals` is read-only like every other loan field, and PATCH on loans is still 403.

**Changes.**
- Migration `0003_loan_renewals.sql`: `loans.renewals INTEGER NOT NULL DEFAULT 0`. Existing loans get 0. It is applied to the committed `data.db`.
- `repository`: `renewals` is added to the loan record, plus `renew_loan` and `book_has_waiting_hold`.
- `permissions.can_renew_loan`.
- `services`: `renew_loan`, `_renewal_refusal`, `RENEWAL_PERIOD` and `MAX_RENEWALS`. `renewals` is added to `LOAN_FIELDS` so it can be filtered on. `loan_actions` offers `renew` exactly when the renewal would succeed.
- API and UI routes `.../loans/{id}/renew`. The loan detail page gets a `renewals` field and a `renew` form, and the loan list gets a Renewals column. README updated.

**Verification.**
- New `tests/test_library_renewals.py` covers success, the payload, the extension from `due_at`, the limit of two, renewing on the due date vs. the day after, the overdue flag using the new date, returned loans, waiting holds, holds left unchanged, permissions and precedence, PATCH, and the UI form.
- Two existing tests were updated for the new field and the newly offered `renew` form.
- The full suite passes: 82 tests. They ran against a local stand-in for `harness/accept_client.py`, because the real harness is outside the allowed workspace.
- I also checked that a version-2 database with existing loans, holds and outbox rows upgrades on startup through `app_entry.py` with all its data preserved.
