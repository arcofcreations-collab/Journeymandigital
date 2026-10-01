# E02: technician self-dispatch and workload cap

Interpretation: workload = work orders with assignee = the technician and status assigned/in_progress.
Changed (one accrete change, app/changes/0003-self-dispatch.yaml, ledger #3):
- New system field `work_orders.dispatch` (enum supervisor|self, nullable; 400 in create/PATCH bodies, filterable incl. `?dispatch=null`).
  Backfill: 'self' if assignee == requested_by, 'supervisor' if other assignee, null without assignee (16 / 46 / 20). No other record changed; ravi's 4 active orders are untouched.
- New action `claim`: 403 unless active technician at the asset's site; 409 unless status open and caller workload < 3; sets assignee=caller, status=assigned, dispatch='self'; emits `assignment` {work_order, asset, technician}. Workload is in the guard, so the UI claim form shows exactly when a claim would succeed.
- `assign`: after the existing 400 technician check, a 409 when the chosen technician's workload excluding this order is >= 3; sets dispatch='supervisor'.
  Per the request's explicit "re-assigning to the current assignee is always allowed", the cap is skipped when the technician is already the order's assignee (only matters for the already overloaded ravi).
Verified: accrete dry-run/apply (replay: 0 unexplained, 0 unacknowledged consequences) with ~45 expectations (backfill counts, claim/assign 403/409/400 precedence, cap, outbox, no emit on failure, read-only field, requester cancel/PATCH after claim); plus checks through harness/accept_client.py on app_entry.py (UI claim form per user, start/use_parts/complete with parts_cost payload after a claim).
