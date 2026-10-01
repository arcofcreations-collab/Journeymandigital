# Message organiser (local, private)

Imports SMS/MMS (and RCS stored as MMS) from an Android "SMS Backup & Restore" XML file (any Android phone,
incl. Samsung), keeps a local searchable archive and answers "when did I tell X I couldn't work?" with evidence.
See docs/DEVICE_ACCESS.md for the import route and its coverage limits.

    python -m msgorg.cli import ~/Downloads/sms-20261001.xml    # repeat imports never duplicate
    python -m msgorg.cli coverage | contacts
    python -m msgorg.cli search "can't" --contact Dana --from 2026-03-01 --to 2026-03-31 --sent
    python -m msgorg.cli context 123                             # message with surrounding conversation
    python -m msgorg.cli job "Dana (Cafe)" cafe                  # editable job labels
    python -m msgorg.cli absences --job cafe [--export md|csv|json]
    python -m msgorg.cli correct 7 status confirmed --note "agreed by phone"   # sources never change
    python -m msgorg.cli delete --all                            # removes archive, index and interpretations

Data: ~/.msgorg/archive.db (override with --db or MSGORG_DB). Nothing is uploaded anywhere.
Statuses: requested, proposed, stated, confirmed, declined, cancelled, rescheduled, uncertain. Whether a day was
actually taken off is never asserted. Interpretation is rule-based and local (no cloud model); it will miss and
mis-read some messages - every finding shows its evidence so you can check and correct it.
Status: core + CLI built and tested on synthetic data only; web interface and a real-device import still to do.
