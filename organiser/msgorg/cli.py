"""organiser CLI. Data lives in a local SQLite file (default ~/.msgorg/archive.db); nothing leaves the machine."""
import argparse, datetime as dt, json, os, sys
from . import store as S, app as A

DB = os.environ.get("MSGORG_DB", os.path.expanduser("~/.msgorg/archive.db"))

def _t(ms): return dt.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")

def main(argv=None):
    p = argparse.ArgumentParser(prog="organiser"); p.add_argument("--db", default=DB)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("import"); s.add_argument("file"); s.add_argument("--month-first", action="store_true"); s.add_argument("--skip-if-imported", action="store_true")
    sp.add_parser("coverage"); sp.add_parser("contacts")
    s = sp.add_parser("search"); s.add_argument("text", nargs="?"); s.add_argument("--contact"); s.add_argument("--from", dest="start")
    s.add_argument("--to", dest="end"); s.add_argument("--job"); s.add_argument("--sent", action="store_true"); s.add_argument("--received", action="store_true")
    s = sp.add_parser("context"); s.add_argument("msg_id", type=int); s.add_argument("-n", type=int, default=5)
    s = sp.add_parser("job"); s.add_argument("contact"); s.add_argument("job"); s.add_argument("--remove", action="store_true")
    s = sp.add_parser("absences"); s.add_argument("--contact"); s.add_argument("--job"); s.add_argument("--from", dest="start"); s.add_argument("--to", dest="end")
    s.add_argument("--status", action="append"); s.add_argument("--export", choices=["md", "csv", "json"]); s.add_argument("--month-first", action="store_true")
    s = sp.add_parser("correct"); s.add_argument("finding_id", type=int); s.add_argument("field"); s.add_argument("value"); s.add_argument("--note", default="")
    s = sp.add_parser("delete"); s.add_argument("--all", action="store_true", required=True)
    a = p.parse_args(argv)
    if a.cmd == "delete":
        S.delete_all(a.db); print("deleted the archive, its search index and all interpretations:", a.db); return 0
    db = S.open_db(a.db)
    if a.cmd == "import":
        import hashlib
        sha = hashlib.sha256(open(a.file, "rb").read()).hexdigest()
        if a.skip_if_imported and db.execute("select 1 from imports where file_sha256=?", (sha,)).fetchone():
            print("this backup was already imported; nothing to do"); return 0
        r = S.import_file(db, a.file); A.recompute_absences(db, day_first=not a.month_first)
        print(f"parsed {r['parsed']} (declared by backup: {r['declared']}), added {r['added']}, duplicates skipped {r['duplicates']}, errors {r['errors']}")
        print(f"sms {r['sms']}, mms {r['mms']} (of which RCS-like {r['rcs_like']}); range {r['first_ms'] and _t(r['first_ms'])} .. {r['last_ms'] and _t(r['last_ms'])}")
        for e in r["error_samples"]: print("  error:", e)
        for g in S.coverage(db)["known_gaps"]: print("  coverage:", g)
    elif a.cmd == "coverage": print(json.dumps(S.coverage(db), indent=1, default=str))
    elif a.cmd == "contacts":
        for c in A.contacts(db): print(f"{c['id']:4} {c['display'] or c['address_key']:30} {c['n']:6} msgs  last {c['last_ms'] and _t(c['last_ms'])}  jobs: {c['jobs'] or '-'}")
    elif a.cmd == "search":
        d = "sent" if a.sent else "received" if a.received else None
        for m in A.search(db, a.text, a.contact, a.start, a.end, a.job, d):
            print(f"#{m['id']} {_t(m['date_ms'])} {m['display']} {'->' if m['direction']=='sent' else '<-'} {m['body'][:160]}")
    elif a.cmd == "context":
        for m in A.context(db, a.msg_id, a.n, a.n):
            print(f"{'*' if m['id']==a.msg_id else ' '}#{m['id']} {_t(m['date_ms'])} {'me' if m['direction']=='sent' else 'them'}: {m['body']}")
    elif a.cmd == "job":
        (A.unset_job if a.remove else A.set_job)(db, a.contact, a.job); A.recompute_absences(db)
    elif a.cmd == "absences":
        fs = A.absences(db, a.contact, a.job, a.start, a.end, a.status)
        if a.export == "json": print(json.dumps(fs, indent=1, default=str))
        elif a.export: print(A.export(fs, a.export))
        else:
            for f in fs:
                print(f"[{f['id']}] {f['work_start']}{'..'+f['work_end'] if f['work_end']!=f['work_start'] else ''}  {f['display']}  {f['status']}{' (corrected)' if f['corrected'] else ''}  sent {f['sent_at']}  \"{f['evidence'][0]['excerpt'][:80]}\"")
    elif a.cmd == "correct": A.correct(db, a.finding_id, a.field, a.value, a.note); print("recorded; source messages unchanged")
    return 0

if __name__ == "__main__": sys.exit(main())
