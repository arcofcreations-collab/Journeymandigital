import csv
import json
from datetime import date, timedelta

from dmguard.cli import main


def write(path, rows):
    with open(path, "w", newline="") as fh:
        csv.writer(fh).writerows(rows)


def weekly_rows(order):
    f = "%d/%m/%Y" if order == "DMY" else "%m/%d/%Y"
    ds = [date(2021, 1, 4) + timedelta(weeks=i) for i in range(60)]
    return [[d.strftime(f), str(i)] for i, d in enumerate(ds) if d.day <= 12]


def test_check_resolves_and_exits_zero(tmp_path, capsys):
    p = tmp_path / "a.csv"
    write(p, [["Week", "Value"]] + weekly_rows("DMY"))
    assert main(["check", str(p)]) == 0
    out = capsys.readouterr().out
    assert "'Week': DMY" in out and "calendar structure" in out


def test_fix_writes_iso(tmp_path):
    p, o = tmp_path / "a.csv", tmp_path / "out.csv"
    write(p, [["Week", "Value"]] + weekly_rows("MDY"))
    assert main(["fix", str(p), "-o", str(o)]) == 0
    rows = list(csv.reader(open(o)))
    assert rows[1][0] == "2021-01-04" and rows[2][0] == "2021-01-11"


def test_ambiguous_exit_code_and_assume(tmp_path, capsys):
    p, o = tmp_path / "a.csv", tmp_path / "out.csv"
    write(p, [["Month", "Value"]] + [[f"01/{m:02d}/2020", m] for m in range(1, 13)])
    assert main(["check", str(p)]) == 2
    assert "AMBIGUOUS" in capsys.readouterr().out
    assert main(["fix", str(p), "-o", str(o)]) == 2
    assert list(csv.reader(open(o)))[1][0] == "01/01/2020"  # left unchanged
    assert main(["fix", str(p), "-o", str(o), "--assume", "DMY"]) == 0
    assert list(csv.reader(open(o)))[2][0] == "2020-02-01"


def test_file_consistency(tmp_path, capsys):
    p = tmp_path / "a.csv"
    rows = [["Start", "End"]] + [[f"01/{m:02d}/2020", f"{27 if m != 2 else 26}/{m:02d}/2020"]
                                 for m in range(1, 13)]
    write(p, rows)
    assert main(["check", str(p), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["columns"]["End"]["method"] == "validity"
    assert data["columns"]["Start"]["verdict"] == "DMY"
    assert data["columns"]["Start"]["method"] == "file-consistency"


def test_bad_inputs(tmp_path, capsys):
    empty = tmp_path / "e.csv"
    empty.write_text("")
    assert main(["check", str(empty)]) == 1
    binf = tmp_path / "b.csv"
    binf.write_bytes(b"\x00\x01\x02garbage")
    assert main(["check", str(binf)]) == 1
    bad = tmp_path / "l1.csv"
    bad.write_bytes("Date\n01/02/2020\ncaf\xe9\n".encode("latin-1"))
    assert main(["check", str(bad)]) == 1
    assert main(["check", str(tmp_path / "missing.csv")]) == 1
    err = capsys.readouterr().err
    assert "empty" in err and "binary" in err and "latin-1" in err
    nodates = tmp_path / "n.csv"
    write(nodates, [["a", "b"], ["x", "1"]])
    assert main(["check", str(nodates)]) == 0
    assert "no numeric date columns" in capsys.readouterr().out


def test_output_piped_into_head_does_not_crash(tmp_path):
    import subprocess
    import sys

    # Enough columns that the report exceeds the OS pipe buffer (64 KiB),
    # so writing continues after `head` has exited.
    p = tmp_path / "a.csv"
    base = weekly_rows("DMY")
    write(p, [[f"d{i}" for i in range(300)]] + [[r[0]] * 300 for r in base])
    proc = subprocess.run(
        f'"{sys.executable}" -m dmguard check "{p}" | head -1',
        shell=True, capture_output=True, text=True,
    )
    assert "Traceback" not in proc.stderr
    assert proc.stdout.startswith("dmguard")
