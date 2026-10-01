# Change notes: approval delegation

Interpretation: a new `delegations` collection (delegator = creator, system field; delegate, starts_on, ends_on required).
Only managers create (403 otherwise); the delegate must be another manager (400 for self, non-manager or unknown id);
ends_on >= starts_on (400). Readable/listed for delegator, delegate and finance; deletable only by the delegator; PATCH is 403 for all.
A delegation is active when starts_on <= today <= ends_on (today = date of X-Now). An active delegate may read, approve and reject
claims of employees whose direct manager is the delegator (state guards unchanged, decided_by = the delegate). No chaining: only the
claim employee's direct manager's own delegations count. Approve/reject on one's own claim is always 403.

Changed (via `accrete apply app changes/0002-delegations.yaml`, ledger #2): added entity `delegations` with rules and two constraints;
claims `read` rule and the `allow` of actions `approve` and `reject` extended with the active-delegation clause (and `record.employee != user`).
No data migration needed (no delegations initially).

Verified: replay of 265 recorded requests is identical (no regressions); 16 expectations in the change file cover creation rules,
visibility, PATCH/DELETE, active window boundaries, approve/reject by delegate, segregation of duties, no chaining and deletion.
Also checked through app_entry.create_app() on a copy: claim detail UI shows approve/reject to an active delegate only when usable.
