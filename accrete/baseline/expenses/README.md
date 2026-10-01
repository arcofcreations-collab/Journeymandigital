# Expense claims

Employees submit expense claims, their manager approves or rejects them, finance pays them.
Flask 3 + SQLite (stdlib `sqlite3`) + Jinja2. External behaviour follows `spec/CONTRACT.md`
and `spec/apps/expenses.md`.

## Layout

```
app_entry.py              create_app() -> WSGI app bound to ./data.db (the contract's entry point)
data.db                   committed database: fully migrated + seed data, nothing else
seed.py                   rebuilds data.db from scratch (migrations + seed_data.json)
seed_data.json            starting records (ids are preserved)
expenses_app/
  __init__.py             app factory: config, migrations, blueprints, error handlers
  db.py                   per-request connection, transaction(), migration runner
  migrations/NNNN_*.sql   schema migrations, applied in order and recorded in schema_version
  auth.py                 X-User -> employee (401), X-Now -> request clock; RequestContext
  errors.py               ValidationError/Forbidden/NotFound/Conflict/... and their rendering
  validation.py           request-body checks (shape, types, required/read-only fields, amount range)
  repository.py           all SQL; returns API-shaped dicts (employee_id column -> "employee" field)
  permissions.py          who may do what (pure functions of user + record + claimant)
  services.py             business rules and the claim workflow; one function per operation
  filters.py              ?field=value list filtering
  routes_api.py           /api/... JSON endpoints (thin: parse, call service, respond)
  routes_ui.py            /ui/... HTML pages and their form handlers
  templates/              Jinja templates, one folder per collection
tests/                    pytest suite using harness/accept_client.py
```

### Request flow

`auth.load_request_context` runs before routing for every request, so a missing or unknown
`X-User` is a 401 even for unknown URLs. Route handlers call one service function with the
`RequestContext` (`ctx.user`, `ctx.now`). Each service checks, in the contract's precedence order:

1. the record exists, else `NotFound` (404)
2. `permissions.*` allows the caller, else `Forbidden` (403)
3. the claim's status allows the operation, else `Conflict` (409)
4. the input is valid (`validation.clean_*`, then uniqueness/reference checks), else `ValidationError` (400)

Writes run inside `with transaction():` (`BEGIN IMMEDIATE` … `COMMIT`, rolled back on any
exception). Errors are rendered by `errors.py`: JSON `{"error", "message", "fields"}` under
`/api`, an HTML error page with the same status under `/ui`.

### Claim workflow

```
draft --submit (owner)--> submitted --approve (manager)--> approved --pay (finance)--> paid
                                    \--reject (manager, reason)--> rejected
```

| Rule | Location |
|---|---|
| transitions, timestamps, `decided_by` | `services.submit_claim/approve_claim/reject_claim/pay_claim` |
| outbox message `payment` | `services.pay_claim` → `repository.add_outbox_message` |
| who can read/edit/decide/pay | `permissions.py` (manager = the claimant's direct `manager`) |
| fields clients may set / never set | `validation.CLAIM_WRITABLE`, `validation.CLAIM_READ_ONLY` |
| amount range, categories, roles | `validation.MAX_CLAIM_AMOUNT`, `CLAIM_CATEGORIES`, `EMPLOYEE_ROLES` |
| actions shown on detail pages | `services.claim_actions` |

## Running the tests

From the workspace root (the tests find `harness/` relative to this directory):

```
python -m pytest apps/expenses/tests -q
# or, as the evaluators run it:
cd harness && ACCEPT_TARGET=../apps/expenses python -m pytest ../apps/expenses/tests -q
```

Every test gets a fresh copy of this directory via `accept_client.fresh_app()`, so tests may
mutate data freely; the committed `data.db` is never touched. Tests talk only HTTP
(through the WSGI app); only the migration tests open the copied database file directly.

To run the app locally (send `X-User` with each request):

```
cd apps/expenses && flask --app app_entry:create_app run
curl -H 'X-User: fiona' localhost:5000/api/claims
```

## Changing the schema: adding a migration

1. Add `expenses_app/migrations/NNNN_short_name.sql` with the next number
   (e.g. `0002_add_claim_paid_at.sql`). Names must match `^\d{4}_[a-z0-9_]+\.sql$`.
2. Write plain SQLite DDL/DML. Don't add `BEGIN`/`COMMIT`: the runner wraps each file in a
   transaction together with its `schema_version` row, so a failing migration leaves nothing behind.
   (For changes SQLite's `ALTER TABLE` can't do, e.g. altering a CHECK constraint, use the
   create-copy-drop-rename recipe.)
3. Update `repository.py` (SELECT lists, row → dict mapping, INSERT/UPDATE), `validation.py`
   (writable/read-only fields and checks), `services.py` (field tuple used for filtering, rules),
   the templates (detail `data-field`, list columns, `new.html` inputs) and `seed.py` if needed.
4. Apply it to the committed database: `create_app()` applies pending migrations on startup,
   so starting the app once is enough; or rebuild from scratch with `python seed.py`.
   Commit the updated `data.db`.
5. Add tests.

Migrations never get edited after they are committed; fix forward with a new file.

## Interpretations of the spec

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
