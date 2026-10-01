# Change notes: spare parts inventory (ledger #2, changes/0002-spare-parts.yaml)

Interpretation: `parts` (readable by all, supervisor-only writes, non-empty text and >= 0 numbers as
constraints, computed `low_stock`) and read-only `part_usages` (read rule = the work order's read rule
on `record.work_order`; create/update/delete False -> 403). `use_parts` is a work_orders action:
allow = current assignee (403); guard = `in_progress` and no item naming a valid part (existing JSON-integer
id, same site as the order's asset) with a valid quantity (JSON integer >= 1) above that part's stock (409,
so it wins over any 400 in the same body); then 400 checks (non-empty list, objects with exactly
`part`/`quantity`, valid part/quantity, no repeated part). Per item in list order: create the usage
(unit_cost copied from the part, used_by = caller, used_at = now), emit `low_stock` when the part goes
from not-low to low, decrease stock. All effects are atomic. `parts_cost` is a computed field
(sum of quantity*stored unit_cost, rounded to 2) and is added to the `work_completed` payload. Cancel is unchanged.
A part at another site counts as an invalid part (400), not as a stock conflict.

Data: the 8 parts were added with ids 1-8; no usages exist, so every work order has parts_cost 0; existing records untouched.

Verification: the change's 60+ expectations (permissions, validation incl. bool/decimal/string numbers,
409-over-400 precedence, atomic failure, low_stock emission, unit_cost snapshot, work_completed payload,
cancel keeps usages) passed; replay showed 0 unexplained differences; `accrete check` ok; UI pages
(/ui/parts, /ui/parts/new, /ui/part_usages, use_parts form on /ui/work_orders/{id}) checked through
app_entry.py with the harness client.
