# Change notes: itemised claims

**Interpretation.** A claim now has one or more `claim_lines` (`claim`, `amount` > 0, `description`).
The claim's `amount` is derived as the sum of its lines rounded to 2 decimals and is no longer stored.
Creating a claim is unchanged externally and also creates its first line. Line create/PATCH/DELETE
follow the claim's edit rules (owner only -> 403, draft only -> 409); missing/invalid fields or an
unknown claim -> 400; a total above 5000 -> 400; deleting the last line -> 409; changing a line's
`claim` -> 400 (repeating the same id is accepted as a no-op). PATCHing a claim's `amount` sets its
single line, or is 409 if it has several lines (checked before body validation, as 409 precedes 400).
Lines are readable exactly when their claim is; `?claim=<id>` filters. Deleting a claim deletes its lines.
Claim `description`/`category` stay independent of line descriptions.

**Changes.** Migration `0002_claim_lines.sql` creates `claim_lines`, copies every claim into one
line with the same id/amount/description, keeps the line id sequence at or above the claims
sequence (new lines get ids > 80), and drops `claims.amount`. Updated `repository.py` (derived amount,
line CRUD), `validation.py` (`clean_claim_line`, shared positive-amount check), `permissions.py`,
`services.py` (line services, total check, claim create/PATCH/delete), `routes_api.py`
(`/api/claim_lines`), `routes_ui.py` + templates (`/ui/claim_lines` list/detail/new, link from the
claim page), `seed.py` (seeds one line per claim), README. The committed `data.db` was migrated by
starting the app; `python seed.py` produces an identical database.

**Verification.** Existing suite (35 tests) unchanged and passing; new `tests/test_expenses_claim_lines.py`
(13 tests: migration/data preservation, derived total and rounding, permissions/state/validation
precedence, 5000 cap, last-line rule, claim amount PATCH compatibility, visibility, cascade delete,
payment payload, UI). 48/48 pass loading the app through `app_entry.py` (run with a local stand-in
for the out-of-tree `harness/accept_client.py`). Checked migrated `data.db`: 80 lines, ids equal to
claim ids, amounts/descriptions identical to the original claims.
