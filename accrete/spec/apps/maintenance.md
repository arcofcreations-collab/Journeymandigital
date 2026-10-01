# Application: Maintenance work orders (`maintenance`)

A facilities team at three sites tracks its staff, the physical assets it maintains and the work
orders raised against those assets. Starting data: `maintenance_seed.json` (the same records, with
the same ids, are loaded into every implementation; the seed contains no derived fields).
`make_maintenance_seed.py` generated it.

Everything in CONTRACT.md applies. This document adds the application rules. Terms used below:

* *today* is the date part of the request's `X-Now`.
* An *unfinished* work order is one whose `status` is `"open"`, `"assigned"` or `"in_progress"`.
* *Non-empty text* is a JSON string containing at least one non-whitespace character.

## Collections and fields

**staff**: `username` (text, required, unique), `name` (text, required),
`role` (`"requester"`, `"technician"` or `"supervisor"`, required), `site` (text, required),
`active` (boolean, default `true`).

**assets**: `tag` (text, required, unique), `name` (text, required), `site` (text, required),
`criticality` (`"low"`, `"medium"` or `"high"`, required), `retired` (boolean, default `false`),
`open_orders` (derived: integer, the number of unfinished work orders whose `asset` is this asset).

**work_orders**:

| field | type | notes |
|---|---|---|
| `asset` | reference to assets | required on create; cannot be changed afterwards |
| `title` | text | required |
| `description` | text or null | optional, default `null` |
| `priority` | `"low"`, `"normal"` or `"urgent"` | required |
| `status` | `"open"`, `"assigned"`, `"in_progress"`, `"completed"`, `"cancelled"` | starts as `"open"` |
| `requested_by` | reference to staff | set automatically to the creator |
| `created_at` | datetime | set automatically to now |
| `assignee` | reference to staff or null | starts `null`; set by `assign` |
| `started_at` | datetime or null | set by `start` |
| `completed_at` | datetime or null | set by `complete` |
| `resolution` | text or null | set by `complete` |
| `labor_minutes` | integer or null | set by `complete` |
| `cancel_reason` | text or null | set by `cancel` |
| `due_date` | derived date | the date part of `created_at` plus 1 day (`urgent`), 7 days (`normal`) or 30 days (`low`); it follows the current `priority` |
| `overdue` | derived boolean | `true` when the order is unfinished and today is after `due_date`; otherwise `false` |

Settable fields (anything else in a create or PATCH body, including `id`, derived fields,
system-managed fields and unknown names, is a `400`, unless a `403` rule below applies first):

* staff, on create and PATCH: `username`, `name`, `role`, `site`, `active`.
* assets, on create and PATCH: `tag`, `name`, `site`, `criticality`, `retired`.
* work_orders, on create: `asset`, `title`, `description`, `priority`.
  On PATCH: `title`, `description`, `priority` (see Permissions for who may change which).

## Actions

All actions are `POST /api/work_orders/{id}/{action}` and return the work order after the action.
Checks happen in the contract's order: permission (`403`), then state (`409`), then parameters (`400`).
A failed action changes nothing and emits nothing.

* `assign` with `{"technician": <staff id>}`: supervisors only. Allowed when the status is `open`
  or `assigned` (re-assignment, also to the same technician), otherwise `409`. `technician` is
  required and must be the id of an existing staff record whose `role` is `technician`, whose
  `active` is `true` and whose `site` equals the site of the work order's asset; otherwise `400`.
  Sets `assignee` = that technician and `status` = `assigned`. Emits an outbox message on channel
  `assignment` with payload `{"work_order": id, "asset": asset id, "technician": staff id}`.
* `start` with `{}`: only the work order's current `assignee`. Only from `assigned`, otherwise
  `409`. Sets `status` = `in_progress` and `started_at` = now.
* `complete` with `{"resolution": text, "labor_minutes": integer}`: only the current `assignee`.
  Only from `in_progress`, otherwise `409`. `resolution` must be non-empty text and
  `labor_minutes` a JSON integer >= 1 (not a boolean, decimal or string), otherwise `400`.
  Sets `status` = `completed`, `completed_at` = now, `resolution` and `labor_minutes`.
  Emits an outbox message on channel `work_completed` with payload
  `{"work_order": id, "asset": asset id, "technician": assignee id, "labor_minutes": n}`.
* `cancel` with `{"reason": text}`: by any supervisor, or by the work order's `requested_by`
  staff member; everyone else gets `403`. A supervisor may cancel from `open`, `assigned` or
  `in_progress`; a requester who is not a supervisor only from `open`. Any other case is `409`.
  `reason` must be non-empty text, otherwise `400`. Sets `status` = `cancelled` and
  `cancel_reason`; `assignee` and `started_at` keep their values.

No other operation emits outbox messages.

## Permissions

* Any authenticated user can read all staff and all assets.
* Only supervisors can create, update or delete staff and assets (`403` for everyone else).
* A work order is readable by: every supervisor; its `requested_by` staff member; its `assignee`;
  and every technician whose `site` equals the site of the order's asset (current values).
* Any staff member can create a work order. A requester or technician may only create work
  orders for an asset at their own `site`: an existing asset at another site gives `403`, and
  this `403` wins over any `400` in the same body. Supervisors may create for any site.
* PATCH of a work order: a supervisor may change `title`, `description` and `priority` while the
  order is unfinished. Otherwise, the order's `requested_by` staff member may change `title` and
  `description` while the order is `open`; if they send `priority` they get `403`. Everyone else
  gets `403`. A PATCH in a state not allowed for the caller is `409`.
* Nobody can delete work orders (`403`).
* Deleting a staff member who is the `requested_by` or `assignee` of any work order is `409`.
  Deleting an asset that has any work orders is `409`.
* Setting an asset's `retired` to `true` while its `open_orders` is greater than 0 is `409`.
* New staff are valid `X-User` identities immediately. Inactive staff (`active` = `false`) are
  still valid identities with all the rights of their role; `active` only matters for `assign`.

## Validation

* Required fields missing or `null` -> `400`. Text fields that are required must be non-empty
  text. Duplicate `username` or `tag` (create or PATCH) -> `400`.
* Enumerated fields (`role`, `criticality`, `priority`) must have one of the listed values,
  booleans must be JSON booleans -> otherwise `400`.
* Creating a work order: `asset` must be the id of an existing asset (otherwise `400`) that is
  not retired (retired -> `400`).

## Lists and filters

`GET /api/{collection}?field=value` filters work on every field, including derived ones.
Integers and references compare as numbers (`?asset=3`), booleans as `true`/`false`, and the
value `null` matches fields whose value is `null` (`?assignee=null`). Several filters combine with
AND. A filter on a field the collection does not have -> `400`.

## User interface

As in CONTRACT.md. On `GET /ui/work_orders/{id}` an action form is shown when the caller may run
that action on the order right now (permission and state; the `technician` parameter of `assign`
is not considered). Create forms: `/ui/staff/new` and `/ui/assets/new` for supervisors only;
`/ui/work_orders/new` for every user, with exactly the inputs `asset`, `title`, `description`
and `priority`.
