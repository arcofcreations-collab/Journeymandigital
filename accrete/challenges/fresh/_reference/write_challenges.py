"""Write meta.json and challenge.md for every challenge in challenges/fresh from challenge_defs.py."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from challenge_defs import C, MEASURE  # noqa: E402


def extra_measures(d):
    cats = set(d["categories"])
    out = []
    if "data_migration" in cats:
        out.append("- Seed records whose migrated values differ from the brief (counted by the existing-data tests).")
    if "failure_atomicity" in cats:
        out.append("- Refused operations that left any trace (records, related collections or outbox) in the snapshot tests.")
    if "sequence" in cats:
        out.append("- Carry-over failures: checks of earlier steps of the sequence that are repeated in this test file.")
    if d["expect_rejection"]:
        out.append("- Whether the implementer refused (CLARIFICATION.md written) and left code and data unchanged "
                   "(diff of the application directory apart from CLARIFICATION.md / CHANGE_NOTES.md).")
    if "permissions" in cats:
        out.append("- 403-ordering failures (a 400/409 returned where the brief requires 403 first).")
    return [""] + out if out else []


def main():
    for cid, d in C.items():
        out = os.path.join(WS, "challenges", "fresh", cid)
        os.makedirs(out, exist_ok=True)
        meta = {
            "id": cid,
            "app": d["app"],
            "categories": d["categories"],
            "depends_on": d["depends_on"],
            "expect_rejection": d["expect_rejection"],
            "brief": d["brief"],
            "superseded_base_tests": d["superseded"],
        }
        with open(os.path.join(out, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2)
            fh.write("\n")
        md = d["md"]
        lines = [f"# {cid} ({d['app']}{', depends on ' + d['depends_on'] if d['depends_on'] else ''})", "",
                 f"Size: {d['size']}. Categories: {', '.join(d['categories'])}."
                 + (" Expected outcome: REJECTION (CLARIFICATION.md, application unchanged)." if d["expect_rejection"] else ""),
                 "", "## 1. Requested outcome", "", md["outcome"], "",
                 "## 2. Observable acceptance criteria", ""]
        lines += [f"- {c}" for c in md["criteria"]]
        lines += ["", "## 3. Behaviour that must remain intact", "", md["intact"],
                  "", f"Superseded base tests ({len(d['superseded'])}): "
                  + (", ".join(f"`{t}`" for t in d["superseded"]) if d["superseded"] else "none") + ".",
                  "", "## 4. Existing-data requirements", "", md["data"],
                  "", "## 5. Failure and recovery conditions", "", md["failure"],
                  "", "## 6. Measurements to collect", "", MEASURE] + extra_measures(d) + [""]
        with open(os.path.join(out, "challenge.md"), "w") as fh:
            fh.write("\n".join(lines))
    print("wrote", len(C), "challenges")


if __name__ == "__main__":
    main()
