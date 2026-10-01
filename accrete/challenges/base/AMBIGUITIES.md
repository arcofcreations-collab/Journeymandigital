# Ambiguities deliberately not tested

## Shared contract

1. **Initial outbox contents.** The seed has no outbox, but the spec never says the outbox starts
   empty. Tests compare before/after counts and only inspect the newly added message.
2. **Outbox `created_at` value.** Probably the request's `X-Now`, but the spec does not say so. Tests
   only check that the key is present.
3. **Which actions emit messages.** Only `loan_created` (borrow) and `payment` (pay) are specified.
   Tests check that *failed* borrow/pay calls emit nothing. They do not check whether successful
   `return`/`submit`/`approve`/`reject` calls emit anything.
4. **Filtering on derived fields** (`books?status=on_loan`, `loans?overdue=true`). Derived fields
   "appear as ordinary fields", but the spec does not say whether `?field=value` filters cover them.
5. **Unknown query parameters** (`?foo=bar`): the spec does not say whether they are ignored or
   cause a 400.
6. **Extra fields in records.** Tests check that every specified field has the right value. They do
   not require that a record has *only* the specified fields.
7. **How the UI shows values:** `null`, booleans (`true`/`True`), references (id or name), decimals
   (`1748` vs `1748.0`) and datetimes. UI tests only check text, date and integer values whose
   display is clear.
8. **Whether `id` appears as a `data-field`** in UI detail pages, and whether the create form has
   inputs for fields that have defaults (`members.active`). Tests check required inputs as a subset.
9. **UI forms for PATCH/DELETE.** The contract lists forms only for named actions. Tests check that
   the forbidden named actions are absent rather than requiring `actions == []`.
10. **Whitespace-only text** (`"reason": "  "`, `"description": "  "`) and empty strings for
    required text fields other than the reject reason.
11. **Type coercion** of numbers sent as strings (e.g. `"amount": "100"`).
12. **References to unknown records** (e.g. `{"member": 999}` on borrow, `"manager": 999` when
    creating an employee): the spec does not say whether this is a 400 or a 404.

## Library

13. **Whether an inactive member (`lena`) can authenticate at all**, and so whether her own borrow
    gets 409 or 401. Tests use a librarian lending to an inactive member instead, which is clearly
    a 409.
14. **A librarian calling `borrow` without `member`:** it probably borrows for themselves, but the
    spec does not say.
15. **A librarian lending to another librarian's member id** (librarians are members too): not
    covered.
16. **Whether new `members` become valid `X-User` identities.** Implied, but not stated.
17. **Deleting a member who has loans** (409? cascade?): not specified.
18. **UI `borrow` form for a member who is at the 3-loan limit** on an available book. The book's
    state allows borrowing, but this member would get 409. It is unclear whether "allowed right now"
    takes the caller's loan count into account. Only the book-on-loan case is tested.
19. **What counts as "today"** when `X-Now` is close to midnight is clear (it is UTC), but how
    `borrowed_at` is shown with sub-second precision is not covered.

## Expenses

20. **Claims of an employee with no manager** (e.g. `marco`, `fiona`): no one can approve them under
    the rules. Tests do not cover this.
21. **Whether a manager can approve their own claim if a data edit makes them their own manager:**
    not covered.
22. **Deleting an employee who has claims or is someone's manager:** not specified.
23. **Effect of PATCHing `employees.manager`/`role`** on who can read or approve claims afterwards:
    not covered.
24. **Whether new employees become valid `X-User` identities:** not covered.
25. **Amount precision** (more than 2 decimal places): not specified.
26. **Whether `pay` changes `decided_at`/`decided_by`.** The spec only says it "sets status = paid".
    Tests assume these fields stay as they were, which follows from "sets status" only. This is
    treated as clear rather than ambiguous.
27. **"That employee's manager" read and approve rights** are taken to mean the *direct* manager (the
    `manager` field), as the text says. A skip-level manager (marco for priya/sam/victor) gets 403.
    This is tested; it is listed here only so the interpretation is visible.
