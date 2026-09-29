"""Command-line interface: ``dmguard check|fix FILE``."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .core import DEFAULT_THRESHOLD_BITS
from .table import DmguardError, analyse_table, read_table, rewrite_iso

EXIT_OK, EXIT_ERROR, EXIT_AMBIGUOUS = 0, 1, 2

METHOD_TEXT = {
    "validity": "some values are impossible under the other order",
    "identical": "both orders give the same dates",
    "structure": "calendar structure",
    "file-consistency": "same order as another column in this file",
    "abstained": "evidence too weak - not guessing",
}


def _print_report(report, path, out=None):
    out = out or sys.stdout
    print(f"dmguard {__version__}: {path}", file=out)
    cols = report.date_columns
    if not cols:
        print("  no numeric date columns found", file=out)
        return
    for name, res in cols.items():
        tag = res.verdict
        how = METHOD_TEXT.get(res.method, "")
        bits = f", {res.evidence_bits:.1f} bits" if res.method in ("structure", "abstained") else ""
        print(f"\n  column {name!r}: {tag}" + (f"  ({how}{bits})" if how else ""), file=out)
        print(f"    values: {res.n_values}, missing: {res.n_missing}, unparsed: {res.n_unparsed}", file=out)
        for r in res.reasons:
            print(f"    - {r}", file=out)
        for raw, readings in res.examples:
            shown = ", ".join(f"{o} -> {d or 'impossible'}" for o, d in readings.items())
            print(f"    e.g. {raw!r}: {shown}", file=out)
    unresolved = report.unresolved
    print("", file=out)
    if unresolved:
        print(
            f"  {len(unresolved)} date column(s) NOT resolved: {', '.join(map(repr, unresolved))}. "
            "Check the source's convention, or use --assume DMY|MDY on 'fix'.",
            file=out,
        )
    else:
        print("  all date columns resolved", file=out)


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
    report = analyse_table(header, rows, dialect, threshold_bits=args.threshold)

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
            print(f"  wrote {args.output} ({total} cells converted to ISO 8601)")
            if report.unresolved:
                print("  unresolved columns were left unchanged")
    return EXIT_AMBIGUOUS if report.unresolved else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
