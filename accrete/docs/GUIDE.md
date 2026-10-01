# accrete guide: changing an application

An accrete application is **one model** (entities, fields, rules, actions, triggers) plus its
data, built and evolved only by **changes**: small YAML files of typed operators. The runtime
derives the whole API, UI, validation and permissions from the model, so a change is written
once and nothing else needs editing. Every change runs through a pipeline that checks it and
then commits it atomically (or rejects it with a precise reason).

## Fast path (most changes need only these steps)

1. `accrete context APP` prints everything needed to start, in one screen:
   - the whole model;
   - the users grouped by role;
   - two sample records per collection, exactly as the API returns them;
   - the recent ledger;
   - the exact request semantics (error order per operation).

   The model is also in `APP/changes/*.yaml`, but you rarely need to read those files.
2. Write `APP/changes/NNNN-name.yaml` with `request`, `interpretation`, `ops` and `expect`. Put
   in `expect` the examples that show the request is met, including UI pages (see below).
3. `accrete apply APP APP/changes/NNNN-name.yaml --notes APP/CHANGE_NOTES.md`
   - All checks run first; the change commits only if every one passes. No separate dry run is
     needed: **a rejected change alters nothing**.
   - On a rejection, the lines starting `NEXT:` say what to fix. Fix the file and apply again.
   - On commit, `--notes` writes the change notes: request, interpretation, what changed, and
     what was verified.

What the checks catch, and what they do not, is measured in "How far to trust the checks"
below. Read it once; it tells you which verification is still your job.

Other commands:

```bash
accrete call APP GET /api/books/3 --as ada [--body '{...}'] [--now ISO]   # one request, nothing saved
accrete show APP [ENTITY]          # the model only
accrete log APP [SEQ]              # history; SEQ shows a full report
accrete revert APP SEQ             # undo a committed change (checked like any change)
accrete upgrade-check APP          # after installing a new accrete version: same behaviour?
```

## Change file

```yaml
request: "Members may borrow at most 2 books"          # the requirement, verbatim
interpretation: "Lower the open-loan limit in the borrow guard from 3 to 2"
ops:                                                   # applied in order, atomically
  - change_action: {entity: books, name: borrow, guard: "record.status == 'available' and count(loans, member=user, returned_at=None) < 2"}
expect:                                                # examples checked on the changed app
  - {as: hana, do: "POST /api/books/2/borrow", status: 409}
  - name: "librarian sees new field"
    steps:
      - {as: ada, do: "PATCH /api/books/2", body: {title: "X"}, status: 200, json: {title: "X"}}
      - {as: ada, do: "GET /api/books?title=X", count: 1}
consequences: [books.action:borrow]                    # only if the report asks (see below)
```

`expect` entries:
- `as` (username), `do` ("METHOD /path?query"), and optionally `body` and `now` (ISO datetime;
  default: now);
- checks: `status`, `json` (subset match) and `count` (number of list items);
- use `steps` for sequences; each expectation starts from the unchanged data.

**UI expectations.** `do: "GET /ui/E/ID"`, `/ui/E` or `/ui/E/new`, with `status` and `ui:`.
The keys of `ui:` are:
- `fields: {name: text}`: the displayed `data-field` text;
- `actions: [..]`: the exact set of action forms;
- `actions_include` / `actions_exclude`;
- `inputs: [..]`: the exact set of form inputs;
- `inputs_include`;
- `rows`: the ids shown, or their count.

Example:
`{as: chen, do: "GET /ui/books/2", ui: {actions: [borrow], fields: {status: available}}}`.
These replace hand-written UI test scripts.
Expectations run through the same runtime that serves the application, so together with the
replay they are the verification of a change; `accrete call` answers ad hoc questions.

## What the pipeline checks

1. **Operators apply.** An unknown entity or field, or a name clash, is reported immediately.
2. **Static check.** Every expression still resolves and type-checks. Renames are rewritten
   for you. If you remove or change something other rules use, those rules are listed:
   update or remove them in the same change.
3. **Data check.** Every existing record must satisfy the changed model: required fields,
   enum values, references, uniqueness and constraints. Fix data with `backfill`, `convert`,
   `map` or `update_records`, or add a constraint with `existing: exempt`.
4. **Replay.** Recorded and generated requests (every collection, record and action, as several
   users) run on the old and new versions:
   - **changed as intended:** differences on what your operators modify directly;
   - **consequences:** other features that changed *because they depend on* what you
     modified (e.g. the borrow guard reads `status`). These are shown with before/after
     examples. If intended, list their labels under `consequences:`; if not, fix the change;
   - **unexplained:** a difference nothing accounts for. Treat it as a bug.
5. **Expectations** run. Then the change is committed with its report and its inverse in
   the ledger.

## Model semantics (what the runtime does for you)

- Collections are entities, at `/api/<entity>`; records have an integer `id`.
- **Rules** (expressions; default `True`): `read` (hidden from lists, 403 on direct access),
  `create`, `update`, `delete` (403), `create_guard`, `update_guard`, `delete_guard` (409).
  `record` is the record (for `create`/`create_guard`: the candidate with defaults applied) and
  `user` is the caller. Order on create: `create` (403), `create_guard` (409), then input errors
  and constraints (400); a list input with some invalid items still reaches `create_guard` with
  its valid items, so "409 wins over 400" holds.
- **Fields**:
  - `type`: text | int | number | bool | date | datetime | enum (`values`) | ref (`ref`: entity)
    | list (`of`: any of those element types, default untyped; `ref`/`values` for its elements; `distinct: true`
    rejects duplicates with 400; `required` means non-empty). A list of refs is a JSON array of
    ids in the API and a list of records in expressions; `?field=id` filters by membership.
  - Flags:
    - `required` (400 if missing), `unique` (400);
    - `default` (expression, applied on create);
    - `computed` (expression, read-only, never stored);
    - `system` (clients may not set it: 400; only defaults and actions set it);
    - `read_if` (field hidden from users when false);
    - `write_if` (setting it when false: 403).
  - Shorthand: `"text required unique"`, `"ref members"`, `"enum a|b|c required"`,
    `"list ref claims required distinct"`, `"list int"`.
- **Display**: `display: <field>` on an entity (or `set_display`) shows that field instead of the
  id wherever a record of it is referenced in the HTML UI (API values stay ids).
- **Constraints**: expressions every record must satisfy (400 on create/update; 409 when an
  action would break them). With `existing: exempt`, current violators are exempt.
- **Actions**: `POST /api/<entity>/<id>/<name>`. Checks run in this order:
  1. `params` are converted, then `allow` (false: 403);
  2. `guard` (false: 409, message `guard_message`);
  3. invalid params: 400;
  4. `effects` run atomically.
  
  Response: the record.
- **Triggers**: effects run `on: create | update | delete | action:<name>`, optionally `when`.
- **Effects**:
  - `{set: {field: expr}}` on the record;
  - `{create: entity, values: {...}, as: var}`;
  - `{update: <records expr>, set: {f: expr}}`, where `it` is each target;
  - `{delete: <records expr>}`;
  - `{emit: channel, payload: {k: expr}}` (outbox, `/api/_outbox`);
  - `{fail: "'message'", status: 409, when: expr}`;
  - `{if: expr, then: [...], else: [...]}`;
  - `{for: var, in: <records or list expr>, do: [...]}` runs the effects once per item, in order.
- Action `params` take the same specs as fields, including lists: `params: {books: list ref books required distinct}`.
- Deleting a record still referenced by another record gives 409 automatically. A reference
  field may say otherwise with `on_delete: cascade` (delete the referencing records too, running
  their delete triggers) or `on_delete: nullify` (clear the reference, or drop the id from a list).
- `GET /api/_outbox?channel=x` filters messages like any list. Filtering a collection on a field it does not have is a 400.
- A `required` text field rejects empty and whitespace-only input (400).
- Error precedence: 401, 404, 403, 409, 400. Unknown or missing `X-User`: 401.

## Expression language (safe Python subset)

Variables:
- `record`, `user`, `now` (datetime), `today` (date);
- `input` (the request body as sent, a dict) in `create`/`update` rules and guards, `write_if`,
  and create/update triggers: e.g. `'amount' in input` tells whether a field was sent;
- `params` (in actions), `old` (in update triggers), `it` (in update effects), effect `as` variables;
- every collection by name (e.g. `loans` is the list of all loans, ignoring permissions).

Attributes follow references: `record.employee.manager.role`.

Functions:
- `count(coll, f=v, ...)`, `find(...)` (list), `first(...)` (record or None);
- `len`, `sum`, `min`, `max`, `any`, `all`, `sorted`, `round`, `abs`, `between(x, lo, hi)`;
- `days(n)`, `hours(n)`, `minutes(n)`, `date(x)`, `datetime(x)`;
- comprehensions: `[l for l in loans if l.member == user]`;
- string and date methods: `.lower()`, `.date()`, `.year`, `.weekday()`.

Text constants need quotes inside YAML strings: `"'draft'"`.

## Escape hatch: functions (when expressions are not enough)

```yaml
- add_function: {name: late_days, params: [loan, today], body: |
    if loan.returned_at is not None or loan.due_at >= today:
        return 0
    return (today - loan.due_at).days}
- add_field: {entity: loans, name: days_late, type: int, computed: "late_days(record, today)"}
```

A function is a small piece of Python callable from any expression. The allowed statements are
assignment, `if`, `for`, `return`, `break`, `continue` and comprehensions. These are **not**
allowed: imports, `while`, private names, global state. A function sees only its arguments, the
built-ins and other functions. Use `change_function` and `remove_function` to change or remove
one.

**What still holds for code that uses a function:**
- atomic commits and exact revert, since functions are part of the model and the ledger;
- the data check, the replay and the expectations, which treat behaviour as a black box;
- error precedence;
- functions cannot write data or emit messages: only effects can.

**What is weaker:**
- Static checking of a function body is limited to:
  - names: every name must be known;
  - attributes: every `.attr` must be a field of some entity or a value method.
- Types inside a body are not checked.
- A call is assumed to read **everything**, because a function can follow references. So any
  change to the model lists callers among its possible consequences. They are only reported if
  replay sees an actual difference.
- `rename_field` does not rewrite function bodies. A rename that a body still uses is rejected
  until you `change_function` it in the same change.
- A function that raises for some records makes the requests that reach it fail (500). Replay
  reports this as an unexplained crash and rejects the change.
- Termination is not proven. Loops run only over finite sequences and there is no `while`, but
  deep recursion is possible.

## Operator reference

Entities:
- `add_entity: {name, fields: {f: spec}, display: f, rules: {...}, constraints: {name: {expr, message, field}}, actions: {...}, triggers: {...}}`
- `rename_entity: {from, to}`: renames every reference.
- `remove_entity: {name}`: its data is kept in the ledger for undo.
- `set_users: {entity, key}`: which records are users, and the field holding `X-User`.
- `set_display: {entity, field}`: how its records are shown where referenced in the UI (`field: null` for ids).

Fields:
- `add_field: {entity, name, type, ..., backfill: expr}`: `backfill` fills existing records; without it, `default` is used.
- `rename_field: {entity, from, to}`: every expression and effect is rewritten; data untouched.
- `remove_field: {entity, name}`
- `change_field: {entity, name, <any spec keys>, convert: expr, map: {old: new}}`: `convert` uses `value` and `record`; `map` renames enum values. Turning a computed field into a stored one materialises its current values.
- `promote_field: {entity, field, to, key: name, fields: {...}, rules: {...}}`: turns a text field into a reference to a new entity holding its distinct values (ids in order of first appearance by record id); the UI keeps showing the text (display = key).

Data:
- `update_records: {entity, where: expr, set: {f: expr}}`
- `add_records: {entity, records: [{...}]}`
- `delete_records: {entity, where: expr}`

Behaviour:
- `set_rule: {entity, rule, expr, message}`: `rule` is read/create/update/delete/update_guard/delete_guard; `expr: null` removes the rule (allowed).
- `add_constraint: {entity, name, expr, message, field, existing: enforce|exempt}`; `change_constraint` (same keys); `remove_constraint: {entity, name}`
- `add_action: {entity, name, params: {p: spec}, allow, guard, guard_message, effects: [...]}`
- `change_action: {entity, name, rename, params, add_params, allow, guard, guard_message, effects, append_effects, prepend_effects}`
- `remove_action: {entity, name}`
- `add_trigger: {entity, name, on, when, effects}`; `change_trigger`; `remove_trigger: {entity, name}`

## Recipes

```yaml
# new related concept + action that notifies an integration
- add_entity: {name: reservations, fields: {book: ref books required, member: ref members required,
               created_at: {type: datetime, default: now, system: true}}, rules: {read: "user.role == 'librarian' or record.member == user", create: "False", update: "False"}}
- add_action: {entity: books, name: reserve, allow: "user.role == 'member'", guard: "record.status == 'on_loan'",
               effects: [{create: reservations, values: {book: record, member: user}, as: r},
                         {emit: reservation_created, payload: {reservation: r, book: record}}]}
# rule change with existing-data policy
- add_constraint: {entity: claims, name: receipt_over_75, expr: "record.amount <= 75 or record.receipt is not None",
                   message: "a receipt is required above 75", field: receipt, existing: exempt}
# several records in one atomic operation (all or nothing), with a 409 rule that wins over 400
- add_entity: {name: batches, fields: {items: list ref claims required distinct, total: {type: number, system: true, default: "sum(c.amount for c in record.claims)"}},
               rules: {create: "user.role == 'finance'", create_guard: "all(c.status == 'approved' for c in record.items)"},
               triggers: {pay: {on: create, effects: [{for: c, in: record.items, do: [{update: c, set: {status: "'paid'"}}, {emit: paid, payload: {claim: c}}]}]}}}
# enum migration
- change_field: {entity: claims, name: category, values: [travel, food, equipment, other], map: {meals: food}}
```

Expressions inside effects, defaults and backfills: `today + days(14)`, `params.reason`, `user`.

## Requests that should not be executed as stated

If a request is contradictory, unsafe for existing data, or too ambiguous to implement
correctly, do not guess. Leave the application unchanged and write `CLARIFICATION.md` in the
application directory, explaining the problem and the decision needed. If you resolve an
ambiguity yourself with a documented interpretation, state it in `interpretation:`.
