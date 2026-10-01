# Maintenance work orders

A facilities team at three sites tracks its staff, the assets it maintains and the work orders
raised against those assets. Requesters raise orders, supervisors assign them to technicians,
technicians start and complete them. Flask 3 + SQLite (stdlib `sqlite3`) + Jinja2, plain explicit
code. External behaviour: `spec/CONTRACT.md` and `spec/apps/maintenance.md` (when you only have this
directory: the contract rules you need are repeated in "Error precedence" and "UI conventions").

This README is meant to be the only thing you read before changing the app. Typical loop:

```
python dev.py overview        # 1. live map: schema, routes + their checks in order, users, samples
                              #    (also snapshots files + data.db for step 6, once per change)
# 2. edit, following a recipe below
python dev.py call POST /api/work_orders/78/assign --as sofia --body '{"technician": 10}'  # 3. try it
python dev.py check           # 4. tests + data.db checks + contract/UI scan + diff from the pinned state
python dev.py pin             # 5. after reviewing that diff: accept it (tests/pinned_state.json), check again
python dev.py notes           # 6. CHANGE_NOTES.md draft: files, migrations, data and behaviour diff, check result
```

`dev.py` never modifies `data.db` except `python dev.py migrate`. `.dev/` (snapshot, last check)
and `CHANGE_NOTES.md` are tooling output; `tests/pinned_state.json` is written only by `pin`. The
snapshot is retaken automatically when a new change starts (app copied to a new directory, or the
previous change's CHANGE_NOTES.md removed); `python dev.py snapshot` forces it.

## 1. Architecture map

| File | Owns |
|---|---|
| `app_entry.py` | contract entry point `create_app()` bound to `./data.db` (don't change) |
| `maintenance_app/__init__.py` | app factory: runs pending migrations, registers blueprints, `display` filter |
| `maintenance_app/db.py` | per-request connection, `transaction()`, migration runner |
| `maintenance_app/migrations/NNNN_*.sql` | schema **and data** changes, applied in order (`schema_version` table) |
| `maintenance_app/auth.py` | `X-User` → staff record (401), `X-Now` → `ctx.now` / `ctx.today` / `ctx.now_text` (400 if malformed); `ctx.role` |
| `maintenance_app/errors.py` | `ValidationError` 400, `Unauthenticated` 401, `Forbidden` 403, `NotFound` 404, `Conflict` 409 → JSON or HTML error page |
| `maintenance_app/validation.py` | vocabulary (`STAFF_ROLES`, `ASSET_CRITICALITIES`, `WORK_ORDER_PRIORITIES`, `WORK_ORDER_STATUSES`, `UNFINISHED_STATUSES`) and body checks `clean_*`, settable/read-only tuples |
| `maintenance_app/permissions.py` | **who** may do what: pure `can_*(user, record, asset)` → bool (403 only); `is_supervisor`, `is_technician`, `is_requester_of`, `is_assignee_of` |
| `maintenance_app/repository.py` | **all SQL**; row → API dict (`asset_id` → `"asset"`, `requested_by_id` → `"requested_by"`, `assignee_id` → `"assignee"`); `assets.open_orders` sub-select |
| `maintenance_app/services.py` | one function per operation, checks in precedence order, `_authorize_<action>` (403+409) used by both API and UI, state constants `*_STATUSES`, `DUE_DAYS`, `present_work_order` (due_date/overdue), outbox, `*_FIELDS` filter tuples |
| `maintenance_app/filters.py` | `?field=value` exact-match filtering on API-shaped records (derived fields too) |
| `maintenance_app/routes_api.py` | `/api/...`: thin handlers → one service call each |
| `maintenance_app/routes_ui.py` | `/ui/...`: pages + form handlers (form strings → JSON-like values → same services) |
| `maintenance_app/templates/<collection>/{list,detail,new}.html` | contract markup (`data-id`, `data-field`, `data-action`, `data-create`); `_macros.html` `field()`; nav in `base.html` |
| `seed.py`, `seed_data.json` | rebuild data.db = migration 0001 + seed + all later migrations (seed file is frozen at 0001) |
| `tests/` | pytest through `harness/accept_client.py` (`app` and `seed` fixtures in `conftest.py`) |
| `dev.py` | developer tool (this README's commands) |

### Where every collection, action, permission and validation lives

| | staff (the users) | assets | work_orders | `_outbox` |
|---|---|---|---|---|
| table | `staff` | `assets` | `work_orders` (`asset_id`, `requested_by_id`, `assignee_id`; CHECKs on priority/status/labor) | `outbox` |
| row → dict | `repository._staff` | `repository._asset` (+`open_orders` in `_ASSET_SELECT`) | `repository._work_order`; `due_date`/`overdue` added by `services.present_work_order` | `list_outbox_messages` |
| writes (SQL) | `insert_staff`, `update_staff`, `delete_staff` | `insert_asset`, `update_asset`, `delete_asset` | `insert_work_order(values, requested_by, created_at)` (status `open`), `update_work_order`, `mark_work_order_assigned/started/completed/cancelled` | `add_outbox_message` |
| reference checks (409 on delete) | `staff_has_work_orders` | `asset_has_work_orders`; retire blocked by `open_orders > 0` | – (delete always 403) | – |
| validation | `clean_staff`, `STAFF_WRITABLE`, `STAFF_ROLES` | `clean_asset`, `ASSET_WRITABLE`, `ASSET_READ_ONLY`, `ASSET_CRITICALITIES` | `clean_work_order` (`WORK_ORDER_CREATABLE` / `EDITABLE` / `READ_ONLY`, `WORK_ORDER_PRIORITIES`); `clean_assign_params`, `clean_complete_params`, `clean_cancel_params`, `clean_no_params` | – |
| DB-dependent 400s | `_ensure_username_free` | `_ensure_tag_free` | asset exists / not retired (`create_work_order`); technician eligibility `_assignment_problem` | – |
| permissions | `can_read_staff`, `can_manage_staff` | `can_read_asset`, `can_manage_assets` | `can_read_work_order(user, order, asset)`, `can_create_work_order`, `can_create_work_order_for(user, asset)`, `can_edit_work_order(user, order, fields)` (+`WORK_ORDER_SUPERVISOR_ONLY`), `can_delete_work_order`, `can_assign_work_order`, `can_work_on_work_order`, `can_cancel_work_order` | any authenticated user |
| services | `list/get/create/update/delete_staff`, `ensure_can_create_staff` | `list/get/create/update/delete_asset`, `ensure_can_create_asset` | `list/get/create/update/delete_work_order`, `_authorize_edit`, `_authorize_assign/start/complete/cancel`, `WORK_ORDER_ACTIONS`, `work_order_actions`, `assign/start/complete/cancel_work_order`, `eligible_technicians` | `list_outbox` |
| filter fields | `services.STAFF_FIELDS` | `ASSET_FIELDS` | `WORK_ORDER_FIELDS` | `OUTBOX_FIELDS` |
| UI | `staff/list,detail,new` | `assets/list,detail,new` | `work_orders/list,detail` (assign+technician select, start, complete+resolution/labor, cancel+reason), `work_orders/new` (own-site assets) | – |

Workflow (`services.py`; statuses allowed per action are the `*_STATUSES` constants):

```
open --assign--> assigned --start--> in_progress --complete--> completed
                 assigned --assign--> assigned               (re-assignment)
open | assigned | in_progress --cancel--> cancelled          (a non-supervisor requester: only from open)
```

Outbox: `assign_work_order` emits `assignment` `{"work_order", "asset", "technician"}`;
`complete_work_order` emits `work_completed` `{"work_order", "asset", "technician", "labor_minutes"}`.
A work order's site is its asset's `site`; requesters/technicians create orders only for own-site
assets (403 before any 400, via `_existing_asset_in(data)` on the raw body); technicians read
own-site orders. `python dev.py overview` prints all of this live, with line numbers and each
route's checks in order.

## 2. Error precedence and how it is implemented

Contract order when several apply: **401 → 404 → 403 → 409 → 400**. A record the caller may not read
is 403 on direct access and absent from lists (and from UI lists).

| Status | Where it comes from |
|---|---|
| 401 | `auth.load_request_context` is a `before_request` hook: missing/unknown `X-User` fails before routing, so even unknown URLs give 401 |
| 404 | unknown URL/collection/action: Flask routing (`errors._HTTP_ERRORS`); unknown record: `services._load_<x>()` is the **first** call inside each service |
| 403 | `permissions.can_*`; for work-order actions inside `_authorize_<action>`; create endpoints call `ensure_can_create_<x>(ctx)` (and the own-site check) before validating the body |
| 409 | `_require_status(order, <X>_STATUSES, message)` inside `_authorize_*`; retire with open orders; `*_has_work_orders` on delete |
| 400 | `validation.clean_*` runs **after** 403/409, then database-dependent checks (asset exists/retired, technician eligibility, uniqueness) |

Rules that keep this working:
* `routes_api._body()` never fails: an empty body is `{}`, malformed JSON becomes a non-dict marker that
  `validation.require_object` rejects with 400 — so a bad body still gets 404/403/409 first.
* A 403/409 that depends on a body value reads the raw body defensively before `clean_*` raises:
  see `update_asset` (`data.get("retired") is True and asset["open_orders"] > 0` → 409),
  `create_work_order` (`_existing_asset_in(data)` → own-site 403), `update_work_order`
  (`can_edit_work_order(user, order, data.keys())`).
* Each `_authorize_<action>(user, order)` raises 403/409 and is the single source for both the API
  action and `work_order_actions` (the forms on the detail page), so they cannot drift.
* Writes run in `with transaction():` (`BEGIN IMMEDIATE` … `COMMIT`, rollback on any exception):
  raise anywhere inside and nothing (rows, outbox messages) is kept — all-or-nothing for free.
* House defaults used so far: `id`, derived, system-managed and unknown fields in a create/PATCH body →
  400 (`*_READ_ONLY`); unknown `?filter` field → 400; a read-only collection answers POST → 403 and
  PATCH/DELETE → 404 for an unknown id, else 403; an action body with unexpected keys → 400; deleting
  a record other rows reference → 409 (never let SQLite raise: an IntegrityError is a 500).

## 3. UI conventions (contract)

* `GET /ui/<c>`: `<tr data-id="{id}">` per **readable** record (same set and order as the API list).
* `GET /ui/<c>/<id>`: one `data-field="{field}"` element per visible API field (derived ones too),
  text = the value as `display` renders it (`true`/`false`, empty for null); use
  `{{ field("name", record.name) }}` from `_macros.html`. One `<form data-action="{action}">` per
  action the caller may run **right now** (`services.work_order_actions`).
* `GET /ui/<c>/new`: `<form data-create="{c}">` with one `input/select/textarea name="{field}"` per
  field the caller may set on create; 403 (via `ensure_can_create_<x>`) if they may not create.
* Forms post to `/ui/...` handlers in `routes_ui.py`, which convert strings with `_text`,
  `_optional_text`, `_integer`, `_boolean` (unconvertible values pass through so validation
  answers 400) and redirect (303, `_redirect_to_work_order`) to the detail page.

## 4. Recipes

Each recipe lists every place to touch. `python dev.py check` catches most omissions (missing
`data-field`, unfilterable field, UI form shown when the API refuses or vice versa, missing UI
handler, 500 on delete, data.db not migrated or not reproducible).

### 4.1 Add a stored field (with migration and backfill)
1. `python dev.py new-migration add_asset_location` → edit the SQL:
   `ALTER TABLE assets ADD COLUMN location TEXT;` then `UPDATE ... SET ... WHERE ...;` for the
   backfill (`NOT NULL` needs a `DEFAULT`). Reference column: `x_id INTEGER REFERENCES xs (id)` +
   `CREATE INDEX`. Changing a CHECK (priority/status values) → table rebuild (4.6).
2. `repository.py`: add the column to `_ASSET_SELECT` / `_WORK_ORDER_SELECT`, the key to `_asset()` /
   `_work_order()` (bool: `bool(row[...])`; reference: `row["x_id"]` under the API name), and to the
   insert / `update_*` `columns` map if clients set it, or to the `mark_work_order_*` function of the
   action that sets it.
3. `validation.py`: client-settable → add to `ASSET_WRITABLE` / `WORK_ORDER_CREATABLE` /
   `WORK_ORDER_EDITABLE` and check it in `clean_*`; set by the system → add to `*_READ_ONLY`
   (→ 400 "cannot be set directly"). Optional booleans: `_clean_boolean_with_default`.
4. `services.py`: add the name to `ASSET_FIELDS` / `WORK_ORDER_FIELDS` (filtering) and set it where
   the rule says.
5. Templates: `detail.html` `{{ field("location", asset.location) }}`; `list.html` column (optional);
   `new.html` input if settable on create, and the converter in `routes_ui.create_*`.
6. `python dev.py migrate`, `python dev.py dbdiff` (confirm only the intended data changed), add
   tests, `python dev.py check`.

Derived field: SQL sub-select in the `_SELECT` (stored data only, like `open_orders`; rounding with
`ROUND(x, 2)`), or computed in `present_work_order` (needs the clock, like `overdue`); add it to
`*_FIELDS`, `*_READ_ONLY` and the detail template. A stored field that becomes derived: drop the column
in a migration (after backfilling what replaces it) and compute it instead.

### 4.2 Add a collection
1. Migration: `CREATE TABLE things (id INTEGER PRIMARY KEY AUTOINCREMENT, ..., work_order_id INTEGER
   NOT NULL REFERENCES work_orders (id))` + indexes; required initial rows with their fixed ids.
2. `repository.py`: `_THING_SELECT`, `_thing(row)`, `list_things`, `get_thing`, insert/update/delete,
   `*_taken` for unique fields, and `<parent>_has_things` queries for 409s.
3. **Existing deletes**: `delete_staff` (`staff_has_work_orders`) and `delete_asset`
   (`asset_has_work_orders`) must also refuse (409) when the new rows reference them — otherwise
   SQLite raises and the API answers 500.
4. `validation.py`: `THING_WRITABLE`, `THING_READ_ONLY`, `clean_thing(data, *, partial)`.
5. `permissions.py`: `can_read_thing`, `can_manage_things` (or finer). "Readable by whoever can read
   its work order" → `can_read_work_order(user, order, asset)` with the order and its asset.
6. `services.py`: `THING_FIELDS`; `list_things` (filter by permission, then `apply_filters`),
   `get_thing` (`_load_thing` 404 → 403), `ensure_can_create_thing`, `create_thing`, `update_thing`,
   `delete_thing` — copy the assets functions, keep the check order.
7. `routes_api.py`: the five routes (copy the assets block). Read-only collection (history): POST →
   `Forbidden`; PATCH/DELETE → `_load_thing` then `Forbidden`.
8. `routes_ui.py` + `templates/things/{list,detail,new}.html` + nav link in `base.html`.
9. Tests: new `tests/test_maintenance_things.py`.

### 4.3 Add an action `POST /api/work_orders/<id>/<action>`
1. `services.py`: `_authorize_<action>(user, order)` — permission (403) then
   `_require_status(order, <ACTION>_STATUSES, "...")` and any other 409 that does not depend on the
   body; register it in `WORK_ORDER_ACTIONS` (this alone makes the UI form appear exactly when allowed).
2. `services.py`: `def <action>_work_order(ctx, work_order_id, params):` inside `with transaction():` —
   `_load_work_order` (404) → `_authorize_<action>(ctx.user, order)` → `validation.clean_<action>_params`
   (400) → checks that need valid params (DB lookups → 400; a 409 that the request orders after the
   400, like a workload cap on the chosen technician) → `repository.mark_*`/inserts → outbox →
   `return present_work_order(ctx, repository.get_work_order(work_order_id))`.
3. `permissions.py`: the `can_*` function; `validation.py`: `clean_<action>_params` (unknown keys → 400).
4. `routes_api.py`: `@bp.post("/work_orders/<int:work_order_id>/<action>")` with `_body()`.
5. UI: `<form data-action="<action>" ...>` block in `work_orders/detail.html` (inputs for its
   parameters; extra data for selects comes from `show_work_order`) and a POST handler in
   `routes_ui.py` (`_form_values({...})`, `_redirect_to_work_order`).
6. Tests: success (+ returned record, outbox payload), each 403/409/400 and one precedence case per
   pair, all-or-nothing on failure (outbox unchanged), UI form shown/hidden per user.

Action on another collection (e.g. `schedules/<id>/generate`): same pattern with that collection's
`_load_*`, its own `_authorize_*` functions and `<THING>_ACTIONS` dict + `<thing>_actions(ctx, thing)`.
Removing an action: delete its route(s), `_authorize_*`, `WORK_ORDER_ACTIONS` entry, form, tests;
the URL then gives 404 automatically.

### 4.4 Change a permission
Edit the `can_*` function in `permissions.py` (pure: user + records; services pass the order's
`asset` where the site matters). Check every caller (`grep -n "can_<name>" maintenance_app/*.py`):
`list_work_orders` / `_ensure_can_read`, writes, `_authorize_*` (API + UI forms), `ensure_can_create_*`
(`/ui/<c>/new`), `routes_ui.new_work_order` (asset choices). Site-scoped rules: compare
`user["site"]` with `asset["site"]` (orders) or the record's own `site` (assets). A new role: CHECK
constraint via table rebuild (4.6), `validation.STAFF_ROLES`, an `is_<role>` helper, every `can_*`
that tests `is_supervisor`.

### 4.5 Change validation
`validation.py`: enums are module constants used by `clean_*` and the UI selects; field checkers
(`required_text`, `optional_text`, `choice`, `boolean`, `record_id`, `positive_integer`,
`is_integer`) raise `FieldInvalid`, collected per field. Rules that need other records (the asset's
criticality, technician eligibility) go in the service after `clean_*`. Keep 400 last: a rule that
must win over 400 is a 409/403 and goes before `clean_*`. The `work_orders` table has CHECKs
(priority, status, labor_minutes) — changing those values needs a table rebuild.

### 4.6 Data migration (backfill, fixed records, rebuild)
* All data changes go in the migration SQL. **Never edit `seed_data.json`** (it is the 0001 baseline;
  `seed.py` replays the migrations over it, and `check` verifies data.db equals that rebuild).
* The runner wraps each file in one transaction with its `schema_version` row (no BEGIN/COMMIT) and
  runs it with foreign keys OFF, then `PRAGMA foreign_key_check` must be clean or it rolls back.
* Table rebuild (new CHECK values, drop/retype a column):
  `CREATE TABLE work_orders_new (...)`; `INSERT INTO work_orders_new (cols) SELECT ..., CASE priority
  WHEN 'urgent' THEN 'p1' ... END, ... FROM work_orders;` `DROP TABLE work_orders;`
  `ALTER TABLE work_orders_new RENAME TO work_orders;` then recreate `work_orders_asset_id`,
  `work_orders_requested_by_id`, `work_orders_assignee_id`. Child tables' `REFERENCES work_orders` keep
  working. If rows were ever deleted, restore the counter: `UPDATE sqlite_sequence SET seq = <n> WHERE
  name = 'work_orders';`. Plain columns can also go with `ALTER TABLE t DROP COLUMN x;`.
* Fixed ids: insert them explicitly; AUTOINCREMENT continues above the highest id. Rows derived from
  existing rows with ids 1, 2, 3...: `INSERT INTO t (id, ...) SELECT ROW_NUMBER() OVER (ORDER BY
  w.id), ... FROM work_orders w WHERE ...`.
* `python dev.py migrate` then `python dev.py dbdiff` shows per table: added/removed columns with value
  counts, +/-/~ rows. Made a mistake? Fix the SQL and `python seed.py` (data.db is reproducible;
  recorded apply times of migrations data.db already had are kept).
* Existing tests that compare with `seed_data.json` (`test_seed_data_is_loaded_with_same_ids`,
  read-rule tests that derive expectations from the seed) need updating when the migration adds or
  changes fields or roles.

### 4.7 Outbox message
`repository.add_outbox_message("<channel>", {payload dict}, ctx.now_text)` inside the action's
`with transaction():` after all checks, so failures emit nothing. Payload keys exactly as the
request specifies. Several messages: emit in the specified order. Test with `GET /api/_outbox`
(outbox starts empty in the seed).

### 4.8 UI form
* Create form: `templates/<c>/new.html` `<form data-create="<c>">` with inputs named exactly as the
  API fields the caller may set; `routes_ui.create_<x>` lists the same fields with converters. Selects
  for enums (`validation.*`) and references (pass records from the view, e.g. the own-site assets in
  `new_work_order`).
* Action form: see 4.3 step 5.

### 4.9 Withdraw a feature (remove a field, status, action or collection)
* Data first: a migration that moves existing rows to the surviving representation exactly as the
  request says (e.g. a removed status → `UPDATE ... SET status = ... WHERE status = ...`), then drops
  the column (`ALTER TABLE t DROP COLUMN x;` for a plain column, otherwise a rebuild, 4.6) or table.
* Code: remove the field from `_SELECT` / row mapping / writes (`repository.py`), from `*_WRITABLE` /
  `*_READ_ONLY` and `clean_*` (`validation.py`; it then becomes an unknown field → 400), from
  `*_FIELDS` (filter → 400), from the templates and `routes_ui.py` converters; remove routes, service
  functions, `*_actions` entries and forms of a removed action (its URL then answers 404 after 401).
  `grep -rn "<name>" maintenance_app tests` must come back empty (apart from the migrations).
* Restore every rule the feature had changed to the behaviour the request describes, and delete or
  rewrite the tests of the withdrawn feature.

## 5. Verifying a change

* `python dev.py check` — the whole verification, about 4-6 seconds:
  1. the test suite (`tests/`), failures reported as test name + location + the assertion lines
     (`--full` for tracebacks, `-k EXPR` to select);
  2. data.db: no pending migration, equal to a fresh rebuild (seed + migrations; schema, rows,
     AUTOINCREMENT counters), integrity and foreign keys OK, migration files well-formed; every
     counter an integer >= the highest id and never lowered by a migration (restore it after a
     rebuild); no partial-index/trigger predicate compares a column with a value its CHECK forbids
     (WARN for such a comparison anywhere in a migration);
  3. contract/UI scan for **every user**: UI list rows = API list ids; detail pages have a
     `data-field` per API field with the displayed value; every field works as `?field=` filter;
     each action form is shown exactly when the API call (body `{}`) is not 403/409; `/ui/<c>/new`
     is 200 exactly when `POST /api/<c>` is not 403; no 5xx anywhere, including DELETE of every record.
     Scan findings are WARN (heuristics: an action whose 409 depends on its parameters, like a
     workload cap on the chosen technician, can legitimately differ — say why in your notes); test
     failures, data.db problems and 5xx are FAIL.
  4. the **pinned state** `tests/pinned_state.json`: every user x every record: GET, every action
     `POST {}`, and on a sample `PATCH {}`/DELETE; lists and `POST /api/<c> {}` per user (status, plus
     a response/outbox hash for 2xx); records as the best reader sees them; schema, AUTOINCREMENT
     counters and a hash per stored row. Any difference is a FAIL listed per route and status
     (`POST /api/<c>/<id>/<action> {}: 403 -> 409 x12 (user c/id; ...)`, `records ...: field x added`,
     `sqlite_sequence t: 80 -> 81`). Read it as the change's observable effect: every line must be
     something the request asks for (or follows from it), and nothing the request says must remain
     intact may appear. Then `python dev.py pin` (`pin --diff` shows the full list without accepting)
     and check again. `notes` copies the accepted diff into CHANGE_NOTES.md.
* `python dev.py call METHOD PATH --as USER [--body JSON] [--now TS]` — one request on a throwaway
  copy with pending migrations applied; prints the JSON, or for `/ui` pages the rows/fields/forms the
  contract sees, then the database rows the request changed (`+`/`-`/`~` per table, outbox included).
  `--form k=v` posts a UI form. `--steps "sofia POST /api/work_orders/78/assign {\"technician\": 10}"
  "ravi POST /api/work_orders/78/start"` runs a sequence on one copy (each step `USER METHOD PATH [JSON]`).
* Tests: add `tests/test_maintenance_<feature>.py`; fixtures `app` (fresh copy per test) and `seed`;
  `app.get/post/patch/delete(path, body, user=..., now=...)` return `.status`, `.json`, `.text`;
  `from accept_client import parse_ui` for pages (`.rows`, `.fields`, `.actions`, `.inputs`,
  `.creates`). Migration results are checked through the API (data.db is already migrated) or by
  opening `os.path.join(app.workdir, "data.db")`. Evaluator mode:
  `cd ../../harness && ACCEPT_TARGET=../apps/maintenance python -m pytest ../apps/maintenance/tests -q`.
* What to test by hand: the pinned state already fixes every status for empty bodies and every
  record/user, so tests are needed for what it cannot see: actions and creates/PATCHes **with**
  parameters (each 400/409 that depends on them, success values), multi-step flows, outbox payloads,
  UI forms. Write them for the new behaviour, not for the unchanged matrix. Ids the request names
  ("new ids above N") deserve one test that creates a record and checks its id.
* `python dev.py notes` writes `CHANGE_NOTES.md` (changed files with +/- lines, new migrations, the
  data.db diff and the accepted pinned-state diff since the snapshot, the last check output); fill
  in the Interpretation paragraph.

### Requests that cannot all be satisfied
Some requests contain requirements that contradict each other or the contract. Do not silently
implement one side or a compromise: implement only what is consistent (often nothing), and state the
conflict and the question to ask in the notes / your report. Requests that *do* state a policy for an
apparent conflict (e.g. "existing overloads are kept") are not contradictions — follow the policy.

## 6. Interpretations of the spec (current behaviour)

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

## 7. Running

```
python -m pytest tests -q                      # the suite alone (from this directory)
flask --app app_entry:create_app run           # then: curl -H 'X-User: sofia' localhost:5000/api/work_orders
python seed.py                                 # rebuild data.db from scratch (seed + migrations)
```
