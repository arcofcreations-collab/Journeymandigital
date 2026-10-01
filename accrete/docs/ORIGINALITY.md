# Originality statement (qualified)

**Basis.** This statement rests on the survey in `docs/prior_art.md`. That survey used web-search
snippets only: full-text fetches of the closest papers were blocked in this environment. Every
claim below should be checked against primary sources before it is relied on.

## Not new

None of these ingredients is new, and accrete does not claim them:

| Ingredient | Established by |
|---|---|
| Recording a change as a typed operator that carries its data migration and often an inverse | PRISM / PRISM++ (schema modification operators), BiDEL / InVerDa (bidirectional operators), COPE / Edapt (coupled metamodel operators), Rails reversible migrations, and recent operation-history systems (Baseline, Denicek) |
| Avoiding rename ambiguity by recording intent instead of diffing states | the same systems, plus EvolveDB |
| Deriving the API, UI, validation and permissions at runtime from a model | Naked Objects / Apache Causeway, Hasura, PostgREST / Supabase, Salesforce, Mendix, OutSystems |
| Replaying recorded traffic against an old and a new version and comparing outcomes | Twitter Diffy, GoReplay / Keploy / Speedscale, Oracle Database Replay, Percona pt-upgrade, Darklang traces |
| Separating *intended* from *unintended* behavioural change | change contracts (ISSTA 2013, hand-written); Testora and DiffTestGen (2025–26, LLM-judged from prose) |
| Blocking a schema change because existing data or dependents would break | Salesforce, and constraint operators in PRISM++ |

## What appears to be new (as far as the survey could tell)

1. **The operator-derived footprint as a deterministic replay oracle.**
   - The allowed behavioural difference of a change is *computed* from what its typed operators
     modified. It is split into **direct** effects and **consequences**, where consequences are
     reached through the model's dependency graph.
   - Every difference found by replaying recorded and generated requests on the old and new
     versions is then checked against that footprint. Unexplained differences are rejected.
     Consequences must be explicitly acknowledged, with concrete before/after examples.
   - Existing intended-change filters are either hand-written (change contracts) or judged by an
     LLM from prose (Testora, DiffTestGen). Existing replay tools filter only non-determinism.
     No system found derives the allowed difference mechanically from the change itself.
2. **One operator ledger drives the whole application lifecycle.** The same typed change:
   - transforms model and data together, with an exact inverse;
   - immediately changes the derived API, UI, validation and permissions;
   - is admitted only through a single combined gate: static obligations, re-validation of
     every stored record, footprint-scoped differential replay, then stated expectations.

   Pairs of these exist (see the table in `prior_art.md` §10); the survey found no system
   combining all of them.
3. **Change acknowledgment as part of the change.** `consequences:` records, in the ledger,
   that a side-effect was seen and intended. Revert reuses the same mechanism: it acknowledges
   the original footprint.

The defensible claim is therefore about the **integration** and the **operator-derived
footprint**, not about any single part. The closest academic work to compare against is
Edwards & Petricek's *Baseline* (operation-based data and schema evolution) and Testora (old-vs-new
differential testing with an intent filter). If either already computes allowed differences
from typed operations, claim 1 falls.

## Whether it is useful

Novelty is not the same as usefulness. Whether this combination actually makes changes
cheaper, measured end to end against a conventional AI-assisted baseline, is reported
separately in `docs/RESULTS.md`, including where it did not help.
