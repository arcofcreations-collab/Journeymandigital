# Getting messages off the Android phone: options and coverage

The status of each item is either **verified** (by a cited source, or by tests on synthetic data) or
**to verify** (it needs the user's actual phone). Nothing here requires rooting the phone or
bypassing its security. The phone's messages are only ever read, never modified.

## Facts that decide the import route

| Fact | Status | Consequence |
|---|---|---|
| Reading `content://sms` through `adb shell content query` requires `READ_SMS`. The adb shell user normally lacks it on unrooted phones. | from documentation/reports; **to verify** on the user's phone (a one-command test, below) | A pure USB/adb export is probably not possible. A permissioned app on the phone is needed. |
| SMS Backup & Restore (SyncTech) exports SMS and MMS to a documented XML file that can be saved locally on the phone and copied over USB. | public documentation | This is the primary route: no custom phone app and no cloud. |
| Google Messages stores RCS chats in the phone's SMS/MMS database as MMS, so SMS Backup & Restore can back them up. | SyncTech FAQ | RCS is partly covered (see the next row). |
| Since about May/June 2026, a Google Messages bug stops **outgoing** RCS messages from being written to that database. **End-to-end-encrypted** RCS messages are marked "restricted" there, and only the default SMS app can read them. This was formalised in Android 17. | SyncTech FAQ | Sent RCS messages, and E2EE RCS chats on recent versions, may be **missing**. The organiser reports this as a coverage gap. It never presents an import as complete. |
| A companion app of our own would need the same `READ_SMS` permission and has the same RCS limits. It is not a way around them. | Android permission model | Build one only if SMS Backup & Restore is unavailable or unacceptable to the user. |
| WhatsApp, Signal and other apps are separate sources, each with its own export (for example WhatsApp "Export chat" produces a .txt per chat). | to verify per app | Optional, separate adapters. Not part of SMS/MMS coverage. |

Sources:
- <https://www.synctech.com.au/?p=2295> (outgoing RCS not backed up)
- <https://www.synctech.com.au/?p=391> (advanced messages, i.e. RCS)
- <https://www.synctech.com.au/faqs/why-are-some-messages-missing-from-the-backup/>
- <https://rapid7.com/blog/post/cve-2025-10184-oneplus-oxygenos-telephony-provider-permission-bypass-not-fixed>
  (`READ_SMS` enforcement on the telephony provider)

## Guided import (primary route)

1. **On the phone**, install *SMS Backup & Restore* (SyncTech) from Google Play. Back up
   **Messages** (and optionally Call logs). Choose **local storage on the phone only**: no Google
   Drive, Dropbox or email. Turn on "Include MMS media" if you want attachments. Reading only; this
   does not change your messages.
2. **Connect the phone to the computer by USB** and choose *File transfer* on the phone. Copy the
   `sms-*.xml` file from the phone's `SMSBackupRestore` folder to the computer. If the computer
   has adb, `adb pull` works too.
3. **On the computer**, run `organiser import <file.xml>`. The import reports:
   - counts of SMS, MMS, and RCS-as-MMS messages;
   - the date range covered;
   - the number of threads;
   - duplicates skipped (repeat imports are safe);
   - parse errors;
   - the known coverage gaps above, so that a partial import is never presented as everything on
     the phone.
4. **Optional check:** on the phone, compare the message count shown by SMS Backup & Restore with
   the count the organiser reports.

## What the user needs to tell or do (only these)

- the phone's make, model and Android version (Settings > About phone);
- which app is the default messaging app (Google Messages, Samsung Messages, ...);
- the computer's operating system;
- whether installing SMS Backup & Restore is acceptable;
- after the import: the organiser's coverage report, which shows counts only and no message
  content.

Privacy: the organiser runs locally on the user's computer. Imported messages are never sent to
any cloud service, never committed to Git, and never included in logs or demos. All development
and tests use synthetic messages. `organiser delete --all` removes the imported data and every
derived index.
