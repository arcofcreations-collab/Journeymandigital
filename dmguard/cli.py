"""Command-line interface: ``dmguard check|fix FILE``."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .core import DEFAULT_THRESHOLD_BITS
from .table import DmguardError, analyse_table, read_table, rewrite_iso

# 0: every date column resolved and every date cell valid
# 1: the input could not be read
# 2: needs attention - an unresolved date column or cells that are not valid dates
EXIT_OK, EXIT_ERROR, EXIT_AMBIGUOUS = 0, 1, 2

METHOD_TEXT = {
    "validity": "some values are impossible under the other order",
    "identical": "both orders give the same dates",
    "structure": "calendar structure",
    "file-consistency": "same order as another column in this file (assumed by you)",
    "likely-accepted": "likely order, accepted by you (--accept-likely)",
    "user-assumed": "order assumed by you (--assume)",
    "abstained": "evidence too weak - not guessing",
    "competing": "two regular patterns fit - not guessing",
}


def _print_report(report, path, out=None):
    out = out or sys.stdout
    print(f"dmguard {__version__}: {path}", file=out)
    cols = report.date_columns
    if not cols:
        print("  no numeric date columns found", file=out)
        return
    for name, res in cols.items():
        tag = res.verdict + (f" (likely {res.likely})" if res.likely and not res.resolved else "")
        how = METHOD_TEXT.get(res.method, "")
        bits = (f", {res.evidence_bits:.1f} bits"
                if res.method in ("structure", "abstained", "competing", "likely-accepted") else "")
        print(f"\n  column {name!r}: {tag}" + (f"  ({how}{bits})" if how else ""), file=out)
        print(f"    values: {res.n_values}, blank: {res.n_missing}, not valid dates: {res.n_unparsed}",
              file=out)
        for r in res.reasons:
            print(f"    - {r}", file=out)
        for r in res.notes:
            print(f"    - note: {r}", file=out)
        if res.unparsed_examples:
            shown = ", ".join(f"line {i + 2}: {v!r}" for i, v in res.unparsed_examples)
            more = res.n_unparsed - len(res.unparsed_examples)
            print(f"    ! not valid dates: {shown}" + (f" and {more} more" if more > 0 else ""),
                  file=out)
        for raw, readings in res.examples:
            shown = ", ".join(f"{o} -> {d or 'impossible'}" for o, d in readings.items())
            print(f"    e.g. {raw!r}: {shown}", file=out)
    unresolved, bad = report.unresolved, report.with_bad_cells
    print("", file=out)
    if unresolved:
        print(
            f"  NEEDS ATTENTION: {len(unresolved)} date column(s) not resolved: "
            f"{', '.join(map(repr, unresolved))}. Check the source's convention, then use "
            "--assume DMY|MDY on 'fix' (or --accept-likely / --assume-same-convention).",
            file=out,
        )
    if bad:
        print(
            f"  NEEDS ATTENTION: {sum(r.n_unparsed for r in bad.values())} cell(s) in "
            f"{', '.join(map(repr, bad))} are not valid dates; they are left unchanged.",
            file=out,
        )
    if not unresolved and not bad:
        print("  all date columns resolved; every date cell is valid", file=out)


def main(argv=None) -> int:
    try:
        return _main(argv)
    except BrokenPipeError:
        # Output piped into e.g. `head`: stop quietly like standard Unix tools.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except (OSError, ValueError):
            pass
        return EXIT_OK


def _main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="dmguard",
        description="Detect whether numeric dates are day-first or month-first, "
        "using the calendar structure of each column; refuses to guess when unsure.",
    )
    p.add_argument("--version", action="version", version=f"dmguard {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, helptext in (
        ("check", "report the order of each date column"),
        ("fix", "write a copy with resolved date columns as ISO 8601"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("file")
        sp.add_argument("--delimiter", help="CSV delimiter (default: sniffed)")
        sp.add_argument("--encoding", default="utf-8-sig")
        sp.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD_BITS,
                        help=f"minimum evidence in bits (default {DEFAULT_THRESHOLD_BITS:g})")
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        sp.add_argument("--assume-same-convention", action="store_true",
                        help="declare that every column in the file uses one date convention, "
                        "so a column the data cannot settle may follow a column it can")
        sp.add_argument("--accept-likely", action="store_true",
                        help="apply the likely order when two regular calendar patterns fit "
                        "(a preference, not proof)")
        if name == "fix":
            sp.add_argument("-o", "--output", required=True)
            sp.add_argument("--assume", choices=["DMY", "MDY", "YMD", "YDM"],
                            help="order to use for columns the data cannot settle "
                            "(your decision, recorded in the output)")

    args = p.parse_args(argv)
    try:
        header, rows, dialect = read_table(args.file, args.delimiter, args.encoding)
    except DmguardError as exc:
        print(f"dmguard: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    report = analyse_table(header, rows, dialect, threshold_bits=args.threshold,
                           same_convention=args.assume_same_convention,
                           accept_likely=args.accept_likely)

    if args.cmd == "fix" and args.assume:
        for res in report.unresolved.values():
            if res.verdict == "AMBIGUOUS" and args.assume in res.candidates:
                res.verdict, res.method = args.assume, "user-assumed"
                res.reasons.append(f"order {args.assume} assumed by the user (--assume)")

    changed = None
    if args.cmd == "fix":
        try:
            changed = rewrite_iso(report, args.output)
        except OSError as exc:
            print(f"dmguard: error: cannot write {args.output}: {exc}", file=sys.stderr)
            return EXIT_ERROR

    if args.json:
        payload = {
            "file": args.file,
            "columns": {k: v.to_dict() for k, v in report.date_columns.items()},
            "unresolved": list(report.unresolved),
            "columns_with_invalid_cells": list(report.with_bad_cells),
            "status": "ok" if report.all_clean else "needs_attention",
        }
        if changed is not None:
            payload["output"] = args.output
            payload["converted_cells"] = changed
        json.dump(payload, sys.stdout, indent=2)
        print()
    else:
        _print_report(report, args.file)
        if changed is not None:
            total = sum(changed.values())
            print(f"  wrote {args.output} ({total} cells converted to ISO 8601, "
                  "keeping each value's full time precision)")
            if report.unresolved:
                print("  unresolved columns were left unchanged")
    return EXIT_OK if report.all_clean else EXIT_AMBIGUOUS


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
