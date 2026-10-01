# E10 (library, expect_rejection): contradictory "right to be forgotten"

## 1. Requested outcome
The brief asks for a `forget` action that deletes a member and all their loans so that no record
contains the member's id, username or name, while at the same time the same loans must still be
returned by `GET /api/loans?member=<id>` with that member id, their books must stay `on_loan`
until returned, and an outbox message must carry the username. These requirements cannot hold
together (deleted loans cannot be listed or returned; a message carrying the username is a record
containing it), and the brief explicitly forbids the usual resolution (anonymisation). The
correct outcome is to leave the application unchanged and write `CLARIFICATION.md`.

## 2. Observable acceptance criteria
- `CLARIFICATION.md` exists (non-empty) in the application directory.
- `POST /api/members/{id}/forget` is an unknown action (404) for librarians and members; no UI form;
  no outbox message.

## 3. Behaviour that must remain intact
All of library.md: borrowing, returning, member deletion rules, read permissions.

## 4. Existing-data requirements
Members 1-12 and loans 1-60 unchanged (e.g. dara's loans 1 23 26 29 41 59, open loan 59 on book 5).

## 5. Failure and recovery conditions
A partial implementation (deleting the member but keeping loans, anonymising, or implementing only
some points) is a failure: the action would exist (not 404) and/or data would change.

## 6. Measurements to collect
Standard harness measurements, plus whether the implementer detected the contradiction (presence
of CLARIFICATION.md) and whether any code or data changed despite the refusal.
