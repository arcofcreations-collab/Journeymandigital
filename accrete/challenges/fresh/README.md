# Fresh evaluation set F01-F14 (v2)

Written by an independent challenger agent in a separate workspace. It saw only the external
contract, the three requirement documents and seed data, the CHALLENGE_FORMAT, the test client,
and the *index* of the 28 earlier challenges (to avoid repeating them). It did not see either
system's engine, code, tooling, documentation, nor any run results.

- `F*/meta.json` (brief = the change request given to implementers), `F*/test_F*.py` (hidden
  acceptance tests, never shown to implementers), `F*/challenge.md`, `INDEX.md`.
- `_reference/`: the challenger's private reference implementation and `validate.py`, kept for
  audit. Validation result (run before the freeze): base suites 59/59, 47/47, 50/50 on the
  reference; every hidden test file passes fully on its changed reference state and does not all
  pass on the state before; the base tests failing after each change are exactly the listed
  `superseded_base_tests`.
- Additional check by the experimenter (before any run): on the real starting applications of
  BOTH systems (apps/ and baseline_v2/), the hidden tests of the non-chained challenges give the
  same before-change pass counts as on the reference (F01 0/9, F07 0/8, F08 3/8, F09 4/5,
  F10 1/8, F11 1/10, F12 0/9, F13 0/4, F14 0/9).

The set was committed and checksummed (`SHA256SUMS`) before any implementer run on it and is not
changed afterwards. F01-F06 form a six-step sequence on expenses; F09 should be rejected.
