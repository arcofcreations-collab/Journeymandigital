
#### dev set: summary (first attempts)

| | accrete | baseline | baseline ÷ accrete |
|---|---|---|---|
| correct (all hidden tests pass, no regressions) | 12/14 | 14/14 | |
| regressions | 1 | 0 | |
| median change time (min) | 1.56 | 3.87 | **2.48x** |
| mean change time (min) | 1.83 | 3.65 | 1.99x |
| total agent time (min) | 25.7 | 51.1 | 1.99x |
| median tool calls | 15.0 | 23.0 | 1.53x |
| median tokens (k) | 70.8 | 109.0 | 1.54x |
| total tokens (k) | 1009.6 | 1441.4 | 1.43x |
| median changed lines (non-zero) | 93 | 407 | 4.38x |
| paired time ratio: median / min / max | | | 2.34x / 0.73x / 3.65x |
| challenges where accrete was ≥5x faster | | | 0/14 |

#### dev set: every run (first attempts; ✔/✘ = success, rN = N regressions)

| ID | app | categories | accrete | min | tools | ktok | Δlines | baseline | min | tools | ktok | Δlines | time ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| D01 | library | data_migration, new_relationship, new_concept, cross_cutting | ✘ 11/12 r1 | 3.11 | 31 | 86 | – | ✔ 12/12 | 5.35 | 32 | 114 | 560 | 1.7x |
| D02 | library | new_concept, cross_cutting, rule_change | ✔ 13/13 | 2.34 | 16 | 75 | 143 | ✔ 13/13 | 4.21 | 22 | 105 | 658 | 1.8x |
| D03 | library | rule_change, sequence, interaction | ✔ 11/11 | 1.08 | 14 | 66 | 55 | ✔ 11/11 | 2.88 | 18 | 106 | 229 | 2.7x |
| D04 | library | rule_change, sequence, interaction, data_migration, cross_cutting | ✔ 11/11 | 2.45 | 16 | 87 | 131 | ✔ 11/11 | 5.56 | 31 | 129 | 397 | 2.3x |
| D05 | library | permissions, rule_change | ✔ 11/11 | 1.25 | 12 | 63 | 79 | ✔ 11/11 | 3.19 | 21 | 97 | 321 | 2.6x |
| D06 | library | failure_atomicity, new_concept, cross_cutting | ✔ 11/11 | 2.85 | 17 | 77 | 86 | ✔ 11/11 | 2.80 | 19 | 91 | 241 | 1.0x |
| D07 | library | rule_change, conflict_or_ambiguity | ✔ 11/11 | 0.96 | 11 | 62 | 53 | ✔ 11/11 | 2.27 | 19 | 79 | 130 | 2.4x |
| D08 | expenses | rule_change, permissions, data_migration, conflict_or_ambiguity | ✔ 12/12 | 1.56 | 14 | 72 | 93 | ✔ 12/12 | 4.10 | 28 | 112 | 404 | 2.6x |
| D09 | expenses | reversal, data_migration, sequence, permissions | ✔ 8/8 | 0.80 | 10 | 63 | 55 | ✔ 8/8 | 2.93 | 21 | 112 | 537 | 3.6x |
| D10 | expenses | cross_cutting, new_concept, data_migration | ✔ 11/11 | 1.57 | 16 | 70 | 218 | ✔ 11/11 | 3.63 | 27 | 104 | 407 | 2.3x |
| D11 | expenses | failure_atomicity, new_concept, new_relationship, interaction, sequence | ✘ 0/11 | 1.56 | 14 | 76 | – | ✔ 11/11 | 4.25 | 24 | 112 | 573 | 2.7x |
| D12 | expenses | new_relationship, data_migration, cross_cutting, conflict_or_ambiguity | ✔ 13/13 | 4.11 | 23 | 96 | 207 | ✔ 13/13 | 5.14 | 32 | 121 | 505 | 1.3x |
| D13 | expenses | new_concept, permissions, conflict_or_ambiguity | ✔ 11/11 | 1.65 | 17 | 66 | 105 | ✔ 11/11 | 4.52 | 29 | 112 | 607 | 2.7x |
| D14 | expenses | should_reject, conflict_or_ambiguity | ✔ 7/7 | 0.39 | 6 | 52 | 0 | ✔ 7/7 | 0.29 | 5 | 49 | 0 | 0.7x |

D01 accrete second attempt (after engine revision, not counted above): ✔ 12/12, 1.02 min, 11 tools, 64 ktok

D11 accrete second attempt (after engine revision, not counted above): ✔ 11/11, 2.19 min, 22 tools, 88 ktok

#### eval set: summary (first attempts)

| | accrete | baseline | baseline ÷ accrete |
|---|---|---|---|
| correct (all hidden tests pass, no regressions) | 12/14 | 14/14 | |
| regressions | 0 | 0 | |
| median change time (min) | 2.02 | 4.91 | **2.43x** |
| mean change time (min) | 2.04 | 4.88 | 2.39x |
| total agent time (min) | 28.6 | 68.3 | 2.39x |
| median tool calls | 17.0 | 31.0 | 1.82x |
| median tokens (k) | 79.3 | 133.3 | 1.68x |
| total tokens (k) | 1127.4 | 1818.4 | 1.61x |
| median changed lines (non-zero) | 120 | 640 | 5.33x |
| paired time ratio: median / min / max | | | 2.46x / 1.22x / 4.00x |
| challenges where accrete was ≥5x faster | | | 0/14 |

#### eval set: every run (first attempts; ✔/✘ = success, rN = N regressions)

| ID | app | categories | accrete | min | tools | ktok | Δlines | baseline | min | tools | ktok | Δlines | time ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E01 | maintenance | new_concept, new_relationship, failure_atomicity, cross_cutting | ✔ 15/15 | 4.25 | 26 | 97 | 228 | ✔ 15/15 | 6.28 | 36 | 142 | 984 | 1.5x |
| E02 | maintenance | new_concept, permissions, rule_change, data_migration, conflict_or_ambiguity, sequence | ✔ 11/11 | 2.16 | 21 | 80 | 120 | ✔ 11/11 | 4.96 | 33 | 137 | 412 | 2.3x |
| E03 | maintenance | rule_change, data_migration, cross_cutting, interaction, sequence | ✔ 8/8 | 1.63 | 17 | 78 | 110 | ✔ 8/8 | 6.52 | 38 | 154 | 521 | 4.0x |
| E04 | maintenance | new_concept, data_migration, rule_change, interaction, sequence | ✔ 10/10 | 2.42 | 20 | 95 | 188 | ✔ 10/10 | 4.86 | 27 | 160 | 654 | 2.0x |
| E05 | maintenance | reversal, data_migration, sequence, interaction, conflict_or_ambiguity | ✘ 6/7 | 1.93 | 19 | 88 | 83 | ✔ 7/7 | 4.86 | 29 | 144 | 743 | 2.5x |
| E06 | maintenance | permissions, rule_change, data_migration, cross_cutting, sequence | ✔ 10/10 | 2.32 | 15 | 90 | 135 | ✔ 10/10 | 6.61 | 35 | 171 | 660 | 2.8x |
| E07 | maintenance | new_concept, new_relationship, interaction, cross_cutting, sequence | ✔ 12/12 | 2.58 | 18 | 97 | 180 | ✔ 12/12 | 6.88 | 43 | 172 | 879 | 2.7x |
| E08 | library | new_concept, new_relationship, data_migration, cross_cutting | ✔ 10/10 | 2.03 | 16 | 74 | 154 | ✔ 10/10 | 5.89 | 36 | 125 | 640 | 2.9x |
| E09 | library | permissions, new_relationship, data_migration, conflict_or_ambiguity | ✔ 9/9 | 1.75 | 12 | 70 | 76 | ✔ 9/9 | 4.20 | 26 | 105 | 383 | 2.4x |
| E10 | library | should_reject, conflict_or_ambiguity | ✔ 4/4 | 0.49 | 6 | 54 | 0 | ✔ 4/4 | 0.59 | 8 | 51 | 0 | 1.2x |
| E11 | expenses | new_relationship, data_migration, rule_change, cross_cutting | ✘ 8/9 | 2.06 | 16 | 82 | 144 | ✔ 9/9 | 6.09 | 33 | 130 | 718 | 3.0x |
| E12 | expenses | failure_atomicity, new_concept, permissions, cross_cutting | ✔ 9/9 | 2.01 | 17 | 73 | 70 | ✔ 9/9 | 3.66 | 22 | 118 | 406 | 1.8x |
| E13 | expenses | rule_change, new_concept, conflict_or_ambiguity | ✔ 8/8 | 1.39 | 17 | 74 | 61 | ✔ 8/8 | 2.65 | 20 | 95 | 344 | 1.9x |
| E14 | library | sequence, interaction, rule_change, data_migration, failure_atomicity | ✔ 7/7 | 1.58 | 15 | 75 | 108 | ✔ 7/7 | 4.21 | 24 | 115 | 450 | 2.7x |
