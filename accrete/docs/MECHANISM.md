# How accrete works

accrete is a form of programming in which an application *is* the accumulated sequence of its
changes. Each change is a short list of typed operators, carried out by a pipeline that checks
it against the running application and its stored data.

## 1. Three ideas

### Idea 1: one model, everything else derived

An application is one data structure, the **model**:

- **entities**, each with fields (types, required, unique, defaults, `computed` expressions,
  `read_if` / `write_if` field permissions);
- **rules**: read, create, update and delete permissions, plus update and delete guards;
- **constraints**: invariants every record must satisfy;
- **actions**: named state transitions, each with params, `allow`, `guard` and effects;
- **triggers**: effects that run on create, update, delete or an action;
- **the user directory**: which entity holds the users, and which field identifies them.

A generic runtime (`accrete/runtime.py`, `accrete/ui.py`, `accrete/wsgi.py`) interprets the
model. It provides:

- the REST API, filtering and the error-precedence rules;
- the HTML UI (lists, detail pages, forms, action buttons only where they are allowed);
- validation and permissions;
- derived values, and the outbox for integrations.

There is no second place where a field, rule or permission must be repeated. Adding a field
adds it to the API, the UI forms, validation and filters at once.

Every expression (rules, guards, computed fields, defaults, effects) is written in a small, safe
Python subset (`accrete/expr.py`). It is parsed against an allow-list of syntax nodes, and has
no attribute access to private names and no imports. Because the language is closed and typed
against the model (`analyse`), the system knows exactly what every expression reads. That is
what makes the next two ideas possible.

### Idea 2: changes are typed, invertible operators over model *and* data

The model and the data never change except through operators (`accrete/ops.py`). Each operator:

1. transforms the model;
2. transforms the stored data in the same step (backfill, convert, map, materialise);
3. rewrites every dependent expression where the change is a rename;
4. returns its **exact inverse**, including the data it destroys.

| Change kind | Operators |
|---|---|
| structure | `add_entity`, `remove_entity`, `rename_entity`, `add_field` (+`backfill`), `remove_field`, `rename_field`, `change_field` (+`convert` / `map`; computed → stored materialises values) |
| macro | `promote_field` (text field → reference to a new entity of its distinct values) |
| data | `update_records`, `add_records`, `delete_records` |
| behaviour | `set_rule`, `add/change/remove_constraint` (with `existing: enforce or exempt`), `add/change/remove_action`, `add/change/remove_trigger`, `set_users` |

- **Stable field ids.** Stored records are keyed by stable field ids (`f7`), not names. A rename
  is a pure model edit, so data is never rewritten for it.
- **Undo.** Removed fields and entities keep their data in the inverse, so undo is lossless.
- **Ledger.** A change file applies its operators in order, atomically. The ledger stores each
  change's request, interpretation, operators, full report and inverse.

### Idea 3: the previous version is the oracle

Before a change commits, the pipeline (`accrete/change.py: apply_change`) runs these stages:

| Stage | What it does | Rejects when |
|---|---|---|
| **apply** | operators run on a copy of model + data | an operator is invalid (unknown name, clash, failed conversion) |
| **static check** | every expression re-analysed against the new model | a name no longer resolves, a type mismatch (e.g. a record compared to a constant), a dependent left inconsistent |
| **data check** | *every* stored record re-validated against the new model (required, enum, references, uniqueness, constraints) | any record violates it; the report counts violations per rule and gives example ids |
| **footprint** | computes what the change may alter (below) | – |
| **differential replay** | the recorded request corpus (every real API request the app served, up to 3000) plus generated probes run against **old and new** versions; each difference is classified | a difference is *unexplained*, a new crash appears, or a *consequence* is not acknowledged |
| **expectations** | the change's own stated examples run on the new version | any fails |
| **commit** | model, data and ledger entry written in one SQLite transaction | – |

Generated probes cover, for a sample of users of every role:

- every collection list;
- sampled records, plus every record whose stored data the change touched;
- every action on those records;
- create, patch and delete;
- the outbox.

Each probe runs from the same starting state and is rolled back afterwards.

## 2. The footprint: direct effects vs consequences

The footprint is a set of labels: `E.read`, `E.create`, `E.update`, `E.delete`,
`E.action:N`, `E.field:F`, `E.any`, `*.any`.

- **Direct** labels come from what the operators themselves modified. They are found by
  comparing model elements and stored data before and after, not by trusting the change's
  description. If you change the borrow guard, `books.action:borrow` is direct.
- **Consequences** are labels reached only through the dependency graph. Other features read
  what changed: a computed field, a guard, a rule or a trigger that mentions the changed field
  or collection. The pipeline computes the transitive closure.

Every difference observed in replay is mapped to the labels that would explain it:

- a status code change on a list needs `E.read`;
- a changed field value needs `E.field:F`;
- an action that now returns 409 needs `E.action:N`.

The difference is then classified:

- **direct**: explained by direct labels, so accepted;
- **consequence**: explained only by a dependent feature. The change is rejected unless it lists
  that label under `consequences:`. The report shows concrete before/after examples, so the
  person or agent sees, say, "POST /api/books/2/borrow as hana: 200 → 409";
- **unexplained**: nothing accounts for it (an engine fault or a mis-modelled operator). Always
  rejected.

This turns "did my change break something?" from a question answered by maintaining tests into
a question the previous version answers mechanically. It also forces every side-effect of a
change to be either intended (acknowledged, recorded in the ledger) or removed.

**What the gate cannot see.** Replay only observes the requests it runs. A difference that no
recorded or generated request exercises goes unnoticed. A *direct* change that does the wrong
thing is accepted by replay, because the operator says it changes that element. Replay checks
"nothing *else* changed", not "the right thing changed". That is what `expect:` is for. The live
demo's step 6 shows exactly this case.

## 3. Revert

`accrete revert APP SEQ` builds a new change from the ledger entry's inverse operators. It
acknowledges the original change's direct and consequence labels, then sends that change
through the *same* pipeline. If a later committed change uses something the original change
introduced, the revert is refused unless forced. After reverting, the model and every stored
record are identical to before. The demo checks this with an exact equality test, and the
independent base acceptance suite passes again.

## 4. What an implementer actually writes

The request "librarians can mark a book as damaged; damaged books show status 'damaged' and
cannot be borrowed" becomes:

```yaml
request: "Librarians can mark a book as damaged; damaged books show status 'damaged'"
interpretation: "Bool field writable by librarians; status derived from it; damaged books cannot be borrowed"
ops:
  - add_field: {entity: books, name: damaged, type: bool, default: "False", write_if: "user.role == 'librarian'"}
  - change_field: {entity: books, name: status,
                   computed: "'damaged' if record.damaged else ('on_loan' if any(l.book == record and l.returned_at is None for l in loans) else 'available')"}
consequences: [books.action:borrow]
expect:
  - {as: hana, do: "PATCH /api/books/3", body: {damaged: true}, status: 403}
```

No schema file, migration, handler, template, serializer or test file is edited. The API, the UI
form input, the permission and the stored data are all derived. The pipeline checks the 40 existing books, replays
about 660 requests against both versions in about 0.4 s, and finds the borrow consequence
itself.

## 5. Source map

| File | Responsibility |
|---|---|
| `accrete/expr.py` | expression language: parse (allow-list), evaluate, type analysis, rename rewriting |
| `accrete/model.py` | model structure, static checks, dependency graph |
| `accrete/runtime.py` | request handling: permissions, validation, actions, triggers, effects, outbox |
| `accrete/ui.py` | generic HTML UI |
| `accrete/store.py` | SQLite persistence: model, records, outbox, request corpus, ledger |
| `accrete/wsgi.py` | WSGI app (`app_entry.create_app()`) |
| `accrete/ops.py` | change operators and their inverses |
| `accrete/change.py` | footprint, probes, replay, classification, pipeline, revert |
| `accrete/cli.py` | `accrete` command |
| `accrete/demo.py` | `accrete demo` live demonstration |
