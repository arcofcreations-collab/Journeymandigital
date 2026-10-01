# Clarification needed: "Instant reimbursement"

The change request was **not implemented**; the application's behaviour is unchanged.

## Why

The two points contradict each other:

1. `POST /api/claims/{id}/approve` should set `status` to `paid` and emit the `payment`
   outbox message immediately, i.e. money leaves the company at the manager's approval.
2. "No money may leave the company before a finance user has reviewed the approved claim and
   called `pay` on it", and finance "must still see every approved claim waiting for payment".

The `payment` outbox message is what triggers the money transfer. If approval emits it, money
leaves without any finance review, violating point 2. And if approval moves claims straight to
`paid`, no claim ever sits in `approved`, so finance has nothing to review and `pay` (which only
works from `approved`) can never be called. Both points cannot hold at once, and choosing one
silently would either remove a financial control or ignore the CFO's explicit request.

## Decision needed (CFO / finance)

Pick one:

- **A. Keep the finance control (current behaviour).** Approve -> `approved`; finance reviews
  and calls `pay` -> `paid` + `payment` message. Speed could instead come from e.g. a finance
  queue/notification of approved claims.
- **B. Remove the finance control.** Approve -> `paid` + `payment` message immediately;
  finance no longer reviews or pays claims (the `pay` step and the `approved` state become
  unused). This needs explicit sign-off that payment without finance review is acceptable,
  and a decision on what to do with claims currently in `approved`.
- **C. A hybrid**, e.g. instant payment only below an amount threshold, with finance review
  above it, specified with the threshold and who decides.
