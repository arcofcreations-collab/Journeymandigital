# Lending library

A small community library: members, books and loans. Flask 3 + SQLite (stdlib `sqlite3`) +
Jinja2. External behaviour follows `spec/CONTRACT.md` and `spec/apps/library.md`.

## Layout

```
app_entry.py              create_app() -> WSGI app bound to ./data.db (the contract's entry point)
data.db                   committed database: fully migrated + seed data, nothing else
seed.py                   rebuilds data.db from scratch (migrations + seed_data.json)
seed_data.json            starting records (ids are preserved)
library_app/
  __init__.py             app factory: config, migrations, blueprints, error handlers
  db.py                   per-request connection, transaction(), migration runner
  migrations/NNNN_*.sql   schema migrations, applied in order and recorded in schema_version
  auth.py                 X-User -> member (401), X-Now -> request clock; RequestContext
  errors.py               ValidationError/Forbidden/NotFound/Conflict/... and their rendering
  validation.py           request-body checks (shape, types, required fields, enums)
  repository.py           all SQL; returns API-shaped dicts (book_id column -> "book" field)
  permissions.py          who may do what (pure functions of user + record)
  services.py             business rules and actions (borrow, return); one function per operation
  filters.py              ?field=value list filtering (works on derived fields too)
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
3. the record's state allows the operation, else `Conflict` (409)
4. the input is valid (`validation.clean_*`, then uniqueness/reference checks), else `ValidationError` (400)

Writes run inside `with transaction():` (`BEGIN IMMEDIATE` … `COMMIT`, rolled back on any
exception), so a failed action never leaves a partial loan or outbox message behind.
Errors are rendered by `errors.py`: JSON `{"error", "message", "fields"}` under `/api`, an HTML
error page with the same status under `/ui`.

### Business rules (where to find them)

| Rule | Location |
|---|---|
| book `status` (on_loan/available) | `repository._BOOK_SELECT` (SQL `EXISTS`) |
| loan `overdue` (depends on X-Now) | `services.present_loan` |
| 14-day loan period, max 3 open loans | `services.LOAN_PERIOD`, `services.MAX_OPEN_LOANS` |
| borrow / return | `services.borrow_book`, `services.return_loan` |
| outbox message `loan_created` | `services.borrow_book` → `repository.add_outbox_message` |
| who can read/edit what | `permissions.py` |
| actions shown on detail pages | `services.book_actions`, `services.loan_actions` |

## Running the tests

From the workspace root (the tests find `harness/` relative to this directory):

```
python -m pytest apps/library/tests -q
# or, as the evaluators run it:
cd harness && ACCEPT_TARGET=../apps/library python -m pytest ../apps/library/tests -q
```

Every test gets a fresh copy of this directory via `accept_client.fresh_app()`, so tests may
mutate data freely; the committed `data.db` is never touched. Tests talk only HTTP
(through the WSGI app); only the migration tests open the copied database file directly.

To run the app locally (send `X-User` with each request, e.g. via curl or a header extension):

```
cd apps/library && flask --app app_entry:create_app run
curl -H 'X-User: ada' localhost:5000/api/books
```

## Changing the schema: adding a migration

1. Add `library_app/migrations/NNNN_short_name.sql` with the next number
   (e.g. `0002_add_book_shelf.sql`). Names must match `^\d{4}_[a-z0-9_]+\.sql$`.
2. Write plain SQLite DDL/DML. Don't add `BEGIN`/`COMMIT`: the runner wraps each file in a
   transaction together with its `schema_version` row, so a failing migration leaves nothing behind.
   (For changes SQLite's `ALTER TABLE` can't do, use the create-copy-drop-rename recipe.)
3. Update `repository.py` (SELECT lists, row → dict mapping, INSERT/UPDATE), `validation.py`
   (writable fields and checks), `services.py` (field tuple used for filtering), the templates
   (detail `data-field`, list columns, `new.html` inputs) and `seed.py` if the seed needs it.
4. Apply it to the committed database: `create_app()` applies pending migrations on startup,
   so starting the app once is enough; or rebuild from scratch with `python seed.py`.
   Commit the updated `data.db`.
5. Add tests.

Migrations never get edited after they are committed; fix forward with a new file.

## Interpretations of the spec

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
