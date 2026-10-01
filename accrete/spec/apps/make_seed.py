"""Generate the deterministic starting data for the development applications."""
import json
import random
from datetime import date, datetime, timedelta

rng = random.Random(20261001)


def library():
    first = ["Ada", "Ben", "Chen", "Dara", "Eli", "Fatima", "Gus", "Hana", "Ivan", "Jo", "Kemal", "Lena"]
    members = []
    for i, n in enumerate(first, 1):
        role = "librarian" if i in (1, 2) else "member"
        members.append({"id": i, "username": n.lower(), "name": f"{n} {rng.choice(['Smith','Okafor','Li','Garcia','Novak','Haddad'])}",
                        "role": role, "active": i != 12})
    titles = ["River", "Glass", "Ember", "Atlas", "Orchard", "Signal", "Harbor", "Lantern", "Meridian", "Quarry"]
    authors = ["M. Reyes", "T. Okoye", "S. Lindqvist", "R. Banerjee", "J. Moreau", "K. Tanaka"]
    books = []
    for i in range(1, 41):
        books.append({"id": i, "title": f"The {rng.choice(titles)} {rng.choice(['Book','Year','Road','Song','House'])} {i}",
                      "author": rng.choice(authors), "isbn": f"978-0-{1000 + i * 7:04d}-{i:03d}-{i % 10}",
                      "year": rng.choice([None, 1999, 2005, 2012, 2018, 2021, 2024])})
    loans = []
    lid = 0
    # 45 returned loans in 2025-2026
    for _ in range(45):
        lid += 1
        b = rng.randint(1, 40)
        m = rng.randint(3, 11)
        start = datetime(2025, 9, 1) + timedelta(days=rng.randint(0, 120), hours=rng.randint(9, 17))
        due = (start + timedelta(days=14)).date()
        ret = start + timedelta(days=rng.randint(1, 20), hours=1)
        loans.append({"id": lid, "book": b, "member": m, "borrowed_at": start.isoformat(),
                      "due_at": due.isoformat(), "returned_at": ret.isoformat()})
    # 15 active loans on distinct books, at most 3 per member; as of 2026-03-01, 5 overdue
    active_books = rng.sample(range(1, 41), 15)
    member_counts = {}
    for k, b in enumerate(active_books):
        lid += 1
        while True:
            m = rng.randint(3, 11)
            if member_counts.get(m, 0) < 3:
                break
        member_counts[m] = member_counts.get(m, 0) + 1
        start = datetime(2026, 2, 1 if k < 5 else 18, 10) + timedelta(hours=k)
        due = (start + timedelta(days=14)).date()
        loans.append({"id": lid, "book": b, "member": m, "borrowed_at": start.isoformat(),
                      "due_at": due.isoformat(), "returned_at": None})
    return {"members": members, "books": books, "loans": loans}


def expenses():
    emps = [
        (1, "fiona", "Fiona Grant", "finance", None, "Finance"),
        (2, "marco", "Marco Diaz", "manager", None, "Engineering"),
        (3, "nadia", "Nadia Petrova", "manager", None, "Sales"),
        (4, "omar", "Omar Haddad", "manager", 2, "Engineering"),
    ]
    names = ["Priya", "Quinn", "Rosa", "Sam", "Tariq", "Uma", "Victor", "Wen", "Xena", "Yusuf", "Zoe"]
    for i, n in enumerate(names, 5):
        mgr = [2, 3, 4][i % 3]
        dept = {2: "Engineering", 3: "Sales", 4: "Engineering"}[mgr]
        emps.append((i, n.lower(), f"{n} {rng.choice(['Shah','Kim','Rossi','Olsen','Mensah'])}", "employee", mgr, dept))
    employees = [{"id": e[0], "username": e[1], "name": e[2], "role": e[3], "manager": e[4], "department": e[5]} for e in emps]
    claims = []
    cats = ["travel", "meals", "equipment", "other"]
    for cid in range(1, 81):
        emp = rng.randint(4, 15)
        status = rng.choice(["draft", "submitted", "submitted", "approved", "approved", "rejected", "paid", "paid"])
        created = datetime(2026, 1, 5) + timedelta(days=rng.randint(0, 50), hours=rng.randint(8, 18))
        mgr = employees[emp - 1]["manager"]
        rec = {"id": cid, "employee": emp, "amount": round(rng.uniform(8, 1800), 2), "category": rng.choice(cats),
               "description": f"{rng.choice(['Train to client','Team lunch','Monitor','Conference fee','Taxi','Hotel night','Keyboard'])} #{cid}",
               "status": status, "submitted_at": None, "decided_at": None, "decided_by": None, "rejection_reason": None}
        if status != "draft":
            rec["submitted_at"] = (created + timedelta(hours=2)).isoformat()
        if status in ("approved", "rejected", "paid"):
            rec["decided_at"] = (created + timedelta(days=2)).isoformat()
            rec["decided_by"] = mgr
        if status == "rejected":
            rec["rejection_reason"] = rng.choice(["Missing receipt", "Not a business expense", "Over policy limit"])
        claims.append(rec)
    return {"employees": employees, "claims": claims}


if __name__ == "__main__":
    for name, fn in (("library", library), ("expenses", expenses)):
        with open(f"{name}_seed.json", "w") as fh:
            json.dump(fn(), fh, indent=1)
        print("wrote", name)
