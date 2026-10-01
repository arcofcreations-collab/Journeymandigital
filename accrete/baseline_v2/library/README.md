# Lending library

Members borrow books; librarians manage the catalogue and membership. Flask 3 + SQLite (stdlib
`sqlite3`) + Jinja2, plain explicit code. External behaviour: `spec/CONTRACT.md` and
`spec/apps/library.md` (when you only have this directory: the contract rules you need are
repeated in "Error precedence" and "UI conventions" below).

This README is meant to be the only thing you read before changing the app. Typical loop:

```
python dev.py overview        # 1. live map: schema, routes + their checks in order, users, samples
                              #    (also snapshots files + data.db for step 6, once per change)
# 2. edit, following a recipe below
python dev.py call POST /api/books/3/borrow --as chen        # 3. try requests on a throwaway copy
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
| `library_app/__init__.py` | app factory: runs pending migrations, registers blueprints, `display` filter |
| `library_app/db.py` | per-request connection, `transaction()`, migration runner |
| `library_app/migrations/NNNN_*.sql` | schema **and data** changes, applied in order (`schema_version` table) |
| `library_app/auth.py` | `X-User` → member (401), `X-Now` → `ctx.now` / `ctx.today` / `ctx.now_text` (400 if malformed) |
| `library_app/errors.py` | `ValidationError` 400, `Unauthenticated` 401, `Forbidden` 403, `NotFound` 404, `Conflict` 409 → JSON or HTML error page |
| `library_app/validation.py` | body shape/type checks: `clean_<collection>(data, partial=)`, `clean_<action>_params`, writable-field tuples, enums |
| `library_app/permissions.py` | **who** may do what: pure functions `can_*(user, record, ...)` → bool (403 only) |
| `library_app/repository.py` | **all SQL**; row → API dict (`book_id` column → `"book"`); derived fields computable in SQL |
| `library_app/services.py` | one function per operation, checks in precedence order, state rules (409), derived fields that need the clock, outbox, `<collection>_actions` for the UI, `*_FIELDS` filter tuples, rule constants |
| `library_app/filters.py` | `?field=value` exact-match filtering on API-shaped records (derived fields too) |
| `library_app/routes_api.py` | `/api/...`: thin handlers → one service call each |
| `library_app/routes_ui.py` | `/ui/...`: pages + form handlers (form strings → JSON-like values → same services) |
| `library_app/templates/<collection>/{list,detail,new}.html` | contract markup (`data-id`, `data-field`, `data-action`, `data-create`); `_macros.html` `field()`; nav in `base.html` |
| `seed.py`, `seed_data.json` | rebuild data.db = migration 0001 + seed + all later migrations (seed file is frozen at 0001) |
| `tests/` | pytest through `harness/accept_client.py` (`app` and `seed` fixtures in `conftest.py`) |
| `dev.py` | developer tool (this README's commands) |

### Where every collection, action, permission and validation lives

| | members (the users) | books | loans | `_outbox` |
|---|---|---|---|---|
| table | `members` | `books` | `loans` (`book_id`, `member_id`) | `outbox` (`payload` JSON text) |
| row → dict | `repository._member` | `repository._book` (+`status` from `_BOOK_SELECT` `EXISTS`) | `repository._loan`; `overdue` added by `services.present_loan` | `repository.list_outbox_messages` |
| writes (SQL) | `insert_member`, `update_member`, `delete_member` | `insert_book`, `update_book`, `delete_book` | `insert_loan`, `mark_loan_returned` | `add_outbox_message(channel, payload, ctx.now_text)` |
| reference checks (409 on delete) | `member_has_loans` | `book_has_loans` | – | – |
| validation | `clean_member`, `MEMBER_WRITABLE`, `MEMBER_ROLES` | `clean_book`, `BOOK_WRITABLE` | none writable; `clean_borrow_params`, `clean_no_params` | – |
| uniqueness (400) | `services._ensure_username_free` | `services._ensure_isbn_free` | – | – |
| permissions | `can_read_member`, `can_create_member`, `can_update_member` (+`MEMBER_SELF_EDITABLE`), `can_delete_member` | `can_read_book`, `can_manage_books`, `can_borrow_for` | `can_read_loan`, `can_return_loan` | any authenticated user |
| services | `list/get/create/update/delete_member`, `ensure_can_create_member` | `list/get/create/update/delete_book`, `borrow_book`, `book_actions` | `list/get_loan`, `create/update/delete_loan` (always 403), `return_loan`, `loan_actions` | `list_outbox` |
| filter fields | `services.MEMBER_FIELDS` | `BOOK_FIELDS` | `LOAN_FIELDS` | `OUTBOX_FIELDS` |
| UI | `members/list,detail,new` | `books/list,detail` (borrow form + member picker for librarians), `books/new` | `loans/list,detail` (return form); `/ui/loans/new` always 403 | – |

Actions: `POST /api/books/<id>/borrow` → `services.borrow_book` (outbox `loan_created`
`{"loan","book","member"}`), `POST /api/loans/<id>/return` → `services.return_loan`.
Rule constants: `services.LOAN_PERIOD` (14 days), `services.MAX_OPEN_LOANS` (3).
`python dev.py overview` prints all of this live, with line numbers and each route's checks in order.

## 2. Error precedence and how it is implemented

Contract order when several apply: **401 → 404 → 403 → 409 → 400**. A record the caller may not read
is 403 on direct access and absent from lists (and from UI lists).

| Status | Where it comes from |
|---|---|
| 401 | `auth.load_request_context` is a `before_request` hook: missing/unknown `X-User` fails before routing, so even unknown URLs give 401 |
| 404 | unknown URL/collection/action: Flask routing (`errors._HTTP_ERRORS`); unknown record: `services._load_<x>()` is the **first** call inside each service |
| 403 | `permissions.can_*` checked right after loading; create endpoints call `ensure_can_create_<x>(ctx)` before reading the body |
| 409 | state checks in the service after permissions (`book["status"] == "on_loan"`, `_ensure_may_borrow`, `returned_at is not None`, `*_has_loans`) |
| 400 | `validation.clean_*` runs **after** 403/409, then database-dependent checks (uniqueness, references) |

Rules that keep this working:
* `routes_api._body()` never fails: an empty body is `{}`, malformed JSON becomes a non-dict marker that
  `validation.require_object` rejects with 400 — so a bad body still gets 404/403/409 first.
* Permission checks that depend on the body (e.g. `can_update_member` looks at the field names,
  `can_borrow_for` at `params.get("member")`) read the raw body defensively (`isinstance(data, dict)`).
* A 409 that depends on a body value (e.g. "the book named in the list is on loan") must be computed
  from the raw body *before* `clean_*` raises; collect the 409 first, then validate.
* Writes run in `with transaction():` (`BEGIN IMMEDIATE` … `COMMIT`, rollback on any exception):
  raise anywhere inside and nothing (rows, outbox messages) is kept — all-or-nothing for free.
* House defaults used so far: unknown or read-only/derived fields in a create/PATCH body → 400;
  unknown `?filter` field → 400; a read-only collection answers POST → 403 and PATCH/DELETE → 404 for
  an unknown id, else 403; an action body with unexpected keys → 400 (`clean_no_params`); deleting a
  record that other rows reference → 409 (never let SQLite raise: an IntegrityError is a 500).

## 3. UI conventions (contract)

* `GET /ui/<c>`: `<tr data-id="{id}">` per **readable** record (same set and order as the API list).
* `GET /ui/<c>/<id>`: one `data-field="{field}"` element per visible API field, text = the value as
  `display` renders it (`true`/`false`, empty for null); use `{{ field("name", record.name) }}` from
  `_macros.html`. One `<form data-action="{action}">` per action the caller may run **right now**.
* `GET /ui/<c>/new`: `<form data-create="{c}">` with one `input/select/textarea name="{field}"` per
  field the caller may set on create; 403 (via `ensure_can_create_<x>`) if they may not create.
* Forms post to `/ui/...` handlers in `routes_ui.py`, which convert strings with `_text`,
  `_optional_int`, `_boolean` (unconvertible values pass through so validation answers 400) and
  redirect (303) to the detail page.

## 4. Recipes

Each recipe lists every place to touch. `python dev.py check` catches most omissions (missing
`data-field`, unfilterable field, UI form shown when the API refuses or vice versa, missing UI
handler, 500 on delete, data.db not migrated or not reproducible).

### 4.1 Add a stored field (with migration and backfill)
1. `python dev.py new-migration add_book_shelf` → edit the SQL:
   `ALTER TABLE books ADD COLUMN shelf TEXT;` then `UPDATE books SET shelf = ... WHERE ...;` for the
   backfill (`NOT NULL` needs a `DEFAULT`). A reference column: `member_id INTEGER REFERENCES members (id)`
   + `CREATE INDEX`. Changing an existing CHECK/type → table rebuild (4.6).
2. `repository.py`: add the column to `_BOOK_SELECT`, the key to `_book()` (bool: `bool(row[...])`;
   reference: `row["x_id"]` under the API name), `insert_book` columns/values, `update_book` `columns`
   map (API name → column).
3. `validation.py`: add to `BOOK_WRITABLE` and check it in `clean_book` (pattern: `if "shelf" in data
   or not partial: with collect(errors, "shelf"): values["shelf"] = <checker>(data.get("shelf"))`).
   Read-only field: don't add it to `*_WRITABLE` (it is then a 400 automatically). References: check
   existence in the service (400 `{"field": "no such ..."}`), after the 403/409 checks.
4. `services.py`: add the name to `BOOK_FIELDS` (filtering), and any rule that uses it.
5. Templates: `books/detail.html` `{{ field("shelf", book.shelf) }}`; `books/list.html` column (optional);
   `books/new.html` input if settable on create, and the converter in `routes_ui.create_book`
   (`"shelf": _text`).
6. `python dev.py migrate` (applies it to data.db), `python dev.py dbdiff` (confirm only the intended
   data changed), add tests, `python dev.py check`.

Derived field: compute it in SQL in `_BOOK_SELECT` when it depends on stored data only (like
`status`), or in a `present_<x>(ctx, record)` service function when it depends on the clock (like
`present_loan`); add it to `*_FIELDS` and the detail template; it is never writable.

### 4.2 Add a collection
1. Migration: `CREATE TABLE things (id INTEGER PRIMARY KEY AUTOINCREMENT, ..., x_id INTEGER NOT NULL
   REFERENCES xs (id))` + indexes; required initial rows with their fixed ids (`INSERT ... (id, ...)`).
2. `repository.py`: `_THING_SELECT`, `_thing(row)`, `list_things`, `get_thing`, insert/update/delete,
   `*_taken` for unique fields, and `<parent>_has_things` for every table the new rows reference.
3. **Existing deletes**: every `delete_<parent>` service must now raise `Conflict` when things reference
   the parent (otherwise SQLite raises and the API answers 500).
4. `validation.py`: `THING_WRITABLE`, `clean_thing(data, *, partial)`.
5. `permissions.py`: `can_read_thing`, `can_manage_things` (or finer).
6. `services.py`: `THING_FIELDS`; `list_things` (filter by `can_read_thing`, then `apply_filters`),
   `get_thing` (`_load_thing` 404 → 403), `ensure_can_create_thing`, `create_thing`,
   `update_thing`, `delete_thing` — copy the books functions, keep the check order.
7. `routes_api.py`: the five routes (copy the books block). Read-only collection: POST → service that
   raises `Forbidden`; PATCH/DELETE → `_load_thing` then `Forbidden` (see `update_loan`).
8. `routes_ui.py` + `templates/things/{list,detail,new}.html` + nav link in `base.html`.
9. Tests: new `tests/test_library_things.py`.

### 4.3 Add an action `POST /api/<c>/<id>/<action>`
1. `services.py`: `def <action>_<thing>(ctx, thing_id, params):` inside `with transaction():` —
   `_load_thing` (404) → permission (403) → state (409) → `validation.clean_<action>_params(params)`
   or `clean_no_params(params)` (400) → effects → outbox → `return` the record (for loans:
   `present_loan(ctx, ...)`). Put new 409 helpers next to `_ensure_may_borrow`.
2. Permission function in `permissions.py`.
3. `routes_api.py`: `@bp.post("/<c>/<int:thing_id>/<action>")` calling the service with `_body()`.
4. UI: add the name to `<thing>_actions(ctx, thing)` exactly when the API call would pass the 403/409
   checks for the caller right now (reuse the same helpers so they cannot drift); add a
   `<form data-action="<action>" method="post" action="{{ url_for('ui.<action>_<thing>', ...) }}">`
   in `detail.html` (inputs for its parameters) and a POST handler in `routes_ui.py` converting form
   values and redirecting (303) to the detail page.
5. Tests: success (+ returned record, outbox payload), each 403/409/400 and one precedence case per
   pair, all-or-nothing on failure (outbox unchanged), UI form shown/hidden.

### 4.4 Change a permission
Edit the `can_*` function in `permissions.py` (pure: user + records; look records up in the service
and pass them in). If the rule needs data (e.g. "guardian of"), add a repository query and pass the
result. Check every caller (`grep -n "can_<name>" library_app/*.py`): list filters, direct reads,
writes, `<thing>_actions` (UI forms), `/ui/<c>/new` (`ensure_can_create_*`). A new role: CHECK
constraint in a table rebuild (4.6), `validation.MEMBER_ROLES`, `is_<role>` helper, every `can_*`.

### 4.5 Change validation
`validation.py`: enums/limits are module constants (`MEMBER_ROLES`, ...) used by `clean_*` and by the
UI selects; field checkers (`required_text`, `choice`, `boolean`, `optional_integer`, `record_id`)
raise `FieldInvalid`, collected per field. Database-dependent rules (uniqueness, existing reference,
"must not be its own guardian") go in the service after `clean_*`. Keep 400 last: a rule that must
win over 400 is a 409/403 and goes before `clean_*`. If the DB has a CHECK for the same rule, change
it with a migration too.

### 4.6 Data migration (backfill, fixed records, rebuild)
* All data changes go in the migration SQL. **Never edit `seed_data.json`** (it is the 0001 baseline;
  `seed.py` replays the migrations over it, and `check` verifies data.db equals that rebuild).
* The runner wraps each file in one transaction with its `schema_version` row (no BEGIN/COMMIT) and
  runs it with foreign keys OFF, then `PRAGMA foreign_key_check` must be clean or it rolls back.
* Table rebuild (change CHECK, drop/retype column, make a column NOT NULL):
  `CREATE TABLE books_new (...)`; `INSERT INTO books_new (cols) SELECT ... FROM books;`
  `DROP TABLE books;` `ALTER TABLE books_new RENAME TO books;` then recreate its indexes.
  Child tables' `REFERENCES books` keep working. If rows were ever deleted, restore the counter:
  `UPDATE sqlite_sequence SET seq = <n> WHERE name = 'books';` ("new ids above N").
* Fixed ids: insert them explicitly; AUTOINCREMENT continues above the highest id.
* Ordering rules ("ids in order of first appearance"): `INSERT ... SELECT ... ORDER BY` with
  `ROW_NUMBER() OVER (ORDER BY ...)` or `MIN(id) GROUP BY`.
* `python dev.py migrate` then `python dev.py dbdiff` shows per table: added/removed columns with value
  counts, +/-/~ rows. Made a mistake? Fix the SQL and `python seed.py` (data.db is reproducible;
  recorded apply times of migrations data.db already had are kept).
* Existing tests that compare with `seed_data.json` (`test_seed_data_is_loaded_with_same_ids`) need
  updating when the migration adds or changes fields.

### 4.7 Outbox message
`repository.add_outbox_message("<channel>", {payload dict}, ctx.now_text)` inside the action's
`with transaction():` after all checks, so failures emit nothing. Payload values are ids/plain
values exactly as the request specifies (keys and order as written). Several messages: emit in the
specified order. Test with `GET /api/_outbox` (outbox starts empty in the seed).

### 4.8 UI form
* Create form: `templates/<c>/new.html` `<form data-create="<c>">` with inputs named exactly as the
  API fields the caller may set; `routes_ui.create_<x>` lists the same fields with converters.
  Selects for enums (`validation.*` constants) and references (pass records from the view).
* Action form: see 4.3 step 4. Detail field showing something other than the raw value (e.g. a name
  for a reference) changes the `data-field` text; do it only when the request says so.

### 4.9 Withdraw a feature (remove a field, status, action or collection)
* Data first: a migration that moves existing rows to the surviving representation exactly as the
  request says (e.g. a removed status → `UPDATE ... SET status = ... WHERE status = ...`), then drops
  the column (`ALTER TABLE t DROP COLUMN x;` for a plain column, otherwise a rebuild, 4.6) or table.
* Code: remove the field from `_SELECT` / row mapping / writes (`repository.py`), from `*_WRITABLE` /
  `*_READ_ONLY` and `clean_*` (`validation.py`; it then becomes an unknown field → 400), from
  `*_FIELDS` (filter → 400), from the templates and `routes_ui.py` converters; remove routes, service
  functions, `*_actions` entries and forms of a removed action (its URL then answers 404 after 401).
  `grep -rn "<name>" library_app tests` must come back empty (apart from the migrations).
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
     Scan findings are WARN (heuristics: an action whose permission depends on its parameters can
     legitimately differ — say why in your notes); test failures, data.db problems and 5xx are FAIL.
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
  `--form k=v` posts a UI form. `--steps "chen POST /api/books/3/borrow" "ada GET /api/_outbox"` runs
  a sequence on one copy (each step `USER METHOD PATH [JSON]`).
* Tests: add `tests/test_library_<feature>.py`; fixtures `app` (fresh copy per test) and `seed`;
  `app.get/post/patch/delete(path, body, user=..., now=...)` return `.status`, `.json`, `.text`;
  `from accept_client import parse_ui` for pages (`.rows`, `.fields`, `.actions`, `.inputs`,
  `.creates`). Migration results are checked through the API (data.db is already migrated) or by
  opening `os.path.join(app.workdir, "data.db")`. Evaluator mode:
  `cd ../../harness && ACCEPT_TARGET=../apps/library python -m pytest ../apps/library/tests -q`.
* What to test by hand: the pinned state already fixes every status for empty bodies and every
  record/user, so tests are needed for what it cannot see: actions and creates/PATCHes **with**
  parameters (each 400/409 that depends on them, success values), multi-step flows, outbox payloads,
  UI forms. Write them for the new behaviour, not for the unchanged matrix. Ids the request names
  ("new ids above N") deserve one test that creates a record and checks its id.
* `python dev.py notes` writes `CHANGE_NOTES.md` (changed files with +/- lines, new migrations, the
  data.db diff and the accepted pinned-state diff since the snapshot, the last check output); fill
  in the Interpretation paragraph.

### Requests that cannot all be satisfied
Some requests contain requirements that contradict each other or the contract (e.g. "delete the
data" and "keep returning it unchanged", or "pay immediately" and "nothing is paid before review").
Do not silently implement one side or a compromise: implement only what is consistent (often
nothing), and state the conflict and the question to ask in the notes / your report.

## 6. Interpretations of the spec (current behaviour)

* `X-User` must name an existing member (inactive members can still sign in and read, but cannot borrow).
* Unknown body fields and read-only/derived fields (`id`, `status`, `overdue`) in a create or
  PATCH body → 400. Unknown `?field=` filters → 400. Filters on null match `null` or an empty value.
* A member PATCHing their own record with any field other than `name` → 403 (the whole request).
* A librarian lending to an unknown or non-integer `member` → 400; if the book is on loan, 409 wins.
* Deleting a member who has loans → 409 (mirrors the book rule; loans keep their history).
* The detail page's `data-field` elements cover the record's fields; the `id` is shown in the
  heading. The borrow form is shown when the book is available and (for members) the caller
  is active with fewer than 3 open loans; librarians get a member picker.
* Invalid `X-Now` → 400. Routing errors map to `not_found` (404) or `method_not_allowed` (405).

## 7. Running

```
python -m pytest tests -q                      # the suite alone (from this directory)
flask --app app_entry:create_app run           # then: curl -H 'X-User: ada' localhost:5000/api/books
python seed.py                                 # rebuild data.db from scratch (seed + migrations)
```
