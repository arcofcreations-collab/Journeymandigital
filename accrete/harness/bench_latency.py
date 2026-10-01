"""Runtime overhead: per-request latency of an application instance, in process, through WSGI.

  python harness/bench_latency.py APP_DIR [APP_DIR ...] [--rounds N] [--json OUT]

Runs the same request mix against every instance (copied to a temp dir first, so nothing is
modified) and reports median and p95 latency per request kind. The mix is chosen from the app's
own collections: list, get, UI list page, and one write (PATCH or action) that is rolled back
by using a fresh copy per round.
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accept_client import fresh_app  # noqa: E402

MIXES = {
    "library": [
        ("list books (librarian)", "GET", "/api/books", None, "ada"),
        ("list loans (member)", "GET", "/api/loans", None, "hana"),
        ("get book", "GET", "/api/books/7", None, "hana"),
        ("UI list books", "GET", "/ui/books", None, "ada"),
        ("borrow + return", "POST", "/api/books/{free}/borrow", {}, "chen"),
    ],
    "expenses": [
        ("list claims (finance)", "GET", "/api/claims", None, "fiona"),
        ("list claims (manager)", "GET", "/api/claims", None, "marco"),
        ("get claim", "GET", "/api/claims/5", None, "fiona"),
        ("UI list claims", "GET", "/ui/claims", None, "fiona"),
        ("create claim", "POST", "/api/claims", {"description": "Bench", "amount": 12.5, "category": "travel"}, "{employee}"),
    ],
}


def detect(app):
    for name in MIXES:
        r = app.get(f"/api/{'books' if name == 'library' else 'claims'}", user="ada" if name == "library" else "fiona")
        if r.status == 200:
            return name
    raise SystemExit("unknown app")


def bench(path, rounds):
    app = fresh_app(path)
    kind = detect(app)
    out = {}
    free = next(b["id"] for b in app.get("/api/books", user="ada").json["items"] if b["status"] == "available") if kind == "library" else None
    employee = None
    if kind == "expenses":
        users = app.get("/api/employees", user="fiona").json["items"]
        employee = next(u["username"] for u in users if u.get("role") == "employee")
    for label, method, p, body, user in MIXES[kind]:
        p = p.format(free=free)
        user = user.format(employee=employee)
        times = []
        for i in range(rounds):
            if method == "GET":
                t = time.perf_counter()
                r = app.request(method, p, body, user, "2026-03-01T12:00:00")
                times.append(time.perf_counter() - t)
            else:
                a = fresh_app(path) if i % 10 == 0 else a  # noqa: F821  (fresh state every 10 writes)
                if kind == "library":
                    t = time.perf_counter()
                    r = a.post(p, {}, user=user)
                    times.append(time.perf_counter() - t)
                    loan = r.json.get("id") if r.status == 200 else None
                    open_loan = [l for l in a.get("/api/loans", user="ada").json["items"] if l["book"] == free and not l.get("returned_at")]
                    if open_loan:
                        a.post(f"/api/loans/{open_loan[0]['id']}/return", {}, user="ada")
                else:
                    t = time.perf_counter()
                    r = a.post(p, body, user=user)
                    times.append(time.perf_counter() - t)
            assert r.status in (200, 201), (label, r.status, r.text[:200])
        times.sort()
        out[label] = {"median_ms": round(statistics.median(times) * 1000, 3),
                      "p95_ms": round(times[int(len(times) * 0.95) - 1] * 1000, 3), "n": len(times)}
    return kind, out


if __name__ == "__main__":
    args = sys.argv[1:]
    rounds, jout = 200, None
    if "--rounds" in args:
        i = args.index("--rounds")
        rounds = int(args[i + 1])
        del args[i:i + 2]
    if "--json" in args:
        i = args.index("--json")
        jout = args[i + 1]
        del args[i:i + 2]
    res = {}
    for path in args:
        kind, out = bench(path, rounds)
        res[path] = {"app": kind, "requests": out}
        print(f"\n{path} ({kind})")
        for label, v in out.items():
            print(f"  {label:28} median {v['median_ms']:8.3f} ms   p95 {v['p95_ms']:8.3f} ms")
    if jout:
        with open(jout, "w") as fh:
            json.dump(res, fh, indent=1)
