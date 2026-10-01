# D12 - Itemised claims (expenses)

Categories: new_relationship, data_migration, cross_cutting, conflict_or_ambiguity. Depends on: none. Expect rejection: no.

## 1. Requested outcome

Claims are composed of lines; the amount is derived; old clients keep working.

## 2. Observable acceptance criteria

- Lines 1..80 mirror claims 1..80 (same id, amount, description).
- Adding/patching/deleting lines updates the claim total; total cap 5000.00 inclusive.
- Owner-only (403) and draft-only (409) line edits; last line cannot be deleted (409); validation 400.
- Claim `amount` PATCH: single line -> updates line; multiple lines -> 409.
- Line visibility follows claim visibility; new claims get a first line; payment uses the total; deleting a draft deletes lines; UI.

## 3. Behaviour that must remain intact

- Claim create validation, submit/approve/pay flow, PATCH of single-line drafts.
- Base tests intentionally superseded: none; every other base test must still pass.

## 4. Existing-data requirements

- 80 migrated lines with ids equal to claim ids; amounts unchanged.

## 5. Failure and recovery conditions

- Rejected line operations leave the claim total unchanged.

## 6. Measurements to collect

- Standard: success, hidden-test pass rate, base-suite regressions, data integrity, elapsed time, tool calls, tokens.
- Whether the 80 migrated lines keep claim ids and amounts.
- Backwards-compatibility regressions in claim PATCH/create.

## Brief (exact text given to implementers)

Itemised claims

A claim can now consist of several line items.

New collection `claim_lines` with fields: `claim` (reference to claims, required), `amount` (number, required, greater than 0), `description` (text, required).

A claim's `amount` becomes the total of its lines (derived, rounded to 2 decimals).
- Creating a claim works exactly as before (`amount`, `category`, `description`, same validation) and also creates the claim's first line with that `amount` and `description`.
- `POST /api/claim_lines` adds a line to a claim; `PATCH /api/claim_lines/{id}` may change `amount` and `description` (changing `claim` -> 400); `DELETE /api/claim_lines/{id}` removes a line. Only the claim's employee may do this (anyone else -> 403), and only while the claim is `draft` (otherwise 409). Missing/invalid fields or an unknown claim id -> 400. A claim's total may never exceed 5000 (-> 400). Deleting a claim's last remaining line -> 409.
- Backwards compatibility: PATCHing a claim's `amount` is still allowed when the claim has exactly one line, and then sets that line's amount (same validation as before). When the claim has more than one line, PATCHing the claim's `amount` -> 409. PATCHing `category`/`description` of the claim works as before.
- Lines are readable by exactly the users who can read their claim (lists contain only those; direct access otherwise 403). `GET /api/claim_lines?claim=<id>` lists one claim's lines.
- Deleting a draft claim also deletes its lines.
- Everything that uses a claim's amount (the claim's `amount` field, validation, the `payment` message) uses the total.

Existing data (required): every existing claim gets exactly one line whose `id` equals the claim's id, with the claim's current `amount` and `description`. No existing claim's amount changes. New lines get ids above 80.
