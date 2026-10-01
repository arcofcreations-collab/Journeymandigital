# D09: Withdraw the second-approval rule

**Interpretation.** The D08 rule is fully reverted. The employee's direct manager approves or rejects any `submitted` claim, whatever the amount. `awaiting_second_approval`, `first_approved_by` and `first_approved_at` are removed from the API, the filters and the UI. Sending those fields is now a 400 "unknown field". Only the employee, the employee's manager and finance can read a claim again. The indirect manager (the former second approver) gets 403 and no longer sees those claims in lists.

**Changes.**
- New migration `0003_withdraw_second_approval.sql` turns every `awaiting_second_approval` claim into `approved`, with `decided_by`/`decided_at` taken from `first_approved_by`/`first_approved_at`. It then rebuilds `claims` with the original status CHECK and without the two columns. Claims that were already decided or paid keep their status, decision and reason.
- `services.py`: the second-approval threshold, branch and chain lookup are removed, and `_check_can_decide` is back to "manager → 403, not submitted → 409". `permissions.py`: the second-approver read and decide rights are removed. `repository.py`, `validation.py`, `claims/detail.html`, `seed.py`, `seed_data.json` (claims 21, 22 and 44 are now approved by omar) and `README.md` are updated.
- Committed `data.db` is migrated to version 3. Only claims 21, 22 and 44 changed, and `seed.py` rebuilds an identical database.

**Verification.** `tests/test_expenses_second_approval.py` is replaced by `tests/test_expenses_single_approval.py`. It covers single approval and rejection of large claims, the indirect manager's lost access, the removed fields and status, the seed claims, and a v2→v3 migration across every claim state. The claims and UI tests are updated too. All 42 tests pass. The original `harness/` is not inside the workspace, so I ran them against a minimal local stand-in for `accept_client`. The app also loads and serves requests through `app_entry.py`.
