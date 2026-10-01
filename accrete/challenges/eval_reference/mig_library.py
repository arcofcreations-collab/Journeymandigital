"""Library migrations for E08 (copies), E09 (guardians), E14 (E08 + lost copies)."""
import copy as _copy

GUARDIANS = {5: 4, 10: 4, 7: 6, 12: 11}   # eli, jo -> dara; gus -> fatima; lena -> kemal
LOST = {46: "2026-02-28T10:00:00", 50: "2026-02-28T10:00:00"}


def migrate(data, level):
    d = _copy.deepcopy(data)
    if level in ("E08", "E14"):
        d["copies"] = [{"id": b["id"], "book": b["id"], "barcode": "C%04d" % b["id"]} for b in d["books"]]
        d["copies"] += [{"id": 41, "book": 1, "barcode": "C0001-2"}, {"id": 42, "book": 22, "barcode": "C0022-2"}]
        for l in d["loans"]:
            l["copy"] = l["book"]
    if level == "E09":
        for m in d["members"]:
            m["guardian"] = GUARDIANS.get(m["id"])
    if level == "E14":
        for c in d["copies"]:
            c["lost"] = False
        for l in d["loans"]:
            l["lost_at"] = LOST.get(l["id"])
            if l["id"] in LOST:
                d["copies"][l["copy"] - 1]["lost"] = True
    return d
