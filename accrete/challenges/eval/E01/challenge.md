# E01 (maintenance): spare parts and atomic part consumption

## 1. Requested outcome
Technicians record the spare parts they use on an in-progress work order. A new `parts` inventory
(per site, with reorder levels) and a read-only `part_usages` history are added; the action
`use_parts` consumes several parts at once, all or nothing. Work orders gain a derived `parts_cost`
that is reported in the `work_completed` message. Parts that drop to their reorder level announce
themselves on a new `low_stock` outbox channel.

## 2. Observable acceptance criteria
- `GET /api/parts` returns parts 1-8 exactly as listed in the brief to every user; `low_stock` is
  derived (`quantity <= reorder_level`), so initially parts 5 and 8 are low; filters work on it.
- `use_parts` by the assignee of an in-progress order creates one usage per item (ascending ids in
  list order, `unit_cost` copied from the part, `used_by` = caller, `used_at` = X-Now), decrements
  stock and returns the work order with the new `parts_cost` (rounded to 2 decimals).
- `low_stock` messages only for parts that cross from not-low to low, in list order, with payload
  `{"part", "sku", "quantity"}`.
- Error rules: non-assignee 403; not `in_progress` 409; malformed items 400; insufficient stock 409,
  and the stock 409 wins over an invalid sibling item; 403 before 409 before 400.
- `part_usages` readable exactly like their work order; POST/PATCH/DELETE on them 403.
- `parts_cost` does not change when a part's `unit_cost` changes later; the `work_completed`
  payload has exactly the keys `work_order, asset, technician, labor_minutes, parts_cost`.
- Parts CRUD: supervisors only (403 before 400), validation 400, duplicate sku 400, delete of a part
  with usages 409. UI: parts lists/forms, `use_parts` form only for the assignee of an in-progress order.

## 3. Behaviour that must remain intact
All maintenance.md rules: read permissions (lists 1-82 for supervisors, ruth's 7 orders), assign/start/
complete/cancel state machine and precedence, the `assignment` payload (exactly three keys),
labor_minutes validation at completion, nobody deletes work orders, derived fields cannot be sent.

## 4. Existing-data requirements
All 129 seed records unchanged. Parts 1-8 created exactly as in the brief, no usages, every existing
work order has `parts_cost` 0. Base tests `test_assignee_completes_order_and_emits` and
`test_full_lifecycle` are superseded (they compare the old exact `work_completed` payload).

## 5. Failure and recovery conditions
A failed `use_parts` (insufficient stock for one item, invalid item, wrong state, wrong user) leaves
parts, part_usages, work orders and the outbox byte-for-byte as before (full snapshot comparison).
Cancelling an order keeps its usages and does not restore stock.

## 6. Measurements to collect
Standard harness measurements, plus: number of snapshot-atomicity assertions passed, whether the
409-over-400 precedence for mixed item lists is respected, and whether `parts_cost` is frozen
against later unit_cost edits.
