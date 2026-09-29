// Reads a JSON list of columns (lists of strings) on stdin, prints verdicts as JSON.
const d = require("./dmguard.js");
let buf = "";
process.stdin.on("data", (c) => (buf += c));
process.stdin.on("end", () => {
  const cols = JSON.parse(buf);
  const out = cols.map((c) => {
    const r = d.resolveColumn(c);
    return [r.verdict, r.method, r.evidenceBits];
  });
  process.stdout.write(JSON.stringify(out));
});
