"""Data migrations for the maintenance E-sequence (reference only). migrate(data, level) applies E01..E<level>."""
import copy

PARTS = [
    # id, sku, name, site, unit_cost, quantity, reorder_level
    (1, "FLT-AHU", "AHU filter", "North", 42.5, 12, 4),
    (2, "BELT-A40", "V-belt A40", "North", 18.0, 3, 2),
    (3, "FUSE-10A", "Fuse 10A", "North", 1.25, 50, 10),
    (4, "BRG-6204", "Bearing 6204", "South", 9.8, 6, 2),
    (5, "BELT-A40-S", "V-belt A40", "South", 18.0, 2, 2),
    (6, "SEAL-KIT", "Pump seal kit", "South", 64.0, 1, 0),
    (7, "LAMP-LED", "LED lamp", "East", 7.4, 20, 5),
    (8, "REMOTE-DK", "Dock door remote", "North", 23.9, 0, 1),
]

SCHEDULES = [
    # id, asset, title, priority, interval_days, next_due, active
    (1, 3, "Boiler annual service", "p2", 365, "2026-03-05", True),
    (2, 16, "Conveyor belt inspection", "p3", 30, "2026-03-20", True),
    (3, 30, "Generator load test", "p3", 90, "2026-02-01", False),
    (4, 25, "Filter replacement", "p4", 60, "2026-02-15", True),
    (5, 21, "Generator monthly run", "p2", 30, "2026-03-03", True),
]


def migrate(data, level):
    d = copy.deepcopy(data)
    level = int(level)
    assets = {a["id"]: a for a in d["assets"]}
    if level >= 1:
        d["parts"] = [dict(id=i, sku=s, name=n, site=site, unit_cost=c, quantity=q, reorder_level=r)
                      for i, s, n, site, c, q, r in PARTS]
        d["part_usages"] = []
    if level >= 2:
        for o in d["work_orders"]:
            if o["assignee"] is None:
                o["dispatch"] = None
            else:
                o["dispatch"] = "self" if o["assignee"] == o["requested_by"] else "supervisor"
    if level >= 3:
        for o in d["work_orders"]:
            p = o["priority"]
            if p == "urgent":
                o["priority"] = "p1"
            elif p == "normal":
                o["priority"] = "p2" if assets[o["asset"]]["criticality"] == "high" else "p3"
            else:
                o["priority"] = "p4"
    if level >= 4:
        d["time_entries"] = []
        n = 0
        for o in sorted(d["work_orders"], key=lambda o: o["id"]):
            if o["labor_minutes"] is not None:
                n += 1
                d["time_entries"].append({"id": n, "work_order": o["id"], "technician": o["assignee"],
                                          "minutes": o["labor_minutes"], "logged_at": o["completed_at"],
                                          "note": "migrated"})
            del o["labor_minutes"]
    if level >= 5:
        for o in d["work_orders"]:
            if o.get("dispatch") == "self" and o["status"] == "assigned":
                o["status"] = "open"
                o["assignee"] = None
            o.pop("dispatch", None)
    if level >= 6:
        for s in d["staff"]:
            if s["username"] == "sofia":
                s["role"] = "manager"
    if level >= 7:
        d["schedules"] = [dict(id=i, asset=a, title=t, priority=p, interval_days=n, next_due=nd, active=ac)
                          for i, a, t, p, n, nd, ac in SCHEDULES]
        for o in d["work_orders"]:
            o["schedule"] = None
    return d
