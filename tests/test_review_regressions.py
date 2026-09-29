"""Regression tests for the four defects found in the external review (v1.0.0)."""
import csv
import json
from datetime import date, timedelta

from dmguard.cli import main


def write(path, rows):
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)


def test_1_no_silent_transfer_between_columns(tmp_path, capsys):
    p = tmp_path / "cross.csv"
    rows = [["uk_invoice", "us_shipped"]]
    for i in range(12):
        rows.append([date(2021, 4, 13 + i % 10).strftime("%d/%m/%Y"),
                     date(2021, 4, 1 + i).strftime("%m/%d/%Y")])
    write(p, rows)
    assert main(["check", str(p), "--json"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["columns"]["uk_invoice"]["verdict"] == "DMY"
    us = data["columns"]["us_shipped"]
    assert us["verdict"] == "AMBIGUOUS"
    assert any("--assume-same-convention" in r for r in us["reasons"])
    # adopting the other column's order is an explicit, labelled assumption
    assert main(["check", str(p), "--json", "--assume-same-convention"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["columns"]["us_shipped"]["method"] == "file-consistency"


def test_2_conversion_keeps_full_time_precision(tmp_path):
    p, o = tmp_path / "t.csv", tmp_path / "o.csv"
    write(p, [["t"], ["13/04/2021 12:30:00.123456"], ["14/04/2021 08:00:00,5"],
              ["15/04/2021 07:05"], ["16/04/2021 1:05 PM"], ["17/04/2021 23:59:59.123456789"]])
    assert main(["fix", str(p), "-o", str(o)]) == 0
    got = [r[0] for r in csv.reader(open(o))][1:]
    assert got == ["2021-04-13 12:30:00.123456", "2021-04-14 08:00:00.5", "2021-04-15 07:05",
                   "2021-04-16 13:05", "2021-04-17 23:59:59.123456789"]


def test_3_mirror_pattern_is_not_resolved_by_default(tmp_path, capsys):
    p = tmp_path / "jan.csv"
    write(p, [["d"]] + [[date(y, 1, d).strftime("%m/%d/%Y")]
                        for y in range(2018, 2023) for d in range(1, 13)])
    assert main(["check", str(p)]) == 2
    out = capsys.readouterr().out
    assert "AMBIGUOUS (likely DMY)" in out and "preference, not proof" in out


def test_4_invalid_cell_is_not_reported_as_success(tmp_path, capsys):
    p, o = tmp_path / "bad.csv", tmp_path / "o.csv"
    write(p, [["d"]] + [[(date(2021, 1, 13) + timedelta(days=i)).strftime("%d/%m/%Y")]
                        for i in range(19)] + [["BAD"]])
    assert main(["fix", str(p), "-o", str(o)]) == 2
    out = capsys.readouterr().out
    assert "line 21: 'BAD'" in out and "NEEDS ATTENTION" in out
    assert list(csv.reader(open(o)))[-1] == ["BAD"]


def test_4b_mostly_dates_column_is_not_silently_skipped(tmp_path, capsys):
    p = tmp_path / "m.csv"
    vals = [(date(2021, 1, 13) + timedelta(days=i)).strftime("%d/%m/%Y") for i in range(10)]
    write(p, [["d"]] + [[v] for v in vals] + [["n/k"], ["tbc"], ["?? "], ["later"], ["x"]])
    assert main(["check", str(p)]) == 2
    assert "not valid dates" in capsys.readouterr().out


def test_fix_keeps_the_input_line_endings(tmp_path):
    for eol in ("\n", "\r\n"):
        p, o = tmp_path / "e.csv", tmp_path / "e_out.csv"
        p.write_bytes(("t" + eol + "13/04/2021" + eol + "14/04/2021" + eol).encode())
        assert main(["fix", str(p), "-o", str(o)]) == 0
        assert o.read_bytes() == ("t" + eol + "2021-04-13" + eol + "2021-04-14" + eol).encode()
