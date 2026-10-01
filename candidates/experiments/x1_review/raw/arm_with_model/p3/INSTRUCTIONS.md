# Review task

Each file C*.md in this directory is one case. It contains a change request for an existing
application and the BEHAVIOUR DELTA of an implementation of that request. The delta is computed by
the system: every request in a large generated set was run against the application before and
after the change, on the same data, and every observable difference is listed, grouped. The data
the change itself modified is listed too. Anything not listed behaved identically within that
generated set.

Your job is the verification step of the workflow. Decide, for each case, whether the
implementation is correct:
- ACCEPT if every listed difference is required or permitted by the request, and nothing in the
  delta contradicts the request.
- REJECT if any difference contradicts the request or changes behaviour the request did not ask
  to change. Also REJECT if behaviour the request requires is visibly wrong. Give the specific
  line or reason.

Some implementations are correct and some are not; there is no fixed proportion. Work
case by case, in file-name order. Read only the files in this directory.

Procedure, for each case in order:
1. Read the case file.
2. Decide.
3. Immediately append one JSON line to verdicts.jsonl in this directory with:
   `{"case": "C..", "verdict": "ACCEPT" or "REJECT", "reason": "...", "ts": <output of date +%s.%N>}`.
   Use one Bash call per case, for example:
   `echo "{\"case\": \"C07\", \"verdict\": \"REJECT\", \"reason\": \"...\", \"ts\": $(date +%s.%N)}" >> verdicts.jsonl`

Before the first case, run `date +%s.%N > start_ts`. When you are done, reply DONE.
