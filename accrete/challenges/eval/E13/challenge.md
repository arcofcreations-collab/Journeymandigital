# E13 (expenses): withdraw submitted claims, revise rejected claims

## 1. Requested outcome
Employees can pull back a recently submitted claim (`withdraw`, within 7 days) and turn a rejected
claim back into a draft (`revise`, at most twice). Two read-only fields record the revision count
and the previous rejection reason.

## 2. Observable acceptance criteria
- All claims start with `revision` 0 and `previous_rejection_reason` null; both are protected (400).
- `withdraw`: owner only (403 first), only `submitted` within 168 hours of `submitted_at`
  (inclusive boundary, checked with X-Now); result `draft`, `submitted_at` null; re-submit sets a
  new timestamp and the normal approval works.
- `revise`: owner only, only `rejected` with revision < 2; moves the reason to
  `previous_rejection_reason`, clears decision fields and `submitted_at`, increments `revision`;
  the third rejection is final (409 on revise).
- Revised claims can be edited, deleted, re-submitted, approved and paid (payment payload unchanged).
- UI forms follow the same rules including the time window; new fields visible on detail pages.

## 3. Behaviour that must remain intact
Submit/approve/reject/pay state machine and permissions, protected fields, draft-only PATCH/DELETE,
read rules.

## 4. Existing-data requirements
New fields defaulted on all 80 claims; nothing else changes. No base test is superseded.

## 5. Failure and recovery conditions
Refused withdraw/revise calls leave status and timestamps unchanged (e.g. claim 3 keeps
`submitted_at` 2026-02-24T14:00:00 after a late withdraw; claim 7 keeps its decision fields after
a forbidden revise).

## 6. Measurements to collect
Standard harness measurements, plus exactness of the time-window boundary and the revision limit.
