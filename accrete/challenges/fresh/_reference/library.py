"""Reference library app: base spec + F10 (reference-only), F11 (membership expiry), F12 (suggestions)."""
from core import RefApp, fail, is_int, is_text, is_date, add_days

F10_REFERENCE = {9, 33, 36, 40}
F12_SEED = [
    {"id": 1, "title": "Salt and Stars", "author": "N. Adeyemi", "isbn": "978-1-2000-001-5",
     "note": "For the book club", "suggested_by": 3, "created_at": "2026-02-10T10:00:00",
     "status": "pending", "book": None, "decline_reason": None},
    {"id": 2, "title": "The Quiet Engine", "author": "P. Varga", "isbn": "978-1-2000-002-2",
     "note": None, "suggested_by": 8, "created_at": "2026-02-12T15:30:00",
     "status": "pending", "book": None, "decline_reason": None},
    {"id": 3, "title": "Old Maps", "author": "R. Ito", "isbn": "978-1-2000-003-9",
     "note": None, "suggested_by": 3, "created_at": "2026-01-20T09:00:00",
     "status": "declined", "book": None, "decline_reason": "Out of print"},
]


class Library(RefApp):
    user_collection = "members"

    def collections(self):
        c = ["members", "books", "loans"]
        if self.has("F12"):
            c.append("suggestions")
        return c

    def actions(self, coll):
        return {"books": ["borrow"], "loans": ["return"],
                "members": ["extend"] if self.has("F11") else [],
                "suggestions": ["accept", "decline"]}.get(coll, [])

    # ---------------------------------------------------------------- migrations
    def migrate_F10(self):
        for b in self.recs("books"):
            b["reference_only"] = b["id"] in F10_REFERENCE

    def migrate_F11(self):
        for m in self.recs("members"):
            first = sorted(l["borrowed_at"] for l in self.recs("loans") if l["member"] == m["id"])
            if m["role"] == "member" and first:
                m["member_until"] = add_days(first[0][:10], 365)
            else:
                m["member_until"] = None

    def migrate_F12(self):
        self.state["suggestions"] = [dict(s) for s in F12_SEED]

    # ---------------------------------------------------------------- helpers
    def lib(self, user):
        return user["role"] == "librarian"

    def open_loan(self, book_id):
        for l in self.recs("loans"):
            if l["book"] == book_id and l["returned_at"] is None:
                return l
        return None

    def serialize(self, coll, rec, user):
        d = dict(rec)
        if coll == "books":
            d["status"] = "on_loan" if self.open_loan(rec["id"]) else "available"
        if coll == "loans":
            d["overdue"] = rec["returned_at"] is None and self.today > rec["due_at"]
        return d

    def can_read(self, coll, rec, user):
        if coll == "books":
            return True
        if self.lib(user):
            return True
        if coll == "members":
            return rec["id"] == user["id"]
        if coll == "loans":
            return rec["member"] == user["id"]
        if coll == "suggestions":
            return rec["suggested_by"] == user["id"]
        return False

    # ---------------------------------------------------------------- validation
    def validate_book(self, body, rec=None):
        allowed = {"title", "author", "isbn", "year"} | ({"reference_only"} if self.has("F10") else set())
        out = dict(rec or {})
        for k, v in body.items():
            if k not in allowed:
                continue
            out[k] = v
        for k in ("title", "author", "isbn"):
            if not is_text(out.get(k)):
                fail(400, f"{k} required")
        if out.get("year") is not None and not is_int(out.get("year")):
            fail(400, "year")
        out.setdefault("year", None)
        if self.has("F10"):
            out.setdefault("reference_only", False)
            if not isinstance(out["reference_only"], bool):
                fail(400, "reference_only")
        for b in self.recs("books"):
            if b["isbn"] == out["isbn"] and (rec is None or b["id"] != rec["id"]):
                fail(400, "duplicate isbn")
        return out

    def validate_member(self, body, rec=None):
        allowed = {"username", "name", "role", "active"} | ({"member_until"} if self.has("F11") else set())
        out = dict(rec or {})
        for k, v in body.items():
            if k in allowed:
                out[k] = v
        for k in ("username", "name"):
            if not is_text(out.get(k)):
                fail(400, k)
        if out.get("role") not in ("member", "librarian"):
            fail(400, "role")
        out.setdefault("active", True)
        if not isinstance(out["active"], bool):
            fail(400, "active")
        if self.has("F11"):
            out.setdefault("member_until", None)
            if out["member_until"] is not None and not is_date(out["member_until"]):
                fail(400, "member_until")
        for m in self.recs("members"):
            if m["username"] == out["username"] and (rec is None or m["id"] != rec["id"]):
                fail(400, "duplicate username")
        return out

    # ---------------------------------------------------------------- CRUD
    def create(self, coll, body, user):
        if coll == "suggestions":
            return self.create_suggestion(body, user)
        if coll == "loans" or not self.lib(user):
            fail(403)
        if coll == "books":
            rec = self.validate_book(body)
        else:
            rec = self.validate_member(body)
        rec["id"] = self.next_id(coll)
        self.recs(coll).append(rec)
        return rec

    def patch(self, coll, rec, body, user):
        if coll == "loans":
            fail(403)
        if coll == "suggestions":
            return self.patch_suggestion(rec, body, user)
        if coll == "books":
            if not self.lib(user):
                fail(403)
            new = self.validate_book(body, rec)
        else:
            if not self.lib(user):
                if rec["id"] != user["id"] or set(body) - {"name"}:
                    fail(403)
            new = self.validate_member(body, rec)
        rec.clear()
        rec.update(new)
        return rec

    def delete(self, coll, rec, user):
        if coll == "loans":
            fail(403)
        if coll == "suggestions":
            if rec["suggested_by"] != user["id"]:
                fail(403)
            if rec["status"] != "pending":
                fail(409)
            self.state[coll].remove(rec)
            return
        if not self.lib(user):
            fail(403)
        if coll == "books":
            if any(l["book"] == rec["id"] for l in self.recs("loans")):
                fail(409)
            if self.has("F12") and any(s["book"] == rec["id"] for s in self.recs("suggestions")):
                fail(409)
        if coll == "members":
            if any(l["member"] == rec["id"] for l in self.recs("loans")):
                fail(409)
        self.state[coll].remove(rec)

    # ---------------------------------------------------------------- actions
    def run_action(self, coll, rec, action, body, user):
        if coll == "books" and action == "borrow":
            return self.borrow(rec, body, user)
        if coll == "loans" and action == "return":
            if not (self.lib(user) or rec["member"] == user["id"]):
                fail(403)
            if rec["returned_at"] is not None:
                fail(409)
            rec["returned_at"] = self.now
            return rec
        if coll == "members" and action == "extend":
            if not self.lib(user):
                fail(403)
            if rec["member_until"] is None or not rec["active"]:
                fail(409)
            base = max(self.today, rec["member_until"])
            rec["member_until"] = add_days(base, 365)
            self.emit("membership_extended", {"member": rec["id"], "member_until": rec["member_until"]})
            return rec
        if coll == "suggestions":
            return self.suggestion_action(rec, action, body, user)
        fail(404)

    def borrow(self, book, body, user):
        target = user
        if "member" in body and body["member"] != user["id"]:
            if not self.lib(user):
                fail(403)
            target = self.get("members", body["member"]) if is_int(body["member"]) else None
            if target is None:
                fail(400, "unknown member")
        if self.open_loan(book["id"]):
            fail(409, "on loan")
        if self.has("F10") and book.get("reference_only"):
            fail(409, "reference only")
        if not target["active"]:
            fail(409, "inactive")
        if self.has("F11") and target.get("member_until") is not None and target["member_until"] < self.today:
            fail(409, "membership expired")
        n = sum(1 for l in self.recs("loans") if l["member"] == target["id"] and l["returned_at"] is None)
        if n >= 3:
            fail(409, "limit")
        loan = {"id": self.next_id("loans"), "book": book["id"], "member": target["id"],
                "borrowed_at": self.now, "due_at": add_days(self.today, 14), "returned_at": None}
        self.recs("loans").append(loan)
        self.emit("loan_created", {"loan": loan["id"], "book": book["id"], "member": target["id"]})
        return book

    # ---------------------------------------------------------------- F12
    SUG_FIELDS = ("title", "author", "isbn", "note")

    def check_sug(self, out, rec=None):
        for k in ("title", "author", "isbn"):
            if not is_text(out.get(k)):
                fail(400, k)
        if out.get("note") is not None and not isinstance(out["note"], str):
            fail(400, "note")
        if any(b["isbn"] == out["isbn"] for b in self.recs("books")):
            fail(400, "isbn in catalogue")
        for s in self.recs("suggestions"):
            if s["status"] == "pending" and s["isbn"] == out["isbn"] and (rec is None or s["id"] != rec["id"]):
                fail(400, "isbn already suggested")

    def create_suggestion(self, body, user):
        for k in body:
            if k not in self.SUG_FIELDS:
                fail(400, k)
        out = {k: body.get(k) for k in self.SUG_FIELDS}
        self.check_sug(out)
        rec = dict(out, id=self.next_id("suggestions"), suggested_by=user["id"], created_at=self.now,
                   status="pending", book=None, decline_reason=None)
        self.recs("suggestions").append(rec)
        return rec

    def patch_suggestion(self, rec, body, user):
        if rec["suggested_by"] != user["id"]:
            fail(403)
        if rec["status"] != "pending":
            fail(409)
        for k in body:
            if k not in self.SUG_FIELDS:
                fail(400, k)
        out = dict(rec)
        out.update(body)
        self.check_sug(out, rec)
        rec.update(out)
        return rec

    def suggestion_action(self, rec, action, body, user):
        if not self.lib(user):
            fail(403)
        if rec["status"] != "pending":
            fail(409)
        if action == "accept":
            if any(b["isbn"] == rec["isbn"] for b in self.recs("books")):
                fail(409, "isbn exists")
            year = body.get("year")
            if year is not None and not is_int(year):
                fail(400, "year")
            book = {"id": self.next_id("books"), "title": rec["title"], "author": rec["author"],
                    "isbn": rec["isbn"], "year": year}
            if self.has("F10"):
                book["reference_only"] = False
            self.recs("books").append(book)
            rec["status"] = "accepted"
            rec["book"] = book["id"]
            self.emit("book_added", {"book": book["id"], "suggestion": rec["id"], "suggested_by": rec["suggested_by"]})
            return rec
        if action == "decline":
            if not is_text(body.get("reason")):
                fail(400, "reason")
            rec["status"] = "declined"
            rec["decline_reason"] = body["reason"]
            return rec
        fail(404)

    # ---------------------------------------------------------------- UI
    def create_form(self, coll, user):
        if coll == "suggestions":
            return list(self.SUG_FIELDS)
        if coll == "loans" or not self.lib(user):
            fail(403)
        if coll == "books":
            return ["title", "author", "isbn", "year"] + (["reference_only"] if self.has("F10") else [])
        return ["username", "name", "role", "active"] + (["member_until"] if self.has("F11") else [])
