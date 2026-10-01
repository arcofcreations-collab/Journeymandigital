# Application: Expense claims (`expenses`)

Employees submit expense claims that their manager approves and finance pays. Starting data:
`expenses_seed.json` (the same records, with the same ids, are loaded into every implementation).

## Collections and fields

**employees**: `username` (text, required, unique), `name` (text, required),
`role` (`"employee"`, `"manager"` or `"finance"`, required), `manager` (reference to employees,
optional), `department` (text, required).

**claims**: `employee` (reference to employees; set automatically to the creator),
`amount` (number, required, greater than 0 and at most 5000), `category` (`"travel"`,
`"meals"`, `"equipment"` or `"other"`, required), `description` (text, required),
`status` (`"draft"`, `"submitted"`, `"approved"`, `"rejected"`, `"paid"`; starts as `"draft"`),
`submitted_at` (datetime or null), `decided_at` (datetime or null),
`decided_by` (reference to employees or null), `rejection_reason` (text or null).
Clients cannot set `employee`, `status`, `submitted_at`, `decided_at`, `decided_by` or
`rejection_reason` directly (sending them -> `400`).

## Actions

* `POST /api/claims/{id}/submit`: by the claim's employee, only from `draft` (else `409`).
  Sets `status` = `submitted`, `submitted_at` = now.
* `POST /api/claims/{id}/approve`: by the claim employee's manager, only from `submitted`
  (else `409`). Sets `status` = `approved`, `decided_at` = now, `decided_by` = the manager.
* `POST /api/claims/{id}/reject` with `{"reason": text}` (required, non-empty, else `400`):
  same permission and state rule as approve. Sets `status` = `rejected`, `decided_at`,
  `decided_by`, `rejection_reason`.
* `POST /api/claims/{id}/pay`: by any finance user, only from `approved` (else `409`).
  Sets `status` = `paid`. Emits outbox message on channel `payment` with payload
  `{"claim": id, "employee": id, "amount": amount}`.

## Permissions

* Any authenticated user can read the employees list. Only finance users can create,
  update or delete employees.
* Any employee (any role) can create claims; the claim's `employee` is the creator.
* A claim is readable by its employee, by that employee's manager, and by finance users
  (finance can read every claim).
* Only the claim's employee can PATCH it, and only while it is `draft` (otherwise `409`);
  editable fields: `amount`, `category`, `description`.
* Only the claim's employee can DELETE it, and only while `draft` (otherwise `409`).
