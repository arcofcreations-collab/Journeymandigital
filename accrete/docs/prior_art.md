# Prior-art survey: ledger of typed invertible change operators with gated evolution

Date: 2026-10-01. Scope: prior art for a system in which (A) the application is a ledger of
typed change operators, each carrying a model transform, a stored-data migration and an inverse;
(B) UI/API/validation/permissions are derived generically from the model; and every change is
gated by (C1) static consequence/obligation analysis over a model dependency graph, (C2)
re-validation of all existing data, and (C3) footprint-scoped differential replay of recorded
requests (old vs new version; differences outside the change's computed footprint are rejected).

Evidence key: **[S]** = seen only as web-search snippets in this session (WebFetch was blocked
for arxiv.org, subtext-lang.org and others; no page was fetched in full). **[K]** = background
knowledge, not re-verified in this session. Treat [S]/[K] claims as needing a primary-source
check before publication.

---

## 1. Low-code / model-driven platforms with automatic schema/data migration

| System | What it achieves | Covers | Gap vs. our design |
|---|---|---|---|
| Mendix | Domain model is synchronised to the DB on deploy; tables/columns generated; data kept "as much as possible"; values converted when attribute types change; DBAs can review DDL. Forum answers conflict on whether renames are matched by name or by stable model GUID. [S] [mendix.com sync component](https://www.mendix.com/?p=32280), [Attribute type migration](https://docs.mendix.com/refguide/attributes-type-migration/), [forum: rename](https://community.mendix.com/link/space/app-development/questions/118) | B (UI/logic from model), partial A (automatic, state-diff migration), partial C1 (Studio Pro consistency checks [K]) | Migration is inferred from model state, not carried by typed operators; no first-class inverse; no replay-based behavioural gate. |
| OutSystems | Model-driven apps; TrueChange gives technical dependency/impact analysis. Renaming an entity attribute creates a new column and leaves the old one (with data) orphaned, deliberately, so other modules' compiled queries do not break. [S] [forum](https://www.outsystems.com/forums/discussion/13670/why-a-new-database-attribute-is-created-when-you-rename-it-in-service-studio), [idea #71](https://www.outsystems.com/ideas/71/rename-entity-attributes-without-loosing-the-database-content/) | B, C1 (dependency analysis) | Rename is not a data-preserving operator; no inverse; no data re-validation or replay gate. |
| Salesforce metadata | Metadata-driven objects/fields; platform blocks field type changes when "existing data" or references (formulas, flows, validation rules) exist; deploy can be validated (checkOnly) with Apex tests. [S] [Gearset note](https://docs.gearset.com/en/articles/16818346-resolving-validation-errors-cannot-change-type-due-to-existing-data), [Metadata deploy docs](https://developer.salesforce.com/docs/atlas.en-us.daas.meta/daas/forcemigrationtool_deploy.htm) | B (generic UI/API/sharing from metadata [K]), C1 (reference-based blocking), C2-like (blocks on existing data) | Change is a metadata state diff; no carried migration/inverse; tests are hand-written, not recorded-traffic replay with an expected footprint. |
| Django admin / makemigrations | Admin UI derived from models [K]; migrations auto-generated from model diffs. | B (admin UI), partial A | See section 2 (diff-based, rename heuristic). Permissions/validation partly derived [K]. |
| Rails scaffolding / ActiveRecord migrations | Scaffolds generate code once (not a live derivation) [K]. `change` migrations are auto-reversible for known operations; others raise `IrreversibleMigration` unless `up`/`down` or `reversible` is supplied. [S] [Rails API](https://edgeapi.rubyonrails.org/classes/ActiveRecord/IrreversibleMigration.html) | A (operator-style migrations with inverses, for schema ops) | Operators are hand-written schema ops not tied to an application model that drives UI/API; no gating beyond the test suite. |
| JHipster (JDL) | Regenerates entities from JDL; Liquibase changesets per entity; modifying an existing entity rewrites its original changelog, and incremental DB change is not managed automatically. [S] [JHipster docs](https://www.jhipster.tech/creating-an-entity), [dev.to](https://dev.to/entando/how-to-use-liquibase-to-update-the-schema-of-your-jhipster-application-1cm3) | B (generated, not runtime-derived) | No incremental typed operators; data migration is manual. |
| Naked Objects / Apache Causeway | UI and REST (Restful Objects) derived generically at runtime from domain classes. [S] [Causeway docs](https://causeway.apache.org/userguide/3.4.0/ui-layout-and-hints.html) | B (strongly) | No evolution/migration machinery. |
| AFAS NEXT (Overeem, PhD 2022) | Generates tailored ERP applications from an ontological enterprise model; thesis "Evolution of Low-Code Platforms" studies evolution and event-sourced storage. [S] [thesis PDF](https://dspace.library.uu.nl/bitstream/1874/420601/1/M%20%20Overeem%20-%20thesis.pdf), [NEXT paper](https://research-portal.uu.nl/en/publications/next-generating-tailored-erp-applications-from-ontological-enterp/) | B, partial A (evolution research) | Not checked in detail; no evidence seen of replay gating with footprints. **Read this thesis before claiming originality.** |

## 2. Diff-based migration generation and rename ambiguity

- **Alembic autogenerate**: renames appear as add/drop pairs; docs say candidate migrations must always be reviewed manually. [S] [Alembic docs](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- **Django makemigrations**: the autodetector asks interactively "Did you rename X to Y?" when a removed and added field match; it cannot detect a rename if other options changed at the same time. [S] [ticket #24735](https://code.djangoproject.com/ticket/24735)
- **Prisma Migrate**: official docs say renaming a field produces a migration that drops the old column and creates a new one (data loss) unless the SQL is hand-edited (`--create-only`) or `@map` is used. One third-party page claims Prisma has rename heuristics; not verified. [S] [Prisma docs](https://www.prisma.io/docs/orm/prisma-migrate/workflows/customizing-migrations)
- **EvolveDB** (MODELS 2022 demo; SoSyM 2025): tracks edits in a model IDE to recover higher-level intent (e.g. rename) and generate migration scripts, explicitly to resolve diff ambiguity. [S] [demo](https://conf.researchr.org/details/models-2022/models-2022-tools---demonstrations/13/EvolveDB-A-tool-for-model-driven-schema-evolution), [SoSyM](https://link.springer.com/article/10.1007/s10270-025-01341-x)

Takeaway: the rename problem is well known; recording intent as operations (rather than
diffing states) is the established fix (PRISM, COPE/Edapt, EvolveDB, Baseline). Our use of
operators to avoid rename ambiguity is **not** novel by itself.

## 3. Operator-based schema evolution and coupled co-evolution

- **PRISM / PRISM++** (Curino, Moon, Deutsch, Zaniolo; VLDB 2008, PVLDB 2010, VLDBJ 2013): SQL-level Schema Modification Operators (SMOs) plus Integrity Constraint Modification Operators (ICMOs); automatic query **and update** rewriting so legacy applications keep working; evaluated on Wikipedia (240+ versions) and Ensembl (410+). PRISM also reasons about information preservation/invertibility of SMOs [K]. [S] [PRISM++](https://pubs.dbs.uni-leipzig.de/se/node/1054), [VLDBJ](https://www.doi.org/10.1007/S00778-012-0302-X)
  - Covers: A (typed operators with data migration; inverses for many SMOs), part of C1 (constraint impact). Gap: database layer only; no derived UI/permissions; no behavioural replay gate.
- **BiDEL / InVerDa** (Herrmann et al., SIGMOD 2017): bidirectional SMOs proven to satisfy symmetric-lens laws; all delta code generated; multiple schema versions co-exist and see each other's writes. [S] [arXiv 1608.05564](https://arxiv.org/pdf/1608.05564)
  - Covers: A (operators that are bidirectional/invertible by construction). Gap: DB-only, no derived app layer, no replay gate.
- **COPE / Eclipse Edapt** (Herrmannsdoerfer et al., ECOOP 2009; operator catalogue 2011): metamodel adaptation recorded as an explicit history of *coupled operations* that bundle metamodel change with model migration. [S] [ECOOP 2009 PDF](https://wwwbroy.in.tum.de/publ/papers/ECOOP2009_herrmannsdoerfer_cope_automating_coupled.pdf), [catalogue](https://www.springerprofessional.de/an-extensive-catalog-of-operators-for-the-coupled-evolution-of-m/3604466)
  - Covers: A almost exactly (history/ledger of coupled operators). The catalogue classifies operators by preservation properties and gives inverses for many [K]. Gap: models, not a running application with stored requests; no derived runtime; no replay gate.
- **Maule, Emmerich, Rosenblum** (ICSE 2008): static dataflow/slicing to predict the impact of schema changes on application code. [S] [record](https://pubs.dbs.uni-leipzig.de/se/node/974)
  - Covers: C1 (static consequence analysis), for hand-written code.

## 4. Lenses and bidirectional schema evolution

- **Cambria** (Ink & Switch, 2020): composable bidirectional lenses translate JSON documents between schema versions on demand so old and new clients interoperate; TypeScript library; formalised with edit lenses (MIT thesis). [S] [Cambria](https://inkandswitch.com/cambria), [MIT thesis](https://dspace.mit.edu/handle/1721.1/145983)
- **Boomerang / edit lenses** (Hofmann, Pierce, Wagner, POPL 2012): lenses that translate edits rather than whole states. [S] [Edit Lenses](https://repository.upenn.edu/cis_papers/677)
- Covers: A's "inverse" aspect, with laws. Gap: data translation only; no derived app, no obligation analysis, no behavioural replay gate.

## 5. Event sourcing and Datomic

- **Event-sourcing schema evolution** (Overeem et al., JSS 2021): five tactics observed in industry: versioned events, weak schema, upcasting, in-place transformation, copy-and-transform. [S] [paper](https://dspace.library.uu.nl/bitstream/1874/412217/1/1_s2.0_S0164121221000674_main.pdf)
  - Covers: an append-only ledger (of *data* events, not *model* changes) and replayable history. Upcasters are per-event migrations, typically hand-written and one-directional.
- **Datomic**: "grow your schema, and never break it": accretion-only production schema; breaking changes are dev-only. [S] [Ten rules of schema growth](https://blog.datomic.com/2017/01/the-ten-rules-of-schema-growth.html)
  - Covers: a philosophy that avoids the need for inverse migrations. Not an operator system.

## 6. Content-addressed, deployless and live systems

- **Unison**: definitions identified by content hash; names are metadata, so renames are exact and never break dependants. [S] [SoftwareMill](https://softwaremill.com/trying-out-unison-part-1-code-as-hashes/) Covers the code-level rename problem; persistent-data migration is a separate concern [K].
- **Darklang (Classic)**: "deployless": deploys are AST diffs written to a DB; trace-driven development records real requests (inputs plus function results) and lets developers replay handlers on them in the editor. [S] [trace-driven development](https://docs.darklang.com/discussion/trace-driven-development), [overview](https://docs.darklang.com/introduction)
  - Covers: recorded real requests replayed against new code (a strong precursor to C3). Gap: replay is an interactive developer aid, not an automated old-vs-new gate with an expected footprint; no operator-carried migrations/inverses seen.
- **Smalltalk images**: live object memory; class reshaping migrates existing instances automatically when instance variables change; change sets record edits [K]. Gap: no typed data-migration operators beyond reshaping, no gating.
- **Edwards, Petricek, van der Storm, Litt, "Schema Evolution in Interactive Programming Systems"** (Programming 2025): challenge problems and a taxonomy for schema evolution across DBs, live front-ends, model-driven development and notebooks. [S] [journal](https://programming-journal.org/2025/9/2/)
- **Denicek** (Petricek & Edwards, UIST 2025): a program is a series of edits building a document of data and formulas; operations are edit application, merge and conflict resolution; supports "schema change control", programming by demonstration, incremental recomputation. [S] [paper page](https://tomasp.net/academic/papers/denicek/)
- **Baseline** (Edwards & Petricek, arXiv 2512.09762, Dec 2025): data managed as high-level operations including refactorings and schema changes ("Operational Differencing"); fine-grained diff/merge across schema changes; queries "operationalized" and rewritten for schema change "for free". [S] [arXiv](https://www.arxiv.org/abs/2512.09762)
  - **Closest academic match for A** (operation ledger in which schema change and data change are the same kind of thing). Gap as far as snippets show: no derived API/permissions layer for a multi-user service, no recorded-request replay gate, no footprint. Needs a full read.

## 7. Relational / declarative application languages and schema-derived APIs

- **Out of the Tar Pit** (Moseley & Marks, 2006): Functional Relational Programming: essential state relational, logic declarative, accidental state separated. [S] [Recurse summary](https://www.recurse.com/blog/51-paper-of-the-out-of-the-tar-pit) Design philosophy behind B; no evolution story.
- **Eve** (Kodowa, 2014-2018): everything is a record; pattern-matching blocks; shut down 2018. [S] [FoC catalog](https://futureofcoding.org/catalog/eve.html)
- **Bloom / Dedalus** (Berkeley BOOM): Datalog with time; CALM analysis of where coordination is needed. [S] [BOOM](https://boom.cs.berkeley.edu) Static analysis over a declarative program (analogous in spirit to C1, different property).
- **Ur/Web** (Chlipala): one typed program yields server, client and SQL; well-typed programs cannot emit invalid SQL/HTML or have form/handler mismatches. [S] [Wikipedia](https://en.wikipedia.org/wiki/Ur_(programming_language)) Strong static guarantees across layers; no evolution/migration support.
- **Hasura**: GraphQL API introspected from the DB; row- and column-level permission rules; per-role schema; permission predicates compiled into SQL. [S] [docs](https://hasura.io/docs/2.0/auth/authorization/roles-variables/)
- **PostgREST / Supabase**: REST API (with OpenAPI) reflected from the Postgres catalog; authz is Postgres roles + RLS; API changes as soon as the schema changes. [S] [PostgREST authz](https://postgrest.org/en/latest/schema_structure.html), [Supabase API](https://supabase.com/docs/guides/api)
- Covers: B (API and permissions derived from schema) is established practice. Gap: they delegate migration to external tools and do not gate schema changes on behaviour.

## 8. Differential / record-replay regression testing

- **Diffy** (Twitter, 2015): proxy multicasts each request to candidate, primary and a second primary; differences that also occur primary-vs-primary are treated as noise. [S] [blog](https://blog.x.com/engineering/en_us/a/2015/diffy-testing-services-without-writing-tests)
  - Covers: C3's old-vs-new comparison and noise filtering. Gap: noise is *empirical* (non-determinism); there is no notion of *intended* difference derived from the change.
- **Traffic replay tools**: GoReplay, Keploy, Speedscale, AREX record production traffic (and dependency calls) and replay against a new version, reporting response diffs; diff suppression is configured manually. [S] [Speedscale guide](https://speedscale.com/blog/definitive-guide-to-traffic-replay/), [Keploy](https://keploy.io/record-replay-testing), [GoReplay](https://goreplay.org/)
- **Oracle Database Replay / Real Application Testing**: capture production workload, replay on changed system, report errors and *data divergence* in rows returned. [S] [Oracle docs](https://docs.oracle.com/cd/B28359_01/server.111/e12253/dbr_analyze.htm)
- **Percona pt-upgrade**: replays logged queries on two MySQL servers and reports result differences. [S] [docs](https://docs.percona.com/percona-toolkit/pt-upgrade.html)
- **Change contracts** (Yi, Qi, Tan, Roychoudhury, ISSTA 2013; TOSEM 2015): JML-based specification of *intended* behavioural change between versions, without specifying unchanged behaviour; checked against the new version. [S] [ISSTA PDF](https://www.comp.nus.edu.sg/~abhik/pdf/issta13.pdf)
  - **Conceptually closest to the "footprint"**: an explicit statement of what may change. Gap: written by hand; not computed from a typed operator; not applied to recorded traffic.
- **Differential assertion checking / SymDiff** (Lahiri et al.): static relative-correctness checking between two versions. [S] [MSR](https://www.microsoft.com/en-us/research/publication/differential-assertion-checking/)
- **Shadow symbolic execution** (Kuchta, Palikareva, Cadar, ICSE 2016, TOSEM 2018): runs old and new versions together to generate inputs exercising divergences. [S] [project](https://srg.doc.ic.ac.uk/projects/shadow/index.html)
- **Golden-master / approval testing** and **change impact analysis** for regression-test selection are standard practice [K]; impact analysis selects *which tests to run*, not *which differences are allowed*.

## 9. AI-era approaches (2024-2026)

- **GitHub Spec Kit** (2025): Specify, Plan, Tasks, Implement phases with checkpoints; agents implement from specs. [S] [Spec Kit](https://github.github.com/spec-kit/)
- **Tessl** (2025): "spec-as-source": code regenerated from specs; critics note LLM non-determinism undermines regeneration. [S] [review](https://codemyspec.com/blog/tessl-review), [launch](https://tessl.io/blog/tessl-launches-spec-driven-framework-and-registry)
- **Copilot Workspace**: spec, plan, implement workflow; preview sunset 30 May 2025, replaced by Copilot coding agent. [S] [GitHub Next](https://githubnext.com/projects/copilot-workspace)
- **Testora** (Pradel, software-lab.org; arXiv 2503.18597; ICSE 2026): LLM-generated tests run on old and new code; behavioural differences classified as intended or unintended against the PR's natural-language description; found 19 regressions in keras/marshmallow/pandas/scipy at about $0.003 per PR. [S] [arXiv](https://arxiv.org/abs/2503.18597)
- **DiffTestGen** (arXiv 2607.16024, 2026): change-directed LLM test generation exposing behavioural differences, with an LLM classifier for intended vs. regression. [S] [arXiv](https://arxiv.org/abs/2607.16024)
  - These two are the **closest matches for C3's intent filter**. Difference: they judge "intended" with an LLM reading prose; our footprint is computed mechanically from typed operators, so the check is deterministic and needs no prose oracle. They also use generated tests, not recorded production requests.
- **Living Databases** (Deshpande, arXiv 2605.00676, 2026): unifies schema evolution, versioning and transformations under one abstraction with provenance and controlled propagation to dependent views/artifacts. [S] [arXiv](https://arxiv.org/abs/2605.00676)
- Spec-driven tools address *what to build*; none seen gates changes with data re-validation or footprint-scoped replay.

## 10. Combinations (the key question)

Searched specifically for systems combining (A) typed invertible operators with data migration,
(B) runtime-derived UI/API/permissions, and (C3) replay-based gating with an expected-difference
footprint. **No single system or paper found combines all three.** Pairwise overlaps found:

| Combination | Nearest examples |
|---|---|
| A + C1 | PRISM++ (ICMOs, constraint impact), COPE/Edapt operator catalogue |
| A + B (partial) | Mendix / OutSystems / AFAS NEXT (model-driven runtime + automatic migration, but state-diff not operator ledger); Baseline/Denicek (operation histories, document-scale UI) |
| B + permissions | Hasura, PostgREST/Supabase, Naked Objects, Salesforce |
| C3 without footprint | Diffy, GoReplay/Keploy/Speedscale, Oracle Database Replay, pt-upgrade, Darklang traces |
| C3 with intended-change filter | Testora, DiffTestGen (LLM + prose intent); change contracts (hand-written) |
| C2 | Salesforce blocking type changes on existing data; Mendix type conversion; generic data-validation migrations [K] |

## Closest matches and remaining gap

In plain language:

- **Recording changes as typed operations that carry their data migration (and often an inverse) already exists**: PRISM/PRISM++ and BiDEL for databases, COPE/Edapt for models, Rails reversible migrations in practice, and Baseline/Denicek for live documents and data. We should not claim this as new.
- **Deriving API, UI and permissions from a model is established**: Naked Objects, Hasura, PostgREST/Supabase, Salesforce, Mendix/OutSystems.
- **Replaying real traffic against old and new versions and diffing is established**: Diffy, traffic-replay tools, Oracle Database Replay, Darklang traces.
- **Separating intended from unintended behavioural change is an active 2025-2026 research topic** (Testora, DiffTestGen), and was proposed earlier with hand-written change contracts (ISSTA 2013).

What we did **not** find (qualified: search-snippet evidence only, no full-text review):

1. A system in which the *allowed* behavioural difference (the footprint) is **computed automatically from the typed change operator** and used as a **deterministic oracle** for old-vs-new replay of **recorded real requests**. Existing intent filters are either LLM-judged prose (Testora, DiffTestGen) or hand-written (change contracts); existing replay tools only filter noise.
2. A single system that uses one operator ledger to drive **all three** of: data migration and inverse, the derived runtime (UI/API/validation/permissions), and a combined admission gate (static obligations + full data re-validation + footprint-scoped replay).

A defensible claim is therefore about the **integration** and specifically the
**operator-derived footprint as a replay oracle**, not about any single ingredient.
Before publishing, read in full: Baseline (arXiv 2512.09762), Denicek (UIST 2025), Overeem's
thesis (AFAS NEXT), the Herrmannsdoerfer operator catalogue, Testora and DiffTestGen, and the
change-contracts TOSEM paper.

## Search log (all WebSearch queries run 2026-10-01; "(ext)" = extended mode)

- Section 1: Mendix domain model automatic database synchronization data migration; Mendix rename attribute data preserved unique id; OutSystems attribute rename data model impact TrueChange; Salesforce metadata API field type change dependency deploy validation; JHipster JDL regeneration Liquibase changelog incremental; Rails reversible migrations irreversible rollback; Naked Objects UI generated from domain model Apache Causeway; Overeem AFAS low-code model-driven ERP evolution thesis.
- Section 2: Prisma migrate rename column detection data loss; Django makemigrations "Did you rename" questioner autodetector; Alembic autogenerate cannot detect column rename; EvolveDB model-driven schema evolution.
- Section 3-4: PRISM++ SMOs integrity constraints query rewriting; COPE Edapt coupled evolution Herrmannsdoerfer operators; InVerDa BiDEL bidirectional database evolution language; Cambria Ink & Switch lenses; edit lenses Hofmann Pierce Wagner Boomerang; Maule Emmerich Rosenblum impact analysis of database schema changes.
- Section 5-6: event sourcing upcasting Overeem empirical study; Datomic "grow your schema"; Unison content-addressed rename; Darklang deployless trace-based replay; Darklang classic traces replay handler; "Schema Evolution in Interactive Programming Systems"; Baseline operation-based evolution (two queries); Denicek edit history; Lamdera Evergreen typed migrations (inconclusive: Lamdera's type-checked migrations between Elm versions are relevant to A but were not verified).
- Section 7: Hasura permissions derived GraphQL; PostgREST API and RLS; Supabase RLS auto-generated API; Ur/Web static guarantees; Bloom/Dedalus CALM; Eve Kodowa; Out of the Tar Pit.
- Section 8: Twitter Diffy noise filtering; pt-upgrade Percona replay; Oracle Database Replay divergence; software change contracts ISSTA; differential assertion checking Lahiri; shadow symbolic execution Kuchta Palikareva Cadar.
- Section 9: GitHub Spec Kit; Copilot Workspace sunset; Tessl spec-centric regeneration; Testora results; LLM agent database schema migration safety verification (ext; nothing directly relevant); "Living Databases" arXiv 2026.
- Section 10 (close-match hunting): "intent-aware" differential testing (ext); intended vs unintended behavioural changes differential testing (ext); coupled evolution schema migration regression testing replay production traffic (ext); semantic diff "expected changes" differential regression testing (ext); application as log of change operations inverse operations derived UI low-code (ext); traffic replay expected diff allowlist schema change (ext); differential testing "frame condition"/"footprint" allowed difference (ext; no match).

WebFetch attempts on arxiv.org/abs/2512.09762 and subtext-lang.org/baseline.html were blocked
by the egress proxy; no source was read in full.
