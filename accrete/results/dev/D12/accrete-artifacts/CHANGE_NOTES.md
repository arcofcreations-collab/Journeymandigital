# Itemised claims (change #2, changes/0002-itemised-claims.yaml)

Interpretation: new collection `claim_lines` (claim, amount > 0, description). `claims.amount` stays a stored field but is kept
equal to round(sum of its lines, 2) by triggers on line create/update/delete, so validation and the `payment` message use the total.
Creating a claim works as before and a trigger creates its first line. Line writes: only the claim's employee (403), only while the
claim is draft (409); deleting the last line 409; total over 5000, missing/invalid fields, unknown claim id, or changing a line's
`claim` -> 400. PATCH claim `amount`: with one line it sets that line (same 0..5000 validation); with several lines -> 409 (wins over
the range check). Deleting a draft claim deletes its lines. Lines are readable exactly by their claim's readers.

Notes: `claim_lines.claim` is stored as the claim's integer id (serialised exactly like a reference, `?claim=<id>` filter works) with an
existence constraint, because the runtime refuses (409) to delete a record that a ref still points to, which would block deleting a
draft claim with its lines. A multi-line PATCH that sends `amount` equal to the current total is a no-op (200), not 409. Claim
`description` PATCHes are not copied to lines.

Migration: 80 lines added, line id = claim id, with each claim's current amount and description; no claim amount changed; new lines
get ids from 81.

Verification: 7 multi-step expectations in the change (creation, totals, 409/403/400 cases, 5000 cap, single-line PATCH, cascade
delete, payment payload, migrated data) passed; replay of 265 recorded requests identical; `accrete check` ok; requests and UI pages
exercised through app_entry.py on a copy of the app.
