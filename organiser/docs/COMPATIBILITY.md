# Compatibility (what has actually been tested)

| item | status |
|---|---|
| Backup format: SMS Backup & Restore (SyncTech) XML, `<smses>` with `<sms>` / `<mms>` | implemented; tested on **synthetic** files only |
| Phones tested | **none yet** (user's Samsung pending) |
| Messaging apps tested | **none yet**; expected: Samsung Messages, Google Messages (default SMS app writes to the Android message store) |
| SMS | parsed; synthetic tests |
| MMS (text parts, group participants, attachment metadata; media bytes not stored) | parsed; synthetic tests |
| RCS | only where the messaging app stores it in the Android message store (Google Messages: as MMS). Detected by a heuristic (`rcs_like`), unverified on real data. Known gaps: outgoing RCS (2026 Google Messages bug), E2EE RCS (restricted), Samsung Messages' own chat storage - unverified |
| Other apps (WhatsApp, Signal, ...) | not supported |
