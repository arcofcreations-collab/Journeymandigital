"""POST-HOC, EXPLORATORY (not in the frozen spec): compare dmguard with a cheap
value-prior heuristic in the spirit of learned field priors (e.g. "a field that
is always 01 is the day"), which could resolve first-of-month series without
using calendar structure.

  H_const_day: if exactly one of the two ambiguous fields is constant across
               the column, read that field as the day; otherwise abstain.

Run after run_eval.py. Writes bench/results/posthoc_value_prior_{SPLIT}.json.
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from cases import generate  # noqa: E402
from methods import dmguard_method, outcome  # noqa: E402

from dmguard.core import _parse_raw, parse_with_order  # noqa: E402


def const_day(case):
    raws = [_parse_raw(s) for s in case.strings if s]
    a = {r.a for r in raws}
    b = {r.b for r in raws}
    if len(a) == 1 and len(b) > 1:
        order = "DMY"
    elif len(b) == 1 and len(a) > 1:
        order = "MDY"
    else:
        return "abstain", None
    return "parsed", parse_with_order(case.strings, order)


def main(split):
    cases = [c for c in generate(split) if c.klass == "ambiguous"]
    res = {}
    for name, fn in (("H_const_day", const_day), ("dmguard", dmguard_method)):
        cnt = Counter(outcome(c, *fn(c)) for c in cases)
        res[name] = dict(cnt)
    # where does the heuristic go wrong?
    wrong_src = Counter(c.source for c in cases if outcome(c, *const_day(c)) == "silent_wrong")
    res["H_const_day_silent_wrong_by_source"] = dict(wrong_src)
    res["n"] = len(cases)
    with open(os.path.join(HERE, "results", f"posthoc_value_prior_{split}.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    print(split, json.dumps(res, indent=1))


if __name__ == "__main__":
    for sp in sys.argv[1:] or ["DEV", "TEST"]:
        main(sp)
