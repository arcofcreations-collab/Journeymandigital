"""CSV-level resolution: per-column verdicts, file consistency, ISO rewrite."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Optional

from .core import (
    DEFAULT_THRESHOLD_BITS,
    ColumnResult,
    iso_with_order,
    resolve_column,
)

__all__ = ["TableReport", "DmguardError", "read_table", "analyse_table", "rewrite_iso"]


class DmguardError(Exception):
    """User-facing error (bad file, bad arguments)."""


@dataclass
class TableReport:
    header: list
    rows: list
    dialect: object
    columns: dict = field(default_factory=dict)  # name -> ColumnResult

    @property
    def date_columns(self) -> dict:
        return {
            k: v for k, v in self.columns.items()
            if v.verdict not in ("NOT_DATE", "EMPTY")
        }

    @property
    def unresolved(self) -> dict:
        return {k: v for k, v in self.date_columns.items() if not v.resolved}

    @property
    def with_bad_cells(self) -> dict:
        """Date columns containing values that are not valid dates."""
        return {k: v for k, v in self.date_columns.items() if v.n_unparsed}

    @property
    def all_clean(self) -> bool:
        return not self.unresolved and not self.with_bad_cells


def read_table(path: str, delimiter: Optional[str] = None, encoding: str = "utf-8-sig"):
    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        raise DmguardError(f"cannot read {path}: {exc.strerror or exc}") from exc
    if b"\x00" in blob[:4096]:
        raise DmguardError(f"{path} looks like a binary file, not CSV text")
    try:
        text = blob.decode(encoding)
    except UnicodeDecodeError as exc:
        raise DmguardError(
            f"{path} is not valid {encoding} (byte {exc.start}); try --encoding latin-1"
        ) from exc
    if not text.strip():
        raise DmguardError(f"{path} is empty")
    if delimiter:
        dialect = csv.excel()
        dialect.delimiter = delimiter
    else:
        try:
            dialect = csv.Sniffer().sniff(text[:65536], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel()
    # Keep the file's own line endings when writing a converted copy.
    dialect.lineterminator = "\r\n" if "\r\n" in text[:65536] else "\n"
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        raise DmguardError(f"{path} has no rows")
    header, body = rows[0], rows[1:]
    if not body:
        raise DmguardError(f"{path} has a header but no data rows")
    return header, body, dialect


def analyse_table(
    header: list, rows: list, dialect=None, threshold_bits: float = DEFAULT_THRESHOLD_BITS,
    same_convention: bool = False, accept_likely: bool = False,
) -> TableReport:
    """Resolve every column.

    ``same_convention=True`` declares that the whole file uses one date
    convention, so an ambiguous column may adopt the order that another
    column's values prove. Without it, that other column is only mentioned
    as a hint: different columns can come from different systems.
    """
    report = TableReport(header=header, rows=rows, dialect=dialect)
    names = _unique_names(header)
    for j, name in enumerate(names):
        col = [r[j] if j < len(r) else "" for r in rows]
        report.columns[name] = resolve_column(
            col, threshold_bits=threshold_bits, accept_likely=accept_likely)

    settled = {}
    for name, res in report.columns.items():
        if res.method == "validity":
            settled.setdefault((res.layout, res.separator), {}).setdefault(res.verdict, []).append(name)
    for name, res in report.columns.items():
        if res.verdict != "AMBIGUOUS":
            continue
        proven = settled.get((res.layout, res.separator), {})
        if len(proven) != 1:
            continue
        order, donors = next(iter(proven.items()))
        donor_txt = ", ".join(map(repr, donors))
        if same_convention:
            res.verdict, res.method = order, "file-consistency"
            res.reasons.append(
                f"adopted {order} from column(s) {donor_txt}, whose values rule out the other "
                f"order, because you declared that the file uses one convention")
        else:
            res.reasons.append(
                f"hint: column(s) {donor_txt} in this file are provably {order}. If every "
                f"column in this file uses the same convention, rerun with "
                f"--assume-same-convention; columns from different systems can differ")
    return report


def _unique_names(header: list) -> list:
    seen: dict = {}
    out = []
    for i, h in enumerate(header):
        name = h.strip() or f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 1
        out.append(name)
    return out


def rewrite_iso(report: TableReport, out_path: str) -> dict:
    """Write a copy of the table with resolved date columns in ISO 8601.

    Conversion is lossless: each value keeps exactly the time precision it
    had (minutes, seconds, every fractional digit). Cells that are not valid
    dates, and every cell of an unresolved column, are copied unchanged.
    Returns {column: number of cells converted}.
    """
    names = list(report.columns)
    converters = {}
    for j, name in enumerate(names):
        res = report.columns[name]
        if res.resolved:
            col = [r[j] if j < len(r) else "" for r in report.rows]
            converters[j] = iso_with_order(col, res.verdict)
    changed = {names[j]: 0 for j in converters}
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=getattr(report.dialect, "delimiter", ","),
                       lineterminator=getattr(report.dialect, "lineterminator", "\n"))
        w.writerow(report.header)
        for i, row in enumerate(report.rows):
            row = list(row)
            for j, iso in converters.items():
                if j < len(row) and iso[i] is not None:
                    if iso[i] != row[j]:
                        changed[names[j]] += 1
                    row[j] = iso[i]
            w.writerow(row)
    return changed
