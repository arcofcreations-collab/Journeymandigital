# Development challenge set (D01-D14)

| ID | App | Categories | depends_on | Superseded base tests | Summary |
|---|---|---|---|---|---|
| D01 | library | data_migration, new_relationship, new_concept, cross_cutting | - | 5 | Authors become a collection; `books.author` turns into a reference; free-text authors migrated with deterministic ids. |
| D02 | library | new_concept, cross_cutting, rule_change | - | 0 | Hold queue for on-loan books: new `holds` collection, `reserved` book status, return/borrow/cancel interplay. |
| D03 | library | rule_change, sequence, interaction | D02 | 1 | Loan renewals (max 2, +14 days from due date), refused when overdue or someone is waiting (holds). |
| D04 | library | rule_change, sequence, interaction, data_migration, cross_cutting | D03 | 1 | Late-return fines with cap, member block, `pay_fine`; historic fines computed and settled; interacts with holds and renewals. |
| D05 | library | permissions, rule_change | - | 0 | New `assistant` role: can lend/return and toggle members' `active`, nothing else. |
| D06 | library | failure_atomicity, new_concept, cross_cutting | - | 0 | Atomic bulk checkout `POST /api/members/{id}/checkout`: all loans and messages, or none. |
| D07 | library | rule_change, conflict_or_ambiguity | - | 2 | Block borrowing for members with overdue loans; 7-day loans for new releases (policy for ambiguities given). |
| D08 | expenses | rule_change, permissions, data_migration, conflict_or_ambiguity | - | 8 | Second approval for claims > 1000.00 when a skip-level manager exists; open large approvals migrated back to `awaiting_second_approval`. |
| D09 | expenses | reversal, data_migration, sequence, permissions | D08 | 0 | Reversal of D08: remove the second approval, restore migrated claims to their first approval, drop fields and extra read access. |
| D10 | expenses | cross_cutting, new_concept, data_migration | - | 0 | Claim history `claim_events` for every status change, with backfill (139 events) from existing claims. |
| D11 | expenses | failure_atomicity, new_concept, new_relationship, interaction, sequence | D10 | 0 | Atomic payment runs (`payment_runs`) paying many claims at once, consistent with outbox and claim history. |
| D12 | expenses | new_relationship, data_migration, cross_cutting, conflict_or_ambiguity | - | 0 | Itemised claims: `claim_lines`, derived claim amount, backward-compatible claim PATCH; one migrated line per claim (same id). |
| D13 | expenses | new_concept, permissions, conflict_or_ambiguity | - | 0 | Time-boxed approval delegation between managers, no self-approval, no chaining. |
| D14 | expenses | should_reject, conflict_or_ambiguity | - | 0 | Contradictory 'instant reimbursement' request (pay on approve vs. finance review first): must be refused with CLARIFICATION.md. **(expect_rejection)** |

## Notes

- Dependency chains: D02 -> D03 -> D04 (library: holds, renewals, fines; each later step interacts with the earlier ones); D08 -> D09 (expenses: change and its reversal); D10 -> D11 (expenses: claim history, then payment runs that must record history atomically).
- For a challenge with `depends_on`, the app under test has the earlier challenge(s) applied. `superseded_base_tests` is cumulative: it lists every base test that is false in the state after the challenge (e.g. D04 repeats D03's superseded 404 test; D09 lists none because the reversal makes all base tests valid again).
- Data migrations that transform seed records: D01 (author text -> reference), D04 (historic fines settled), D08 (approved -> awaiting_second_approval), D09 (awaiting -> approved with first approval restored), D10 (history backfill), D12 (one line per claim).
- Failure/atomicity: D06 and D11 compare full snapshots (records, statuses, outbox, history) before/after each failed multi-record operation.
- Ambiguity with stated policy: D07 (time/overdue/override policy), D08 (managers without a manager, 403-vs-409 matrix), D12 (PATCH of a derived amount), D13 (self-approval via delegation, chaining).
- Should reject: D14 (contradictory requirements); tests check CLARIFICATION.md and unchanged behaviour.
- Outbox assertions only inspect messages on the channels a brief defines, because the base spec does not say whether successful return/submit/approve/reject emit anything.
