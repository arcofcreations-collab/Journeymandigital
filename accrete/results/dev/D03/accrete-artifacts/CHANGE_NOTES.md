# Loan renewals (change 0003)

Interpretation: new loan field `renewals` (int, system, default 0; all 60 existing loans backfilled to 0) and
action `POST /api/loans/{id}/renew`. allow = librarian or the loan's member (others 403). guard (409) =
not returned, `today <= due_at` (the due date itself is allowed), `renewals < 2`, and no `waiting` hold on the
book. Effects: `due_at += 14 days` (from the current due_at), `renewals += 1`, then one `loan_renewed`
message `{loan, due_at: new date}`. `overdue` is computed from the stored due_at, so it uses the extended
date. Loans' update rule stays False (PATCH 403). Holds are untouched. The UI renew form follows allow + guard.

Changed via `accrete apply` of changes/0003-renewals.yaml (replay: 0 unexplained differences, 0 consequences;
10 expectations pass). Also verified through app_entry.py on a copy: success/outbox payload, 2-renewal
limit, overdue/returned/waiting-hold 409s, other member 403, PATCH 403, new loans start at renewals 0,
and the renew form appears only when renewal is possible.
