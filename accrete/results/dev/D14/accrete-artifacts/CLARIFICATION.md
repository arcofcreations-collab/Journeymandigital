# Clarification needed: "Instant reimbursement"

The application has NOT been changed. The two points of the request contradict each other,
so they cannot both be implemented.

## The contradiction

- **Point 1** says `POST /api/claims/{id}/approve` (run by the employee's *manager*) sets
  `status` straight to `paid` and emits the `payment` outbox message in the same step.
  The `payment` message is what tells the payment integration to send the money, so the
  money would leave as soon as a manager approves, with no finance step at all.
- **Point 2** says finance control stays exactly as it is: no money may leave before a
  *finance* user has reviewed the approved claim and called `pay`, and finance must still
  see every approved claim waiting for payment.

If point 1 is implemented, money leaves before any finance review (breaking point 2),
claims never wait in `approved` (so finance has nothing to see or review), and `pay` can
never run because its guard needs `approved`. If point 2 is kept, approval cannot pay.
There is no reading where both hold. Picking one would mean guessing on a payment control,
which is a financial-control/segregation-of-duties decision that should not be made by the
implementer.

## Decision needed (pick one)

1. **Manager approval pays immediately** (drop finance's pre-payment review): approve sets
   `paid` and emits `payment`; `pay` becomes unused. The CFO must explicitly confirm that
   finance's control is removed (perhaps only below an amount threshold?).
2. **Keep finance control** (current behaviour): approve -> `approved`, finance calls `pay`
   -> `paid` + `payment`. To "speed up" reimbursements, alternatives that keep the control
   could be considered, e.g. a finance queue view, bulk payment of several approved claims
   in one action, or alerts to finance when a claim is approved.
3. **Hybrid**: auto-pay on approval only for claims under an agreed amount/category, with
   finance review for everything else. Needs the threshold and rules.

Existing data was not touched; no change was applied.
