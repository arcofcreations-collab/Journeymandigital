# v1, preserved unchanged

This is the first experiment ("v1"), kept exactly as evaluated. Nothing here is edited by the v2 work.

| Item | Where |
|---|---|
| Engine exactly as frozen for the v1 evaluation (commit `cefce2f`; checksums in `docs/FREEZE.md`) | `engine_frozen/` |
| Engine after the post-evaluation fixes PE1/PE2 (commit `bce703c`) | `engine_post_eval/` |
| Guide given to v1 implementers | `GUIDE_frozen.md` |
| v1 results, including the failed benchmark | `../../results/dev/`, `../../results/eval/` and `../../docs/RESULTS.md` (not modified after v1) |
| v1 baseline applications | `../../baseline/` (v2 baseline tooling lives in `../../baseline_v2/`) |
| v1 challenge sets | `../../challenges/dev/`, `../../challenges/eval/` |

The v1 verdict stands: target **not met** (2.43x median, accrete 12/14 vs baseline 14/14).

To run v1 exactly: `PYTHONPATH=archive/v1/engine_frozen/.. python -m engine_frozen.cli ...`. That
needs the package renamed; the simplest way is `git checkout cefce2f -- accrete/accrete` in a
scratch clone.
