# Change notes: withdraw / revise claims

Interpretation: as stated in the request. `withdraw` = own claim, `submitted`, X-Now <= submitted_at + 7 days (inclusive; one second later -> 409); sets `draft`, `submitted_at` null. `revise` = own claim, `rejected`, `revision` < 2; copies `rejection_reason` to `previous_rejection_reason`, clears `rejection_reason`/`decided_at`/`decided_by`/`submitted_at`, sets `draft`, `revision` + 1. Non-owner -> 403 (checked before state -> 409). No outbox messages; read rules, submit/approve/reject/pay unchanged.

Changed (via `accrete apply`, ledger #2, `changes/0002-withdraw-revise.yaml`):
- added system fields `claims.revision` (int, required, default 0, existing claims backfilled to 0) and `claims.previous_rejection_reason` (text, null) - clients sending them get 400;
- added actions `withdraw` and `revise` (allow + guard as above); UI forms appear automatically only when allow and guard pass.

Verified: dry-run replay (1375 requests, 0 unexplained/unacknowledged differences), 15 expectations (window boundary 7d exactly vs +1s, 403 for manager/finance, 409 states, revise twice then third rejection stays rejected, resubmit/approve/pay with unchanged payment payload, withdraw-then-PATCH/DELETE, 400 on protected fields, no outbox from withdraw/revise), `accrete check` ok, and the harness client via app_entry.py (UI forms and new data-field values on /ui/claims/{id}).
