# D11 - Atomic payment runs (expenses)

Categories: failure_atomicity, new_concept, new_relationship, interaction, sequence. Depends on: D10. Expect rejection: no.

## 1. Requested outcome

Batch payment that is atomic across claims, outbox and claim history.

## 2. Observable acceptance criteria

- Run of [13, 4, 12]: total 1185.63, claims paid with payment_run, 3 ordered payment messages then payment_run message.
- Pay events recorded for each claim in the run.
- Any non-approved claim (first, middle or last) -> 409 with no trace in claims, events, runs or outbox.
- Total cap 10000.00 (11027.90 refused, 9620.45 accepted); validation errors 400 with no trace; 409 beats 400.
- Only finance creates/reads runs; runs immutable; paid claims cannot be paid again.

## 3. Behaviour that must remain intact

- Single `pay` unchanged (payment_run null, payment message, pay event).
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- All seed claims have payment_run null; no runs initially.

## 5. Failure and recovery conditions

- Snapshot of claims, claim_events, payment_runs and outbox is identical after every failed run.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Partial-write incidents across claims/events/outbox/runs.
- D10 hidden-test pass rate after this change.

## Brief (exact text given to implementers)

Payment runs

(This change is made on top of the claim history feature: collection `claim_events`, one event per successful submit/approve/reject/pay.)

Finance wants to pay several approved claims in one operation.

New collection `payment_runs` with fields: `claims` (list of claim ids, in the order given), `total` (number: the sum of those claims' amounts, rounded to 2 decimals), `created_by` (reference to employees, set to the caller), `created_at` (datetime, set to now). Claims get a new field `payment_run` (reference to payment_runs or null): null for all existing claims and for claims paid with the single `pay` action. Clients cannot set `payment_run` on claims (400).

`POST /api/payment_runs` with `{"claims": [<claim id>, ...]}`:
- Finance users only (others -> 403, also with an invalid body).
- 400 if `claims` is missing, not a list, empty, contains a duplicate or the id of a claim that does not exist, or if the total would exceed 10000.00.
- 409 if any listed claim is not `approved`. When both a 409 and a 400 condition apply, the 409 wins.
- On success (201, returns the run): every listed claim becomes `paid` with `payment_run` = the run's id. For each claim, in list order, a `payment` outbox message is emitted with the same payload as the `pay` action and a `pay` claim event is recorded (`actor` = the caller, `at` = now, `approved` -> `paid`). After these, one outbox message on channel `payment_run` with payload `{"run": <run id>, "claims": [<ids in order>], "total": <total>}`.
- All or nothing: if the request fails for any reason, no claim changes, no outbox message is emitted, no claim event is recorded and no run is created.

Runs are readable only by finance users (others get an empty list and 403 on a single run). Runs cannot be changed or deleted (PATCH / DELETE -> 403 for everyone).

The single `pay` action is unchanged.
