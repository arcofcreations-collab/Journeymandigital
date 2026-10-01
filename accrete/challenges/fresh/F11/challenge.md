# F11 (library)

Size: medium. Categories: new_concept, rule_change, data_migration, permissions, conflict_or_ambiguity.

## 1. Requested outcome

Memberships expire; expired members cannot borrow until a librarian extends them.

## 2. Observable acceptance criteria

- member_until on members, librarian-settable with date validation; member PATCH with it 403.
- Borrow 409 after the expiry date (inclusive end), for self and librarian lending; returns and reads still work.
- extend: librarian only; 409 for null or inactive; +365 days from max(today, member_until); `membership_extended` message.
- UI field, extend form, create input; filters on member_until.

## 3. Behaviour that must remain intact

Base borrow/return rules at the default test dates, inactive-member rule, member name editing.

Superseded base tests (0): none.

## 4. Existing-data requirements

member_until: chen 2026-10-27, dara 2026-09-02, eli 2026-09-07, fatima 2026-09-19, gus 2026-11-15, hana 2026-09-05, ivan 2026-09-10, jo 2026-09-18, kemal 2026-09-02; ada, ben, lena null.

## 5. Failure and recovery conditions

Refused extends and borrows change nothing and emit nothing.

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Seed records whose migrated values differ from the brief (counted by the existing-data tests).
- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
