# E12 (expenses): atomic employee offboarding

## 1. Requested outcome
Finance can offboard an employee in one atomic step: deactivate them, move their direct reports to
a successor manager, delete their draft claims and announce it on `employee_offboarded`.
Inactive employees keep reading but can no longer write.

## 2. Observable acceptance criteria
- All seed employees `active: true`; `active` is read-only (400 when sent) and filterable.
- Offboarding marco with successor nadia: marco inactive, employees 4 6 9 12 15 now managed by 3,
  payload `{"employee":2,"successor":3,"reassigned":[4,6,9,12,15],"deleted_claims":[]}`, nadia now
  reads and approves their claims, marco reads none and cannot approve.
- sam cannot be offboarded while claims 22/61 are approved (409); after they are paid, offboarding
  deletes drafts 20 54 73 (404 afterwards) and lists them in the payload.
- Check order 404, 403, 409, 400; invalid successors (missing, unknown, non-manager, finance, self,
  a report of the leaver, inactive) are 400.
- Inactive users: 403 on every write and action, reads unchanged, create forms 403; inactive
  employees cannot be set as `manager` (400). UI `offboard` form only when allowed now.

## 3. Behaviour that must remain intact
Approvals by the current direct manager, payment payload (3 keys), claim creation by active
employees, finance employee management.

## 4. Existing-data requirements
Every employee gets `active: true`; nothing else changes. No base test is superseded.

## 5. Failure and recovery conditions
Every refused offboard (403/409/400) leaves employees, claims and outbox identical (full snapshot
comparison). After settling in-flight claims the same offboard succeeds.

## 6. Measurements to collect
Standard harness measurements, plus number of atomicity snapshots preserved and whether inactive
users are blocked from all write paths (create, actions, UI forms).
