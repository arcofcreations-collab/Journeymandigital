# F02 (expenses, depends on F01)

Size: large. Categories: new_concept, permissions, rule_change, data_migration, interaction, sequence.

## 1. Requested outcome

Per-category policies maintained by finance replace the fixed category list and the global 5000 limit; hotel costs move to a new `lodging` category; late or over-limit drafts cannot be submitted.

## 2. Observable acceptance criteria

- `category_policies` seeded with ids 1-5 exactly as in the brief; readable by everyone; finance-only writes (403 first); PATCH cannot rename `category`; delete of a used policy 409.
- Claim category must match a policy; amount <= policy maximum on create, and on PATCH only when `amount`/`category` is sent.
- Submit 409 when amount > current maximum or when today - incurred_on > submit_within_days; boundary day allowed; policy edits take effect immediately.
- New categories created by finance are usable by claims; deleted unused ones are not.
- UI list/detail/create form for policies; submit form follows the new rules.

## 3. Behaviour that must remain intact

F01 behaviour (incurred_on validation and submit rule), approve/reject/pay (no policy checks), payment payload, claim read permissions.

Superseded base tests (5): `test_submit_own_draft`, `test_full_claim_lifecycle`, `test_ui_claim_detail_draft_owner`, `test_claim_fields_match_seed`, `test_create_claim_amount_bounds`.

## 4. Existing-data requirements

13 claims with description "Hotel night ..." (1 7 11 15 17 31 36 39 43 48 54 55 57) become `lodging`; all other categories, amounts and statuses unchanged (e.g. 21 stays meals 1644.21, 79 meals 553.87).

## 5. Failure and recovery conditions

403/400/409 on policy writes change no policy; refused submits leave the draft unchanged; a 400 claim create adds nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.
- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
