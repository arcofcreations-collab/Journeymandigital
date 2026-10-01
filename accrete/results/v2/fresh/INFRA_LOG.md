# Infrastructure events during the fresh evaluation

- 2026-10-01 ~10:5x UTC: the account's session usage limit (HTTP 429, "resets 11am UTC") terminated 15 of the
  16 trial-1 implementer agents mid-work (all except F09/accrete2, which finished). Not attributable to either
  system. Per docs/TARGET_V2.md these runs are discarded (workspaces re-prepared from clean state; partial work
  deleted) and rerun after the reset. The discarded transcripts are kept in the session task directory; their
  partial durations are not counted anywhere.
