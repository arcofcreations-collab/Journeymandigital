# Candidate mechanisms and how one was selected

Before building anything substantial I wrote down five candidate answers to "what would make a
change after the first build cheap?", ran the smallest experiment that could *disprove* four of
them, and selected on that evidence. The experiments are in `experiments/early_experiments.py`.
Their output is in `results/early_experiments.json`. They are deliberately tiny: each one tests
one assumption, not a whole system.

The common diagnosis behind all five: in conventional code a change is expensive mainly because
one intent ("rename author to writer", "require a receipt above 75") is smeared across many
artifacts: schema, migration, model class, validation, handlers, templates, permission checks
and tests. Each artifact must be found, edited consistently and re-verified. A cheaper form of
programming must either remove the smearing, or make it mechanical *and* checked.

---

## C1: Declarative spec + diff-inferred migration

- **Central idea.** The app is a declarative spec (like Prisma, Django models, or an OpenAPI plus
  schema document). You edit the spec. The tool diffs old against new and infers the migration
  and code changes.
- **Why changes would get cheaper.** You edit one file and everything else is generated.
- **Assumption challenged.** That a change has to be written as edits to many artifacts.
- **Smallest experiment.** Rename `author` to `writer` in a 5-record spec and let the diff infer
  the migration.
- **Result.** The diff sees "removed author, added writer". **5 of 5 values are lost** unless a
  human supplies the hint "this was a rename". The diff of two states does not contain the
  intent: rename, split, merge and enum remapping are all indistinguishable from drop + add.
- **Weakness.** The *state* is declarative, but the *change* is not. The step that matters is the
  one that cannot be inferred.
- **Decision.** Rejected as the core. The derivation half (one model → API, UI, validation) is
  kept.

## C2: Ledger of typed, invertible change operators (selected, core)

- **Central idea.** The program is not its current source. It is an ordered ledger of *typed
  change operators* (`rename_field`, `add_constraint(existing: exempt)`,
  `change_field(map: {...})`, `promote_field`, ...). Each operator transforms the model, every
  dependent expression *and* the stored data together, and returns its exact inverse.
- **Why changes get cheaper.**
  - The intent is the operator, written once.
  - Its consequences for data, dependents and undo are part of the operator's definition, not
    re-derived by the person making the change.
- **Assumption challenged.** That code and data migrations are separate artifacts that must be
  kept consistent by hand.
- **Smallest experiment.** The same rename as an operator.
- **Result.**
  - The dependent rule `visible` was rewritten.
  - All values were preserved.
  - Applying the returned inverse restores model and data **exactly** (structural equality).
- **Weakness.**
  - It only covers what the operator vocabulary covers. Something unanticipated needs either a
    new operator or a fallback (e.g. `update_records` with an expression).
  - Rewriting dependents requires analysing the expression language, so expressions must be
    restricted to a language the system understands.
- **Decision.** Selected as the core representation.

## C3: Everything as relational rules (Datalog-style)

- **Central idea.** Behaviour is a set of rules over facts, and derived state is a fixpoint.
  Adding a concept means adding a rule.
- **Why changes would get cheaper.** Rules are local and order-independent. A new derived
  concept needs no coordination.
- **Assumption challenged.** That behaviour must be written as procedures.
- **Smallest experiment.** Add a "discounted" concept by rule, then attempt a rename.
- **Result.**
  - Adding the concept was a single local rule (books 3, 4, 5 derived correctly).
  - **A rename is not expressible as a rule:** stored facts must be rewritten by an outside
    process. This was established by inspecting the formalism, not by running a failing case.
    The experiment records it as an argued result.
  - UI and permissions were not derived.
- **Weakness.**
  - Strong for derived data.
  - Says nothing about stored-data evolution, which is where much of the change cost lies.
  - Imperative effects (notifications, state transitions) are awkward.
- **Decision.** Not selected as the core. The idea that *derived fields are expressions, never
  stored* is kept: accrete computed fields and rules are side-effect-free expressions.

## C4: Footprint-scoped differential replay as the regression gate (selected, verification layer)

- **Central idea.** Every change declares (or has computed) a *footprint*: what it is allowed to
  change. The old and new versions are run side by side on recorded real requests plus
  generated probes. Every observable difference must be explained by the footprint; anything
  else blocks the commit.
- **Why changes get cheaper.** The expensive part of a safe change is proving that *nothing
  else* changed. Conventionally that requires writing and maintaining tests. Here the previous
  version of the app is the oracle, so no new test is required to detect a regression.
- **Assumption challenged.** That regression safety requires hand-written tests proportional to
  the size of the app.
- **Smallest experiment.** A 20-request history. One intended change (price threshold) and one
  accidental change (a visibility rule flipped alongside it).
- **Result.**
  - Intended: 2 differences, 0 outside the footprint, **accepted**.
  - Accidental: 12 differences, 10 outside the footprint, **rejected**.
- **Weakness.**
  - It can only see differences that the recorded or generated requests exercise.
  - The first full implementation auto-accepted everything that *depended* on the change, which
    is too permissive. It was redesigned to separate *direct* effects from *consequences* that
    must be acknowledged. See `docs/REVISIONS.md`.
- **Decision.** Selected as the verification layer on top of C2.

## C5: Regenerate the whole app from a natural-language spec on every change (considered, not run)

- **Central idea.** Keep only the requirements text. After each change, have an AI regenerate
  the application and a data migration from scratch.
- **Why it was not run.** It inherits C1's flaw (the migration must still be inferred from two
  states). It adds nondeterminism: two regenerations of unchanged requirements need not be
  behaviourally identical, so every change would need full re-verification. Its experiment
  would cost a full app build per data point. The conventional baseline already measures the
  "AI edits a codebase" path more fairly.
- **Decision.** Not pursued. Recorded so the space of options is visible.

---

## What was built

**accrete = C2 + C4 + the derivation half of C1 + the expression discipline of C3.**

- **Model and runtime.** One model (entities, fields, rules, constraints, actions, triggers) is
  interpreted by a generic runtime. The runtime derives the API, the UI, validation,
  permissions, derived fields and outbox messages. Nothing about the app is written twice.
- **Ledger of operators.** The model and its data change *only* through a ledger of typed,
  invertible operators. Stored records are keyed by stable field ids, so renames never touch
  data.
- **Pipeline.** Each change runs through: static obligations, a data re-validation of every
  record, footprint computation, differential replay (corpus + generated + focus probes),
  stated expectations, then an atomic commit with a full report and the inverse. A rejected
  change is also recorded with its reason.

The selection was made on the evidence above, before the challenge sets existed. Whether it
actually makes changes cheaper end to end is the question answered by the experiments in
`docs/RESULTS.md`, not by this document.
