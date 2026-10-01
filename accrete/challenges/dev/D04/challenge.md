# D04 - Late-return fines (library)

Categories: rule_change, sequence, interaction, data_migration, cross_cutting. Depends on: D03. Expect rejection: no.

## 1. Requested outcome

Fines accrue on late loans, block members with unpaid fines, and can be settled by librarians; historic fines are computed and settled.

## 2. Observable acceptance criteria

- Historic late loans (2,4,14,17,19,26,28,29,35,36,41,44) show the computed fine and `fine_paid` true; others 0/false (incl. same-day returns 11, 38).
- Open loans accrue 0.50/day capped at 5.00; `fines_due` is 0 for every seed member.
- Late return emits `fine_charged`; the member is blocked from borrow, librarian lending, holds and renewals (409).
- `pay_fine` by librarians only; 409 for unreturned, zero, already-paid; emits `fine_paid`; unblocks the member.
- Fine uses the renewed due date; a ready-hold member with fines cannot borrow until paid; UI `pay_fine` form.

## 3. Behaviour that must remain intact

- On-time returns emit no fine message; holds and renewals behave as in D02/D03 otherwise.
- Base tests intentionally superseded: test_unknown_collection_record_and_action_are_404; every other base test must still pass.

## 4. Existing-data requirements

- Historic fines as listed (cap 5.00, 0.50/day) and settled; no member owes anything initially.

## 5. Failure and recovery conditions

- Blocked borrow/hold/renew calls create nothing and emit nothing; failed pay_fine changes nothing and emits nothing.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- D02 and D03 hidden-test pass rate after this change (accumulated regressions).
- Correctness of the 12 historic fines.

## Brief (exact text given to implementers)

Late-return fines

(This change is made on top of holds and loan renewals: `holds`, `POST /api/books/{id}/hold`, `POST /api/holds/{id}/cancel`, `POST /api/loans/{id}/renew`, loan field `renewals`.)

Loans get two new fields:
- `fine` (derived, read-only number): 0.50 for each day the loan is late, capped at 5.00. For a returned loan, days late = (calendar date of `returned_at`) - `due_at`, or 0 if that is not positive. For an unreturned loan, days late = today - `due_at`, or 0 if not positive (so it grows daily until the cap). Always computed from the loan's current `due_at`, i.e. after any renewals.
- `fine_paid` (boolean).

Members get a new derived, read-only field `fines_due`: the sum of `fine` over that member's returned loans whose `fine_paid` is false. Fines on loans that are still out do not count until the book is returned.

Rules:
- While a member's `fines_due` is greater than 0, that member cannot borrow (neither for themselves nor through a librarian lending to them), renew a loan, or place a hold: 409. This also applies to a member whose hold is `ready`; their hold stays `ready`.
- Returning a loan whose `fine` is greater than 0 emits an outbox message on channel `fine_charged` with payload `{"loan": <loan id>, "member": <member id>, "amount": <fine>}`.
- New action `POST /api/loans/{id}/pay_fine` (body `{}`), librarians only (members -> 403). 409 if the loan is not returned, its `fine` is 0, or `fine_paid` is already true. Sets `fine_paid` = true, emits exactly one outbox message on channel `fine_paid` with payload `{"loan": <loan id>, "member": <member id>, "amount": <fine>}`, and returns the loan.
- UI: the loan detail page shows a `pay_fine` form exactly when the caller may pay that loan's fine right now.

Existing data (required): existing loans that were returned late carry their computed fine and are treated as already settled: `fine_paid` = true. Every other existing loan has `fine_paid` = false. So no existing member owes anything when this change ships.

Holds and renewals keep working as before, subject to the new rule.
