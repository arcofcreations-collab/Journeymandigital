"""Reference implementation of `maintenance`, base spec plus E01..E07 by level (data.json `_level`)."""
from datetime import timedelta

from refcore import App, Collection, HttpError, E400, nonempty, is_int, is_num, parse_dt, valid_date, parse_date

UNFINISHED = ("open", "assigned", "in_progress")
OFFSETS0 = {"urgent": 1, "normal": 7, "low": 30}
OFFSETS3 = {"p1": 1, "p2": 3, "p3": 7, "p4": 30}
CAP = 3


class Base(Collection):
    @property
    def L(self):
        return self.app.level

    # role helpers
    def is_global(self, u):
        return u["role"] == ("manager" if self.L >= 6 else "supervisor")

    def sup_for(self, u, site):
        if self.L >= 6:
            return u["role"] == "manager" or (u["role"] == "supervisor" and u["site"] == site)
        return u["role"] == "supervisor"

    def is_supish(self, u):
        return u["role"] in ("supervisor", "manager")


class Staff(Base):
    name = "staff"
    stored = ("username", "name", "role", "site", "active")
    fields = stored

    @property
    def ROLES(self):
        r = ("requester", "technician", "supervisor")
        return r + ("manager",) if self.L >= 6 else r

    def _perm(self, ctx):
        if not self.is_global(ctx.user):
            raise HttpError(403)

    def _validate(self, body, rec=None):
        for k in body:
            if k not in self.stored:
                raise E400("not settable", k)
        merged = dict(rec or {"active": True})
        merged.update(body)
        for f in ("username", "name", "site"):
            if not nonempty(merged.get(f)):
                raise E400("required", f)
        if merged.get("role") not in self.ROLES:
            raise E400("bad role", "role")
        if not isinstance(merged.get("active"), bool):
            raise E400("bad active", "active")
        for o in self.app.recs("staff"):
            if o["username"] == merged["username"] and (rec is None or o["id"] != rec["id"]):
                raise E400("duplicate", "username")
        return merged

    def create(self, ctx, body):
        self._perm(ctx)
        m = self._validate(body)
        return self.app.insert("staff", {k: m[k] for k in self.stored})

    def patch(self, ctx, rec, body):
        self._perm(ctx)
        m = self._validate(body, rec)
        rec.update({k: m[k] for k in self.stored})
        return rec

    def delete(self, ctx, rec):
        self._perm(ctx)
        for o in self.app.recs("work_orders"):
            if o["requested_by"] == rec["id"] or o["assignee"] == rec["id"]:
                raise HttpError(409)
        if self.L >= 1:
            if any(u["used_by"] == rec["id"] for u in self.app.recs("part_usages")):
                raise HttpError(409)
        if self.L >= 4:
            if any(t["technician"] == rec["id"] for t in self.app.recs("time_entries")):
                raise HttpError(409)
        self.app.remove("staff", rec["id"])

    def ui_create_fields(self, ctx):
        self._perm(ctx)
        return list(self.stored)


class SiteScoped(Base):
    """Assets and parts: writes by global role, or (L>=6) supervisors of the record's site."""

    def _perm_create(self, ctx, body):
        u = ctx.user
        if self.L >= 6:
            if u["role"] == "manager":
                return
            if u["role"] == "supervisor":
                site = body.get("site")
                if isinstance(site, str) and site != u["site"]:
                    raise HttpError(403)
                return
            raise HttpError(403)
        if u["role"] != "supervisor":
            raise HttpError(403)

    def _perm_rec(self, ctx, rec, body=None):
        u = ctx.user
        if self.L >= 6:
            if u["role"] == "manager":
                return
            if u["role"] == "supervisor" and rec["site"] == u["site"]:
                if body and "site" in body and isinstance(body["site"], str) and body["site"] != u["site"]:
                    raise HttpError(403)
                return
            raise HttpError(403)
        if u["role"] != "supervisor":
            raise HttpError(403)

    def ui_create_fields(self, ctx):
        u = ctx.user
        ok = u["role"] in ("manager", "supervisor") if self.L >= 6 else u["role"] == "supervisor"
        if not ok:
            raise HttpError(403)
        return list(self.stored)


class Assets(SiteScoped):
    name = "assets"
    stored = ("tag", "name", "site", "criticality", "retired")
    fields = stored + ("open_orders",)

    def derive(self, ctx, rec):
        n = sum(1 for o in self.app.recs("work_orders") if o["asset"] == rec["id"] and o["status"] in UNFINISHED)
        return {"open_orders": n}

    def _validate(self, body, rec=None):
        for k in body:
            if k not in self.stored:
                raise E400("not settable", k)
        merged = dict(rec or {"retired": False})
        merged.update(body)
        for f in ("tag", "name", "site"):
            if not nonempty(merged.get(f)):
                raise E400("required", f)
        if merged.get("criticality") not in ("low", "medium", "high"):
            raise E400("bad criticality", "criticality")
        if not isinstance(merged.get("retired"), bool):
            raise E400("bad retired", "retired")
        for o in self.app.recs("assets"):
            if o["tag"] == merged["tag"] and (rec is None or o["id"] != rec["id"]):
                raise E400("duplicate", "tag")
        return merged

    def create(self, ctx, body):
        self._perm_create(ctx, body)
        m = self._validate(body)
        return self.app.insert("assets", {k: m[k] for k in self.stored})

    def patch(self, ctx, rec, body):
        self._perm_rec(ctx, rec, body)
        if body.get("retired") is True and self.derive(ctx, rec)["open_orders"] > 0:
            raise HttpError(409)
        m = self._validate(body, rec)
        rec.update({k: m[k] for k in self.stored})
        if self.L >= 7 and body.get("retired") is True:
            for s in self.app.recs("schedules"):
                if s["asset"] == rec["id"]:
                    s["active"] = False
        return rec

    def delete(self, ctx, rec):
        self._perm_rec(ctx, rec)
        if any(o["asset"] == rec["id"] for o in self.app.recs("work_orders")):
            raise HttpError(409)
        if self.L >= 7 and any(s["asset"] == rec["id"] for s in self.app.recs("schedules")):
            raise HttpError(409)
        self.app.remove("assets", rec["id"])


class Parts(SiteScoped):
    name = "parts"
    stored = ("sku", "name", "site", "unit_cost", "quantity", "reorder_level")
    fields = stored + ("low_stock",)

    def derive(self, ctx, rec):
        return {"low_stock": rec["quantity"] <= rec["reorder_level"]}

    def _validate(self, body, rec=None):
        for k in body:
            if k not in self.stored:
                raise E400("not settable", k)
        merged = dict(rec or {})
        merged.update(body)
        for f in ("sku", "name", "site"):
            if not nonempty(merged.get(f)):
                raise E400("required", f)
        if not is_num(merged.get("unit_cost")) or merged["unit_cost"] < 0:
            raise E400("bad unit_cost", "unit_cost")
        for f in ("quantity", "reorder_level"):
            if not is_int(merged.get(f)) or merged[f] < 0:
                raise E400("bad " + f, f)
        for o in self.app.recs("parts"):
            if o["sku"] == merged["sku"] and (rec is None or o["id"] != rec["id"]):
                raise E400("duplicate", "sku")
        return merged

    def create(self, ctx, body):
        self._perm_create(ctx, body)
        m = self._validate(body)
        return self.app.insert("parts", {k: m[k] for k in self.stored})

    def patch(self, ctx, rec, body):
        self._perm_rec(ctx, rec, body)
        m = self._validate(body, rec)
        rec.update({k: m[k] for k in self.stored})
        return rec

    def delete(self, ctx, rec):
        self._perm_rec(ctx, rec)
        if any(u["part"] == rec["id"] for u in self.app.recs("part_usages")):
            raise HttpError(409)
        self.app.remove("parts", rec["id"])


class ChildOfOrder(Base):
    def can_read(self, ctx, rec):
        wo = self.app.get("work_orders", rec["work_order"])
        return self.app.cols["work_orders"].can_read(ctx, wo)


class PartUsages(ChildOfOrder):
    name = "part_usages"
    stored = ("work_order", "part", "quantity", "unit_cost", "used_by", "used_at")
    fields = stored


class TimeEntries(ChildOfOrder):
    name = "time_entries"
    stored = ("work_order", "technician", "minutes", "logged_at", "note")
    fields = stored


class Schedules(Base):
    name = "schedules"
    stored = ("asset", "title", "priority", "interval_days", "next_due", "active")
    fields = stored

    def _perm_site(self, ctx, site):
        if not self.sup_for(ctx.user, site):
            raise HttpError(403)

    def _validate(self, body, rec=None):
        allowed = self.stored if rec is None else tuple(f for f in self.stored if f != "asset")
        for k in body:
            if k not in allowed:
                raise E400("not settable", k)
        merged = dict(rec or {"active": True})
        merged.update(body)
        a = merged.get("asset")
        asset = self.app.get("assets", a) if is_int(a) else None
        if asset is None:
            raise E400("bad asset", "asset")
        if rec is None and asset["retired"]:
            raise E400("retired", "asset")
        if not nonempty(merged.get("title")):
            raise E400("required", "title")
        if merged.get("priority") not in OFFSETS3:
            raise E400("bad priority", "priority")
        if "priority" in body and body["priority"] == "p4" and asset["criticality"] == "high":
            raise E400("p4 on high", "priority")
        iv = merged.get("interval_days")
        if not is_int(iv) or not 1 <= iv <= 365:
            raise E400("bad interval", "interval_days")
        if not valid_date(merged.get("next_due")):
            raise E400("bad next_due", "next_due")
        if not isinstance(merged.get("active"), bool):
            raise E400("bad active", "active")
        return merged

    def create(self, ctx, body):
        a = body.get("asset")
        asset = self.app.get("assets", a) if is_int(a) else None
        if asset is not None:
            self._perm_site(ctx, asset["site"])
        elif not self.is_supish(ctx.user):
            raise HttpError(403)
        m = self._validate(body)
        return self.app.insert("schedules", {k: m[k] for k in self.stored})

    def patch(self, ctx, rec, body):
        self._perm_site(ctx, self.app.get("assets", rec["asset"])["site"])
        m = self._validate(body, rec)
        rec.update({k: m[k] for k in self.stored})
        return rec

    def delete(self, ctx, rec):
        self._perm_site(ctx, self.app.get("assets", rec["asset"])["site"])
        if any(o.get("schedule") == rec["id"] for o in self.app.recs("work_orders")):
            raise HttpError(409)
        self.app.remove("schedules", rec["id"])

    def ui_create_fields(self, ctx):
        if not self.is_supish(ctx.user):
            raise HttpError(403)
        return list(self.stored)

    def actions(self):
        return {"generate": (self.p_gen, self.s_gen, self.do_gen)}

    def p_gen(self, ctx, rec, body):
        self._perm_site(ctx, self.app.get("assets", rec["asset"])["site"])

    def s_gen(self, ctx, rec, body):
        asset = self.app.get("assets", rec["asset"])
        if not rec["active"] or asset["retired"]:
            raise HttpError(409)
        if any(o.get("schedule") == rec["id"] and o["status"] in UNFINISHED for o in self.app.recs("work_orders")):
            raise HttpError(409)
        if ctx.today < parse_date(rec["next_due"]) - timedelta(days=7):
            raise HttpError(409)

    def do_gen(self, ctx, rec, body):
        if body:
            raise E400("no parameters")
        wo = {"asset": rec["asset"], "title": rec["title"], "description": "Preventive maintenance",
              "priority": rec["priority"], "status": "open", "requested_by": ctx.user["id"],
              "created_at": ctx.now_s, "assignee": None, "started_at": None, "completed_at": None,
              "resolution": None, "cancel_reason": None, "schedule": rec["id"]}
        new = self.app.insert("work_orders", wo)
        rec["next_due"] = (parse_date(rec["next_due"]) + timedelta(days=rec["interval_days"])).isoformat()
        self.app.emit(ctx, "preventive_generated", {"schedule": rec["id"], "work_order": new["id"],
                                                    "next_due": rec["next_due"]})
        return rec


class WorkOrders(Base):
    name = "work_orders"

    @property
    def stored(self):
        s = ["asset", "title", "description", "priority", "status", "requested_by", "created_at",
             "assignee", "started_at", "completed_at", "resolution", "labor_minutes", "cancel_reason"]
        if self.L >= 4:
            s.remove("labor_minutes")
        if 2 <= self.L <= 4:
            s.append("dispatch")
        if self.L >= 7:
            s.append("schedule")
        return tuple(s)

    @property
    def fields(self):
        f = self.stored + ("due_date", "overdue")
        if self.L >= 1:
            f += ("parts_cost",)
        if self.L >= 4:
            f += ("labor_minutes",)
        return f

    @property
    def PRIORITIES(self):
        return OFFSETS3 if self.L >= 3 else OFFSETS0

    def due(self, rec):
        return parse_dt(rec["created_at"]).date() + timedelta(days=self.PRIORITIES[rec["priority"]])

    def parts_cost(self, rec):
        return round(sum(u["quantity"] * u["unit_cost"] for u in self.app.recs("part_usages")
                         if u["work_order"] == rec["id"]), 2)

    def labor(self, rec):
        es = [t["minutes"] for t in self.app.recs("time_entries") if t["work_order"] == rec["id"]]
        return sum(es) if es else None

    def derive(self, ctx, rec):
        d = self.due(rec)
        out = {"due_date": d.isoformat(), "overdue": rec["status"] in UNFINISHED and ctx.today > d}
        if self.L >= 1:
            out["parts_cost"] = self.parts_cost(rec)
        if self.L >= 4:
            out["labor_minutes"] = self.labor(rec)
        return out

    def site_of(self, rec):
        return self.app.get("assets", rec["asset"])["site"]

    def asset_of(self, rec):
        return self.app.get("assets", rec["asset"])

    def can_read(self, ctx, rec):
        u = ctx.user
        if self.L >= 6:
            if u["role"] == "manager":
                return True
            if u["role"] == "supervisor" and self.site_of(rec) == u["site"]:
                return True
        elif u["role"] == "supervisor":
            return True
        if rec["requested_by"] == u["id"] or rec["assignee"] == u["id"]:
            return True
        return u["role"] == "technician" and self.site_of(rec) == u["site"]

    def create(self, ctx, body):
        u = ctx.user
        a = body.get("asset")
        asset = self.app.get("assets", a) if is_int(a) else None
        if asset is not None and not self.is_global(u) and asset["site"] != u["site"]:
            raise HttpError(403)
        for k in body:
            if k not in ("asset", "title", "description", "priority"):
                raise E400("not settable", k)
        if asset is None:
            raise E400("bad asset", "asset")
        if asset["retired"]:
            raise E400("retired asset", "asset")
        if not nonempty(body.get("title")):
            raise E400("required", "title")
        if body.get("priority") not in self.PRIORITIES:
            raise E400("bad priority", "priority")
        if self.L >= 3 and body["priority"] == "p4" and asset["criticality"] == "high":
            raise E400("p4 on high", "priority")
        d = body.get("description")
        if d is not None and not isinstance(d, str):
            raise E400("bad description", "description")
        rec = {"asset": asset["id"], "title": body["title"], "description": d, "priority": body["priority"],
               "status": "open", "requested_by": u["id"], "created_at": ctx.now_s, "assignee": None,
               "started_at": None, "completed_at": None, "resolution": None, "labor_minutes": None,
               "cancel_reason": None}
        if self.L >= 4:
            del rec["labor_minutes"]
        if 2 <= self.L <= 4:
            rec["dispatch"] = None
        if self.L >= 7:
            rec["schedule"] = None
        return self.app.insert("work_orders", rec)

    def patch(self, ctx, rec, body):
        u = ctx.user
        if self.sup_for(u, self.site_of(rec)):
            editable = ("title", "description", "priority")
            if rec["status"] not in UNFINISHED:
                raise HttpError(409)
        elif rec["requested_by"] == u["id"]:
            editable = ("title", "description")
            if "priority" in body:
                raise HttpError(403)
            if rec["status"] != "open":
                raise HttpError(409)
        else:
            raise HttpError(403)
        for k in body:
            if k not in editable:
                raise E400("not settable", k)
        if "title" in body and not nonempty(body["title"]):
            raise E400("required", "title")
        if "priority" in body:
            if body["priority"] not in self.PRIORITIES:
                raise E400("bad priority", "priority")
            if self.L >= 3 and body["priority"] == "p4" and self.asset_of(rec)["criticality"] == "high":
                raise E400("p4 on high", "priority")
        if "description" in body and body["description"] is not None and not isinstance(body["description"], str):
            raise E400("bad description", "description")
        rec.update(body)
        return rec

    def delete(self, ctx, rec):
        raise HttpError(403)

    def ui_create_fields(self, ctx):
        return ["asset", "title", "description", "priority"]

    # ---- actions
    def actions(self):
        a = {
            "assign": (self.p_sup, self.s_in(("open", "assigned")), self.do_assign),
            "start": (self.p_assignee, self.s_in(("assigned",)), self.do_start),
            "complete": (self.p_assignee, self.s_complete, self.do_complete),
            "cancel": (self.p_cancel, self.s_cancel, self.do_cancel),
        }
        if self.L >= 1:
            a["use_parts"] = (self.p_assignee, self.s_in(("in_progress",)), self.do_use_parts)
        if 2 <= self.L <= 4:
            a["claim"] = (self.p_claim, self.s_claim, self.do_claim)
        if self.L >= 4:
            a["log_time"] = (self.p_assignee, self.s_in(("in_progress",)), self.do_log_time)
        return a

    def load(self, staff_id, exclude=None):
        return sum(1 for o in self.app.recs("work_orders")
                   if o["assignee"] == staff_id and o["status"] in ("assigned", "in_progress") and o["id"] != exclude)

    def p_sup(self, ctx, rec, body):
        if not self.sup_for(ctx.user, self.site_of(rec)):
            raise HttpError(403)

    def p_assignee(self, ctx, rec, body):
        if rec["assignee"] != ctx.user["id"]:
            raise HttpError(403)

    def s_in(self, states):
        def check(ctx, rec, body):
            if rec["status"] not in states:
                raise HttpError(409)
        return check

    def s_complete(self, ctx, rec, body):
        if rec["status"] != "in_progress":
            raise HttpError(409)
        if self.L >= 4 and self.labor(rec) is None:
            raise HttpError(409)

    def p_cancel(self, ctx, rec, body):
        if not self.sup_for(ctx.user, self.site_of(rec)) and rec["requested_by"] != ctx.user["id"]:
            raise HttpError(403)

    def s_cancel(self, ctx, rec, body):
        allowed = UNFINISHED if self.sup_for(ctx.user, self.site_of(rec)) else ("open",)
        if rec["status"] not in allowed:
            raise HttpError(409)

    def p_claim(self, ctx, rec, body):
        u = ctx.user
        if u["role"] != "technician" or not u["active"] or u["site"] != self.site_of(rec):
            raise HttpError(403)
        if self.L >= 3 and rec["priority"] in ("p1", "p2"):
            raise HttpError(403)

    def s_claim(self, ctx, rec, body):
        if rec["status"] != "open":
            raise HttpError(409)
        if self.load(ctx.user["id"]) >= CAP:
            raise HttpError(409)

    def do_claim(self, ctx, rec, body):
        if body:
            raise E400("no parameters")
        rec.update(assignee=ctx.user["id"], status="assigned", dispatch="self")
        self.app.emit(ctx, "assignment", {"work_order": rec["id"], "asset": rec["asset"], "technician": ctx.user["id"]})
        return rec

    def do_assign(self, ctx, rec, body):
        t = body.get("technician")
        tech = self.app.get("staff", t) if is_int(t) else None
        if (tech is None or tech["role"] != "technician" or not tech["active"]
                or tech["site"] != self.site_of(rec)):
            raise E400("bad technician", "technician")
        if self.L >= 2 and tech["id"] != rec["assignee"] and self.load(tech["id"], exclude=rec["id"]) >= CAP:
            raise HttpError(409)
        rec["assignee"] = tech["id"]
        rec["status"] = "assigned"
        if 2 <= self.L <= 4:
            rec["dispatch"] = "supervisor"
        self.app.emit(ctx, "assignment", {"work_order": rec["id"], "asset": rec["asset"], "technician": tech["id"]})
        return rec

    def do_start(self, ctx, rec, body):
        rec["status"] = "in_progress"
        rec["started_at"] = ctx.now_s
        return rec

    def do_complete(self, ctx, rec, body):
        if self.L >= 4:
            for k in body:
                if k != "resolution":
                    raise E400("unknown", k)
        if not nonempty(body.get("resolution")):
            raise E400("required", "resolution")
        if self.L < 4:
            lm = body.get("labor_minutes")
            if not is_int(lm) or lm < 1:
                raise E400("bad labor_minutes", "labor_minutes")
            rec["labor_minutes"] = lm
        else:
            lm = self.labor(rec)
        rec.update(status="completed", completed_at=ctx.now_s, resolution=body["resolution"])
        payload = {"work_order": rec["id"], "asset": rec["asset"], "technician": rec["assignee"], "labor_minutes": lm}
        if self.L >= 1:
            payload["parts_cost"] = self.parts_cost(rec)
        self.app.emit(ctx, "work_completed", payload)
        return rec

    def do_cancel(self, ctx, rec, body):
        if not nonempty(body.get("reason")):
            raise E400("required", "reason")
        rec["status"] = "cancelled"
        rec["cancel_reason"] = body["reason"]
        return rec

    def do_use_parts(self, ctx, rec, body):
        items = body.get("items")
        site = self.site_of(rec)
        valid = []
        problem = None
        if set(body) - {"items"}:
            problem = "unknown"
        if not isinstance(items, list) or not items:
            raise E400("items required", "items")
        seen = set()
        for it in items:
            if not isinstance(it, dict) or set(it) != {"part", "quantity"}:
                problem = "bad item"
                continue
            p = self.app.get("parts", it["part"]) if is_int(it["part"]) else None
            q = it["quantity"]
            if p is None or p["site"] != site or not is_int(q) or q < 1:
                problem = "bad item"
                continue
            if p["id"] in seen:
                problem = "duplicate"
                continue
            seen.add(p["id"])
            valid.append((p, q))
        for p, q in valid:
            if q > p["quantity"]:
                raise HttpError(409, "insufficient stock")
        if problem:
            raise E400(problem, "items")
        for p, q in valid:
            was_low = p["quantity"] <= p["reorder_level"]
            p["quantity"] -= q
            self.app.insert("part_usages", {"work_order": rec["id"], "part": p["id"], "quantity": q,
                                            "unit_cost": p["unit_cost"], "used_by": ctx.user["id"],
                                            "used_at": ctx.now_s})
            if not was_low and p["quantity"] <= p["reorder_level"]:
                self.app.emit(ctx, "low_stock", {"part": p["id"], "sku": p["sku"], "quantity": p["quantity"]})
        return rec

    def do_log_time(self, ctx, rec, body):
        for k in body:
            if k not in ("minutes", "note"):
                raise E400("unknown", k)
        m = body.get("minutes")
        if not is_int(m) or not 1 <= m <= 600:
            raise E400("bad minutes", "minutes")
        note = body.get("note")
        if note is not None and not isinstance(note, str):
            raise E400("bad note", "note")
        self.app.insert("time_entries", {"work_order": rec["id"], "technician": ctx.user["id"], "minutes": m,
                                         "logged_at": ctx.now_s, "note": note})
        return rec

    def ui_actions(self, ctx, rec):
        return super().ui_actions(ctx, rec)


class MaintenanceApp(App):
    def __init__(self, workdir):
        import json, os
        with open(os.path.join(workdir, "data.json")) as fh:
            self.level = int(json.load(fh).get("_level") or 0)
        cols = {"staff": Staff, "assets": Assets, "work_orders": WorkOrders}
        if self.level >= 1:
            cols.update(parts=Parts, part_usages=PartUsages)
        if self.level >= 4:
            cols["time_entries"] = TimeEntries
        if self.level >= 7:
            cols["schedules"] = Schedules
        self.collections = cols
        super().__init__(workdir)

    def user_by_name(self, username):
        for s in self.db["staff"]:
            if s["username"] == username:
                return s
        return None
