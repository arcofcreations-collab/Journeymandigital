# E09 (library): household guardians

## 1. Requested outcome
Members can be linked to a guardian member. Guardians can see their dependants' member records and
loans, borrow for them and return their loans, but cannot edit them. Four existing family links are
migrated.

## 2. Observable acceptance criteria
- `guardian` values after migration: 5->4, 10->4, 7->6, 12->11, others null; filterable.
- dara sees members [4, 5, 10] and her own + eli's + jo's loans (23 loans); fatima [6, 7]; kemal
  [11, 12]; dependants see nothing of their guardian.
- Guardian borrowing for a dependant creates the dependant's loan and the normal `loan_created`
  message; dependant's limit (jo has 3) and inactivity (lena) give 409; borrowing for non-dependants
  stays 403 and wins over 409.
- Guardian returns dependants' loans; not others' (403); already returned 409.
- Only librarians set `guardian`; validation of self/unknown/chained guardians (400); members PATCH
  only their name; guardians cannot PATCH/DELETE dependants; deleting a guardian 409.
- Removing the link removes access immediately; new members can be created with a guardian.

## 3. Behaviour that must remain intact
Members without dependants (chen, hana) see exactly what they saw before; 3-loan limit; librarians'
full access; return/borrow precedence; UI conventions.

## 4. Existing-data requirements
Exactly four members get a guardian; no other changes. No base test is superseded.

## 5. Failure and recovery conditions
Refused borrows (403/409) create no loan and emit nothing; refused returns leave `returned_at` null.
A refused guardian assignment leaves the previous value.

## 6. Measurements to collect
Standard harness measurements, plus the number of permission surfaces (member read, loan read/list,
borrow, return, UI) where guardian rights were applied consistently.
