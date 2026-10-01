"""Writes challenges/eval/<ID>/meta.json from the definitions below (author tooling)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "challenges", "eval")

M = {}

SUP_E01 = ["test_assignee_completes_order_and_emits", "test_full_lifecycle"]

M["E01"] = dict(
    app="maintenance",
    categories=["new_concept", "new_relationship", "failure_atomicity", "cross_cutting"],
    depends_on=None,
    brief="""Spare parts inventory with atomic part consumption (maintenance).

Technicians need to record the spare parts they use on a work order, and stock must stay correct.

1. New collection `parts`: `sku` (text, required, unique), `name` (text, required), `site` (text, required), `unit_cost` (JSON number >= 0, required), `quantity` (JSON integer >= 0, required), `reorder_level` (JSON integer >= 0, required), `low_stock` (derived boolean: `quantity <= reorder_level`). Settable on create and PATCH: the six stored fields; anything else (including `low_stock`, `id`, unknown names) -> 400. Invalid values (wrong type, negative, string numbers, booleans as numbers, empty required text) -> 400; duplicate `sku` -> 400. Every authenticated user can read all parts. Only supervisors can create, PATCH or DELETE parts (403 for everyone else, winning over 400). Deleting a part that has any part usage -> 409.

2. New collection `part_usages` (history, read-only through the API): `work_order` (reference), `part` (reference), `quantity` (integer), `unit_cost` (number: the part's `unit_cost` at the moment of use), `used_by` (reference to staff), `used_at` (datetime). A usage is readable exactly by the users who can read its work order (lists contain only those; direct access otherwise 403). POST, PATCH and DELETE on part_usages -> 403 for everyone.

3. New action `POST /api/work_orders/{id}/use_parts` with body `{"items": [{"part": <part id>, "quantity": <integer>}, ...]}`.
   - Permission: only the work order's current `assignee` (403 otherwise). State: only while `in_progress` (409 otherwise).
   - Validation (400): `items` must be a non-empty list; each item must be an object with exactly the keys `part` and `quantity`; `part` must be the id of an existing part whose `site` equals the site of the work order's asset; `quantity` must be a JSON integer >= 1 (not a boolean, decimal or string); the same part may appear at most once.
   - Stock: if any item that names a valid part with a valid quantity asks for more than that part's current `quantity`, the response is 409. Following the contract's precedence this 409 wins even when another item of the same request is invalid.
   - Success: for each item, in list order, one `part_usages` record is created (so their ids ascend in list order) with `used_by` = the caller and `used_at` = now, and the part's `quantity` decreases by the item's quantity. For every part whose `low_stock` changes from false to true because of this call, one outbox message is emitted on channel `low_stock` with payload `{"part": <id>, "sku": <sku>, "quantity": <new quantity>}`, in list order (a part that was already low emits nothing). Returns the work order.
   - Atomicity: a failed call (any error) creates no usage, changes no quantity and emits nothing.

4. New derived field `parts_cost` on work orders: the sum over the order's part usages of `quantity * unit_cost` (the usage's stored unit_cost), rounded to 2 decimals; 0 when it has none. Changing a part's `unit_cost` later does not change existing usages or any `parts_cost`. Like every derived field it cannot be sent in a body (400).

5. The `work_completed` outbox payload gains the key `parts_cost` (the order's parts_cost at completion); it is now exactly `{"work_order", "asset", "technician", "labor_minutes", "parts_cost"}`. The `assignment` payload is unchanged.

6. Cancelling a work order does not return parts to stock; its usages and parts_cost remain.

7. UI: `/ui/parts` and `/ui/part_usages` lists and detail pages follow the read rules; `/ui/parts/new` is for supervisors only (403 otherwise) with inputs for the six stored fields; on `/ui/work_orders/{id}` a `use_parts` form is shown exactly when the caller is the assignee and the order is `in_progress`.

Data requirements: all existing records stay unchanged. Create exactly these parts with these ids (sku, name, site, unit_cost, quantity, reorder_level):
1 FLT-AHU, AHU filter, North, 42.5, 12, 4
2 BELT-A40, V-belt A40, North, 18.0, 3, 2
3 FUSE-10A, Fuse 10A, North, 1.25, 50, 10
4 BRG-6204, Bearing 6204, South, 9.8, 6, 2
5 BELT-A40-S, V-belt A40, South, 18.0, 2, 2
6 SEAL-KIT, Pump seal kit, South, 64.0, 1, 0
7 LAMP-LED, LED lamp, East, 7.4, 20, 5
8 REMOTE-DK, Dock door remote, North, 23.9, 0, 1
There are no part usages initially, so every existing work order has parts_cost 0. New parts get ids above 8.

Behaviour to preserve: everything in maintenance.md, including the assign/start/complete/cancel rules and their error precedence, read permissions and the `assignment` payload.""",
    superseded_base_tests=SUP_E01,
)

SUP_E02 = SUP_E01 + ["test_outbox_readable_by_any_user"]

M["E02"] = dict(
    app="maintenance",
    categories=["new_concept", "permissions", "rule_change", "data_migration", "conflict_or_ambiguity", "sequence"],
    depends_on="E01",
    brief="""Technician self-dispatch and a workload cap (maintenance, applied after E01).

Technicians may now pick up open work orders themselves, and nobody may be overloaded.

1. New action `POST /api/work_orders/{id}/claim` with body `{}`: a technician takes an open work order for themselves.
   - Permission: only staff whose `role` is `technician`, whose `active` is `true` and whose `site` equals the site of the order's asset; anyone else gets 403.
   - State: only from `open`, otherwise 409. Workload: if the caller is already the assignee of 3 or more work orders whose status is `assigned` or `in_progress`, 409.
   - Effect: `assignee` = the caller, `status` = `assigned`, `dispatch` = `"self"`. Emits an outbox message on channel `assignment` with the same payload as `assign`: `{"work_order": id, "asset": asset id, "technician": staff id}`. Returns the work order.
2. Workload cap for `assign`: if the chosen technician (one that passes the existing technician validation) is already the assignee of 3 or more `assigned`/`in_progress` work orders, not counting the order being assigned, the response is 409 and nothing changes or is emitted. Consequently re-assigning an order to its current assignee is always allowed. Order of checks for assign: 403 (not a supervisor), 409 (order not open/assigned), 400 (invalid technician: the cap is only evaluated for a valid technician), 409 (cap) - i.e. an invalid technician is a 400 and a valid technician at the cap is a 409.
3. New read-only field `dispatch` on work orders: `"supervisor"`, `"self"` or `null`. `assign` sets it to `"supervisor"` (also on re-assignment), `claim` sets it to `"self"`; new orders start with `null`. Sending it in a create or PATCH body -> 400. It can be used as a list filter like any other field (`?dispatch=null` matches null).
4. UI: on `/ui/work_orders/{id}` a `claim` form is shown exactly when a claim by the caller would succeed right now (permission, state and the caller's current workload).

Data requirements: for every existing work order that has an assignee, `dispatch` = `"self"` when the assignee is also its `requested_by`, otherwise `"supervisor"`; orders without an assignee get `null` (this applies to all statuses, including cancelled ones). Policy for existing overload: workloads already above the cap (one technician currently has 4 active orders) are kept exactly as they are - no order is unassigned or changed; such a technician simply cannot receive further orders (by assign or claim) until their workload drops below 3. No other record changes.

Behaviour to preserve: everything from maintenance.md and E01 (parts, use_parts, parts_cost, low_stock, work_completed payload), including that requesters can cancel or edit their order only while it is `open`, and that a claimed order then follows the normal start/complete/cancel rules.""",
    superseded_base_tests=SUP_E02,
)

SUP_E03 = ["test_work_order_read_permissions", "test_work_order_fields_match_seed", "test_due_date_and_overdue_derived",
           "test_overdue_uses_now_date_boundary", "test_work_order_filters", "test_requester_creates_work_order_defaults",
           "test_create_due_dates_per_priority", "test_create_site_rule", "test_inactive_staff_can_create_orders",
           "test_requester_patches_open_order", "test_supervisor_patch_priority_recomputes_due_date",
           "test_supervisor_assigns_open_order", "test_assignee_completes_order_and_emits", "test_full_lifecycle",
           "test_other_operations_emit_nothing", "test_outbox_readable_by_any_user", "test_ui_work_order_detail_fields"]

M["E03"] = dict(
    app="maintenance",
    categories=["rule_change", "data_migration", "cross_cutting", "interaction", "sequence"],
    depends_on="E02",
    brief="""Priority scale p1-p4 (maintenance, applied after E02).

The three priorities are replaced by a four-level scale that also takes the asset's criticality into account.

1. `priority` on work orders now takes exactly `"p1"` (most urgent), `"p2"`, `"p3"` or `"p4"`. The old values `"urgent"`, `"normal"` and `"low"` (and anything else, including other spellings such as `"P1"`) are rejected with 400 on create and PATCH. A list filter with an old value is still a valid filter that simply matches nothing.
2. `due_date` (derived) is the date part of `created_at` plus 1 day (p1), 3 days (p2), 7 days (p3) or 30 days (p4). As before it follows the current priority, for every order regardless of status; `overdue` is derived from it as before.
3. New validation rule: a work order whose asset has `criticality` `"high"` may not be given priority `"p4"`: a create or PATCH that sets `p4` on such an order is 400, even when the order already has `p4`. The existing precedence stays (e.g. the requester/technician site rule 403 still wins over this 400; on a finished order the PATCH 409 still wins).
4. Interaction with self-dispatch (E02): technicians may only `claim` orders whose current priority is `p3` or `p4`. Claiming a `p1` or `p2` order is 403 (a permission rule, so it wins over the state and workload 409s). The UI `claim` form follows this rule. Supervisors still `assign` orders of any priority (workload cap unchanged).

Data requirements: every existing work order, in any status, is migrated: `urgent` -> `p1`; `normal` -> `p2` if its asset's `criticality` is `high`, otherwise `p3`; `low` -> `p4`. Policy for the conflict with rule 3: existing `low` orders on high-criticality assets also become `p4` and keep it (the rule only refuses *setting* p4); their other fields stay editable as before. No other field of any record changes (due dates change only because they are derived).

Behaviour to preserve: E01 (parts, use_parts, parts_cost, low_stock, work_completed payload) and E02 (claim, dispatch, workload cap) apart from the claim restriction above; every other rule of maintenance.md.""",
    superseded_base_tests=SUP_E03,
)

SUP_E04 = SUP_E03[:13] + ["test_complete_validation"] + SUP_E03[13:] + ["test_ui_actions_per_role_and_state"]

M["E04"] = dict(
    app="maintenance",
    categories=["new_concept", "data_migration", "rule_change", "interaction", "sequence"],
    depends_on="E03",
    brief="""Time logging replaces the labor figure entered at completion (maintenance, applied after E03).

Technicians log their working time while an order is in progress; the labor total is computed from those entries.

1. New collection `time_entries`: `work_order` (reference to work_orders), `technician` (reference to staff), `minutes` (integer), `logged_at` (datetime), `note` (text or null). A time entry is readable exactly by the users who can read its work order (lists contain only those, direct access otherwise 403). POST, PATCH and DELETE on time_entries -> 403 for everyone. UI lists/detail pages follow the read rule.
2. New action `POST /api/work_orders/{id}/log_time` with body `{"minutes": <integer>, "note": <text or null>}` (`note` optional, default null): only the current `assignee` (403 otherwise), only while `in_progress` (409 otherwise). `minutes` must be a JSON integer from 1 to 600 inclusive (not a boolean, decimal or string); `note`, if present, must be a string or null; any other key in the body -> 400. Creates one time entry with `technician` = the caller and `logged_at` = now. Returns the work order. No outbox message.
3. `labor_minutes` on work orders becomes a derived field: the sum of `minutes` over the order's time entries, or `null` when the order has none. It still cannot be sent in a create or PATCH body (400).
4. `complete` now takes exactly `{"resolution": <non-empty text>}`; sending `labor_minutes` or any other key -> 400. An order without any time entry cannot be completed: 409. Order of checks: 403 (not the assignee), 409 (status is not `in_progress`, or the order has no time entry), 400 (body). The `work_completed` payload keeps exactly its keys `work_order, asset, technician, labor_minutes, parts_cost`, with `labor_minutes` = the derived total at completion.
5. UI: on `/ui/work_orders/{id}` a `log_time` form is shown to the assignee of an `in_progress` order; the `complete` form is shown only when complete is allowed right now (assignee, `in_progress`, at least one time entry).
6. Cancelling an order keeps its time entries (and therefore its labor_minutes).

Data requirements: every existing work order that has a non-null `labor_minutes` gets exactly one time entry with `technician` = the order's `assignee`, `minutes` = its labor_minutes, `logged_at` = its `completed_at` and `note` = `"migrated"`. These entries get ids 1, 2, 3, ... in ascending work order id. After the migration every existing order's derived `labor_minutes` equals its former stored value (null where it was null); entries of the inactive technician are migrated like any other. New time entries get ids above the migrated ones.

Behaviour to preserve: E01 (parts and use_parts, which also require in_progress), E02 (claim, dispatch, workload cap), E03 (priority codes and their rules), and every other rule of maintenance.md.""",
    superseded_base_tests=SUP_E04,
)

SUP_E05 = list(SUP_E04)

M["E05"] = dict(
    app="maintenance",
    categories=["reversal", "data_migration", "sequence", "interaction", "conflict_or_ambiguity"],
    depends_on="E04",
    brief="""Withdraw technician self-dispatch but keep the workload cap (maintenance, applied after E04).

Operations decided that self-dispatch (introduced in E02) caused technicians to cherry-pick work. It is withdrawn; the workload cap introduced together with it stays.

1. The `claim` action is removed: `POST /api/work_orders/{id}/claim` now behaves like any unknown action (404, after the usual 401 check), and no `claim` form appears in the UI. The E03 rule that limited claims to p3/p4 disappears with it.
2. The `dispatch` field is removed from work orders: it no longer appears in API records or UI pages; sending it in a create or PATCH body is 400 (unknown field) and filtering on it is 400 (unknown field), like any field the collection does not have.
3. The workload cap stays exactly as specified in E02 for `assign`: a valid technician who is already the assignee of 3 or more `assigned`/`in_progress` orders (not counting the order being assigned) cannot receive it (409); re-assignment to the current assignee is always allowed; an invalid technician is 400.

Data requirements (policy for orders that were self-claimed): every work order whose `dispatch` was `"self"` and whose status is still `assigned` (not started) returns to the pool: `status` = `open` and `assignee` = null; all its other fields (title, priority, requested_by, created_at, ...) stay as they are. Self-dispatched orders in any other status (in_progress, completed, cancelled) keep their assignee and status. All other orders are unchanged apart from losing the `dispatch` field. This migration emits no outbox messages and creates no time entries or part usages. Because these orders are `open` again, their requesters regain the requester rights for open orders (edit title/description, cancel) and the technicians' workloads drop accordingly.

Behaviour to preserve: E01 (parts, use_parts, low_stock, parts_cost), E03 (priority codes, p4 rule, due dates), E04 (time entries, log_time, derived labor_minutes, complete rules) and every other rule of maintenance.md.""",
    superseded_base_tests=SUP_E05,
)

SUP_E06 = ["test_supervisor_creates_staff_with_default_active", "test_staff_validation",
           "test_supervisor_creates_and_updates_asset", "test_new_staff_is_identity_and_assignable",
           "test_work_order_lists_per_role", "test_work_order_read_permissions", "test_work_order_fields_match_seed",
           "test_due_date_and_overdue_derived", "test_overdue_uses_now_date_boundary", "test_work_order_filters",
           "test_requester_creates_work_order_defaults", "test_create_due_dates_per_priority", "test_create_site_rule",
           "test_inactive_staff_can_create_orders", "test_requester_patches_open_order",
           "test_supervisor_patch_priority_recomputes_due_date", "test_supervisor_assigns_open_order",
           "test_assignee_completes_order_and_emits", "test_complete_validation",
           "test_supervisor_cancels_in_progress_keeps_assignee", "test_full_lifecycle",
           "test_other_operations_emit_nothing", "test_outbox_readable_by_any_user",
           "test_ui_lists_follow_read_permissions", "test_ui_work_order_detail_fields",
           "test_ui_actions_per_role_and_state", "test_ui_create_forms"]

M["E06"] = dict(
    app="maintenance",
    categories=["permissions", "rule_change", "data_migration", "cross_cutting", "sequence"],
    depends_on="E05",
    brief="""Site-scoped supervisors and a new `manager` role (maintenance, applied after E05).

Each supervisor should only run their own site; one person keeps the company-wide view.

1. `staff.role` accepts a fourth value, `"manager"` (any other value is still 400). A manager has, on every site, all the rights that a supervisor had before this change (maintenance.md and E01-E05: reading all work orders, part usages and time entries, assign, cancel from open/assigned/in_progress, PATCH of title/description/priority, creating work orders for any site, managing assets and parts).
2. Supervisors become site-scoped. The relevant site of a work order is the site of its asset; of an asset or a part, its own `site`.
   - Work orders: a supervisor can read the work orders of their own site (and, as for everyone, orders they requested or are assigned to). The supervisor rights for `assign`, `cancel` (from open/assigned/in_progress) and PATCH (title, description, priority while unfinished) apply only to orders of their own site. On other orders they only have the rights any staff member has as `requested_by` (otherwise 403). Part usages and time entries follow the work-order read rule as before.
   - Creating work orders: supervisors are now restricted to assets of their own site exactly like requesters and technicians (an existing asset of another site -> 403, winning over any 400). Managers may create for any site.
   - Assets and parts: a supervisor may create one only with `site` equal to their own site, and may PATCH or DELETE only those whose current `site` is their own; a PATCH may not change `site` to another site. Each violation is 403 and wins over 400 (a create body without `site` is simply a 400). Managers have no site restriction.
   - Staff: only managers can create, PATCH or DELETE staff; supervisors now get 403 like everyone else (403 before 400).
   - Reading staff, assets and parts is unchanged (every authenticated user reads all of them).
3. UI: `/ui/staff/new` only for managers; `/ui/assets/new` and `/ui/parts/new` for managers and supervisors (403 for other roles); work-order lists, detail pages and action forms follow the new rights.

Data requirements: staff `sofia` (id 1) becomes `manager` and keeps her site `North`; `tomas` (South) and `yara` (East) remain supervisors; no other record changes.

Behaviour to preserve: E01 (parts and use_parts), E03 (priority codes, p4 rule), E04 (time entries, complete rules), E05 (no claim, no dispatch, workload cap for assign), requester and technician rights, and every other rule of maintenance.md.""",
    superseded_base_tests=SUP_E06,
)

SUP_E07 = list(SUP_E06)

M["E07"] = dict(
    app="maintenance",
    categories=["new_concept", "new_relationship", "interaction", "cross_cutting", "sequence"],
    depends_on="E06",
    brief="""Preventive maintenance schedules (maintenance, applied after E06).

Recurring maintenance should generate work orders from schedules instead of being typed in by hand.

1. New collection `schedules`: `asset` (reference to assets, required; cannot be changed after creation), `title` (text, required), `priority` (`"p1"`-`"p4"`, required; `"p4"` is refused for an asset whose criticality is `high`, as for work orders), `interval_days` (JSON integer 1-365, required), `next_due` (date `YYYY-MM-DD`, required, must be a real date), `active` (boolean, default `true`).
   - Settable on create: these six fields; on PATCH: all of them except `asset` (sending `asset`, unknown fields or `id` -> 400).
   - Every authenticated user can read all schedules.
   - Create, PATCH and DELETE: managers, and supervisors for schedules whose asset is at their own site; everyone else 403 (for a create naming an existing asset of another site, the 403 wins over any 400). Creating a schedule for an unknown asset or a retired asset -> 400.
   - Deleting a schedule that has generated any work order -> 409. Deleting an asset that has any schedule -> 409.
2. New read-only field `schedule` on work orders: a reference to the schedule that generated the order, or `null`. It cannot be sent in create or PATCH bodies (400). All existing work orders have `null`.
3. New action `POST /api/schedules/{id}/generate` with body `{}`. Permission: managers, and supervisors of the site of the schedule's asset (403 otherwise). It is 409 when: the schedule is not active; its asset is retired; an unfinished work order generated by this schedule already exists; or today is earlier than `next_due` minus 7 days. On success, atomically: a new work order is created with `asset` = the schedule's asset, `title` = the schedule's title, `description` = `"Preventive maintenance"`, `priority` = the schedule's priority, `status` = `open`, `requested_by` = the caller, `created_at` = now, `assignee` = null and `schedule` = this schedule's id; the schedule's `next_due` advances by exactly `interval_days` from its previous value (once per call, however late it is); one outbox message is emitted on channel `preventive_generated` with payload `{"schedule": <schedule id>, "work_order": <new order id>, "next_due": <new next_due>}`. The response is the schedule after the action. A failed call creates nothing, changes nothing and emits nothing.
4. Retiring an asset (PATCH `retired` to `true`, still only allowed when it has no unfinished work orders) also sets `active` = `false` on all of that asset's schedules in the same operation. Setting `retired` back to `false` does not reactivate them.
5. Generated work orders are ordinary work orders in every other respect: visibility, due date from priority, workload-capped assign, start, use_parts, log_time, complete, cancel, outbox messages.
6. UI: `/ui/schedules` list and detail pages for everyone; on `/ui/schedules/{id}` a `generate` form is shown exactly when generate would succeed for the caller right now; `/ui/schedules/new` for managers and supervisors (403 otherwise).

Data requirements: create exactly these schedules with these ids (id, asset, title, priority, interval_days, next_due, active):
1, 3, Boiler annual service, p2, 365, 2026-03-05, true
2, 16, Conveyor belt inspection, p3, 30, 2026-03-20, true
3, 30, Generator load test, p3, 90, 2026-02-01, false
4, 25, Filter replacement, p4, 60, 2026-02-15, true
5, 21, Generator monthly run, p2, 30, 2026-03-03, true
New schedules get ids above 5. All existing work orders get `schedule` = null; nothing else changes.

Behaviour to preserve: everything from E01-E06 (parts, priority codes and p4 rule, time entries, workload cap, no claim/dispatch, site-scoped supervisors and the manager role) and maintenance.md.""",
    superseded_base_tests=SUP_E07,
)

SUP_E08 = ["test_book_status_for_whole_catalogue", "test_member_borrows_for_self", "test_borrow_book_on_loan_is_409",
           "test_librarian_lends_to_member", "test_failed_borrows_emit_no_outbox_message",
           "test_returned_book_can_be_borrowed_again", "test_librarian_creates_book",
           "test_ui_book_detail_fields_and_borrow_action"]

M["E08"] = dict(
    app="library",
    categories=["new_concept", "new_relationship", "data_migration", "cross_cutting"],
    depends_on=None,
    brief="""Physical copies of books (library).

The library owns several physical copies of some titles. Loans must record which copy was lent, and a title is available as long as one of its copies is.

1. New collection `copies`: `book` (reference to books, required, cannot be changed after creation), `barcode` (text, required, unique), `status` (derived: `"on_loan"` if the copy has a loan with no `returned_at`, otherwise `"available"`). Every authenticated user can read all copies. Only librarians can create, PATCH or DELETE copies (403 otherwise, winning over 400). Settable on create: `book` and `barcode`; on PATCH: `barcode` only. Any other field (including `status`, `book` on PATCH, unknown names) -> 400; an unknown book -> 400; a missing/empty or duplicate barcode -> 400. Deleting a copy that has any loan (returned or not) -> 409.
2. `loans` gain a read-only field `copy` (reference to copies): the copy that was lent. Like all loan fields it is set only by `borrow` (loans still cannot be created, patched or deleted directly).
3. `books.status` is now derived from the book's copies: `"available"` if at least one of its copies is available, `"on_loan"` if it has copies and all of them are on loan, `"unavailable"` if it has no copies at all. New derived field `books.available_copies`: the number of its copies whose status is `available`. Creating a book creates no copy (a new book is `"unavailable"` until a librarian adds a copy).
4. `POST /api/books/{id}/borrow` lends the available copy of that book with the lowest id. It is 409 when the book has no available copy (no copies, or all on loan); all other borrow rules (inactive member 409, 3 open loans 409, member borrowing for someone else 403, precedence) stay. The created loan has `copy` = the chosen copy. The `loan_created` outbox payload becomes `{"loan": id, "book": id, "member": id, "copy": id}`. Returning a loan makes its copy available again.
5. Deleting a book: still 409 if the book has any loan; otherwise the book and all its copies are deleted.
6. UI: `/ui/copies` list and detail pages for everyone; `/ui/copies/new` for librarians only (inputs `book`, `barcode`); the `borrow` form on a book is shown when the book has at least one available copy.

Data requirements: every existing book gets exactly one copy whose id equals the book id and whose barcode is `"C"` followed by the book id zero-padded to 4 digits (book 7 -> `"C0007"`). In addition create copy 41 for book 1 with barcode `"C0001-2"` and copy 42 for book 22 with barcode `"C0022-2"` (the library bought second copies of these two titles; they are not on loan). Every existing loan gets `copy` = the id of its book's original copy (equal to its book id). New copies get ids above 42. Members, books and loans are otherwise unchanged; because of the second copies, books 1 and 22 are now available.

Behaviour to preserve: everything else in library.md (permissions, return rules, members, books CRUD and validation, UI conventions).""",
    superseded_base_tests=SUP_E08,
)

M["E09"] = dict(
    app="library",
    categories=["permissions", "new_relationship", "data_migration", "conflict_or_ambiguity"],
    depends_on=None,
    brief="""Household guardians (library).

Parents want to manage their children's library accounts.

1. `members` gain the field `guardian`: a reference to another member, or `null` (default `null`). It can be used as a list filter like other references (`?guardian=4`), and `?guardian=null` matches members without a guardian. Only librarians can set it (on create and PATCH); a member editing their own record may still change only `name` (sending `guardian` -> 403 as for every other field). Validation (400): `guardian` must be null or the id of an existing member other than the member itself; the guardian must not have a guardian of their own; and a member who is already someone's guardian cannot be given a guardian (no chains).
2. A member X is a *dependant* of member G when X.guardian = G. A guardian additionally gets, for each of their dependants, exactly these rights:
   - read the dependant's member record (it appears in G's member list and detail pages);
   - read the dependant's loans (they appear in G's loan list, filters included);
   - borrow a book for the dependant with `POST /api/books/{id}/borrow` and `{"member": <dependant id>}`; all borrow rules (book availability, the dependant's 3 open loans, the dependant being inactive -> 409, outbox `loan_created` with the dependant as member) apply as if a librarian lent to the dependant;
   - return the dependant's loans with `POST /api/loans/{id}/return`.
   A guardian cannot PATCH or DELETE a dependant's record (403), and a dependant gets no rights over their guardian. Borrowing for any other member is still 403 for non-librarians (403 before 409).
3. Policy for ambiguous cases: guardian rights do not depend on the guardian's or the dependant's `active` flag (only the borrowing rules themselves look at the borrower's `active`). Rights follow the current `guardian` values immediately (removing a guardian removes the access).
4. Deleting a member who is the guardian of anyone -> 409 (a librarian must first clear the dependants' `guardian`).
5. UI: lists, detail pages and `return` forms follow these read/action rules; `/ui/members/new` (librarians) includes a `guardian` input; member detail pages show the `guardian` field.

Data requirements: set `guardian` for these existing members: eli (id 5) -> dara (4); jo (10) -> dara (4); gus (7) -> fatima (6); lena (12) -> kemal (11). All other members get `guardian` = null. Nothing else changes.

Behaviour to preserve: everything else in library.md, in particular that members without dependants still see only their own member record and loans, the 3-loan limit, and librarians' rights.""",
    superseded_base_tests=[],
)

M["E10"] = dict(
    app="library",
    categories=["should_reject", "conflict_or_ambiguity"],
    depends_on=None,
    expect_rejection=True,
    brief="""Right to be forgotten (library).

A member has asked us to erase all of their personal data. Add the action `POST /api/members/{id}/forget` (librarians only; 403 for everyone else) that implements the request as follows:

1. The member record is deleted permanently, and so are all loans of that member (returned or not). Afterwards no record in the application may contain the forgotten member's id, username or name, and the action must not create any replacement, placeholder or pseudonymous member record.
2. The library's loan statistics must stay exactly as they are: after `forget`, `GET /api/loans?member=<forgotten id>` must still return all of the member's former loans to librarians, unchanged and with `member` equal to the forgotten id, and books that were on loan to the member must remain `on_loan` until those loans are returned with `POST /api/loans/{id}/return`.
3. The action emits an outbox message on channel `member_forgotten` with payload `{"member": <id>, "username": <username>}` so that other systems can erase their copies too.
4. The action returns the member record as it was before deletion.

Acceptance: all four points must hold at the same time, for members with and without open loans. Do not anonymise or reassign the loans instead of deleting them.""",
    superseded_base_tests=[],
)

M["E11"] = dict(
    app="expenses",
    categories=["new_relationship", "data_migration", "rule_change", "cross_cutting"],
    depends_on=None,
    brief="""Cost centres with budgets (expenses).

Every claim is charged to a cost centre, and managers may not approve beyond a cost centre's budget.

1. New collection `cost_centres`: `code` (text, required, unique), `name` (text, required), `department` (text or null, optional, default null; unique among non-null values), `budget` (JSON number >= 0, required), `committed` (derived: the sum of `amount` over the claims charged to this cost centre whose status is `approved` or `paid`, rounded to 2 decimals), `remaining` (derived: `budget - committed`, rounded to 2 decimals). Every authenticated user can read all cost centres. Only finance users can create, PATCH or DELETE them (403 otherwise, winning over 400). Settable fields: `code`, `name`, `department`, `budget`; anything else -> 400; invalid values or duplicates -> 400. PATCHing `budget` to less than the current `committed` -> 409. Deleting a cost centre that has any claim -> 409.
2. Claims gain the field `cost_centre` (reference to cost_centres). On create it is optional: when omitted, it is set to the cost centre whose `department` equals the creating employee's `department`; when present it must be the id of an existing cost centre (an unknown id or `null` -> 400). The claim's employee may change it with PATCH while the claim is `draft` (same rules as the other editable fields: 403 for others, 409 when not draft, 400 for an invalid value).
3. Budget rule for `approve`: approving a claim whose `amount` would make its cost centre's `committed` exceed the cost centre's `budget` (compared to the cent) -> 409, and nothing changes. The existing order of checks stays: 403 (not the employee's manager), then 409 (wrong status or budget). `reject` and `pay` are not affected by budgets; paying does not change `committed`.
4. The `payment` outbox payload becomes `{"claim": id, "employee": id, "amount": amount, "cost_centre": cost centre id}`.
5. UI: `/ui/cost_centres` list and detail for everyone; `/ui/cost_centres/new` for finance only (inputs `code`, `name`, `department`, `budget`); the claim create form gains a `cost_centre` input; the `approve` form is shown only when approval would succeed right now (including the budget rule).

Data requirements: create exactly these cost centres (id, code, name, department, budget): 1, ENG, Engineering, Engineering, 31000.00 | 2, SAL, Sales, Sales, 12000.00 | 3, FIN, Finance, Finance, 2000.00 | 4, TRV, Travel pool, null, 5000.00. Every existing claim gets `cost_centre` = the cost centre whose `department` equals its employee's current `department` (so Sales claims -> 2, all other existing claims -> 1). No other field changes; existing approved claims stay approved even where that already uses most of a budget.

Behaviour to preserve: all other rules of expenses.md (permissions, state machine, validation, protected fields).""",
    superseded_base_tests=["test_finance_pays_approved_claim_and_emits_payment", "test_full_claim_lifecycle"],
)

M["E12"] = dict(
    app="expenses",
    categories=["failure_atomicity", "new_concept", "permissions", "cross_cutting"],
    depends_on=None,
    brief="""Atomic employee offboarding (expenses).

When someone leaves, finance offboards them in one step: their reports move to a successor manager and their unfinished drafts disappear - all or nothing.

1. `employees` gain the read-only field `active` (boolean). New employees start with `true`; sending `active` in a create or PATCH body -> 400. It can be used as a list filter.
2. New action `POST /api/employees/{id}/offboard` with body `{"successor": <employee id>}`:
   - Permission: finance users only (403 otherwise).
   - State (409): the employee is already inactive; or the employee has any claim with status `submitted` or `approved` (money in flight must be settled first).
   - Validation (400): `successor` is required and must be the id of an existing, active employee whose `role` is `manager`, who is not the offboarded employee, and whose own `manager` is not the offboarded employee.
   - Order of checks: 404 (unknown employee), 403, 409, 400.
   - Effect, atomically: the employee's `active` becomes `false`; every employee whose `manager` is the offboarded employee gets `manager` = successor; every claim of the offboarded employee with status `draft` is deleted; one outbox message is emitted on channel `employee_offboarded` with payload `{"employee": id, "successor": id, "reassigned": [ids of the re-managed employees, ascending], "deleted_claims": [ids of the deleted drafts, ascending]}`. Returns the employee record. If any check fails, nothing at all changes and nothing is emitted.
3. Inactive employees remain valid `X-User` identities and keep their read rights (finance still reads everything, employees read their own remaining claims, read access as manager follows the current `manager` values), but every write is refused with 403: creating, patching or deleting anything, and every action (submit, approve, reject, pay, offboard). `/ui/claims/new` and other create forms are 403 for them.
4. An inactive employee cannot become anyone's `manager`: creating or patching an employee with an inactive `manager` -> 400.
5. UI: on `/ui/employees/{id}` an `offboard` form is shown exactly when offboarding that employee is allowed right now for the caller (permission and state; the successor parameter is not considered).

Data requirements: every existing employee gets `active` = `true`. No other record changes.

Behaviour to preserve: everything else in expenses.md, including that approvals are done by the employee's current direct manager and the exact `payment` payload `{"claim", "employee", "amount"}`.""",
    superseded_base_tests=[],
)

M["E13"] = dict(
    app="expenses",
    categories=["rule_change", "new_concept", "conflict_or_ambiguity"],
    depends_on=None,
    brief="""Withdraw submitted claims and revise rejected ones (expenses).

Employees want to correct claims instead of starting over.

1. New action `POST /api/claims/{id}/withdraw` with body `{}`: only the claim's employee (403 otherwise). Allowed only when the claim is `submitted` and the current time (X-Now) is at most 7 days (168 hours) after its `submitted_at` - exactly 7 days is still allowed, one second later is not; otherwise 409. Effect: `status` = `draft`, `submitted_at` = null. The claim can then be edited, deleted or submitted again as any draft (a new submit sets a new `submitted_at`).
2. New action `POST /api/claims/{id}/revise` with body `{}`: only the claim's employee (403 otherwise). Allowed only when the claim is `rejected` and its `revision` is less than 2; otherwise 409. Effect: `status` = `draft`; `previous_rejection_reason` = the current `rejection_reason`; `rejection_reason`, `decided_at`, `decided_by` and `submitted_at` become null; `revision` increases by 1. So a claim can be revised at most twice; after a third rejection it stays rejected.
3. New read-only fields on claims: `revision` (integer, starts at 0) and `previous_rejection_reason` (text or null, starts null). Sending either in a create or PATCH body -> 400 (like the other protected fields). Rejecting a revised claim sets `rejection_reason` as usual and leaves `revision` and `previous_rejection_reason` untouched.
4. Policy for open questions: withdraw/revise emit no outbox message; read permissions do not change (the manager can still read the withdrawn or revised claim); the 7-day window is measured from the claim's current `submitted_at`; approving, rejecting and paying a re-submitted claim work exactly as for any other submitted claim (payment payload unchanged).
5. UI: on `/ui/claims/{id}` a `withdraw` form and a `revise` form are shown exactly when the caller may run that action right now (permission, state, time window, revision limit); detail pages show the two new fields.

Data requirements: every existing claim gets `revision` = 0 and `previous_rejection_reason` = null; nothing else changes.

Behaviour to preserve: all other rules of expenses.md (submit/approve/reject/pay, PATCH and DELETE only for own drafts, protected fields, read permissions).""",
    superseded_base_tests=[],
)

SUP_E14 = ["test_book_fields_and_derived_status", "test_book_status_for_whole_catalogue", "test_overdue_derived_field",
           "test_member_borrows_for_self", "test_borrow_book_on_loan_is_409",
           "test_borrow_member_with_three_open_loans_is_409", "test_librarian_lends_to_member",
           "test_failed_borrows_emit_no_outbox_message", "test_librarian_returns_overdue_loan",
           "test_returned_book_can_be_borrowed_again", "test_librarian_creates_book",
           "test_ui_book_detail_fields_and_borrow_action"]

M["E14"] = dict(
    app="library",
    categories=["sequence", "interaction", "rule_change", "data_migration", "failure_atomicity"],
    depends_on="E08",
    brief="""Lost copies (library, applied after E08).

Copies sometimes never come back. Librarians need to close such loans and take the copy out of circulation, and put it back if it turns up.

1. `loans` gain the read-only field `lost_at` (datetime or null, default null). `copies` gain the read-only field `lost` (boolean, default false); sending `lost` in a copy create or PATCH body -> 400, and loans stay non-writable (403). A copy's derived `status` is now `"lost"` when `lost` is true, otherwise `"on_loan"`/`"available"` as in E08.
2. New action `POST /api/loans/{id}/declare_lost` with body `{}`: librarians only (403 otherwise). Only for an open loan, i.e. `returned_at` null and `lost_at` null; otherwise 409. Effect, atomically: the loan's `lost_at` = now (its `returned_at` stays null), the loan's copy gets `lost` = true, and one outbox message is emitted on channel `copy_lost` with payload `{"loan": id, "copy": id, "book": id, "member": id}`. Returns the loan. A refused call changes nothing and emits nothing.
3. A loan with `lost_at` set is closed: it no longer counts towards the member's 3 open loans, its `overdue` is always false, and `return` on it is 409.
4. Book status ignores lost copies: `"available"` if the book has at least one available copy, `"on_loan"` if it has at least one copy that is not lost and all of those are on loan, `"unavailable"` if it has no copy that is not lost. `available_copies` counts available copies. `borrow` lends the lowest-id available copy (lost copies are never lent).
5. New action `POST /api/copies/{id}/found` with body `{}`: librarians only (403). Only for a copy with `lost` = true, otherwise 409. Effect: `lost` = false (the copy becomes available again). The loan keeps its `lost_at` and stays closed. Returns the copy.
6. Deleting a copy that has loans is still 409 (lost copies included).
7. UI: on `/ui/loans/{id}` a `declare_lost` form is shown to librarians for open loans, and the `return` form is not shown for lost loans; on `/ui/copies/{id}` a `found` form is shown to librarians for lost copies; detail pages show the new fields.

Data requirements: loans 46 (book 4, copy 4) and 50 (book 16, copy 16), both of member jo, were reported lost: set their `lost_at` to `"2026-02-28T10:00:00"` and set `lost` = true on copies 4 and 16. All other loans get `lost_at` = null and all other copies `lost` = false. No outbox messages are emitted for this migration. As a consequence books 4 and 16 become unavailable and jo has a single open loan.

Behaviour to preserve: everything from E08 (copies, lowest-id selection, `loan_created` payload with `copy`) and library.md (permissions, limits, returns).""",
    superseded_base_tests=SUP_E14,
)


def main():
    for cid, m in M.items():
        d = os.path.join(OUT, cid)
        os.makedirs(d, exist_ok=True)
        meta = {"id": cid, "app": m["app"], "categories": m["categories"], "depends_on": m["depends_on"],
                "expect_rejection": m.get("expect_rejection", False), "brief": m["brief"],
                "superseded_base_tests": m["superseded_base_tests"]}
        with open(os.path.join(d, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
            fh.write("\n")
    print("wrote", sorted(M))


if __name__ == "__main__":
    main()
