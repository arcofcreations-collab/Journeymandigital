"""Expenses migrations for E11 (cost centres), E12 (active flag), E13 (revision fields)."""
import copy as _copy

CENTRES = [
    (1, "ENG", "Engineering", "Engineering", 31000.0),
    (2, "SAL", "Sales", "Sales", 12000.0),
    (3, "FIN", "Finance", "Finance", 2000.0),
    (4, "TRV", "Travel pool", None, 5000.0),
]


def migrate(data, level):
    d = _copy.deepcopy(data)
    emp = {e["id"]: e for e in d["employees"]}
    if level == "E11":
        d["cost_centres"] = [dict(id=i, code=c, name=n, department=dep, budget=b) for i, c, n, dep, b in CENTRES]
        by_dep = {dep: i for i, c, n, dep, b in CENTRES if dep}
        for c in d["claims"]:
            c["cost_centre"] = by_dep[emp[c["employee"]]["department"]]
    if level == "E12":
        for e in d["employees"]:
            e["active"] = True
    if level == "E13":
        for c in d["claims"]:
            c["revision"] = 0
            c["previous_rejection_reason"] = None
    return d
