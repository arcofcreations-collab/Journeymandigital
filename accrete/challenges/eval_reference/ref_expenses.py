"""Reference `expenses` (base) plus E11 (cost centres), E12 (offboarding), E13 (withdraw/revise)."""
import json
import os
from datetime import timedelta

from refcore import App, Collection, HttpError, E400, nonempty, is_int, is_num, parse_dt

CATS = ("travel", "meals", "equipment", "other")


class XBase(Collection):
    @property
    def lv(self):
        return self.app.level

    def fin(self, ctx):
        return ctx.user["role"] == "finance"

    def writer(self, ctx):
        """E12: inactive employees may not write."""
        if self.lv == "E12" and not ctx.user.get("active", True):
            raise HttpError(403)


class Employees(XBase):
    name = "employees"

    @property
    def stored(self):
        s = ("username", "name", "role", "manager", "department")
        return s + ("active",) if self.lv == "E12" else s

    @property
    def fields(self):
        return self.stored

    def _validate(self, body, rec=None):
        settable = ("username", "name", "role", "manager", "department")
        for k in body:
            if k not in settable:
                raise E400("unknown", k)
        m = dict(rec or {"manager": None})
        m.update(body)
        for f in ("username", "name", "department"):
            if not nonempty(m.get(f)):
                raise E400("required", f)
        if m.get("role") not in ("employee", "manager", "finance"):
            raise E400("role", "role")
        if m.get("manager") is not None:
            mg = self.app.get("employees", m["manager"]) if is_int(m["manager"]) else None
            if mg is None:
                raise E400("manager", "manager")
            if self.lv == "E12" and not mg.get("active", True):
                raise E400("inactive manager", "manager")
        for o in self.app.recs("employees"):
            if o["username"] == m["username"] and (rec is None or o["id"] != rec["id"]):
                raise E400("dup", "username")
        return m

    def create(self, ctx, body):
        if not self.fin(ctx):
            raise HttpError(403)
        self.writer(ctx)
        m = self._validate(body)
        rec = {k: m.get(k) for k in ("username", "name", "role", "manager", "department")}
        if self.lv == "E12":
            rec["active"] = True
        return self.app.insert("employees", rec)

    def patch(self, ctx, rec, body):
        if not self.fin(ctx):
            raise HttpError(403)
        self.writer(ctx)
        m = self._validate(body, rec)
        rec.update({k: m.get(k) for k in ("username", "name", "role", "manager", "department")})
        return rec

    def delete(self, ctx, rec):
        if not self.fin(ctx):
            raise HttpError(403)
        self.writer(ctx)
        self.app.remove("employees", rec["id"])

    def ui_create_fields(self, ctx):
        if not self.fin(ctx):
            raise HttpError(403)
        return ["username", "name", "role", "manager", "department"]

    def actions(self):
        if self.lv != "E12":
            return {}
        return {"offboard": (self.p_off, self.s_off, self.do_off)}

    def p_off(self, ctx, rec, body):
        if not self.fin(ctx):
            raise HttpError(403)
        self.writer(ctx)

    def s_off(self, ctx, rec, body):
        if not rec["active"]:
            raise HttpError(409)
        if any(c["employee"] == rec["id"] and c["status"] in ("submitted", "approved") for c in self.app.recs("claims")):
            raise HttpError(409)

    def do_off(self, ctx, rec, body):
        s = body.get("successor")
        succ = self.app.get("employees", s) if is_int(s) else None
        if (succ is None or not succ["active"] or succ["role"] != "manager" or succ["id"] == rec["id"]
                or succ["manager"] == rec["id"]):
            raise E400("successor", "successor")
        rec["active"] = False
        reassigned = []
        for e in self.app.recs("employees"):
            if e["manager"] == rec["id"]:
                e["manager"] = succ["id"]
                reassigned.append(e["id"])
        deleted = [c["id"] for c in self.app.recs("claims") if c["employee"] == rec["id"] and c["status"] == "draft"]
        for cid in deleted:
            self.app.remove("claims", cid)
        self.app.emit(ctx, "employee_offboarded", {"employee": rec["id"], "successor": succ["id"],
                                                   "reassigned": reassigned, "deleted_claims": deleted})
        return rec


class CostCentres(XBase):
    name = "cost_centres"
    stored = ("code", "name", "department", "budget")
    fields = stored + ("committed", "remaining")

    def committed(self, rid):
        return round(sum(c["amount"] for c in self.app.recs("claims")
                         if c.get("cost_centre") == rid and c["status"] in ("approved", "paid")), 2)

    def derive(self, ctx, rec):
        com = self.committed(rec["id"])
        return {"committed": com, "remaining": round(rec["budget"] - com, 2)}

    def _validate(self, body, rec=None):
        for k in body:
            if k not in self.stored:
                raise E400("unknown", k)
        m = dict(rec or {"department": None})
        m.update(body)
        for f in ("code", "name"):
            if not nonempty(m.get(f)):
                raise E400("required", f)
        if m.get("department") is not None and not nonempty(m["department"]):
            raise E400("department", "department")
        if not is_num(m.get("budget")) or m["budget"] < 0:
            raise E400("budget", "budget")
        for o in self.app.recs("cost_centres"):
            if rec is not None and o["id"] == rec["id"]:
                continue
            if o["code"] == m["code"]:
                raise E400("dup", "code")
            if m["department"] is not None and o["department"] == m["department"]:
                raise E400("dup", "department")
        return m

    def create(self, ctx, body):
        if not self.fin(ctx):
            raise HttpError(403)
        m = self._validate(body)
        return self.app.insert("cost_centres", {k: m.get(k) for k in self.stored})

    def patch(self, ctx, rec, body):
        if not self.fin(ctx):
            raise HttpError(403)
        if "budget" in body and is_num(body["budget"]) and body["budget"] < self.committed(rec["id"]):
            raise HttpError(409)
        m = self._validate(body, rec)
        rec.update({k: m.get(k) for k in self.stored})
        return rec

    def delete(self, ctx, rec):
        if not self.fin(ctx):
            raise HttpError(403)
        if any(c.get("cost_centre") == rec["id"] for c in self.app.recs("claims")):
            raise HttpError(409)
        self.app.remove("cost_centres", rec["id"])

    def ui_create_fields(self, ctx):
        if not self.fin(ctx):
            raise HttpError(403)
        return list(self.stored)


class Claims(XBase):
    name = "claims"

    @property
    def stored(self):
        s = ("employee", "amount", "category", "description", "status", "submitted_at", "decided_at",
             "decided_by", "rejection_reason")
        if self.lv == "E11":
            s += ("cost_centre",)
        if self.lv == "E13":
            s += ("revision", "previous_rejection_reason")
        return s

    @property
    def fields(self):
        return self.stored

    @property
    def editable(self):
        e = ("amount", "category", "description")
        return e + ("cost_centre",) if self.lv == "E11" else e

    def mgr(self, rec):
        return self.app.get("employees", rec["employee"])["manager"]

    def can_read(self, ctx, rec):
        u = ctx.user
        return self.fin(ctx) or rec["employee"] == u["id"] or self.mgr(rec) == u["id"]

    def _check(self, body):
        for k in body:
            if k not in self.editable:
                raise E400("not settable", k)
        if "amount" in body and (not is_num(body["amount"]) or not 0 < body["amount"] <= 5000):
            raise E400("amount", "amount")
        if "category" in body and body["category"] not in CATS:
            raise E400("category", "category")
        if "description" in body and not nonempty(body["description"]):
            raise E400("description", "description")
        if "cost_centre" in body:
            cc = body["cost_centre"]
            if not (is_int(cc) and self.app.get("cost_centres", cc)):
                raise E400("cost_centre", "cost_centre")

    def create(self, ctx, body):
        self.writer(ctx)
        self._check(body)
        for f in ("amount", "category", "description"):
            if f not in body:
                raise E400("required", f)
        rec = {"employee": ctx.user["id"], "amount": body["amount"], "category": body["category"],
               "description": body["description"], "status": "draft", "submitted_at": None, "decided_at": None,
               "decided_by": None, "rejection_reason": None}
        if self.lv == "E11":
            cc = body.get("cost_centre")
            if cc is None:
                match = [c for c in self.app.recs("cost_centres") if c["department"] == ctx.user["department"]]
                if not match:
                    raise E400("no default cost centre", "cost_centre")
                cc = match[0]["id"]
            rec["cost_centre"] = cc
        if self.lv == "E13":
            rec.update(revision=0, previous_rejection_reason=None)
        return self.app.insert("claims", rec)

    def patch(self, ctx, rec, body):
        if rec["employee"] != ctx.user["id"]:
            raise HttpError(403)
        self.writer(ctx)
        if rec["status"] != "draft":
            raise HttpError(409)
        self._check(body)
        rec.update(body)
        return rec

    def delete(self, ctx, rec):
        if rec["employee"] != ctx.user["id"]:
            raise HttpError(403)
        self.writer(ctx)
        if rec["status"] != "draft":
            raise HttpError(409)
        self.app.remove("claims", rec["id"])

    def ui_create_fields(self, ctx):
        if self.lv == "E12" and not ctx.user.get("active", True):
            raise HttpError(403)
        return list(self.editable)

    def actions(self):
        a = {
            "submit": (self.p_owner, self.s_is("draft"), self.do_submit),
            "approve": (self.p_mgr, self.s_approve, self.do_approve),
            "reject": (self.p_mgr, self.s_is("submitted"), self.do_reject),
            "pay": (self.p_fin, self.s_is("approved"), self.do_pay),
        }
        if self.lv == "E13":
            a["withdraw"] = (self.p_owner, self.s_withdraw, self.do_withdraw)
            a["revise"] = (self.p_owner, self.s_revise, self.do_revise)
        return a

    def p_owner(self, ctx, rec, body):
        if rec["employee"] != ctx.user["id"]:
            raise HttpError(403)
        self.writer(ctx)

    def p_mgr(self, ctx, rec, body):
        if self.mgr(rec) != ctx.user["id"]:
            raise HttpError(403)
        self.writer(ctx)

    def p_fin(self, ctx, rec, body):
        if not self.fin(ctx):
            raise HttpError(403)
        self.writer(ctx)

    def s_is(self, st):
        def check(ctx, rec, body):
            if rec["status"] != st:
                raise HttpError(409)
        return check

    def s_approve(self, ctx, rec, body):
        if rec["status"] != "submitted":
            raise HttpError(409)
        if self.lv == "E11":
            cc = self.app.get("cost_centres", rec["cost_centre"])
            com = self.app.cols["cost_centres"].committed(cc["id"])
            if round(com + rec["amount"], 2) > cc["budget"]:
                raise HttpError(409)

    def s_withdraw(self, ctx, rec, body):
        if rec["status"] != "submitted":
            raise HttpError(409)
        if ctx.now > parse_dt(rec["submitted_at"]) + timedelta(days=7):
            raise HttpError(409)

    def s_revise(self, ctx, rec, body):
        if rec["status"] != "rejected" or rec["revision"] >= 2:
            raise HttpError(409)

    def do_submit(self, ctx, rec, body):
        rec.update(status="submitted", submitted_at=ctx.now_s)
        return rec

    def do_approve(self, ctx, rec, body):
        rec.update(status="approved", decided_at=ctx.now_s, decided_by=ctx.user["id"])
        return rec

    def do_reject(self, ctx, rec, body):
        if not nonempty(body.get("reason")):
            raise E400("reason", "reason")
        rec.update(status="rejected", decided_at=ctx.now_s, decided_by=ctx.user["id"], rejection_reason=body["reason"])
        return rec

    def do_pay(self, ctx, rec, body):
        rec["status"] = "paid"
        payload = {"claim": rec["id"], "employee": rec["employee"], "amount": rec["amount"]}
        if self.lv == "E11":
            payload["cost_centre"] = rec["cost_centre"]
        self.app.emit(ctx, "payment", payload)
        return rec

    def do_withdraw(self, ctx, rec, body):
        rec.update(status="draft", submitted_at=None)
        return rec

    def do_revise(self, ctx, rec, body):
        rec.update(status="draft", previous_rejection_reason=rec["rejection_reason"], rejection_reason=None,
                   decided_at=None, decided_by=None, submitted_at=None, revision=rec["revision"] + 1)
        return rec


class ExpensesApp(App):
    def __init__(self, workdir):
        with open(os.path.join(workdir, "data.json")) as fh:
            self.level = json.load(fh).get("_level")
        cols = {"employees": Employees, "claims": Claims}
        if self.level == "E11":
            cols["cost_centres"] = CostCentres
        self.collections = cols
        super().__init__(workdir)

    def user_by_name(self, username):
        for e in self.db["employees"]:
            if e["username"] == username:
                return e
        return None
