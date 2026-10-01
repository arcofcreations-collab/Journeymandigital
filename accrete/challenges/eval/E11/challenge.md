# E11 (expenses): cost centres with budgets

## 1. Requested outcome
Claims are charged to `cost_centres` that carry a budget; derived `committed`/`remaining` track
approved and paid amounts; approval beyond the budget is refused; the payment message names the
cost centre. Existing claims are assigned to their department's cost centre.

## 2. Observable acceptance criteria
- Cost centres 1-4 as listed; committed ENG 28886.18 / SAL 10750.94 / FIN 0 / TRV 0 (remaining
  2113.82 / 1249.06 / 2000 / 5000).
- All 24 Sales claims -> 2, other 56 -> 1; filterable.
- Approvals within budget succeed and update committed; beyond budget 409 (e.g. 62 after 58,
  2 after 43); 403 still first; `approve` UI form hidden when over budget; reject unaffected.
- Payment payload `{"claim","employee","amount","cost_centre"}`; paying leaves committed unchanged.
- Default cost centre from the creator's department; explicit valid id accepted; invalid/null 400;
  PATCH of cost_centre only on own drafts.
- Finance-only CRUD with validation; budget below committed 409 (equal allowed); delete with claims 409.

## 3. Behaviour that must remain intact
Claim permissions, state machine, amount bounds, protected fields, employee management.

## 4. Existing-data requirements
4 cost centres exactly; 80 claims get the department's centre; nothing else changes. Superseded base
tests (2): the two tests comparing the exact `payment` payload.

## 5. Failure and recovery conditions
A budget-refused approval leaves the claim submitted with no decision fields; raising the budget
makes the same approval succeed.

## 6. Measurements to collect
Standard harness measurements, plus cent-exact budget arithmetic and whether the UI approve form
reflects the budget rule.
