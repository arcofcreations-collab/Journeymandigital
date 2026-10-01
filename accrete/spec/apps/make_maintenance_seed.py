"""Generate maintenance_seed.json deterministically.

usage: python make_maintenance_seed.py            (writes maintenance_seed.json next to this file)

The unfinished work orders (open / assigned / in_progress) are listed explicitly so that their
edge cases (overdue boundaries, technician workloads, self-raised orders, an inactive assignee)
are stable. Finished history (completed / cancelled) is generated with a fixed random seed.
Work order ids are assigned in ascending `created_at` order.
"""
import json
import os
import random
from datetime import datetime, timedelta

FMT = "%Y-%m-%dT%H:%M:%S"

STAFF = [
    # username, name, role, site, active
    ("sofia", "Sofia Marin", "supervisor", "North", True),
    ("tomas", "Tomas Berg", "supervisor", "South", True),
    ("ruth", "Ruth Adler", "requester", "North", True),
    ("kofi", "Kofi Mensah", "requester", "North", True),
    ("lina", "Lina Park", "requester", "South", True),
    ("pavel", "Pavel Novak", "requester", "South", True),
    ("mei", "Mei Tanaka", "requester", "East", True),
    ("nils", "Nils Holm", "technician", "North", True),
    ("olga", "Olga Ivanova", "technician", "North", True),
    ("ravi", "Ravi Shah", "technician", "South", True),
    ("sara", "Sara Lopez", "technician", "South", True),
    ("tess", "Tess Moore", "technician", "East", True),
    ("umar", "Umar Farouk", "technician", "North", False),
    ("vera", "Vera Lind", "requester", "North", False),
    ("wade", "Wade Cole", "technician", "South", True),
    ("yara", "Yara Haddad", "supervisor", "East", True),
]

ASSETS = [
    # tag, name, site, criticality, retired
    ("N-AHU-01", "Air handler 1", "North", "high", False),
    ("N-AHU-02", "Air handler 2", "North", "medium", False),
    ("N-BLR-01", "Boiler 1", "North", "high", False),
    ("N-CHL-01", "Chiller 1", "North", "high", False),
    ("N-ELV-01", "Passenger elevator", "North", "high", False),
    ("N-FLT-01", "Forklift 1", "North", "medium", False),
    ("N-FLT-02", "Forklift 2", "North", "medium", True),
    ("N-PMP-01", "Water pump 1", "North", "medium", False),
    ("N-CMP-01", "Air compressor", "North", "low", False),
    ("N-DCK-01", "Dock door 1", "North", "low", False),
    ("N-DCK-02", "Dock door 2", "North", "low", False),
    ("N-LGT-01", "Yard lighting", "North", "low", False),
    ("N-FIR-01", "Fire panel", "North", "high", False),
    ("S-AHU-01", "Air handler South", "South", "high", False),
    ("S-BLR-01", "Boiler South", "South", "high", False),
    ("S-CNV-01", "Conveyor line A", "South", "high", False),
    ("S-CNV-02", "Conveyor line B", "South", "medium", False),
    ("S-FLT-01", "Forklift South", "South", "medium", False),
    ("S-PMP-01", "Process pump 1", "South", "medium", False),
    ("S-PMP-02", "Process pump 2", "South", "low", False),
    ("S-GEN-01", "Standby generator", "South", "high", False),
    ("S-DCK-01", "Dock door South", "South", "low", False),
    ("S-LGT-01", "Car park lighting", "South", "low", False),
    ("S-CMP-01", "Old compressor", "South", "low", True),
    ("E-AHU-01", "Air handler East", "East", "medium", False),
    ("E-ELV-01", "Goods lift", "East", "high", False),
    ("E-PMP-01", "Sump pump", "East", "low", False),
    ("E-DCK-01", "Dock door East", "East", "low", False),
    ("E-LGT-01", "Signage lighting", "East", "low", False),
    ("E-GEN-01", "Old generator", "East", "medium", True),
    ("E-FIR-01", "Fire panel East", "East", "high", False),
]

# Unfinished work orders: tag, priority, status, requested_by, assignee, created_at, started_at, title, description
CURRENT = [
    ("N-AHU-01", "normal", "open", "ruth", None, "2026-02-26T09:00:00", None, "Rattling noise", "Loud rattle near the intake"),
    ("N-BLR-01", "urgent", "open", "kofi", None, "2026-03-01T08:30:00", None, "Pressure alarm", None),
    ("N-DCK-01", "low", "open", "ruth", None, "2026-01-20T10:00:00", None, "Seal worn", None),
    ("N-PMP-01", "normal", "open", "vera", None, "2026-02-10T11:00:00", None, "Slow flow", "Flow rate dropped by half"),
    ("N-LGT-01", "low", "open", "kofi", None, "2026-02-20T14:00:00", None, "Lamp out", None),
    ("N-CHL-01", "normal", "open", "sofia", None, "2026-02-22T09:00:00", None, "Coolant top-up", None),
    ("S-CNV-01", "urgent", "open", "lina", None, "2026-02-27T16:00:00", None, "Belt slipping", "Belt slips under load"),
    ("S-PMP-02", "low", "open", "pavel", None, "2026-02-25T10:00:00", None, "Paint flaking", None),
    ("S-DCK-01", "normal", "open", "lina", None, "2026-02-28T13:00:00", None, "Sensor misaligned", None),
    ("S-GEN-01", "normal", "open", "tomas", None, "2026-02-14T09:00:00", None, "Load test", None),
    ("S-LGT-01", "low", "open", "ravi", None, "2026-02-18T08:00:00", None, "Timer drift", None),
    ("E-PMP-01", "normal", "open", "mei", None, "2026-02-24T12:00:00", None, "Float switch stuck", None),
    ("E-DCK-01", "low", "open", "mei", None, "2026-01-05T09:00:00", None, "Hinge squeak", None),
    ("E-ELV-01", "urgent", "open", "yara", None, "2026-03-01T07:45:00", None, "Door fault", "Doors reopen repeatedly"),
    # nils: 3 active
    ("N-ELV-01", "urgent", "assigned", "ruth", "nils", "2026-02-28T09:00:00", None, "Stuck between floors", None),
    ("N-AHU-02", "normal", "in_progress", "kofi", "nils", "2026-02-20T10:00:00", "2026-02-23T09:00:00", "Filter change", None),
    ("N-FLT-01", "low", "in_progress", "ruth", "nils", "2026-02-02T13:00:00", "2026-02-05T08:00:00", "Mirror cracked", None),
    # olga: 2 active (one self-raised)
    ("N-CMP-01", "normal", "assigned", "olga", "olga", "2026-02-27T11:00:00", None, "Oil change", None),
    ("N-FIR-01", "urgent", "in_progress", "sofia", "olga", "2026-02-28T15:00:00", "2026-02-28T16:00:00", "Zone 3 fault", None),
    # umar (inactive): 1 active
    ("N-DCK-02", "low", "assigned", "kofi", "umar", "2026-01-15T09:00:00", None, "Remote not working", None),
    # ravi: 4 active (one self-raised)
    ("S-AHU-01", "normal", "assigned", "lina", "ravi", "2026-02-24T08:00:00", None, "Thermostat fault", None),
    ("S-BLR-01", "urgent", "assigned", "pavel", "ravi", "2026-02-26T07:00:00", None, "No hot water", None),
    ("S-FLT-01", "normal", "in_progress", "ravi", "ravi", "2026-02-16T10:00:00", "2026-02-17T09:00:00", "Brake check", None),
    ("S-PMP-01", "low", "in_progress", "tomas", "ravi", "2026-02-11T15:00:00", "2026-02-12T10:00:00", "Gland leak", None),
    # sara: 3 active (one self-raised)
    ("S-CNV-02", "normal", "assigned", "sara", "sara", "2026-02-25T14:00:00", None, "Roller replacement", None),
    ("S-CNV-01", "normal", "in_progress", "pavel", "sara", "2026-02-19T09:00:00", "2026-02-20T08:30:00", "Motor overheating", None),
    ("S-GEN-01", "low", "assigned", "tomas", "sara", "2026-02-21T10:00:00", None, "Battery check", None),
    # wade: 1 active
    ("S-DCK-01", "urgent", "in_progress", "lina", "wade", "2026-02-28T18:00:00", "2026-03-01T07:00:00", "Door off track", None),
    # tess: 2 active
    ("E-AHU-01", "normal", "assigned", "mei", "tess", "2026-02-23T13:00:00", None, "Fan belt", None),
    ("E-LGT-01", "low", "in_progress", "yara", "tess", "2026-01-28T09:00:00", "2026-02-02T10:00:00", "Flicker", None),
]

PHRASES = ["Replace filter", "Bearing noise", "Leak at valve", "Inspect belt", "Reset controller",
           "Lubricate chain", "Replace lamp", "Calibrate sensor", "Tighten mounts", "Clean coils",
           "Replace fuse", "Check wiring"]
RESOLUTIONS = ["Replaced part", "Adjusted and tested", "Cleaned and lubricated", "No fault found",
               "Repaired wiring"]
CANCEL_REASONS = ["Duplicate request", "Asset replaced", "Not a maintenance issue", "Raised by mistake"]

N_COMPLETED = 40
N_CANCELLED = 12


def main():
    rng = random.Random(20260301)
    staff = []
    for i, (u, n, role, site, active) in enumerate(STAFF, 1):
        staff.append({"id": i, "username": u, "name": n, "role": role, "site": site, "active": active})
    sid = {s["username"]: s["id"] for s in staff}
    assets = []
    for i, (tag, name, site, crit, retired) in enumerate(ASSETS, 1):
        assets.append({"id": i, "tag": tag, "name": name, "site": site, "criticality": crit, "retired": retired})
    aid = {a["tag"]: a for a in assets}

    def site_people(site, roles):
        return [s["username"] for s in staff if s["site"] == site and s["role"] in roles]

    supervisor_of = {"North": "sofia", "South": "tomas", "East": "yara"}
    orders = []
    for tag, prio, status, req, asg, created, started, title, desc in CURRENT:
        orders.append({
            "asset": aid[tag]["id"], "title": title, "description": desc, "priority": prio,
            "status": status, "requested_by": sid[req], "created_at": created,
            "assignee": sid[asg] if asg else None, "started_at": started, "completed_at": None,
            "resolution": None, "labor_minutes": None, "cancel_reason": None,
        })

    # finished history; never on S-CMP-01 (retired, no orders) or E-FIR-01 (no orders at all)
    hist_assets = [a for a in assets if a["tag"] not in ("S-CMP-01", "E-FIR-01", "E-GEN-01")]
    start = datetime(2025, 10, 1, 8, 0, 0)
    span_hours = int((datetime(2026, 2, 24, 18, 0, 0) - start).total_seconds() // 3600)
    plan = ["completed"] * N_COMPLETED + ["cancelled"] * N_CANCELLED
    rng.shuffle(plan)
    for k, status in enumerate(plan):
        a = rng.choice(hist_assets)
        if k == 3:
            a = aid["N-FLT-02"]
        if k == 9:
            a = aid["E-GEN-01"]
            status = "cancelled"
        site = a["site"]
        created = start + timedelta(hours=rng.randrange(span_hours))
        prio = rng.choice(["low", "normal", "normal", "urgent"])
        techs = site_people(site, ("technician",))
        tech = rng.choice(techs)
        pool = site_people(site, ("requester", "technician")) + [supervisor_of[site]]
        req = rng.choice(pool)
        if k % 11 == 5:  # self-raised by the technician who did the work
            req = tech
        o = {
            "asset": a["id"], "title": rng.choice(PHRASES), "description": None, "priority": prio,
            "status": status, "requested_by": sid[req], "created_at": created.strftime(FMT),
            "assignee": None, "started_at": None, "completed_at": None,
            "resolution": None, "labor_minutes": None, "cancel_reason": None,
        }
        if rng.random() < 0.3:
            o["description"] = "Reported during routine walk-round"
        if status == "completed":
            st = created + timedelta(hours=rng.randrange(2, 30))
            done = st + timedelta(hours=rng.randrange(1, 48))
            o.update(assignee=sid[tech], started_at=st.strftime(FMT), completed_at=done.strftime(FMT),
                     resolution=rng.choice(RESOLUTIONS), labor_minutes=15 * rng.randrange(2, 33))
        else:
            stage = rng.choice(["open", "open", "assigned", "in_progress"])
            if stage in ("assigned", "in_progress"):
                o["assignee"] = sid[tech]
            if stage == "in_progress":
                o["started_at"] = (created + timedelta(hours=rng.randrange(2, 30))).strftime(FMT)
            o["cancel_reason"] = rng.choice(CANCEL_REASONS)
        orders.append(o)

    orders.sort(key=lambda o: o["created_at"])
    out_orders = []
    for i, o in enumerate(orders, 1):
        out_orders.append(dict({"id": i}, **o))
    data = {"staff": staff, "assets": assets, "work_orders": out_orders}
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "maintenance_seed.json")
    with open(path, "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    print(f"wrote {path}: staff={len(staff)} assets={len(assets)} work_orders={len(out_orders)}")


if __name__ == "__main__":
    main()
