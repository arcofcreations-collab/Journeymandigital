# Fresh challenge set (F01-F14)

| ID | App | Categories | depends_on | Superseded | Size | Summary |
|---|---|---|---|---|---|---|
| F01 | expenses | rule_change, data_migration, sequence | - | 3 | small | Claims gain `incurred_on` (real date, not in the future); `submit` needs it (409); migrated from the date of `submitted_at`, drafts null. |
| F02 | expenses | new_concept, permissions, rule_change, data_migration, interaction, sequence | F01 | 5 | large | Finance-managed `category_policies` (5 seeded: max amount, submission deadline) replace the fixed category list and the 5000 limit; new `lodging` category, 13 "Hotel night" claims migrated; submit refuses over-limit or late drafts (uses `incurred_on`). |
| F03 | expenses | rule_change, data_migration, interaction, sequence, conflict_or_ambiguity | F02 | 6 | medium | Partial approval: `approve` takes optional `amount`/`note` (note required when partial); payment pays `approved_amount`; approved claims above their new policy maximum (21, 22, 38) migrated as capped. |
| F04 | expenses | new_concept, new_relationship, cross_cutting, failure_atomicity, permissions, data_migration, interaction, sequence | F03 | 6 | large | Cash `advances` (3 seeded, finance-only creation, `advance_issued`), recovered oldest-first from the employee's next payments; claims gain `advance_recovered`/`paid_amount`; payment payload extended; refused payments leave no trace. |
| F05 | expenses | reversal, data_migration, interaction, sequence | F04 | 13 | medium | Withdrawal of F03: approve takes no parameters (400), `approved_amount`/`approval_note` removed, recovery from the full amount; capped approvals 21, 22, 38 go back to `submitted` with the decision cleared. |
| F06 | expenses | permissions, rule_change, interaction, sequence | F05 | 13 | small | Segregation of duties: finance cannot pay own claims (403 before 409), issue advances to themselves (403 before 400) or edit/delete their own employee record; role changes take effect immediately. |
| F07 | maintenance | new_concept, failure_atomicity, cross_cutting, permissions, rule_change | - | 0 | medium | Atomic asset `transfer` between sites: assigned orders return to `open`, one `asset_transferred` message, 409 for retired/in-progress, visibility and assignment follow the new site; `site` no longer PATCHable. |
| F08 | maintenance | permissions, rule_change, conflict_or_ambiguity | - | 2 | small | Requesters may cancel their own `assigned` orders; cancelling assigned or in-progress work emits `assignment_cancelled` to the technician. |
| F09 | maintenance | should_reject, conflict_or_ambiguity, permissions | - | 0 | small | Kiosk request: anonymous requests should act as supervisor sofia while clients omitting X-User must still get 401. Contradictory and unsafe: must be refused with CLARIFICATION.md. **(expect_rejection)** |
| F10 | library | rule_change, data_migration | - | 0 | small | Books gain `reference_only` (books 9, 33, 36, 40 migrated true, 9 stays on loan); borrowing a reference book is 409; no borrow form. |
| F11 | library | new_concept, rule_change, data_migration, permissions, conflict_or_ambiguity | - | 0 | medium | Annual memberships: `member_until` (inclusive) blocks borrowing after expiry; librarian-only `extend` (+365 days from the later of today and the end date, `membership_extended`); dates migrated from each member's first loan. |
| F12 | library | new_concept, new_relationship, failure_atomicity, permissions, cross_cutting | - | 0 | large | Purchase `suggestions` (3 seeded): suggester edits/withdraws while pending; librarian `accept` atomically creates the book and emits `book_added`; `decline` with reason; books from suggestions cannot be deleted. |
| F13 | expenses | data_migration, rule_change | - | 2 | small | Renamed concept: claim category `other` becomes `miscellaneous` (26 claims migrated); `other` is now a 400. |
| F14 | expenses | rule_change, permissions, conflict_or_ambiguity | - | 0 | medium | Finance `query` of an approved claim (at most once): back to `submitted` with `finance_query`, `claim_queried` message to the current manager; cleared on the next decision. |

## Notes

- **Sequence (F01-F06, expenses).** The app under test for F0k has F01..F0k applied in order, including every
  data migration. The steps interact. F02's submission deadline is measured from F01's `incurred_on`. F03's
  migration caps approvals at F02's policy maximums, which creates the partially approved seed claims 21, 22
  and 38. F04 recovers advances from F03's `approved_amount`. F05 withdraws F03, sends exactly those capped
  claims back to their managers and switches F04's recovery to the full amount. F06 restricts the F04
  operations (pay, advances) for finance users. Every test file re-checks behaviour of the earlier steps.
- **Superseded lists are cumulative** (as in the earlier sets). F01 supersedes the 3 base tests that submit a
  draft without a date. F02 adds 2: claim 7 becomes `lodging`, and the 5000 bound gives way to policy
  maximums. F03 adds the exact-amount payment test for claim 22 (now capped at 400). F04 adds none. F05 adds
  7 more, because claim 22 (used by many base tests as "the approved claim") is sent back to `submitted`.
  F06 adds none. Independent challenges list only their own: F08 has 2 (requester cancel of order 77) and
  F13 has 2 (category `other`).
- **Data migrations that transform seed records:** F01 (`incurred_on` from `submitted_at`), F02 (13 claims to
  `lodging`), F03 (approved/paid amounts, 3 capped), F04 (paid claims gain payment fields), F05 (3 claims
  back to `submitted`), F10 (4 books flagged), F11 (`member_until` from first loans), F13 (26 claims
  renamed). F04 and F12 also seed new records with exact ids.
- **Reversal:** F05 withdraws F03 after F04 has been built on it, so the reversal has to touch both the data
  (capped approvals) and the payment logic introduced in between.
- **Failure atomicity:** F04 (refused payments, snapshot of claims, advances and outbox), F07 (refused
  transfers, snapshot of staff, assets, work orders and outbox) and F12 (refused accepts, snapshot of books,
  suggestions and outbox).
- **Permissions:** F02 (finance-only policies), F04 (advance read and write rules), F06 (segregation of
  duties), F07 (supervisor-only transfer), F08 (requester cancel), F11 (librarian-only extend,
  member-protected field), F12 (suggester and librarian rights), F14 (finance-only query).
- **Ambiguity with a stated policy:** F02 (when the maximum is re-checked on PATCH, the deadline boundary),
  F03 (existing approvals above the new limits), F08 (requester who is also the assignee), F11 (inclusive
  expiry, extension base date, null/inactive), F14 (one query per claim, field clearing). **Should reject:**
  F09. Its tests check CLARIFICATION.md and that unauthenticated behaviour is unchanged.
- **Sizes:** 6 small (F01, F06, F08, F09, F10, F13), 5 medium (F03, F05, F07, F11, F14), 3 large (F02, F04, F12).
- **Freshness:** none of the 28 earlier challenges covers expense dates or submission deadlines, category
  policies, partial approval, cash advances, finance segregation of duties, a category rename, finance
  queries, asset transfer, requester withdrawal of assigned orders, reference-only books, membership expiry,
  or purchase suggestions. F09 is a new kind of refusal: a contradiction in authentication, not in data.
- **Validation.** A private reference implementation (`_ref/`, author tooling, not for implementers)
  implements the three base apps and every challenge state. `python _ref/validate.py` rebuilds all 17
  reference states and checks four things. All three base suites pass on the base reference. Every hidden
  test file passes 100% on its changed state. The hidden tests do not all pass on the state before the
  change; for F09, only `test_clarification_written` fails before. The base tests that fail on each changed
  state are exactly that challenge's `superseded_base_tests`, and every listed name exists. Expected values
  were computed from the seed JSON with small scripts (see the docstring of each test file).
- Outbox assertions only look at messages added after a recorded point, and only on channels the spec or a
  brief defines. Money values from advance recovery are compared after rounding to 2 decimals, as the brief
  specifies. The tests do not depend on the ids of new records.
