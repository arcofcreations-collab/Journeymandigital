# Expense claims

Employees submit expense claims, their manager approves or rejects them, finance pays them.
Flask 3 + SQLite (stdlib `sqlite3`) + Jinja2, plain explicit code. External behaviour:
`spec/CONTRACT.md` and `spec/apps/expenses.md` (when you only have this directory: the contract
rules you need are repeated in "Error precedence" and "UI conventions" below).

This README is meant to be the only thing you read before changing the app. Typical loop:

```
python dev.py overview        # 1. live map: schema, routes + their checks in order, users, samples
                              #    (also snapshots files + data.db for step 5)
# 2. edit, following a recipe below
python dev.py call POST /api/claims/2/approve --as omar      # 3. try requests on a throwaway copy
python dev.py check           # 4. tests + data.db rebuild check + contract/UI scan, concise output
python dev.py notes           # 5. CHANGE_NOTES.md draft: changed files, migrations, data diff, check result
```

`dev.py` never modifies `data.db` except `python dev.py migrate`. `.dev/` (snapshot, last check)
and `CHANGE_NOTES.md` are tooling output.

## 1. Architecture map

| File | Owns |
|---|---|
| `app_entry.py` | contract entry point `create_app()` bound to `./data.db` (don't change) |
| `expenses_app/__init__.py` | app factory: runs pending migrations, registers blueprints, `display` filter |
| `expenses_app/db.py` | per-request connection, `transaction()`, migration runner |
| `expenses_app/migrations/NNNN_*.sql` | schema **and data** changes, applied in order (`schema_version` table) |
| `expenses_app/auth.py` | `X-User` → employee (401), `X-Now` → `ctx.now` / `ctx.today` / `ctx.now_text` (400 if malformed); `ctx.role` |
| `expenses_app/errors.py` | `ValidationError` 400, `Unauthenticated` 401, `Forbidden` 403, `NotFound` 404, `Conflict` 409 → JSON or HTML error page |
| `expenses_app/validation.py` | body shape/type checks: `clean_<collection>(data, partial=)`, `clean_<action>_params`, writable/read-only tuples, enums, `MAX_CLAIM_AMOUNT` |
| `expenses_app/permissions.py` | **who** may do what: pure functions `can_*(user, record, claimant)` → bool (403 only); `is_finance`, `is_manager_of` |
| `expenses_app/repository.py` | **all SQL**; row → API dict (`employee_id` column → `"employee"`, `decided_by_id` → `"decided_by"`) |
| `expenses_app/services.py` | one function per operation, checks in precedence order, workflow state rules (409), outbox, `claim_actions` for the UI, `*_FIELDS` filter tuples |
| `expenses_app/filters.py` | `?field=value` exact-match filtering on API-shaped records |
| `expenses_app/routes_api.py` | `/api/...`: thin handlers → one service call each |
| `expenses_app/routes_ui.py` | `/ui/...`: pages + form handlers (form strings → JSON-like values → same services) |
| `expenses_app/templates/<collection>/{list,detail,new}.html` | contract markup (`data-id`, `data-field`, `data-action`, `data-create`); `_macros.html` `field()`; nav in `base.html` |
| `seed.py`, `seed_data.json` | rebuild data.db = migration 0001 + seed + all later migrations (seed file is frozen at 0001) |
| `tests/` | pytest through `harness/accept_client.py` (`app` and `seed` fixtures in `conftest.py`) |
| `dev.py` | developer tool (this README's commands) |

### Where every collection, action, permission and validation lives

| | employees (the users) | claims | `_outbox` |
|---|---|---|---|
| table | `employees` (`manager_id` → employees) | `claims` (`employee_id`, `decided_by_id` → employees; CHECKs on amount/category/status) | `outbox` (`payload` JSON text) |
| row → dict | `repository._employee` | `repository._claim` | `repository.list_outbox_messages` |
| writes (SQL) | `insert_employee`, `update_employee`, `delete_employee` | `insert_claim(employee_id, values)` (status `draft`), `update_claim`, `delete_claim`, `mark_claim_submitted`, `mark_claim_decided`, `mark_claim_paid` | `add_outbox_message(channel, payload, ctx.now_text)` |
| reference checks (409 on delete) | `employee_is_referenced` (claims, decisions, reports) | – | – |
| validation | `clean_employee`, `EMPLOYEE_WRITABLE`, `EMPLOYEE_ROLES` | `clean_claim`, `CLAIM_WRITABLE`, `CLAIM_READ_ONLY` (→ "cannot be set directly"), `CLAIM_CATEGORIES`, `claim_amount` (`MAX_CLAIM_AMOUNT`); `clean_reject_params`, `clean_no_params` | – |
| DB-dependent 400s | `services._check_employee_references` (unique username, manager exists, no reporting loop via `_is_same_or_reports_to`) | – | – |
| permissions | `can_read_employee`, `can_manage_employees` | `can_create_claim`, `can_read_claim(user, claim, claimant)`, `can_edit_claim`, `can_submit_claim`, `can_decide_claim(user, claimant)`, `can_pay_claim` | any authenticated user |
| services | `list/get/create/update/delete_employee`, `ensure_can_create_employee` | `list/get/create/update/delete_claim`, `ensure_can_create_claim`, `submit/approve/reject/pay_claim`, `claim_actions`, `_claimant(claim)`, `_require_status` | `list_outbox` |
| filter fields | `services.EMPLOYEE_FIELDS` | `CLAIM_FIELDS` | `OUTBOX_FIELDS` |
| UI | `employees/list,detail,new` (manager select) | `claims/list,detail` (submit/approve/reject+reason/pay forms), `claims/new` | – |

Workflow (`services.py`):

```
draft --submit (owner)--> submitted --approve (claimant's manager)--> approved --pay (finance)--> paid
                                    \--reject (claimant's manager, {"reason"})--> rejected
```

Outbox: `pay_claim` emits `payment` `{"claim", "employee", "amount"}`. "Manager" always means the
claimant's current direct `manager` (`permissions.is_manager_of(user, claimant)`); services look the
claimant up with `_claimant(claim)` (lists build an `employees` map once).
`python dev.py overview` prints all of this live, with line numbers and each route's checks in order.

## 2. Error precedence and how it is implemented

Contract order when several apply: **401 → 404 → 403 → 409 → 400**. A record the caller may not read
is 403 on direct access and absent from lists (and from UI lists).

| Status | Where it comes from |
|---|---|
| 401 | `auth.load_request_context` is a `before_request` hook: missing/unknown `X-User` fails before routing, so even unknown URLs give 401 |
| 404 | unknown URL/collection/action: Flask routing (`errors._HTTP_ERRORS`); unknown record: `services._load_<x>()` is the **first** call inside each service |
| 403 | `permissions.can_*` checked right after loading; create endpoints call `ensure_can_create_<x>(ctx)` before reading the body |
| 409 | state checks after permissions: `_require_status(claim, "<status>", message)`, `employee_is_referenced` |
| 400 | `validation.clean_*` runs **after** 403/409, then database-dependent checks (`_check_employee_references`) |

Rules that keep this working:
* `routes_api._body()` never fails: an empty body is `{}`, malformed JSON becomes a non-dict marker that
  `validation.require_object` rejects with 400 — so a bad body still gets 404/403/409 first.
* A permission or 409 that depends on a body value must read the raw body defensively
  (`isinstance(data, dict)`) **before** `clean_*` raises.
* Writes run in `with transaction():` (`BEGIN IMMEDIATE` … `COMMIT`, rollback on any exception):
  raise anywhere inside and nothing (rows, outbox messages) is kept — all-or-nothing for free.
* House defaults used so far: workflow/protected fields and unknown fields in a create/PATCH body → 400
  (`CLAIM_READ_ONLY`); unknown `?filter` field → 400; a read-only collection answers POST → 403 and
  PATCH/DELETE → 404 for an unknown id, else 403; an action body with unexpected keys → 400
  (`clean_no_params`); deleting a record other rows reference → 409 (never let SQLite raise: an
  IntegrityError is a 500).

## 3. UI conventions (contract)

* `GET /ui/<c>`: `<tr data-id="{id}">` per **readable** record (same set and order as the API list).
* `GET /ui/<c>/<id>`: one `data-field="{field}"` element per visible API field, text = the value as
  `display` renders it (`true`/`false`, numbers as JSON, empty for null); use
  `{{ field("name", record.name) }}` from `_macros.html`. One `<form data-action="{action}">` per
  action the caller may run **right now** (`services.claim_actions`).
* `GET /ui/<c>/new`: `<form data-create="{c}">` with one `input/select/textarea name="{field}"` per
  field the caller may set on create; 403 (via `ensure_can_create_<x>`) if they may not create.
* Forms post to `/ui/...` handlers in `routes_ui.py`, which convert strings with `_text`,
  `_optional_int`, `_number` (unconvertible values pass through so validation answers 400) and
  redirect (303) to the detail page.

## 4. Recipes

Each recipe lists every place to touch. `python dev.py check` catches most omissions (missing
`data-field`, unfilterable field, UI form shown when the API refuses or vice versa, missing UI
handler, 500 on delete, data.db not migrated or not reproducible).

### 4.1 Add a stored field (with migration and backfill)
1. `python dev.py new-migration add_claim_paid_at` → edit the SQL:
   `ALTER TABLE claims ADD COLUMN paid_at TEXT;` then `UPDATE claims SET ... WHERE ...;` for the
   backfill (`NOT NULL` needs a `DEFAULT`). Reference column: `cost_centre_id INTEGER REFERENCES
   cost_centres (id)` + `CREATE INDEX`. Changing a CHECK (e.g. a new status) → table rebuild (4.6).
2. `repository.py`: add the column to `_CLAIM_SELECT`, the key to `_claim()` (bool: `bool(row[...])`;
   reference: `row["x_id"]` under the API name), and to `insert_claim` / `update_claim` `columns` map
   if clients set it, or to the `mark_claim_*` function of the action that sets it.
3. `validation.py`: client-settable → add to `CLAIM_WRITABLE` and check it in `clean_claim`
   (`if "x" in data or not partial: with collect(errors, "x"): values["x"] = <checker>(...)`).
   Set only by the system/workflow → add to `CLAIM_READ_ONLY` (sending it → 400).
   References: check existence in the service (400 `{"field": "no such ..."}`) after 403/409.
4. `services.py`: add the name to `CLAIM_FIELDS` (filtering) and set it in the action that owns it.
5. Templates: `claims/detail.html` `{{ field("paid_at", claim.paid_at) }}`; `claims/list.html` column
   (optional); `claims/new.html` input if settable on create, and the converter in
   `routes_ui.create_claim` (`"x": _text | _number | _optional_int`).
6. `python dev.py migrate`, `python dev.py dbdiff` (confirm only the intended data changed), add
   tests, `python dev.py check`.

Derived field: compute it in SQL in `_CLAIM_SELECT` (sub-select) when it depends on stored data, or
in a `present_<x>(ctx, record)` service function when it depends on the clock; add it to
`*_FIELDS`, to `CLAIM_READ_ONLY` and the detail template.

### 4.2 Add a collection
1. Migration: `CREATE TABLE things (id INTEGER PRIMARY KEY AUTOINCREMENT, ..., claim_id INTEGER NOT NULL
   REFERENCES claims (id))` + indexes; required initial rows with their fixed ids; backfills.
2. `repository.py`: `_THING_SELECT`, `_thing(row)`, `list_things`, `get_thing`, insert/update/delete,
   `*_taken` for unique fields, and reference queries for 409s.
3. **Existing deletes**: `delete_employee` (`employee_is_referenced`) and `delete_claim` must account
   for rows that now reference them (409, or delete the children in the same transaction if the request
   says so) — otherwise SQLite raises and the API answers 500.
4. `validation.py`: `THING_WRITABLE`, `THING_READ_ONLY`, `clean_thing(data, *, partial)`.
5. `permissions.py`: `can_read_thing`, `can_manage_things` (or finer). "Readable by whoever can read
   its claim" → reuse `can_read_claim(user, claim, claimant)`.
6. `services.py`: `THING_FIELDS`; `list_things` (filter by permission, then `apply_filters`),
   `get_thing` (`_load_thing` 404 → 403), `ensure_can_create_thing`, `create_thing`, `update_thing`,
   `delete_thing` — copy the employees functions, keep the check order.
7. `routes_api.py`: the five routes (copy the employees block). Read-only collection: POST →
   `Forbidden`; PATCH/DELETE → `_load_thing` then `Forbidden`.
8. `routes_ui.py` + `templates/things/{list,detail,new}.html` + nav link in `base.html`.
9. Tests: new `tests/test_expenses_things.py`.

### 4.3 Add an action `POST /api/<c>/<id>/<action>`
1. `services.py`: `def <action>_claim(ctx, claim_id, params):` inside `with transaction():` —
   `_load_claim` (404) → `permissions.can_<...>` (403) → `_require_status` / other 409 → 
   `validation.clean_<action>_params(params)` or `clean_no_params(params)` (400) → effects
   (`repository.mark_claim_*`) → outbox → `return repository.get_claim(claim_id)`.
2. Permission function in `permissions.py`.
3. `routes_api.py`: `@bp.post("/claims/<int:claim_id>/<action>")` calling the service with `_body()`.
4. UI: extend `claim_actions(ctx, claim)` so the name appears exactly when the API call would pass
   the 403/409 checks for the caller right now (same permission function, same status/time/limit
   conditions); add `<form data-action="<action>" method="post" action="{{ url_for('ui.<action>_claim',
   claim_id=claim.id) }}">` (inputs for parameters, like `reason`) in `claims/detail.html` and a POST
   handler in `routes_ui.py` (`_form_values({...})`, redirect 303).
5. Tests: success (+ returned record, outbox payload), each 403/409/400 and one precedence case per
   pair, all-or-nothing on failure (outbox unchanged), UI form shown/hidden per user.

Time windows (`X-Now`): compare `ctx.now` with `datetime.strptime(claim["submitted_at"],
"%Y-%m-%dT%H:%M:%S")`; dates with `ctx.today` / `date.fromisoformat(...)`.

### 4.4 Change a permission
Edit the `can_*` function in `permissions.py` (pure: user + records; the service loads what it needs,
e.g. the claimant, and passes it in). Check every caller (`grep -n "can_<name>" expenses_app/*.py`):
list filters (`list_claims`), direct reads, writes, `claim_actions` (UI forms), `/ui/<c>/new`
(`ensure_can_create_*`). Rules for "every write" (e.g. inactive users) belong in one helper called by
every write path and every `ensure_can_create_*`. A new role: CHECK constraint via table rebuild
(4.6), `validation.EMPLOYEE_ROLES`, `is_<role>` helper, every `can_*`.

### 4.5 Change validation
`validation.py`: enums/limits are module constants (`EMPLOYEE_ROLES`, `CLAIM_CATEGORIES`,
`MAX_CLAIM_AMOUNT`) used by `clean_*` and the UI selects; field checkers (`required_text`, `choice`,
`optional_record_id`, `claim_amount`) raise `FieldInvalid`, collected per field. Database-dependent
rules (references, loops, totals across rows) go in the service after `clean_*`. Keep 400 last: a rule
that must win over 400 is a 409/403 and goes before `clean_*`. The `claims` table has CHECKs
(amount range, category, status) — a changed rule may need a table rebuild.

### 4.6 Data migration (backfill, fixed records, rebuild)
* All data changes go in the migration SQL. **Never edit `seed_data.json`** (it is the 0001 baseline;
  `seed.py` replays the migrations over it, and `check` verifies data.db equals that rebuild).
* The runner wraps each file in one transaction with its `schema_version` row (no BEGIN/COMMIT) and
  runs it with foreign keys OFF, then `PRAGMA foreign_key_check` must be clean or it rolls back.
* Table rebuild (new status in the CHECK, drop/retype a column, make a column NOT NULL):
  `CREATE TABLE claims_new (...)`; `INSERT INTO claims_new (cols) SELECT ... FROM claims;`
  `DROP TABLE claims;` `ALTER TABLE claims_new RENAME TO claims;` then recreate its indexes
  (`claims_employee_id`, `claims_decided_by_id`). Child tables' `REFERENCES claims` keep working.
  If rows were ever deleted, restore the counter: `UPDATE sqlite_sequence SET seq = <n> WHERE name = 'claims';`.
  Plain columns can also go with `ALTER TABLE claims DROP COLUMN x;`.
* Fixed ids: insert them explicitly; AUTOINCREMENT continues above the highest id. Backfilled history
  rows in a given order: `INSERT ... SELECT ... ORDER BY` (several sources: `UNION ALL` + `ORDER BY`).
* `python dev.py migrate` then `python dev.py dbdiff` shows per table: added/removed columns with value
  counts, +/-/~ rows. Made a mistake? Fix the SQL and `python seed.py` (data.db is reproducible).
* Existing tests that compare with `seed_data.json` (`test_seed_data_is_loaded_with_same_ids`) need
  updating when the migration adds or changes fields.

### 4.7 Outbox message
`repository.add_outbox_message("<channel>", {payload dict}, ctx.now_text)` inside the action's
`with transaction():` after all checks, so failures emit nothing. Payload keys exactly as the request
specifies; amounts as stored numbers. Several messages: emit in the specified order. Test with
`GET /api/_outbox` (outbox starts empty in the seed).

### 4.8 UI form
* Create form: `templates/<c>/new.html` `<form data-create="<c>">` with inputs named exactly as the
  API fields the caller may set; `routes_ui.create_<x>` lists the same fields with converters
  (`_number` for amounts, `_optional_int` for references). Selects for enums (`validation.*`) and
  references (pass records from the view, e.g. `managers=services.list_employees(ctx)`).
* Action form: see 4.3 step 4.

### 4.9 Withdraw a feature (remove a field, status, action or collection)
* Data first: a migration that moves existing rows to the surviving representation exactly as the
  request says (e.g. a removed status → `UPDATE ... SET status = ... WHERE status = ...`), then drops
  the column (`ALTER TABLE t DROP COLUMN x;` for a plain column, otherwise a rebuild, 4.6) or table.
* Code: remove the field from `_SELECT` / row mapping / writes (`repository.py`), from `*_WRITABLE` /
  `*_READ_ONLY` and `clean_*` (`validation.py`; it then becomes an unknown field → 400), from
  `*_FIELDS` (filter → 400), from the templates and `routes_ui.py` converters; remove routes, service
  functions, `*_actions` entries and forms of a removed action (its URL then answers 404 after 401).
  `grep -rn "<name>" expenses_app tests` must come back empty (apart from the migrations).
* Restore every rule the feature had changed to the behaviour the request describes, and delete or
  rewrite the tests of the withdrawn feature.

## 5. Verifying a change

* `python dev.py check` — the whole verification, about 3 seconds:
  1. the test suite (`tests/`), failures reported as test name + location + the assertion lines
     (`--full` for tracebacks, `-k EXPR` to select);
  2. data.db: no pending migration, equal to a fresh rebuild (seed + migrations; schema, rows,
     AUTOINCREMENT counters), integrity and foreign keys OK, migration files well-formed;
  3. contract/UI scan for **every user**: UI list rows = API list ids; detail pages have a
     `data-field` per API field with the displayed value; every field works as `?field=` filter;
     each action form is shown exactly when the API call (body `{}`) is not 403/409; `/ui/<c>/new`
     is 200 exactly when `POST /api/<c>` is not 403; no 5xx anywhere, including DELETE of every record.
     Scan findings are WARN (heuristics: an action whose permission depends on its parameters can
     legitimately differ — say why in your notes); test failures, data.db problems and 5xx are FAIL.
* `python dev.py call METHOD PATH --as USER [--body JSON] [--now TS]` — one request on a throwaway
  copy with pending migrations applied; prints the JSON, or for `/ui` pages the rows/fields/forms the
  contract sees, then the database rows the request changed (`+`/`-`/`~` per table, outbox included).
  `--form k=v` posts a UI form. `--steps "wen POST /api/claims/1/submit" "marco POST /api/claims/1/approve"`
  runs a sequence on one copy (each step `USER METHOD PATH [JSON]`).
* Tests: add `tests/test_expenses_<feature>.py`; fixtures `app` (fresh copy per test) and `seed`;
  `app.get/post/patch/delete(path, body, user=..., now=...)` return `.status`, `.json`, `.text`;
  `from accept_client import parse_ui` for pages (`.rows`, `.fields`, `.actions`, `.inputs`,
  `.creates`). Migration results are checked through the API (data.db is already migrated) or by
  opening `os.path.join(app.workdir, "data.db")`. Evaluator mode:
  `cd ../../harness && ACCEPT_TARGET=../apps/expenses python -m pytest ../apps/expenses/tests -q`.
* `python dev.py notes` writes `CHANGE_NOTES.md` (changed files with +/- lines, new migrations, the
  data.db diff since the snapshot, the last check output); fill in the Interpretation paragraph.

### Requests that cannot all be satisfied
Some requests contain requirements that contradict each other or the contract (e.g. "pay
immediately on approval" and "no money leaves before finance has reviewed and paid"). Do not silently
implement one side or a compromise: implement only what is consistent (often nothing), and state the
conflict and the question to ask in the notes / your report.

## 6. Interpretations of the spec (current behaviour)

* "The claim employee's manager" means the direct manager (the claimant's `manager` reference),
  regardless of role; managers do not see or decide claims of indirect reports.
* Managers and finance users can create claims for themselves like anyone else.
* Sending a workflow field (`employee`, `status`, `submitted_at`, `decided_at`, `decided_by`,
  `rejection_reason`) or `id` or an unknown field in a create/PATCH body → 400 (after 403/409 checks).
  Unknown `?field=` filters → 400. Filters on null match `null` or an empty value.
* `amount` must be a JSON number (not a string or boolean); any precision is accepted.
* `pay` leaves `decided_at`/`decided_by` unchanged.
* Employee `manager` must be an existing employee and must not create a reporting loop → else 400.
  Deleting an employee who has claims, decided claims or reports → 409.
* The detail page's `data-field` elements cover the record's fields; the `id` is shown in the heading.
* Invalid `X-Now` → 400. Routing errors map to `not_found` (404) or `method_not_allowed` (405).

## 7. Running

```
python -m pytest tests -q                      # the suite alone (from this directory)
flask --app app_entry:create_app run           # then: curl -H 'X-User: fiona' localhost:5000/api/claims
python seed.py                                 # rebuild data.db from scratch (seed + migrations)
```
