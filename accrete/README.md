# accrete: applications as ledgers of verified, invertible changes

accrete is an experimental form of programming built for one purpose: making changes after
the first build cheap and safe.

- **One model.** An application is a single model of entities, fields, rules, constraints,
  actions and triggers. A generic runtime turns it into an API, an HTML UI, validation,
  permissions, derived values and integration messages.
- **Typed operators.** The model and its stored data change only through **typed, invertible
  operators** written in short YAML change files.
- **A checking pipeline.** Every change goes through a pipeline before it can commit:
  - a static check;
  - re-validation of every stored record;
  - **footprint-scoped differential replay** of recorded and generated requests against the
    old and new versions;
  - the change's own expectations.

  The change then commits atomically, together with its inverse, or is rejected with a precise
  reason.

This directory has everything needed to inspect, run and reproduce the experiment:

- the engine;
- three applications;
- the conventional baseline;
- the frozen challenge sets with their hidden tests;
- the experiment harness;
- every raw result.

**Headline.** On 14 fresh evaluation challenges implemented by the same AI assistant on both
systems, accrete changes:
- took a median of **2.0 minutes vs 4.9** for a clean Flask codebase (**2.4x faster**, faster in
  every challenge);
- were about 5x smaller;
- used about 1.6x fewer tokens.

**But the pre-declared target (≥5x, every task correct) was missed.** accrete solved 12/14 tasks
against the baseline's 14/14, and both misses were engine gaps. Details, failures and caveats are
in [`docs/RESULTS.md`](docs/RESULTS.md); the target is in [`docs/TARGET.md`](docs/TARGET.md).

## Quick start

```bash
pip install -e accrete          # from the repository root (needs Python >= 3.10 and PyYAML)
accrete demo                    # live demo: real changes and checks on a fresh copy of the library app
python -m pytest accrete/tests -q   # engine regression tests
```

`accrete demo` is not a replay of a recording. In a temporary copy of the library application
it:

1. applies a rename;
2. is rejected for a new required field with no data plan, then succeeds once a backfill is
   added;
3. detects a hidden consequence (damaged books can no longer be borrowed), which must be
   acknowledged before it commits;
4. rejects a change whose stated expectation fails;
5. reverts every committed change;
6. proves that the model and all stored records are byte-identical to the original;
7. runs the independent acceptance suite.

## Working with an application

```bash
accrete show apps/library              # what the application is now
accrete apply apps/library change.yaml --dry-run
accrete apply apps/library change.yaml # check and commit (or reject, with reasons)
accrete call apps/library GET /api/books/3 --as ada
accrete log apps/library               # the ledger
accrete revert apps/library 2          # undo change #2 (itself a checked change)
accrete serve apps/library             # http://127.0.0.1:8000/ui/books?as=ada
```

A change file:

```yaml
request: "Librarians can mark a book as damaged; damaged books cannot be borrowed"
interpretation: "Bool field writable by librarians; status derived from it"
ops:
  - add_field: {entity: books, name: damaged, type: bool, default: "False", write_if: "user.role == 'librarian'"}
  - change_field: {entity: books, name: status,
                   computed: "'damaged' if record.damaged else ('on_loan' if any(l.book == record and l.returned_at is None for l in loans) else 'available')"}
consequences: [books.action:borrow]      # the pipeline found this; listing it says "intended"
expect:
  - {as: hana, do: "PATCH /api/books/3", body: {damaged: true}, status: 403}
```

The practical guide is [`docs/GUIDE.md`](docs/GUIDE.md). It is the complete documentation that
implementers were given in the experiment.

## Documents

| Document | Contents |
|---|---|
| [`docs/MECHANISM.md`](docs/MECHANISM.md) | How it works: model, operators, footprint, replay, revert |
| [`docs/GUIDE.md`](docs/GUIDE.md) | Practical guide (operators, expressions, recipes) |
| [`docs/CANDIDATES.md`](docs/CANDIDATES.md) | The five candidate mechanisms, the small experiments, and why this one was selected |
| [`docs/TARGET.md`](docs/TARGET.md) | The quantitative target, declared before any challenge ran |
| [`docs/EXPERIMENT.md`](docs/EXPERIMENT.md) | Baseline, challenge sets, comparison procedure, how to reproduce |
| [`docs/RESULTS.md`](docs/RESULTS.md) | Results, failures, what improved and what did not, what remains unproven |
| [`docs/REVISIONS.md`](docs/REVISIONS.md) | Every design revision and the evidence that caused it |
| [`docs/FREEZE.md`](docs/FREEZE.md) | Engine checksums at the evaluation freeze |
| [`docs/ORIGINALITY.md`](docs/ORIGINALITY.md) | Qualified originality statement |
| [`docs/prior_art.md`](docs/prior_art.md) | Prior-art survey |

## Layout

```
accrete/            the engine (expr, model, runtime, ui, store, wsgi, ops, change, cli, demo)
apps/               library, expenses, maintenance: built with accrete (changes/0001-initial.yaml)
baseline/           the same three applications as conventional Flask + SQLite codebases
spec/               the external contract, the three requirement documents and their seed data
challenges/         base acceptance suites, development set D01-D14, evaluation set E01-E14 (frozen)
harness/            accept_client (test client), run_acceptance, experiment runner, analysis, latency benchmark
results/            raw per-run results (dev/, eval/), summaries, latency, transfer-build cost
experiments/        the early candidate experiments
tests/              engine regression tests
```
