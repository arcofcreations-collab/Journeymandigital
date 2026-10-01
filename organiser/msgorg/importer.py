"""Import SMS/MMS (incl. RCS stored as MMS) from an "SMS Backup & Restore" XML file.

The format is the de-facto Android interchange format (works for any Android phone: Samsung, Pixel, ...).
<smses count=N>
  <sms address date(ms) type(1=in,2=sent,3=draft,4=outbox,5=failed,6=queued) body contact_name readable_date .../>
  <mms date(ms) msg_box(1=in,2=sent,...) address m_id tr_id creator ...>
     <parts><part ct="text/plain" text="..."/>...</parts>
     <addrs><addr address type(137=from,151=to,130=cc,129=bcc)/></addrs>
  </mms>
</smses>
Originals are kept verbatim (raw XML attributes as JSON); nothing on the phone is touched.
"""
from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET

SMS_DIR = {"1": "received", "2": "sent", "3": "draft", "4": "outbox", "5": "failed", "6": "queued"}
MMS_DIR = {"1": "received", "2": "sent", "3": "draft", "4": "outbox"}


def norm_address(a: str | None) -> str:
    """Canonical phone key: digits only, last 10 digits (handles +44/0/+1 prefixes); emails/short codes kept."""
    if not a:
        return ""
    a = a.strip()
    if "@" in a:
        return a.lower()
    d = re.sub(r"\D", "", a)
    return d[-10:] if len(d) >= 10 else d or a.lower()


def _key(kind, addr, date_ms, direction, body):
    h = hashlib.sha256(f"{kind}|{norm_address(addr)}|{date_ms}|{direction}|{body or ''}".encode()).hexdigest()
    return h[:32]


def _rcs_like(attrs):
    """Heuristic only: Google Messages writes RCS chats into the MMS table; markers vary by version."""
    tr = attrs.get("tr_id", "") or ""
    creator = attrs.get("creator", "") or ""
    return tr.startswith("proto:") or ("rcs" in json.dumps(attrs).lower() and "messaging" in creator)


def parse(path):
    """Yield (record dict, error str|None). Streaming, so large backups are fine."""
    for ev, el in ET.iterparse(path, events=("end",)):
        tag = el.tag
        if tag not in ("sms", "mms"):
            continue
        try:
            a = dict(el.attrib)
            if tag == "sms":
                d = SMS_DIR.get(a.get("type", ""), "other")
                body = a.get("body")
                body = None if body == "null" else body
                rec = {"kind": "sms", "date_ms": int(a["date"]), "direction": d, "address": a.get("address", ""),
                       "participants": [a.get("address", "")], "body": body or "", "contact_name": _cn(a),
                       "attachments": [], "rcs_like": False}
            else:
                d = MMS_DIR.get(a.get("msg_box", ""), "other")
                texts, atts = [], []
                for p in el.iter("part"):
                    ct = p.get("ct", "")
                    if ct == "text/plain" and p.get("text") not in (None, "null"):
                        texts.append(p.get("text"))
                    elif ct not in ("application/smil",):
                        atts.append({"ct": ct, "name": p.get("name") or p.get("cl"), "has_data": bool(p.get("data"))})
                addrs = [(x.get("address"), x.get("type")) for x in el.iter("addr")]
                parts = [x for x, _ in addrs if x and x != "insert-address-token"]
                sender = next((x for x, t in addrs if t == "137"), None)
                main = a.get("address", "") or (sender or (parts[0] if parts else ""))
                rec = {"kind": "mms", "date_ms": int(a["date"]) * (1000 if len(a["date"]) <= 10 else 1),
                       "direction": d, "address": main, "participants": parts or [main], "body": "\n".join(texts),
                       "contact_name": _cn(a), "attachments": atts, "rcs_like": _rcs_like(a), "sender": sender}
            rec["source_id"] = a.get("_id") or a.get("m_id") or None
            rec["raw"] = a
            rec["key"] = _key(rec["kind"], rec["address"], rec["date_ms"], rec["direction"], rec["body"])
            yield rec, None
        except Exception as exc:  # noqa: BLE001
            yield None, f"{tag}: {type(exc).__name__}: {exc}"
        finally:
            el.clear()


def _cn(a):
    c = a.get("contact_name")
    return None if c in (None, "", "(Unknown)", "null") else c


def declared_count(path):
    """The count attribute the backup app wrote on the root element (for coverage checks)."""
    for ev, el in ET.iterparse(path, events=("start",)):
        return int(el.attrib.get("count", "-1")) if el.tag == "smses" else -1
    return -1
