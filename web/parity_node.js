// Reads a JSON list of columns (lists of strings) on stdin, prints verdicts as JSON.
const d = require("./dmguard.js");
let buf = "";
process.stdin.on("data", (c) => (buf += c));
process.stdin.on("end", () => {
  const cols = JSON.parse(buf);
  const out = cols.map((c) => {
    const r = d.resolveColumn(c);
    const ra = d.resolveColumn(c, { acceptLikely: true });
    const resolved = ["DMY", "MDY", "YMD", "YDM"].includes(ra.verdict);
    const iso = resolved ? d.isoWithOrder(c, ra.verdict) : null;
    return [r.verdict, r.method, r.evidenceBits, r.likely, r.nUnparsed, ra.verdict, ra.method, iso];
  });
  process.stdout.write(JSON.stringify(out));
});
