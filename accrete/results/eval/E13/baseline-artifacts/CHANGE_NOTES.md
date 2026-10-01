# Change notes: withdraw submitted claims, revise rejected ones

**Interpretation.** `withdraw` (owner only, else 403) takes a `submitted` claim back to `draft` and
clears `submitted_at`. It is allowed while `X-Now <= submitted_at + 7 days`, so exactly 7 days still
works and one second later is a 409. `revise` (owner only) takes a `rejected` claim with
`revision < 2` back to `draft`. It copies `rejection_reason` to `previous_rejection_reason`, clears
`rejection_reason`/`decided_at`/`decided_by`/`submitted_at` and adds 1 to `revision`. Neither action
writes to the outbox, read permissions stay the same, and the bodies accept no parameters (unknown
keys → 400, checked after 404/403/409). `revision` and `previous_rejection_reason` are read-only
(400 in create/PATCH bodies) and can be used as list filters like any other field.

**Changes.**
- `migrations/0002_claim_revisions.sql` adds `revision INTEGER NOT NULL DEFAULT 0` and
  `previous_rejection_reason TEXT`, so every existing claim gets 0/NULL and nothing else changes.
  The committed `data.db` is migrated.
- `repository.py` handles the new columns and adds `mark_claim_withdrawn` and `mark_claim_revised`.
- `permissions.py` adds `can_withdraw_claim` and `can_revise_claim`.
- `services.py` adds `withdraw_claim` and `revise_claim`, with `WITHDRAW_WINDOW` and
  `MAX_REVISIONS` as constants. `claim_actions` now offers `withdraw`/`revise` exactly when the
  action would succeed.
- `validation.CLAIM_READ_ONLY` includes the two new fields.
- `routes_api.py` and `routes_ui.py` have the new action endpoints. The claim detail template shows
  the two new fields and the two new forms. README updated.

**Verification.** Updated the existing tests that compare whole records (seed equality, create
response, detail page fields; claim 7's detail page now offers `revise`). Added
`tests/test_expenses_revisions.py`. It covers the window boundary, re-submitting, the revision limit
over three rejections, permissions, error precedence, no outbox writes, approve/pay after a revise,
the UI forms and fields, and migrating a database rebuilt in its pre-0002 state. All 49 tests pass,
both run directly and the way the evaluators run them (`cd harness && ACCEPT_TARGET=...`).
`seed.py` also still rebuilds the database.
