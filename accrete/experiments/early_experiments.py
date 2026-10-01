"""Early, deliberately tiny experiments for the four candidate mechanisms.

Each experiment asks one question that could disprove its candidate. Run:
    python experiments/early_experiments.py
Results are printed and summarised in docs/CANDIDATES.md.
"""
import copy
import json
import time

# A miniature app used by all experiments: books with a rule and a permission.
DATA = [{"id": i, "title": f"T{i}", "author": "A" if i % 2 else "B", "price": 10 + i} for i in range(1, 6)]


# ---------------------------------------------------------------------------
# C1  Declarative spec + diff-inferred migration (what Prisma/Alembic-style tools do)
# Question: when a spec changes, can the system infer the data migration from the diff?
# ---------------------------------------------------------------------------
def c1_diff_inferred_migration():
    v1 = {"book": {"title": "text", "author": "text", "price": "int"}}
    v2 = {"book": {"title": "text", "writer": "text", "price": "int"}}  # intent: rename author -> writer
    removed = {f for f in v1["book"] if f not in v2["book"]}
    added = {f for f in v2["book"] if f not in v1["book"]}
    # a diff only sees "removed author" + "added writer"; it cannot know the intent
    migrated = [{k: v for k, v in r.items() if k not in removed} | {f: None for f in added} for r in DATA]
    lost = sum(1 for r in migrated if r["writer"] is None)
    return {"diff_sees": {"removed": sorted(removed), "added": sorted(added)},
            "values_lost_without_human_hint": lost, "records": len(DATA)}


# ---------------------------------------------------------------------------
# C2  Ledger of typed, invertible change operators carrying their own data lens
# Question: can one operator update model, dependents and stored data, and be reversed exactly?
# ---------------------------------------------------------------------------
def c2_operator_ledger():
    model = {"book": {"fields": ["title", "author", "price"],
                      "rules": {"cheap": "record.price < 13", "visible": "record.author == user.name"}}}
    data = copy.deepcopy(DATA)

    def rename_field(model, data, ent, old, new):
        m, d = copy.deepcopy(model), copy.deepcopy(data)
        m[ent]["fields"] = [new if f == old else f for f in m[ent]["fields"]]
        touched = []
        for rname, expr in m[ent]["rules"].items():  # dependents rewritten (token-level for the toy)
            if f"record.{old}" in expr:
                m[ent]["rules"][rname] = expr.replace(f"record.{old}", f"record.{new}")
                touched.append(rname)
        for r in d:
            r[new] = r.pop(old)
        inverse = ("rename_field", ent, new, old)
        return m, d, inverse, touched

    m2, d2, inv, touched = rename_field(model, data, "book", "author", "writer")
    m3, d3, _, _ = rename_field(m2, d2, *inv[1:])
    return {"dependents_rewritten": touched, "values_preserved": all(r["writer"] for r in d2),
            "inverse_restores_exactly": (m3 == model and d3 == data), "inverse": inv}


# ---------------------------------------------------------------------------
# C3  Everything as relational rules (Datalog-style); behaviour derived by fixpoint
# Question: does adding an unanticipated concept stay a local rule addition, and what about stored data?
# ---------------------------------------------------------------------------
def c3_relational_rules():
    facts = {("book", r["id"], "author", r["author"]) for r in DATA} | {("book", r["id"], "price", r["price"]) for r in DATA}
    rules = []

    def derive(facts, rules):
        out = set(facts)
        changed = True
        while changed:
            changed = False
            for rule in rules:
                for f in rule(out) - out:
                    out.add(f)
                    changed = True
        return out

    # new concept "discount": derived purely by adding a rule -> local, no coordination
    rules.append(lambda fs: {("book", e, "discounted", True) for (t, e, a, v) in fs if a == "price" and v > 12})
    derived = derive(facts, rules)
    discounted = sorted(e for (t, e, a, v) in derived if a == "discounted")
    # renaming 'author' is NOT expressible as a rule: stored facts must be rewritten by an outside process
    rename_needs_external_migration = True
    return {"new_concept_by_rule": discounted, "rename_needs_external_migration": rename_needs_external_migration,
            "ui_and_permissions_derived": False}


# ---------------------------------------------------------------------------
# C4  Footprint-scoped differential replay as a regression gate
# Question: does replaying recorded requests catch an accidental behaviour change, while
# letting the intended change through without hand-written tests?
# ---------------------------------------------------------------------------
def c4_replay_gate():
    def make_app(price_rule, author_rule):
        def handle(req):
            r = next(x for x in DATA if x["id"] == req["id"])
            if req["op"] == "is_cheap":
                return eval(price_rule, {}, {"record": r})
            if req["op"] == "can_see":
                return eval(author_rule, {}, {"record": r, "user": req["user"]})
        return handle

    history = [{"op": op, "id": i, "user": u} for op in ("is_cheap", "can_see") for i in range(1, 6) for u in ("A", "B")]
    old = make_app("record['price'] < 13", "record['author'] == user")

    def gate(new, footprint):
        diffs = [h for h in history if old(h) != new(h)]
        outside = [h for h in diffs if h["op"] not in footprint]
        return {"diffs": len(diffs), "outside_footprint": len(outside), "accepted": not outside}

    intended = gate(make_app("record['price'] < 14", "record['author'] == user"), footprint={"is_cheap"})
    # an accidental edit: the change was meant to touch only the price rule but broke visibility
    accidental = gate(make_app("record['price'] < 14", "record['author'] != user"), footprint={"is_cheap"})
    return {"intended_change": intended, "accidental_regression": accidental}


if __name__ == "__main__":
    out = {}
    for name, fn in [("C1_diff_inferred_migration", c1_diff_inferred_migration),
                     ("C2_operator_ledger", c2_operator_ledger),
                     ("C3_relational_rules", c3_relational_rules),
                     ("C4_replay_gate", c4_replay_gate)]:
        t = time.perf_counter()
        out[name] = fn()
        out[name]["ms"] = round((time.perf_counter() - t) * 1000, 2)
    print(json.dumps(out, indent=1))
    with open("results/early_experiments.json", "w") as fh:
        json.dump(out, fh, indent=1)
