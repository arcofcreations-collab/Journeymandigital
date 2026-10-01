"""Reference expenses app: base + sequence F01..F06 + independent F13, F14."""
import datetime as dt
from core import RefApp, fail, is_num, is_int, is_text, is_date, r2

POLICIES = [
    {"id": 1, "category": "travel", "max_amount": 2500, "submit_within_days": 60},
    {"id": 2, "category": "meals", "max_amount": 400, "submit_within_days": 30},
    {"id": 3, "category": "equipment", "max_amount": 2000, "submit_within_days": 90},
    {"id": 4, "category": "other", "max_amount": 1000, "submit_within_days": 60},
    {"id": 5, "category": "lodging", "max_amount": 1800, "submit_within_days": 60},
]
ADVANCES = [
    {"id": 1, "employee": 11, "amount": 300, "purpose": "Conference travel float",
     "issued_at": "2026-02-01T09:00:00", "issued_by": 1, "recovered": 0},
    {"id": 2, "employee": 11, "amount": 250, "purpose": "Client visit float",
     "issued_at": "2026-02-20T09:00:00", "issued_by": 1, "recovered": 0},
    {"id": 3, "employee": 7, "amount": 500, "purpose": "Trade fair float",
     "issued_at": "2026-02-10T09:00:00", "issued_by": 1, "recovered": 0},
]
CAP_NOTE = "Capped at policy maximum"


class Expenses(RefApp):
    user_collection = "employees"

    def partial(self):
        return self.has("F03") and not self.has("F05")

    def collections(self):
        c = ["employees", "claims"]
        if self.has("F02"):
            c.append("category_policies")
        if self.has("F04"):
            c.append("advances")
        return c

    def actions(self, coll):
        if coll == "claims":
            a = ["submit", "approve", "reject", "pay"]
            if self.has("F14"):
                a.append("query")
            return a
        return []

    # ---------------------------------------------------------------- migrations
    def migrate_F01(self):
        for c in self.recs("claims"):
            c["incurred_on"] = c["submitted_at"][:10] if c["submitted_at"] else None

    def migrate_F02(self):
        self.state["category_policies"] = [dict(p) for p in POLICIES]
        for c in self.recs("claims"):
            if c["description"].startswith("Hotel night"):
                c["category"] = "lodging"

    def migrate_F03(self):
        for c in self.recs("claims"):
            c["approved_amount"] = None
            c["approval_note"] = None
            if c["status"] == "paid":
                c["approved_amount"] = c["amount"]
            elif c["status"] == "approved":
                mx = self.policy(c["category"])["max_amount"]
                if c["amount"] > mx:
                    c["approved_amount"] = mx
                    c["approval_note"] = CAP_NOTE
                else:
                    c["approved_amount"] = c["amount"]

    def migrate_F04(self):
        self.state["advances"] = [dict(a) for a in ADVANCES]
        for c in self.recs("claims"):
            if c["status"] == "paid":
                c["advance_recovered"] = 0
                c["paid_amount"] = c["approved_amount"]
            else:
                c["advance_recovered"] = None
                c["paid_amount"] = None

    def migrate_F05(self):
        for c in self.recs("claims"):
            if c["status"] == "approved" and c["approved_amount"] is not None and c["approved_amount"] < c["amount"]:
                c["status"] = "submitted"
                c["decided_at"] = None
                c["decided_by"] = None
            c.pop("approved_amount", None)
            c.pop("approval_note", None)

    def migrate_F13(self):
        for c in self.recs("claims"):
            if c["category"] == "other":
                c["category"] = "miscellaneous"

    def migrate_F14(self):
        for c in self.recs("claims"):
            c["finance_query"] = None
            c["query_count"] = 0

    # ---------------------------------------------------------------- helpers
    def emp(self, eid):
        return self.get("employees", eid)

    def manager_of(self, claim):
        e = self.emp(claim["employee"])
        return e["manager"] if e else None

    def fin(self, user):
        return user["role"] == "finance"

    def policy(self, category):
        for p in self.recs("category_policies"):
            if p["category"] == category:
                return p
        return None

    def categories(self):
        if self.has("F02"):
            return [p["category"] for p in self.recs("category_policies")]
        if self.has("F13"):
            return ["travel", "meals", "equipment", "miscellaneous"]
        return ["travel", "meals", "equipment", "other"]

    def protected(self):
        p = {"employee", "status", "submitted_at", "decided_at", "decided_by", "rejection_reason"}
        if self.has("F03"):
            p |= {"approved_amount", "approval_note"}
        if self.has("F04"):
            p |= {"advance_recovered", "paid_amount"}
        if self.has("F14"):
            p |= {"finance_query", "query_count"}
        return p

    def editable(self):
        e = {"amount", "category", "description"}
        if self.has("F01"):
            e.add("incurred_on")
        return e

    def serialize(self, coll, rec, user):
        d = dict(rec)
        if coll == "advances":
            d["outstanding"] = r2(rec["amount"] - rec["recovered"])
        return d

    def can_read(self, coll, rec, user):
        if coll == "claims":
            return self.fin(user) or rec["employee"] == user["id"] or self.manager_of(rec) == user["id"]
        if coll == "advances":
            if self.fin(user) or rec["employee"] == user["id"]:
                return True
            e = self.emp(rec["employee"])
            return e is not None and e["manager"] == user["id"]
        return True

    # ---------------------------------------------------------------- validation
    def validate_claim(self, body, rec=None):
        for k in body:
            if k in self.protected():
                fail(400, f"{k} is not settable")
        out = dict(rec or {})
        for k in self.editable():
            if k in body:
                out[k] = body[k]
        if not is_num(out.get("amount")) or out["amount"] <= 0:
            fail(400, "amount")
        if out.get("category") not in self.categories():
            fail(400, "category")
        if not is_text(out.get("description")):
            fail(400, "description")
        if self.has("F02"):
            if rec is None or "amount" in body or "category" in body:
                if out["amount"] > self.policy(out["category"])["max_amount"]:
                    fail(400, "amount above policy maximum")
        else:
            if out["amount"] > 5000:
                fail(400, "amount")
        if self.has("F01"):
            v = out.get("incurred_on")
            if v is not None and (not is_date(v) or v > self.today):
                fail(400, "incurred_on")
        return out

    def validate_employee(self, body, rec=None):
        out = dict(rec or {})
        for k in ("username", "name", "role", "manager", "department"):
            if k in body:
                out[k] = body[k]
        for k in ("username", "name", "department"):
            if not is_text(out.get(k)):
                fail(400, k)
        if out.get("role") not in ("employee", "manager", "finance"):
            fail(400, "role")
        out.setdefault("manager", None)
        if out["manager"] is not None and (not is_int(out["manager"]) or self.emp(out["manager"]) is None):
            fail(400, "manager")
        for e in self.recs("employees"):
            if e["username"] == out["username"] and (rec is None or e["id"] != rec["id"]):
                fail(400, "duplicate username")
        return out

    def validate_policy(self, body, rec=None):
        allowed = {"max_amount", "submit_within_days"} | ({"category"} if rec is None else set())
        for k in body:
            if k not in allowed:
                fail(400, k)
        out = dict(rec or {})
        out.update(body)
        if not is_text(out.get("category")):
            fail(400, "category")
        if not is_num(out.get("max_amount")) or out["max_amount"] <= 0:
            fail(400, "max_amount")
        if not is_int(out.get("submit_within_days")) or out["submit_within_days"] < 1:
            fail(400, "submit_within_days")
        if rec is None and self.policy(out["category"]) is not None:
            fail(400, "duplicate category")
        return out

    # ---------------------------------------------------------------- CRUD
    def create(self, coll, body, user):
        if coll == "claims":
            rec = self.validate_claim(body)
            rec.update({"employee": user["id"], "status": "draft", "submitted_at": None, "decided_at": None,
                        "decided_by": None, "rejection_reason": None})
            if self.has("F01"):
                rec.setdefault("incurred_on", None)
            if self.partial():
                rec.update({"approved_amount": None, "approval_note": None})
            if self.has("F04"):
                rec.update({"advance_recovered": None, "paid_amount": None})
            if self.has("F14"):
                rec.update({"finance_query": None, "query_count": 0})
        elif coll == "employees":
            if not self.fin(user):
                fail(403)
            rec = self.validate_employee(body)
        elif coll == "category_policies":
            if not self.fin(user):
                fail(403)
            rec = self.validate_policy(body)
        elif coll == "advances":
            rec = self.create_advance(body, user)
        else:
            fail(403)
        rec["id"] = self.next_id(coll)
        self.recs(coll).append(rec)
        if coll == "advances":
            self.emit("advance_issued", {"advance": rec["id"], "employee": rec["employee"], "amount": rec["amount"]})
        return rec

    def create_advance(self, body, user):
        if not self.fin(user):
            fail(403)
        if self.has("F06") and is_int(body.get("employee")) and body.get("employee") == user["id"]:
            fail(403, "no advances to oneself")
        for k in body:
            if k not in ("employee", "amount", "purpose"):
                fail(400, k)
        if not is_int(body.get("employee")) or self.emp(body["employee"]) is None:
            fail(400, "employee")
        if not is_num(body.get("amount")) or body["amount"] <= 0 or body["amount"] > 2000:
            fail(400, "amount")
        if not is_text(body.get("purpose")):
            fail(400, "purpose")
        return {"employee": body["employee"], "amount": body["amount"], "purpose": body["purpose"],
                "issued_at": self.now, "issued_by": user["id"], "recovered": 0}

    def patch(self, coll, rec, body, user):
        if coll == "claims":
            if rec["employee"] != user["id"]:
                fail(403)
            if rec["status"] != "draft":
                fail(409)
            new = self.validate_claim(body, rec)
        elif coll == "employees":
            if not self.fin(user):
                fail(403)
            if self.has("F06") and rec["id"] == user["id"]:
                fail(403, "own record")
            new = self.validate_employee(body, rec)
        elif coll == "category_policies":
            if not self.fin(user):
                fail(403)
            new = self.validate_policy(body, rec)
        else:
            fail(403)
        rec.clear()
        rec.update(new)
        return rec

    def delete(self, coll, rec, user):
        if coll == "claims":
            if rec["employee"] != user["id"]:
                fail(403)
            if rec["status"] != "draft":
                fail(409)
        elif coll == "employees":
            if not self.fin(user):
                fail(403)
            if self.has("F06") and rec["id"] == user["id"]:
                fail(403, "own record")
        elif coll == "category_policies":
            if not self.fin(user):
                fail(403)
            if any(c["category"] == rec["category"] for c in self.recs("claims")):
                fail(409)
        else:
            fail(403)
        self.state[coll].remove(rec)

    # ---------------------------------------------------------------- actions
    def days_between(self, a, b):
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days

    def run_action(self, coll, rec, action, body, user):
        c = rec
        if action == "submit":
            if c["employee"] != user["id"]:
                fail(403)
            if c["status"] != "draft":
                fail(409)
            if self.has("F01") and c["incurred_on"] is None:
                fail(409, "incurred_on missing")
            if self.has("F02"):
                p = self.policy(c["category"])
                if c["amount"] > p["max_amount"]:
                    fail(409, "over policy maximum")
                if self.days_between(c["incurred_on"], self.today) > p["submit_within_days"]:
                    fail(409, "too late")
            c["status"] = "submitted"
            c["submitted_at"] = self.now
            return c
        if action in ("approve", "reject"):
            if self.manager_of(c) != user["id"]:
                fail(403)
            if c["status"] != "submitted":
                fail(409)
            if action == "reject":
                reason = body.get("reason")
                if not (isinstance(reason, str) and reason):
                    fail(400, "reason")
                c["status"] = "rejected"
                c["rejection_reason"] = reason
            else:
                if self.partial():
                    amt = body.get("amount", c["amount"])
                    if "amount" in body and (not is_num(amt) or amt <= 0 or amt > c["amount"]):
                        fail(400, "amount")
                    note = body.get("note")
                    if note is not None and not isinstance(note, str):
                        fail(400, "note")
                    if note is not None and not note.strip():
                        note = None
                    if amt < c["amount"] and note is None:
                        fail(400, "note required")
                    c["approved_amount"] = amt
                    c["approval_note"] = note
                elif self.has("F05"):
                    if "amount" in body or "note" in body:
                        fail(400, "partial approval withdrawn")
                c["status"] = "approved"
            c["decided_at"] = self.now
            c["decided_by"] = user["id"]
            if self.has("F14"):
                c["finance_query"] = None
            return c
        if action == "pay":
            if not self.fin(user):
                fail(403)
            if self.has("F06") and c["employee"] == user["id"]:
                fail(403, "own claim")
            if c["status"] != "approved":
                fail(409)
            c["status"] = "paid"
            if self.has("F04"):
                base = c["approved_amount"] if self.partial() else c["amount"]
                remaining = base
                recovered = 0
                for a in sorted(self.recs("advances"), key=lambda a: a["id"]):
                    if a["employee"] != c["employee"]:
                        continue
                    out = r2(a["amount"] - a["recovered"])
                    take = r2(min(out, remaining))
                    if take > 0:
                        a["recovered"] = r2(a["recovered"] + take)
                        remaining = r2(remaining - take)
                        recovered = r2(recovered + take)
                c["advance_recovered"] = recovered
                c["paid_amount"] = r2(base - recovered)
                self.emit("payment", {"claim": c["id"], "employee": c["employee"], "amount": c["paid_amount"],
                                      "advance_recovered": recovered})
            else:
                amt = c["approved_amount"] if self.partial() else c["amount"]
                self.emit("payment", {"claim": c["id"], "employee": c["employee"], "amount": amt})
            return c
        if action == "query":
            if not self.fin(user):
                fail(403)
            if c["status"] != "approved" or c["query_count"] >= 1:
                fail(409)
            if not is_text(body.get("question")):
                fail(400, "question")
            c["status"] = "submitted"
            c["decided_at"] = None
            c["decided_by"] = None
            c["finance_query"] = body["question"]
            c["query_count"] += 1
            self.emit("claim_queried", {"claim": c["id"], "manager": self.manager_of(c), "question": body["question"]})
            return c
        fail(404)

    # ---------------------------------------------------------------- UI
    def create_form(self, coll, user):
        if coll == "claims":
            return ["amount", "category", "description"] + (["incurred_on"] if self.has("F01") else [])
        if coll == "employees":
            if not self.fin(user):
                fail(403)
            return ["username", "name", "role", "manager", "department"]
        if coll == "category_policies":
            if not self.fin(user):
                fail(403)
            return ["category", "max_amount", "submit_within_days"]
        if coll == "advances":
            if not self.fin(user):
                fail(403)
            return ["employee", "amount", "purpose"]
        fail(403)
