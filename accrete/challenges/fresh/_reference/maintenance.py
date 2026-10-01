"""Reference maintenance app: base + F07 (asset transfer), F08 (requester cancel while assigned)."""
from core import RefApp, fail, is_int, is_text, add_days

UNFINISHED = ("open", "assigned", "in_progress")
OFFSET = {"urgent": 1, "normal": 7, "low": 30}


class Maintenance(RefApp):
    user_collection = "staff"
    strict_filters = True

    def collections(self):
        return ["staff", "assets", "work_orders"]

    def actions(self, coll):
        if coll == "work_orders":
            return ["assign", "start", "complete", "cancel"]
        if coll == "assets" and self.has("F07"):
            return ["transfer"]
        return []

    def filter_fields(self, coll):
        return {
            "staff": {"id", "username", "name", "role", "site", "active"},
            "assets": {"id", "tag", "name", "site", "criticality", "retired", "open_orders"},
            "work_orders": {"id", "asset", "title", "description", "priority", "status", "requested_by",
                            "created_at", "assignee", "started_at", "completed_at", "resolution",
                            "labor_minutes", "cancel_reason", "due_date", "overdue"},
        }[coll]

    def listing(self, coll, query, user):
        for k, _ in query:
            if k not in self.filter_fields(coll):
                fail(400, f"unknown filter {k}")
        items = [self.serialize(coll, r, user) for r in sorted(self.state[coll], key=lambda r: r["id"])
                 if self.can_read(coll, r, user)]
        from core import matches
        for k, v in query:
            items = [it for it in items if matches(it.get(k), v)]
        return items

    # ---------------------------------------------------------------- helpers
    def sup(self, user):
        return user["role"] == "supervisor"

    def asset_of(self, wo):
        return self.get("assets", wo["asset"])

    def open_orders(self, aid):
        return sum(1 for w in self.recs("work_orders") if w["asset"] == aid and w["status"] in UNFINISHED)

    def serialize(self, coll, rec, user):
        d = dict(rec)
        if coll == "assets":
            d["open_orders"] = self.open_orders(rec["id"])
        if coll == "work_orders":
            due = add_days(rec["created_at"][:10], OFFSET[rec["priority"]])
            d["due_date"] = due
            d["overdue"] = rec["status"] in UNFINISHED and self.today > due
        return d

    def can_read(self, coll, w, user):
        if coll != "work_orders":
            return True
        if self.sup(user) or w["requested_by"] == user["id"] or w["assignee"] == user["id"]:
            return True
        return user["role"] == "technician" and user["site"] == self.asset_of(w)["site"]

    # ---------------------------------------------------------------- staff / assets
    def validate(self, coll, body, rec=None):
        if coll == "staff":
            allowed = ("username", "name", "role", "site", "active")
            required = ("username", "name", "role", "site")
        else:
            allowed = ("tag", "name", "site", "criticality", "retired")
            required = ("tag", "name", "site", "criticality")
        for k in body:
            if k not in allowed:
                fail(400, k)
        out = dict(rec or {})
        out.update(body)
        for k in required:
            if k in ("role", "criticality"):
                continue
            if not is_text(out.get(k)):
                fail(400, k)
        if coll == "staff":
            if out.get("role") not in ("requester", "technician", "supervisor"):
                fail(400, "role")
            out.setdefault("active", True)
            if not isinstance(out["active"], bool):
                fail(400, "active")
            key = "username"
        else:
            if out.get("criticality") not in ("low", "medium", "high"):
                fail(400, "criticality")
            out.setdefault("retired", False)
            if not isinstance(out["retired"], bool):
                fail(400, "retired")
            key = "tag"
        for r in self.recs(coll):
            if r[key] == out[key] and (rec is None or r["id"] != rec["id"]):
                fail(400, "duplicate " + key)
        return out

    def create(self, coll, body, user):
        if coll == "work_orders":
            return self.create_wo(body, user)
        if not self.sup(user):
            fail(403)
        rec = self.validate(coll, body)
        rec["id"] = self.next_id(coll)
        self.recs(coll).append(rec)
        return rec

    def patch(self, coll, rec, body, user):
        if coll == "work_orders":
            return self.patch_wo(rec, body, user)
        if not self.sup(user):
            fail(403)
        if coll == "assets":
            if body.get("retired") is True and self.open_orders(rec["id"]) > 0:
                fail(409)
            if self.has("F07") and "site" in body:
                fail(400, "use transfer to change the site")
        new = self.validate(coll, body, rec)
        rec.clear()
        rec.update(new)
        return rec

    def delete(self, coll, rec, user):
        if coll == "work_orders" or not self.sup(user):
            fail(403)
        wos = self.recs("work_orders")
        if coll == "staff" and any(w["requested_by"] == rec["id"] or w["assignee"] == rec["id"] for w in wos):
            fail(409)
        if coll == "assets" and any(w["asset"] == rec["id"] for w in wos):
            fail(409)
        self.state[coll].remove(rec)

    # ---------------------------------------------------------------- work orders
    def create_wo(self, body, user):
        a = body.get("asset")
        asset = self.get("assets", a) if is_int(a) else None
        if user["role"] != "supervisor" and asset is not None and asset["site"] != user["site"]:
            fail(403)
        for k in body:
            if k not in ("asset", "title", "description", "priority"):
                fail(400, k)
        if asset is None:
            fail(400, "asset")
        if asset["retired"]:
            fail(400, "retired")
        if not is_text(body.get("title")):
            fail(400, "title")
        d = body.get("description")
        if d is not None and not isinstance(d, str):
            fail(400, "description")
        if body.get("priority") not in OFFSET:
            fail(400, "priority")
        rec = {"id": self.next_id("work_orders"), "asset": asset["id"], "title": body["title"],
               "description": d, "priority": body["priority"], "status": "open", "requested_by": user["id"],
               "created_at": self.now, "assignee": None, "started_at": None, "completed_at": None,
               "resolution": None, "labor_minutes": None, "cancel_reason": None}
        self.recs("work_orders").append(rec)
        return rec

    def patch_wo(self, w, body, user):
        if self.sup(user):
            if w["status"] not in UNFINISHED:
                fail(409)
        elif w["requested_by"] == user["id"]:
            if "priority" in body:
                fail(403)
            if w["status"] != "open":
                fail(409)
        else:
            fail(403)
        for k in body:
            if k not in ("title", "description", "priority"):
                fail(400, k)
        if "title" in body and not is_text(body["title"]):
            fail(400, "title")
        if "description" in body and body["description"] is not None and not isinstance(body["description"], str):
            fail(400, "description")
        if "priority" in body and body["priority"] not in OFFSET:
            fail(400, "priority")
        w.update(body)
        return w

    def run_action(self, coll, rec, action, body, user):
        if coll == "assets":
            return self.transfer(rec, body, user)
        w = rec
        if action == "assign":
            if not self.sup(user):
                fail(403)
            if w["status"] not in ("open", "assigned"):
                fail(409)
            t = body.get("technician")
            tech = self.get("staff", t) if is_int(t) else None
            if (tech is None or tech["role"] != "technician" or not tech["active"]
                    or tech["site"] != self.asset_of(w)["site"]):
                fail(400, "technician")
            w["assignee"] = tech["id"]
            w["status"] = "assigned"
            self.emit("assignment", {"work_order": w["id"], "asset": w["asset"], "technician": tech["id"]})
            return w
        if action == "start":
            if w["assignee"] != user["id"]:
                fail(403)
            if w["status"] != "assigned":
                fail(409)
            w["status"] = "in_progress"
            w["started_at"] = self.now
            return w
        if action == "complete":
            if w["assignee"] != user["id"]:
                fail(403)
            if w["status"] != "in_progress":
                fail(409)
            if not is_text(body.get("resolution")):
                fail(400, "resolution")
            lm = body.get("labor_minutes")
            if not is_int(lm) or lm < 1:
                fail(400, "labor_minutes")
            w.update(status="completed", completed_at=self.now, resolution=body["resolution"], labor_minutes=lm)
            self.emit("work_completed", {"work_order": w["id"], "asset": w["asset"], "technician": w["assignee"],
                                         "labor_minutes": lm})
            return w
        if action == "cancel":
            if self.sup(user):
                if w["status"] not in UNFINISHED:
                    fail(409)
            elif w["requested_by"] == user["id"]:
                allowed = ("open", "assigned") if self.has("F08") else ("open",)
                if w["status"] not in allowed:
                    fail(409)
            else:
                fail(403)
            if not is_text(body.get("reason")):
                fail(400, "reason")
            had_assignee = w["status"] in ("assigned", "in_progress")
            w["status"] = "cancelled"
            w["cancel_reason"] = body["reason"]
            if self.has("F08") and had_assignee:
                self.emit("assignment_cancelled", {"work_order": w["id"], "technician": w["assignee"],
                                                   "reason": body["reason"]})
            return w
        fail(404)

    # ---------------------------------------------------------------- F07
    def transfer(self, asset, body, user):
        if not self.sup(user):
            fail(403)
        orders = [w for w in sorted(self.recs("work_orders"), key=lambda w: w["id"]) if w["asset"] == asset["id"]]
        if asset["retired"] or any(w["status"] == "in_progress" for w in orders):
            fail(409)
        for k in body:
            if k != "site":
                fail(400, k)
        site = body.get("site")
        if not is_text(site) or site == asset["site"] or not any(s["site"] == site for s in self.recs("staff")):
            fail(400, "site")
        old = asset["site"]
        unassigned = []
        for w in orders:
            if w["status"] == "assigned":
                w["status"] = "open"
                w["assignee"] = None
                unassigned.append(w["id"])
        asset["site"] = site
        self.emit("asset_transferred", {"asset": asset["id"], "from_site": old, "to_site": site,
                                        "unassigned": unassigned})
        return asset

    # ---------------------------------------------------------------- UI
    def action_probe_body(self, coll, rec, action, user):
        return {}

    def create_form(self, coll, user):
        if coll == "work_orders":
            return ["asset", "title", "description", "priority"]
        if not self.sup(user):
            fail(403)
        if coll == "staff":
            return ["username", "name", "role", "site", "active"]
        return ["tag", "name", "site", "criticality", "retired"]
