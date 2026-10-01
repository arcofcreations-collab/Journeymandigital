# Change-challenge format

A challenge is a change request to an existing application (library or expenses, as specified
in spec/). Two independent teams will implement each challenge, each on their own
implementation of the application, given only the BRIEF (see below). Your hidden tests then
decide whether they succeeded. Nobody implementing sees your tests.

Each challenge lives in `challenges/<set>/<ID>/` with three files:

## meta.json
{
  "id": "D01",
  "app": "library" | "expenses",
  "categories": [...],            # from the category list below
  "depends_on": null | "D07",     # this challenge is applied to the result of an earlier one
  "expect_rejection": false,      # true if a correct implementer must NOT carry out the request
  "brief": "...",                 # EXACT text given to implementers: the request plus observable
                                  # acceptance criteria, behaviour to preserve, data requirements
  "superseded_base_tests": ["test_name", ...]   # base tests (tests/base/*.py) that the change
                                  # intentionally makes false; all other base tests must still pass
}

## challenge.md  (frozen criteria, written BEFORE any implementation exists)
1. Requested outcome
2. Observable acceptance criteria
3. Behaviour that must remain intact
4. Existing-data requirements
5. Failure and recovery conditions
6. Measurements to collect (the harness always collects: success, hidden-test pass rate,
   base-suite regressions, data integrity, elapsed time, tool calls, tokens)

## test_<ID>.py  (hidden acceptance tests)
pytest, using only `from accept_client import fresh_app, parse_ui`; a fresh app per test; explicit
user= and now=. Test the observable outcome, preserved behaviour near the change, and existing
data (seed records must be preserved or migrated as the brief requires). For
expect_rejection challenges, test that behaviour is unchanged AND that the file
`CLARIFICATION.md` exists in the app directory: `os.path.exists(os.path.join(app.workdir, "CLARIFICATION.md"))`.

Implementers are told: "If a request must not be executed as stated (contradictory, unsafe,
too ambiguous), leave the application unchanged and write CLARIFICATION.md in the application
directory. If you resolve an ambiguity with a reasonable documented interpretation, note it in
CHANGE_NOTES.md." So a challenge that is ambiguous but resolvable should specify, in the brief,
the policy the implementer must follow, or test only the parts that are unambiguous.

The brief may introduce new endpoints only of the contract's shapes (new collections, new
fields, new actions `POST /api/{collection}/{id}/{action}`, outbox channels). New collections
and fields need exact names in the brief so tests can call them.

## Categories (cover all of them across the set; most challenges should combine several)
cross_cutting (new behaviour with consequences across several parts), new_concept (a concept the
apps do not have at all), rule_change, data_migration (existing records must be transformed),
new_relationship (link previously unrelated features), permissions, failure_atomicity (failed
operations / partial execution must leave no trace), conflict_or_ambiguity, reversal (undo an
earlier change), sequence (several changes accumulating), interaction (two independently
introduced capabilities that must work together), should_reject.
