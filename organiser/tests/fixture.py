"""Synthetic backup in SMS Backup & Restore XML format. Entirely fictional people and numbers."""
import datetime as dt
from xml.sax.saxutils import quoteattr as q

def ms(y, mo, d, h, mi=0): return int(dt.datetime(y, mo, d, h, mi).timestamp() * 1000)

# (address, name, when, direction 1=in 2=sent, body)
CONV = [
 ("+15550000001", "Dana (Cafe)", ms(2026,3,4,9),  2, "Hi Dana, I might need Friday off, not sure yet"),           # tentative, Wed -> Fri 6th
 ("+15550000001", "Dana (Cafe)", ms(2026,3,4,9,5), 1, "ok let me know"),                                          # positive reply to tentative
 ("+15550000001", "Dana (Cafe)", ms(2026,3,9,8),  2, "Can I have Thursday off? Doctor's appointment"),             # request Mon -> Thu 12th
 ("+15550000001", "Dana (Cafe)", ms(2026,3,9,8,30),1, "Sure, no problem"),                                         # confirmed
 ("+15550000001", "Dana (Cafe)", ms(2026,3,16,6,45),2,"Sorry I can't come in today, I'm sick"),                   # statement, Mon 16th
 ("+15550000001", "Dana (Cafe)", ms(2026,3,16,7),  1, "Get well soon"),                                            # confirmed
 ("+15550000001", "Dana (Cafe)", ms(2026,3,18,10), 2, "I won't be able to work Saturday"),                        # statement Wed -> Sat 21st
 ("+15550000001", "Dana (Cafe)", ms(2026,3,18,11), 1, "No, we really need you Saturday"),                         # declined
 ("05550000002", "Mr Okafor", ms(2026,3,10,18),    2, "I can't make it to the job tomorrow"),                      # statement -> Wed 11th, other format of number
 ("05550000002", "Mr Okafor", ms(2026,3,10,20),    2, "Actually I can come in after all, see you tomorrow"),      # retraction -> cancelled
 ("+15550000002", "Mr Okafor", ms(2026,3,23,9),    2, "I can't do the clean on Wednesday, can we do Friday instead?"),  # statement Mon -> Wed 25th; reschedule -> Fri 27th
 ("+15550000002", "Mr Okafor", ms(2026,3,23,9,20), 1, "Friday works"),
 ("+15550000003", "Sam", ms(2026,3,5,12),          2, "can't make it to the gym tonight lol"),                     # not work related? contains 'make it' -> statement (known limitation)
 ("+15550000001", "Dana (Cafe)", ms(2026,3,20,9),  1, "We don't need you tomorrow, the cafe is closed"),         # their cancellation Sat 21st
]

def build(path, extra_dup=False, mms=True):
    rows = CONV + (CONV[:3] if extra_dup else [])
    xs = []
    for a, n, t, d, b in rows:
        xs.append(f'<sms protocol="0" address={q(a)} date="{t}" type="{d}" subject="null" body={q(b)} toa="null" sc_toa="null" service_center="null" read="1" status="-1" locked="0" date_sent="0" readable_date="x" contact_name={q(n)} />')
    if mms:
        t = ms(2026,3,25,12)
        xs.append(f'<mms date="{t}" msg_box="1" address="+15550000004~+15550000001" m_id="m1" tr_id="proto:abc" creator="com.google.android.apps.messaging" contact_name="Group" readable_date="x">'
                  '<parts><part seq="0" ct="text/plain" name="null" text="Team: rota for next week is posted" /></parts>'
                  '<addrs><addr address="+15550000004" type="137" charset="106" /><addr address="+15550000001" type="151" charset="106" /></addrs></mms>')
    xs.append('<sms address="+1555" date="notanumber" type="1" body="broken" />')  # unreadable record
    open(path, "w").write(f'<?xml version="1.0" encoding="UTF-8"?>\n<smses count="{len(xs)}">\n' + "\n".join(xs) + "\n</smses>\n")
    return len(xs)
