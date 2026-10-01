# F07 (maintenance)

Size: medium. Categories: new_concept, failure_atomicity, cross_cutting, permissions, rule_change.

## 1. Requested outcome

Supervisors can move an asset to another site in one atomic operation that returns assigned work to the new site's pool and notifies integrations once.

## 2. Observable acceptance criteria

- transfer moves the site, un-assigns `assigned` orders (status open, assignee null), leaves open/finished orders, returns the asset.
- One `asset_transferred` message with from/to sites and the ascending list of un-assigned ids.
- 403 (non-supervisor) -> 409 (retired or in_progress order) -> 400 (site missing/blank/same/unknown, extra fields).
- Visibility, assignment and creation follow the new site.
- PATCH of `site` is 400; UI transfer form for supervisors when allowed.

## 3. Behaviour that must remain intact

Assign/start/complete/cancel, retire rule, asset creation, other outbox channels, base read rules.

Superseded base tests (0): none.

## 4. Existing-data requirements

No migration; seed assets/orders unchanged until a transfer is made.

## 5. Failure and recovery conditions

Every refused transfer leaves staff, assets, work orders and the outbox identical (snapshot comparison).

## 6. Measurements to collect

Harness defaults (success, hidden-test pass rate, base-suite regressions against the superseded list, data integrity, elapsed time, tool calls, tokens).

- Refused operations that left any trace (records, related collections or outbox) in the snapshot tests.
- 403-ordering failures (a 400/409 returned where the brief requires 403 first).
