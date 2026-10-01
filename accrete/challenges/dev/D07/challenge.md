# D07 - Overdue block and new releases (library)

Categories: rule_change, conflict_or_ambiguity. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Borrowing is refused for members with overdue loans; recent books get 7-day loans.

## 2. Observable acceptance criteria

- Members with overdue seed loans (gus, ivan, kemal, jo) get 409 on borrow, also via librarian lending; nothing created.
- Members without overdue loans borrow normally; due-today does not block, the next day does.
- Returning the overdue loan lifts the block; returning a different loan does not.
- New releases (current/previous year of the request) get 7 days; older and undated books 14 days.

## 3. Behaviour that must remain intact

- Limit, inactive, on-loan 409s; 403 for borrowing for someone else; returns allowed; seed due dates unchanged.
- Base tests intentionally superseded: test_member_with_two_open_loans_may_borrow_third, test_member_borrows_for_self; every other base test must still pass.

## 4. Existing-data requirements

- Existing loans' due dates and overdue flags unchanged.

## 5. Failure and recovery conditions

- Blocked borrows create no loan and emit no message.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Whether the implementer followed the stated policies (librarian no override, due-today rule, year from X-Now).
- Base-suite regressions besides the 2 superseded tests.

## Brief (exact text given to implementers)

Borrowing restrictions

1. A member who has an overdue loan (an unreturned loan whose `due_at` is before today) cannot borrow: `POST /api/books/{id}/borrow` -> 409. Returning the overdue loan(s) lifts the block.
2. New releases have a shorter loan period: a book whose `year` is the current year or the previous year is lent for 7 days (`due_at` = today + 7 days). All other books, including books without a `year`, keep 14 days.

Our answers to the questions the team raised (follow these):
- "Today" and "current year" come from the request time (`X-Now`, UTC). Example: on 2026-03-01 books from 2025 and 2026 are new releases; on 2025-12-31 books from 2024 and 2025 are.
- A loan due today is not overdue (it becomes overdue tomorrow), consistent with the existing `overdue` field.
- The block applies equally when a librarian lends to the member; there is no override.
- Returns are never blocked.
- Existing loans keep their due dates; nothing is recalculated.

Everything else is unchanged (3-loan limit, inactive members, the `loan_created` message).
