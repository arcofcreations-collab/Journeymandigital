# Clarification needed: `POST /api/members/{id}/forget`

The change request has not been implemented. The application's behaviour is unchanged, because
the request's acceptance criteria contradict each other and cannot all hold at the same time.

## The contradictions

1. **The loans are deleted, but they must still be listed.** Point 1 says all of the member's
   loans are "deleted permanently". Point 2 says that afterwards
   `GET /api/loans?member=<id>` "must still return all of the member's former loans ...
   unchanged". A deleted record can't be returned. To keep returning them, the loans would
   have to stay stored somewhere, which is the same as not deleting them.
2. **No record may hold the member's id, but the loans must show it.** Point 1 says no record
   may contain the forgotten member's id. Point 2 says the returned loans keep `member` equal
   to that id. The outbox payload in point 3 (`{"member": <id>, "username": <username>}`) also
   stores both the id and the username in a persisted record (`/api/_outbox`). That breaks
   point 1 again.
3. **Deleted loans must still be returnable.** Point 2 says the books stay `on_loan` "until
   those loans are returned with `POST /api/loans/{id}/return`". After deletion those loan ids
   don't exist, so the return call would answer 404. Also, `status` is worked out from open
   loans, so a book whose open loan has been deleted becomes `available` straight away.
4. **The usual workarounds are ruled out.** The request forbids replacement, placeholder or
   pseudonymous members, and forbids anonymising or reassigning the loans. Those are the
   standard ways to reconcile erasure with keeping statistics.
5. **A dangling reference is not possible either.** `loans.member_id` is a foreign key to
   `members`. Keeping loans that point at a member who no longer exists would break
   referential integrity.

## Decisions needed

Choose one consistent model, for example:

- **A. True erasure.** Delete the member and all their loans. Books with open loans become
  `available`. `GET /api/loans?member=<id>` then returns `[]`. Statistics would come from
  aggregate counts kept separately, with no member id in them. You would also decide whether
  the outbox message may contain the id and username, or only an opaque erasure token.
- **B. Keep the loans, remove the personal data.** Delete the member's personal data (name and
  username) but keep the loans, either under a non-identifying key or with
  `member` = null. You would need to lift the ban on anonymisation or pseudonymisation and
  decide what `?member=<id>` should return.
- **C. Block erasure while loans are open.** Reject `forget` with 409 while the member has
  unreturned loans, and settle the history question with A or B.

Legal or compliance should also confirm whether the library must keep loan history for an
erased member at all (GDPR Art. 17(3) exemptions), because that decides between A and B.
