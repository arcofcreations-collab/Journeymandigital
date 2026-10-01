# Maintenance work orders

A facilities team at three sites tracks its staff, the assets it maintains and the work orders
raised against those assets. Requesters raise orders, supervisors assign them to technicians,
technicians start and complete them. Flask 3 + SQLite (stdlib `sqlite3`) + Jinja2. External
behaviour follows `spec/CONTRACT.md` and `spec/apps/maintenance.md`.

## Layout

```
app_entry.py              create_app() -> WSGI app bound to ./data.db (the contract's entry point)
data.db                   committed database: fully migrated + seed data, nothing else
seed.py                   rebuilds data.db from scratch (migrations + seed_data.json)
seed_data.json            starting records (ids are preserved)
maintenance_app/
  __init__.py             app factory: config, migrations, blueprints, error handlers
  db.py                   per-request connection, transaction(), migration runner
  migrations/NNNN_*.sql   schema migrations, applied in order and recorded in schema_version
  auth.py                 X-User -> staff record (401), X-Now -> request clock; RequestContext
  errors.py               ValidationError/Forbidden/NotFound/Conflict/... and their rendering
  validation.py           vocabulary (roles, statuses, ...) and request-body/action-parameter checks
  repository.py           all SQL; returns API-shaped dicts (asset_id column -> "asset" field)
  permissions.py          who may do what (pure functions of user + record + asset)
  services.py             business rules, derived fields and the work order workflow
  filters.py              ?field=value list filtering
  routes_api.py           /api/... JSON endpoints (thin: parse, call service, respond)
  routes_ui.py            /ui/... HTML pages and their form handlers
  templates/              Jinja templates, one folder per collection
tests/                    pytest suite using harness/accept_client.py
```

### Request flow

`auth.load_request_context` runs before routing for every request, so a missing or unknown
`X-User` is a 401 even for unknown URLs. Route handlers call one service function with the
`RequestContext` (`ctx.user`, `ctx.now`, `ctx.today`). Each service checks, in the contract's
precedence order:

1. the record exists, else `NotFound` (404)
2. `permissions.*` allows the caller, else `Forbidden` (403)
3. the work order's status (or the asset's open orders, or existing references) allows the
   operation, else `Conflict` (409)
4. the input is valid (`validation.clean_*`, then uniqueness/reference checks), else `ValidationError` (400)

Writes run inside `with transaction():` (`BEGIN IMMEDIATE` … `COMMIT`, rolled back on any
exception), so a failed action changes nothing and emits no outbox message. Errors are rendered
by `errors.py`: JSON `{"error", "message", "fields"}` under `/api`, an HTML error page with the
same status under `/ui`.

### Derived fields

| Field | Where |
|---|---|
| `assets.open_orders` | SQL sub-select in `repository._ASSET_SELECT` (counts `validation.UNFINISHED_STATUSES`) |
| `work_orders.due_date` | `services.due_date` (`created_at` date + `services.DUE_DAYS[priority]`) |
| `work_orders.overdue` | `services.present_work_order` (unfinished and `ctx.today > due_date`) |

Derived fields are part of the API records, so list filters (`?overdue=true`, `?open_orders=0`)
work on them too.

### Work order workflow

```
open --assign--> assigned --start--> in_progress --complete--> completed
                 assigned --assign--> assigned               (re-assignment)
open | assigned | in_progress --cancel--> cancelled          (a non-supervisor requester: only from open)
```

| Rule | Location |
|---|---|
| transitions and timestamps | `services.assign_/start_/complete_/cancel_work_order` |
| who may run an action, from which statuses | `services._authorize_<action>` (+ `permissions.py`, `*_STATUSES` constants) |
| technician eligibility for `assign` | `services._assignment_problem` |
| outbox messages `assignment`, `work_completed` | `services.assign_work_order`, `services.complete_work_order` |
| who can read/create/edit an order | `permissions.can_read_work_order`, `can_create_work_order_for`, `can_edit_work_order` |
| PATCH status rules | `services._authorize_edit` |
| fields clients may set / never set | `validation.WORK_ORDER_CREATABLE/EDITABLE/READ_ONLY`, `STAFF_WRITABLE`, `ASSET_WRITABLE` |
| actions shown on the detail page | `services.work_order_actions` (runs the same `_authorize_<action>` checks) |

To add an action: write `_authorize_<name>` and `<name>_work_order` in `services.py`, add it to
`services.WORK_ORDER_ACTIONS`, add an API route and a UI route, and a `data-action` form in
`templates/work_orders/detail.html`.

## Running the tests

From the workspace root (the tests find `harness/` relative to this directory):

```
python -m pytest apps/maintenance/tests -q
# or, as the evaluators run it:
cd harness && ACCEPT_TARGET=../apps/maintenance python -m pytest ../apps/maintenance/tests -q
```

Every test gets a fresh copy of this directory via `accept_client.fresh_app()`, so tests may
mutate data freely; the committed `data.db` is never touched. Tests talk only HTTP (through the
WSGI app); only the migration tests open the copied database file directly.

To run the app locally (send `X-User` with each request):

```
cd apps/maintenance && flask --app app_entry:create_app run
curl -H 'X-User: sofia' localhost:5000/api/work_orders
```

## Changing the schema: adding a migration

1. Add `maintenance_app/migrations/NNNN_short_name.sql` with the next number
   (e.g. `0002_add_asset_location.sql`). Names must match `^\d{4}_[a-z0-9_]+\.sql$`.
2. Write plain SQLite DDL/DML. Don't add `BEGIN`/`COMMIT`: the runner wraps each file in a
   transaction together with its `schema_version` row, so a failing migration leaves nothing behind.
   (For changes SQLite's `ALTER TABLE` can't do, e.g. altering a CHECK constraint, use the
   create-copy-drop-rename recipe.)
3. Update `repository.py` (SELECT lists, row → dict mapping, INSERT/UPDATE), `validation.py`
   (writable/read-only fields and checks), `services.py` (`*_FIELDS` tuples used for filtering,
   rules), the templates (detail `data-field`, list columns, `new.html` inputs) and `seed.py` if needed.
4. Apply it to the committed database: `create_app()` applies pending migrations on startup,
   so starting the app once is enough; or rebuild from scratch with `python seed.py`.
   Commit the updated `data.db`.
5. Add tests.

Migrations never get edited after they are committed; fix forward with a new file.

## Interpretations of the spec

* Sending `id`, a derived field (`open_orders`, `due_date`, `overdue`), a system-managed field
  (`status`, `requested_by`, `created_at`, `assignee`, …), `asset` in a work order PATCH, or an
  unknown field → 400 (after any 403/409 that applies). Unknown `?field=` filters → 400.
  Filters on null match `null` (or an empty value).
* Optional booleans (`active`, `retired`) default when omitted; an explicit `null` is a 400.
  `description` accepts any string or `null`.
* The requester's PATCH 403 applies to sending `priority` at all (even unchanged). A staff member
  who is both a supervisor and the requester follows the supervisor rules (PATCH and cancel).
* Retiring an asset: the 409 check runs when the body sets `retired` to `true` and the asset has
  unfinished orders, before other validation (409 beats 400).
* `start`/`complete` are for the current assignee only (supervisors get 403); an unassigned
  order cannot be started by anyone (403). Action parameter bodies with unknown keys → 400.
* Re-assigning an `assigned` order emits a new `assignment` message, also for the same technician.
* On creation, the own-site 403 applies when `asset` is the integer id of an existing asset
  (retired or not); any other `asset` value is a 400.
* The detail page's `data-field` elements cover every field including derived ones; the `id` is
  shown in the heading. The `assign` form lists the eligible technicians; it is shown whenever
  the caller may assign right now, even if no technician is eligible.
* Invalid `X-Now` → 400. Routing errors map to `not_found` (404) or `method_not_allowed` (405).
