"""Reference `library` (base) plus E08 (copies), E09 (guardians), E14 (lost copies, on top of E08).

data.json `_level`: None (base), "E08", "E09", "E14".
"""
import json
import os
from datetime import timedelta

from refcore import App, Collection, HttpError, E400, nonempty, is_int, parse_dt


class LBase(Collection):
    @property
    def lv(self):
        return self.app.level

    @property
    def copies_on(self):
        return self.lv in ("E08", "E14")

    def lib(self, ctx):
        return ctx.user["role"] == "librarian"


class Members(LBase):
    name = "members"

    @property
    def stored(self):
        s = ("username", "name", "role", "active")
        return s + ("guardian",) if self.lv == "E09" else s

    @property
    def fields(self):
        return self.stored

    def dependants(self, mid):
        return [m["id"] for m in self.app.recs("members") if m.get("guardian") == mid]

    def can_read(self, ctx, rec):
        if self.lib(ctx) or rec["id"] == ctx.user["id"]:
            return True
        return self.lv == "E09" and rec.get("guardian") == ctx.user["id"]

    def _validate(self, body, rec=None):
        for k in body:
            if k not in self.stored:
                raise E400("unknown", k)
        m = dict(rec or {"active": True, "guardian": None})
        m.update(body)
        for f in ("username", "name"):
            if not nonempty(m.get(f)):
                raise E400("required", f)
        if m.get("role") not in ("member", "librarian"):
            raise E400("role", "role")
        if not isinstance(m.get("active"), bool):
            raise E400("active", "active")
        for o in self.app.recs("members"):
            if o["username"] == m["username"] and (rec is None or o["id"] != rec["id"]):
                raise E400("dup", "username")
        if self.lv == "E09" and m.get("guardian") is not None:
            g = m["guardian"]
            gm = self.app.get("members", g) if is_int(g) else None
            if gm is None or (rec is not None and g == rec["id"]):
                raise E400("guardian", "guardian")
            if gm.get("guardian") is not None:
                raise E400("guardian has guardian", "guardian")
            if rec is not None and self.dependants(rec["id"]):
                raise E400("is a guardian", "guardian")
        return m

    def create(self, ctx, body):
        if not self.lib(ctx):
            raise HttpError(403)
        m = self._validate(body)
        return self.app.insert("members", {k: m.get(k) for k in self.stored})

    def patch(self, ctx, rec, body):
        if not self.lib(ctx):
            if rec["id"] != ctx.user["id"] or set(body) - {"name"}:
                raise HttpError(403)
        m = self._validate(body, rec)
        rec.update({k: m.get(k) for k in self.stored})
        return rec

    def delete(self, ctx, rec):
        if not self.lib(ctx):
            raise HttpError(403)
        if self.lv == "E09" and self.dependants(rec["id"]):
            raise HttpError(409)
        self.app.remove("members", rec["id"])

    def ui_create_fields(self, ctx):
        if not self.lib(ctx):
            raise HttpError(403)
        return list(self.stored)


class Books(LBase):
    name = "books"
    stored = ("title", "author", "isbn", "year")

    @property
    def fields(self):
        f = self.stored + ("status",)
        return f + ("available_copies",) if self.copies_on else f

    def copy_list(self, bid):
        return [c for c in self.app.recs("copies") if c["book"] == bid]

    def derive(self, ctx, rec):
        if not self.copies_on:
            on = any(l["book"] == rec["id"] and l["returned_at"] is None and not l.get("lost_at")
                     for l in self.app.recs("loans"))
            return {"status": "on_loan" if on else "available"}
        cps = [c for c in self.copy_list(rec["id"]) if not c.get("lost")]
        cc = self.app.cols["copies"]
        avail = [c for c in cps if cc.cstatus(c) == "available"]
        if not cps:
            st = "unavailable"
        elif avail:
            st = "available"
        else:
            st = "on_loan"
        return {"status": st, "available_copies": len(avail)}

    def _validate(self, body, rec=None):
        for k in body:
            if k not in self.stored:
                raise E400("unknown", k)
        m = dict(rec or {"year": None})
        m.update(body)
        for f in ("title", "author", "isbn"):
            if not nonempty(m.get(f)):
                raise E400("required", f)
        if m.get("year") is not None and not is_int(m["year"]):
            raise E400("year", "year")
        for o in self.app.recs("books"):
            if o["isbn"] == m["isbn"] and (rec is None or o["id"] != rec["id"]):
                raise E400("dup", "isbn")
        return m

    def create(self, ctx, body):
        if not self.lib(ctx):
            raise HttpError(403)
        m = self._validate(body)
        return self.app.insert("books", {k: m.get(k) for k in self.stored})

    def patch(self, ctx, rec, body):
        if not self.lib(ctx):
            raise HttpError(403)
        m = self._validate(body, rec)
        rec.update({k: m.get(k) for k in self.stored})
        return rec

    def delete(self, ctx, rec):
        if not self.lib(ctx):
            raise HttpError(403)
        if any(l["book"] == rec["id"] for l in self.app.recs("loans")):
            raise HttpError(409)
        if self.copies_on:
            for c in self.copy_list(rec["id"]):
                self.app.remove("copies", c["id"])
        self.app.remove("books", rec["id"])

    def ui_create_fields(self, ctx):
        if not self.lib(ctx):
            raise HttpError(403)
        return list(self.stored)

    def actions(self):
        return {"borrow": (self.p_borrow, self.s_none, self.do_borrow)}

    def p_borrow(self, ctx, rec, body):
        if self.lib(ctx) or body is None:
            return
        target = body.get("member", ctx.user["id"])
        if target == ctx.user["id"]:
            return
        if self.lv == "E09":
            t = self.app.get("members", target) if is_int(target) else None
            if t is not None and t.get("guardian") == ctx.user["id"]:
                return
        raise HttpError(403)

    def s_none(self, ctx, rec, body):
        if body is None:  # UI: book state only
            if self.derive(ctx, rec)["status"] != "available":
                raise HttpError(409)

    def open_loans(self, mid):
        return sum(1 for l in self.app.recs("loans")
                   if l["member"] == mid and l["returned_at"] is None and not l.get("lost_at"))

    def do_borrow(self, ctx, rec, body):
        mid = body.get("member", ctx.user["id"]) if self.lib(ctx) else body.get("member", ctx.user["id"])
        member = self.app.get("members", mid) if is_int(mid) else None
        if self.derive(ctx, rec)["status"] != "available":
            raise HttpError(409)
        if member is None:
            raise E400("member", "member")
        if not member["active"] or self.open_loans(member["id"]) >= 3:
            raise HttpError(409)
        loan = {"book": rec["id"], "member": member["id"], "borrowed_at": ctx.now_s,
                "due_at": (ctx.today + timedelta(days=14)).isoformat(), "returned_at": None}
        payload_extra = {}
        if self.copies_on:
            cc = self.app.cols["copies"]
            avail = [c for c in self.copy_list(rec["id"]) if not c.get("lost") and cc.cstatus(c) == "available"]
            copy = min(avail, key=lambda c: c["id"])
            loan["copy"] = copy["id"]
            payload_extra = {"copy": copy["id"]}
        if self.lv == "E14":
            loan["lost_at"] = None
        new = self.app.insert("loans", loan)
        self.app.emit(ctx, "loan_created", dict({"loan": new["id"], "book": rec["id"], "member": member["id"]},
                                                **payload_extra))
        return rec


class Copies(LBase):
    name = "copies"

    @property
    def stored(self):
        return ("book", "barcode", "lost") if self.lv == "E14" else ("book", "barcode")

    @property
    def fields(self):
        return self.stored + ("status",)

    def cstatus(self, c):
        if c.get("lost"):
            return "lost"
        on = any(l.get("copy") == c["id"] and l["returned_at"] is None and not l.get("lost_at")
                 for l in self.app.recs("loans"))
        return "on_loan" if on else "available"

    def derive(self, ctx, rec):
        return {"status": self.cstatus(rec)}

    def create(self, ctx, body):
        if not self.lib(ctx):
            raise HttpError(403)
        for k in body:
            if k not in ("book", "barcode"):
                raise E400("unknown", k)
        b = body.get("book")
        if not (is_int(b) and self.app.get("books", b)):
            raise E400("book", "book")
        self._barcode(body.get("barcode"))
        rec = {"book": b, "barcode": body["barcode"]}
        if self.lv == "E14":
            rec["lost"] = False
        return self.app.insert("copies", rec)

    def _barcode(self, bc, rid=None):
        if not nonempty(bc):
            raise E400("barcode", "barcode")
        for c in self.app.recs("copies"):
            if c["barcode"] == bc and c["id"] != rid:
                raise E400("dup", "barcode")

    def patch(self, ctx, rec, body):
        if not self.lib(ctx):
            raise HttpError(403)
        for k in body:
            if k != "barcode":
                raise E400("unknown", k)
        if "barcode" in body:
            self._barcode(body["barcode"], rec["id"])
            rec["barcode"] = body["barcode"]
        return rec

    def delete(self, ctx, rec):
        if not self.lib(ctx):
            raise HttpError(403)
        if any(l.get("copy") == rec["id"] for l in self.app.recs("loans")):
            raise HttpError(409)
        self.app.remove("copies", rec["id"])

    def ui_create_fields(self, ctx):
        if not self.lib(ctx):
            raise HttpError(403)
        return ["book", "barcode"]

    def actions(self):
        if self.lv != "E14":
            return {}
        return {"found": (self.p_lib, self.s_lost, self.do_found)}

    def p_lib(self, ctx, rec, body):
        if not self.lib(ctx):
            raise HttpError(403)

    def s_lost(self, ctx, rec, body):
        if not rec.get("lost"):
            raise HttpError(409)

    def do_found(self, ctx, rec, body):
        rec["lost"] = False
        return rec


class Loans(LBase):
    name = "loans"

    @property
    def stored(self):
        s = ("book", "member", "borrowed_at", "due_at", "returned_at")
        if self.copies_on:
            s = ("book", "copy", "member", "borrowed_at", "due_at", "returned_at")
        if self.lv == "E14":
            s += ("lost_at",)
        return s

    @property
    def fields(self):
        return self.stored + ("overdue",)

    def derive(self, ctx, rec):
        from refcore import parse_date
        od = rec["returned_at"] is None and not rec.get("lost_at") and ctx.today > parse_date(rec["due_at"])
        return {"overdue": od}

    def can_read(self, ctx, rec):
        if self.lib(ctx) or rec["member"] == ctx.user["id"]:
            return True
        if self.lv == "E09":
            m = self.app.get("members", rec["member"])
            return m is not None and m.get("guardian") == ctx.user["id"]
        return False

    def actions(self):
        a = {"return": (self.p_return, self.s_open, self.do_return)}
        if self.lv == "E14":
            a["declare_lost"] = (self.p_lib, self.s_open, self.do_lost)
        return a

    def p_lib(self, ctx, rec, body):
        if not self.lib(ctx):
            raise HttpError(403)

    def p_return(self, ctx, rec, body):
        if self.lib(ctx) or rec["member"] == ctx.user["id"]:
            return
        if self.lv == "E09":
            m = self.app.get("members", rec["member"])
            if m is not None and m.get("guardian") == ctx.user["id"]:
                return
        raise HttpError(403)

    def s_open(self, ctx, rec, body):
        if rec["returned_at"] is not None or rec.get("lost_at"):
            raise HttpError(409)

    def do_return(self, ctx, rec, body):
        rec["returned_at"] = ctx.now_s
        return rec

    def do_lost(self, ctx, rec, body):
        rec["lost_at"] = ctx.now_s
        c = self.app.get("copies", rec["copy"])
        c["lost"] = True
        self.app.emit(ctx, "copy_lost", {"loan": rec["id"], "copy": c["id"], "book": rec["book"],
                                         "member": rec["member"]})
        return rec


class LibraryApp(App):
    def __init__(self, workdir):
        with open(os.path.join(workdir, "data.json")) as fh:
            self.level = json.load(fh).get("_level")
        cols = {"members": Members, "books": Books, "loans": Loans}
        if self.level in ("E08", "E14"):
            cols["copies"] = Copies
        self.collections = cols
        super().__init__(workdir)

    def user_by_name(self, username):
        for m in self.db["members"]:
            if m["username"] == username:
                return m
        return None
