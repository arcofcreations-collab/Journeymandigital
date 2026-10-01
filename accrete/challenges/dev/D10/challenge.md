# D10 - Claim history (expenses)

Categories: cross_cutting, new_concept, data_migration. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Every status change is recorded; history is reconstructed for existing claims.

## 2. Observable acceptance criteria

- 139 backfilled events: 68 submit, 44 approve, 6 reject, 21 pay; reject events by omar are on claims 7, 14, 23, 60.
- Exact backfill for claims 6 (submit/approve/pay with null actor/at), 7 (submit/reject), 2 (submit), 20 (none).
- New actions record events with caller and X-Now, after all backfilled ids.
- Failed actions (403/404/409/400) and draft create/patch/delete record nothing.
- Event visibility follows claim visibility (sam 10 events, omar 62); events are read-only; UI list.

## 3. Behaviour that must remain intact

- Claim actions and the `payment` message unchanged.
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- Backfill counts and contents as above.

## 5. Failure and recovery conditions

- No event for any failed action; events cannot be forged or altered.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Backfill accuracy (139 events, ordering).
- Events recorded for failed actions (should be 0).

## Brief (exact text given to implementers)

Claim history

We need an audit trail of every status change of a claim.

New read-only collection `claim_events` with fields: `claim` (reference to claims), `action` (`"submit"`, `"approve"`, `"reject"` or `"pay"`), `actor` (reference to employees, or null), `at` (datetime, or null), `from_status` and `to_status` (claim status values).

- Every successful `submit`, `approve`, `reject` and `pay` action records exactly one event: `actor` = the caller, `at` = now, `from_status` / `to_status` = the claim's status before and after the action. A failed action (any error) records nothing. Creating, editing and deleting draft claims record nothing.
- An event is readable by exactly the users who can read its claim; lists contain only those, and direct access to another event -> 403. `GET /api/claim_events?claim=<id>` lists one claim's events (all fields filter as usual).
- Nobody can create, PATCH or DELETE events (403 for everyone).
- Event ids increase in the order events are recorded.
- This change adds no outbox messages.

Existing data (required): backfill the history of the existing claims from their fields:
- each claim with a `submitted_at` gets a `submit` event: `actor` = the claim's employee, `at` = `submitted_at`, `draft` -> `submitted`;
- each claim with a `decided_at` gets an `approve` event (`submitted` -> `approved`) if the claim is now `approved` or `paid`, or a `reject` event (`submitted` -> `rejected`) if it is `rejected`; `actor` = `decided_by`, `at` = `decided_at`;
- each `paid` claim gets a `pay` event (`approved` -> `paid`) with `actor` = null and `at` = null, because who paid and when was never recorded.
Backfilled events have lower ids than any event recorded afterwards, and a claim's backfilled events are in the order submit, decision, pay.
