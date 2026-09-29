/*
 * dmguard (JavaScript port of dmguard/core.py, v1.1.0).
 *
 * Decides whether a column of numeric dates is day-first or month-first from
 * the column's calendar structure, abstaining when the evidence is weak.
 * Mirrors the Python reference implementation step by step, including the
 * surrogate randomisation test: surrogate coins use CPython's tuple hash and
 * long-column subsampling uses CPython's Mersenne Twister, so verdicts match
 * the Python tool (checked by web/parity_check.py on every benchmark case).
 * Runs in browsers and in Node (module.exports).
 */
(function (root) {
  "use strict";

  var DEFAULT_THRESHOLD_BITS = 2.0;
  var WEEKDAY_WEIGHT = 1.0;
  var MIN_Z = 3.0;
  var N_SURROGATES = 39;
  var SURROGATE_SEED = 20260929;
  var SURROGATE_MAX_ROWS = 2000;
  var COMPETING_SHARE = 0.3;
  var REGULAR_STEP_ENTROPY = 2.0;
  var MIN_DATE_SHARE = 0.5;
  var MISSING = { "": 1, "na": 1, "n/a": 1, "nan": 1, "null": 1, "none": 1, "nat": 1, "-": 1, "--": 1, "?": 1 };
  var DATE_RE = /^\s*(\d{1,4})([\/.\-])(\d{1,2})\2(\d{1,4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?\s*([AaPp][Mm])?)?\s*$/;
  var YEAR_LAST = ["DMY", "MDY"];
  var YEAR_FIRST = ["YMD", "YDM"];
  var LN2 = Math.log(2);

  // ---------------------------------------------------------------- dates
  var DIM = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  function isLeap(y) { return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0); }
  function daysInMonth(y, m) { return m === 2 && isLeap(y) ? 29 : DIM[m]; }
  function ordinal(y, m, d) { // Python date.toordinal(): 0001-01-01 -> 1
    var y1 = y - 1;
    var n = y1 * 365 + Math.floor(y1 / 4) - Math.floor(y1 / 100) + Math.floor(y1 / 400);
    for (var i = 1; i < m; i++) n += daysInMonth(y, i);
    return n + d;
  }
  // A parsed value: {y, m, d, secs, ord, key}; key orders values like Python datetimes.
  function mkDate(y, m, d, secs) {
    if (y < 1 || y > 9999 || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m)) return null;
    var o = ordinal(y, m, d);
    return { y: y, m: m, d: d, secs: secs, ord: o, key: o * 86400 + secs };
  }
  function weekday(v) { return (v.ord + 6) % 7; } // Monday = 0
  function isoDate(v) {
    function p(n, w) { n = String(n); while (n.length < w) n = "0" + n; return n; }
    var s = p(v.y, 4) + "-" + p(v.m, 2) + "-" + p(v.d, 2);
    if (v.secs) {
      s += " " + p(Math.floor(v.secs / 3600), 2) + ":" + p(Math.floor(v.secs % 3600 / 60), 2) + ":" + p(v.secs % 60, 2);
    }
    return s;
  }

  // ---------------------------------------------------------------- parsing
  function parseRaw(text) {
    var m = DATE_RE.exec(text);
    if (!m) return null;
    var secs = 0, hasTime = m[5] !== undefined;
    if (hasTime) {
      var h = +m[5], mi = +m[6], s = m[7] !== undefined ? +m[7] : 0;
      if (m[9]) {
        if (h < 1 || h > 12) return null;
        h = h % 12 + (m[9].toLowerCase() === "pm" ? 12 : 0);
      }
      if (h > 23 || mi > 59 || s > 59) return null;
      secs = h * 3600 + mi * 60 + s;
    }
    return { a: +m[1], b: +m[3], c: +m[4], aLen: m[1].length, cLen: m[4].length, sep: m[2], secs: secs,
      hasTime: hasTime, hasSecs: m[7] !== undefined, frac: m[8] || "" };
  }
  function expandYear(y, digits) { return digits === 2 ? (y >= 69 ? 1900 + y : 2000 + y) : y; }
  function layoutOf(r) {
    if (r.aLen === 4 && r.cLen <= 2) return "Y-first";
    if (r.aLen <= 2 && (r.cLen === 2 || r.cLen === 4)) return "Y-last";
    return null;
  }
  function canonicalKey(r, layout) {
    return layout === "Y-last" ? [r.a, r.b, expandYear(r.c, r.cLen), r.secs] : [r.b, r.c, r.a, r.secs];
  }
  function toDate(r, order) {
    if (order === "DMY") return mkDate(expandYear(r.c, r.cLen), r.b, r.a, r.secs);
    if (order === "MDY") return mkDate(expandYear(r.c, r.cLen), r.a, r.b, r.secs);
    if (order === "YMD") return mkDate(r.a, r.b, r.c, r.secs);
    return mkDate(r.a, r.c, r.b, r.secs); // YDM
  }
  function pad(n, w) { n = String(n); while (n.length < w) n = "0" + n; return n; }
  function isoText(r, order) { // lossless: keeps exactly the time precision written
    var d = toDate(r, order);
    if (!d) return null;
    var out = pad(d.y, 4) + "-" + pad(d.m, 2) + "-" + pad(d.d, 2);
    if (r.hasTime) {
      out += " " + pad(Math.floor(r.secs / 3600), 2) + ":" + pad(Math.floor(r.secs % 3600 / 60), 2);
      if (r.hasSecs) {
        out += ":" + pad(r.secs % 60, 2);
        if (r.frac) out += "." + r.frac;
      }
    }
    return out;
  }
  function isMissing(v) { return v === null || v === undefined || MISSING[String(v).trim().toLowerCase()] === 1; }

  // ---------------------------------------------------------------- codes
  function gammaBits(n) { return 2 * Math.floor(Math.log2(n)) + 1; }
  function newSymbolBits(kind, units, secs) {
    var bits = 2; // log2(4)
    if (kind !== "T") bits += gammaBits(Math.abs(units) + 1);
    bits += 1;
    if (secs) bits += 1 + gammaBits(Math.floor(Math.abs(secs) / 60) + 1);
    return bits;
  }
  function monthEnd(v) { return v.d === daysInMonth(v.y, v.m); }
  function deltaSymbol(x, y) {
    var secs = y.secs - x.secs;
    if (x.ord === y.ord) return ["T", 0, secs];
    var months = (y.y - x.y) * 12 + (y.m - x.m);
    if (months && x.d === y.d) return ["M", months, secs];
    if (months && monthEnd(x) && monthEnd(y)) return ["E", months, secs];
    return ["D", y.ord - x.ord, secs];
  }
  function sequenceBits(values) {
    var counts = new Map(), n = 0, dirs = [0, 0], items = [];
    for (var i = 0; i + 1 < values.length; i++) {
      var s = deltaSymbol(values[i], values[i + 1]);
      var kind = s[0], units = s[1], secs = s[2];
      var sign = (units > 0) - (units < 0) || (secs > 0) - (secs < 0);
      var bits = 0;
      if (sign) {
        var d = sign > 0 ? 0 : 1;
        bits += -Math.log2((dirs[d] + 0.5) / (dirs[0] + dirs[1] + 1));
        dirs[d] += 1;
        units *= sign; secs *= sign;
      }
      var k = kind + "|" + units + "|" + secs;
      var c = counts.get(k) || 0;
      if (c) bits += -Math.log2(c / (n + 1));
      else bits += -Math.log2(1 / (n + 1)) + newSymbolBits(kind, units, secs);
      items.push(bits);
      counts.set(k, c + 1);
      n += 1;
    }
    return { items: items, counts: counts };
  }
  function distinctSorted(values, keyFn) {
    var seen = new Map();
    for (var i = 0; i < values.length; i++) {
      var k = keyFn(values[i]);
      if (!seen.has(k)) seen.set(k, values[i]);
    }
    return Array.from(seen.values()).sort(function (p, q) { return keyFn(p) - keyFn(q); });
  }
  function weekdayBits(values) {
    var counts = [0, 0, 0, 0, 0, 0, 0], items = [];
    var dates = distinctSorted(values, function (v) { return v.ord; });
    for (var i = 0; i < dates.length; i++) {
      var wd = weekday(dates[i]);
      items.push(-Math.log2((counts[wd] + 0.5) / (i + 3.5)));
      counts[wd] += 1;
    }
    return { items: items, counts: counts, dates: dates };
  }
  var LOGFACT = [0];
  function logFact(n) { // ln(n!) == math.lgamma(n + 1)
    while (LOGFACT.length <= n) LOGFACT.push(LOGFACT[LOGFACT.length - 1] + Math.log(LOGFACT.length));
    return LOGFACT[n];
  }
  function arrangementBits(values) {
    var counts = new Map();
    for (var i = 0; i < values.length; i++) counts.set(values[i].key, (counts.get(values[i].key) || 0) + 1);
    var perm = logFact(values.length), mult = 0;
    counts.forEach(function (c) { perm -= logFact(c); mult += gammaBits(c); });
    return perm / LN2 + mult;
  }
  function sum(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s; }
  function describeStep(k) {
    var p = k.split("|"), kind = p[0], units = +p[1], secs = +p[2];
    if (kind === "T") return secs % 3600 ? Math.floor(secs / 60) + " min" : Math.floor(secs / 3600) + " h";
    var unit = { M: "month", E: "month (month-end)", D: "day" }[kind];
    return units + " " + unit + (Math.abs(units) !== 1 && kind !== "E" ? "s" : "");
  }
  function mostCommon(map, n) { // stable, like collections.Counter.most_common
    return Array.from(map.entries()).map(function (e, i) { return [e[0], e[1], i]; })
      .sort(function (p, q) { return q[1] - p[1] || p[2] - q[2]; }).slice(0, n);
  }

  function readingStats(order, values, keys) {
    var ord = sequenceBits(values);
    var distinct = distinctSorted(values, function (v) { return v.key; });
    var grid = sequenceBits(distinct);
    var wd = weekdayBits(values);
    var keyOf = new Map(), dkeyOf = new Map();
    for (var i = 0; i < values.length; i++) {
      keyOf.set(values[i].key, keys[i].join(","));
      dkeyOf.set(values[i].ord, keys[i].slice(0, 3).join(","));
    }
    var gridByKey = new Map();
    for (var j = 1; j < distinct.length; j++) gridByKey.set(keyOf.get(distinct[j].key), grid.items[j - 1]);
    var wdByKey = new Map();
    for (var t = 0; t < wd.dates.length; t++) wdByKey.set(dkeyOf.get(wd.dates[t].ord), wd.items[t]);
    var fwd = 0, back = 0;
    for (var s = 0; s + 1 < values.length; s++) {
      if (values[s + 1].key > values[s].key) fwd++;
      else if (values[s + 1].key < values[s].key) back++;
    }
    var top = mostCommon(grid.counts, 3), gridN = 0;
    grid.counts.forEach(function (c) { gridN += c; });
    var nwd = sum(wd.counts), distinctWd = wd.counts.filter(function (c) { return c > 0; }).length;
    var ent = 0;
    grid.counts.forEach(function (c) { ent -= c / gridN * Math.log2(c / gridN); });
    var st = {
      stepEntropy: gridN ? ent : 0,
      order: order,
      orderBits: sum(ord.items), gridBits: sum(grid.items),
      arrangementBits: arrangementBits(values), weekdayBits: sum(wd.items),
      forwardShare: fwd + back ? Math.max(fwd, back) / (fwd + back) : 1,
      topStep: top.length ? describeStep(top[0][0]) : "-",
      topStepShare: top.length ? top[0][1] / gridN : 0,
      weekdayShareMonFri: nwd ? (wd.counts[0] + wd.counts[1] + wd.counts[2] + wd.counts[3] + wd.counts[4]) / nwd : 0,
      distinctWeekdays: distinctWd,
      stepSizes: top.map(function (e) { return describeStep(e[0]); }),
      nStepSizes: grid.counts.size,
      orderItems: ord.items, gridItems: grid.items, weekdayItems: wd.items,
      gridByKey: gridByKey, weekdayByKey: wdByKey,
      values: values
    };
    st.usesFileOrder = st.orderBits <= st.gridBits + st.arrangementBits;
    st.sequenceBits = Math.min(st.orderBits, st.gridBits + st.arrangementBits);
    st.sequenceItems = st.usesFileOrder ? st.orderItems : st.gridItems;
    st.totalBits = st.sequenceBits + WEEKDAY_WEIGHT * st.weekdayBits;
    return st;
  }
  function varSum(items) {
    var n = items.length;
    if (n < 2) return 0;
    var mean = sum(items) / n, ss = 0;
    for (var i = 0; i < n; i++) ss += (items[i] - mean) * (items[i] - mean);
    return n * ss / (n - 1);
  }
  function sequenceZ(best, other) {
    var e = other.sequenceBits - best.sequenceBits, v;
    if (best.usesFileOrder && other.usesFileOrder) {
      var diffs = [];
      for (var i = 0; i < other.orderItems.length; i++) diffs.push(other.orderItems[i] - best.orderItems[i]);
      v = varSum(diffs);
    } else if (!best.usesFileOrder && !other.usesFileOrder) {
      var keys = new Set(Array.from(other.gridByKey.keys()).concat(Array.from(best.gridByKey.keys())));
      var d2 = [];
      keys.forEach(function (k) { d2.push((other.gridByKey.get(k) || 0) - (best.gridByKey.get(k) || 0)); });
      v = varSum(d2);
    } else {
      v = varSum(best.sequenceItems) + varSum(other.sequenceItems);
    }
    if (v <= 0) return e > 0 ? Infinity : (e < 0 ? -Infinity : 0);
    return e / Math.sqrt(v);
  }
  function signedEvidence(v1, v2, keys, o1, o2) {
    var s1 = readingStats(o1, v1, keys), s2 = readingStats(o2, v2, keys);
    var seq = s2.sequenceBits - s1.sequenceBits;
    var z = seq >= 0 ? sequenceZ(s1, s2) : -sequenceZ(s2, s1);
    var wd = WEEKDAY_WEIGHT * (s2.weekdayBits - s1.weekdayBits);
    return { s1: s1, s2: s2, seq: seq, z: z, wd: wd };
  }

  // ------------------------------------------- CPython-compatible randomness
  var M64 = (1n << 64n) - 1n;
  var XP1 = 11400714785074694791n, XP2 = 14029467366897019727n, XP5 = 2870177450012600261n;
  function pyTupleHash(ints) { // hash(tuple_of_small_non_negative_ints), CPython >= 3.8, 64-bit
    var acc = XP5;
    for (var i = 0; i < ints.length; i++) {
      acc = (acc + BigInt(ints[i]) * XP2) & M64;
      acc = ((acc << 31n) | (acc >> 33n)) & M64;
      acc = (acc * XP1) & M64;
    }
    acc = (acc + (BigInt(ints.length) ^ (XP5 ^ 3527539n))) & M64;
    if (acc === M64) return 1546275796n;
    return acc; // unsigned view; bit tests agree with Python's signed value
  }
  function MT(seed) { // Python random.Random(int seed)
    var mt = new Array(624), i, j, k;
    function initGenrand(s) {
      mt[0] = s >>> 0;
      for (var n = 1; n < 624; n++) {
        var prev = mt[n - 1] ^ (mt[n - 1] >>> 30);
        mt[n] = ((((prev & 0xffff0000) >>> 16) * 1812433253) << 16) + (prev & 0x0000ffff) * 1812433253 + n;
        mt[n] >>>= 0;
      }
    }
    initGenrand(19650218);
    var key = [seed >>> 0];
    i = 1; j = 0;
    for (k = Math.max(624, key.length); k; k--) {
      var p = mt[i - 1] ^ (mt[i - 1] >>> 30);
      mt[i] = ((mt[i] ^ (((((p & 0xffff0000) >>> 16) * 1664525) << 16) + ((p & 0x0000ffff) * 1664525))) + key[j] + j) >>> 0;
      i++; j++;
      if (i >= 624) { mt[0] = mt[623]; i = 1; }
      if (j >= key.length) j = 0;
    }
    for (k = 623; k; k--) {
      var q = mt[i - 1] ^ (mt[i - 1] >>> 30);
      mt[i] = ((mt[i] ^ (((((q & 0xffff0000) >>> 16) * 1566083941) << 16) + (q & 0x0000ffff) * 1566083941)) - i) >>> 0;
      i++;
      if (i >= 624) { mt[0] = mt[623]; i = 1; }
    }
    mt[0] = 0x80000000;
    var mti = 624;
    function genrand() {
      var y;
      if (mti >= 624) {
        for (var kk = 0; kk < 624; kk++) {
          y = (mt[kk] & 0x80000000) | (mt[(kk + 1) % 624] & 0x7fffffff);
          mt[kk] = (mt[(kk + 397) % 624] ^ (y >>> 1) ^ (y & 1 ? 0x9908b0df : 0)) >>> 0;
        }
        mti = 0;
      }
      y = mt[mti++];
      y ^= y >>> 11; y ^= (y << 7) & 0x9d2c5680; y ^= (y << 15) & 0xefc60000; y ^= y >>> 18;
      return y >>> 0;
    }
    function randbelow(n) { // n < 2**32
      var bits = n.toString(2).length, r;
      do { r = genrand() >>> (32 - bits); } while (r >= n);
      return r;
    }
    function sample(n, k) { // indices, as random.sample(range(n), k)
      var result = new Array(k), setsize = 21;
      if (k > 5) setsize += Math.pow(4, Math.ceil(Math.log(k * 3) / Math.log(4)));
      if (n <= setsize) {
        var pool = []; for (var a = 0; a < n; a++) pool.push(a);
        for (var b = 0; b < k; b++) { var jj = randbelow(n - b); result[b] = pool[jj]; pool[jj] = pool[n - b - 1]; }
      } else {
        var selected = new Set();
        for (var c = 0; c < k; c++) {
          var jx = randbelow(n);
          while (selected.has(jx)) jx = randbelow(n);
          selected.add(jx); result[c] = jx;
        }
      }
      return result;
    }
    return { sample: sample };
  }

  function surrogateBestBits(raws, layout, o1, o2, k) {
    if (raws.length > SURROGATE_MAX_ROWS) {
      var idx = MT(SURROGATE_SEED).sample(raws.length, SURROGATE_MAX_ROWS).sort(function (p, q) { return p - q; });
      raws = idx.map(function (i) { return raws[i]; });
    }
    function bestBits(rs) {
      var v1 = rs.map(function (r) { return toDate(r, o1); });
      var v2 = rs.map(function (r) { return toDate(r, o2); });
      var keys = rs.map(function (r) { return canonicalKey(r, layout); });
      var s1 = readingStats(o1, v1, keys), s2 = readingStats(o2, v2, keys);
      return [s1.totalBits, s2.totalBits, WEEKDAY_WEIGHT * (s2.weekdayBits - s1.weekdayBits)];
    }
    var nul = [], nulWd = [];
    for (var i = 0; i < k; i++) {
      var sr = raws.map(function (r) {
        var ck = canonicalKey(r, layout);
        var h = pyTupleHash([SURROGATE_SEED, i, Math.min(ck[0], ck[1]), Math.max(ck[0], ck[1]), ck[2], ck[3]]);
        if ((h >> 11n) & 1n) {
          return layout === "Y-last"
            ? { a: r.b, b: r.a, c: r.c, aLen: r.aLen, cLen: r.cLen, sep: r.sep, secs: r.secs }
            : { a: r.a, b: r.c, c: r.b, aLen: r.aLen, cLen: r.cLen, sep: r.sep, secs: r.secs };
        }
        return r;
      });
      var t = bestBits(sr);
      nul.push(Math.min(t[0], t[1])); nulWd.push(Math.abs(t[2]));
    }
    var o = bestBits(raws);
    return { b1: o[0], b2: o[1], nul: nul, wd: o[2], nulWd: nulWd };
  }

  // ---------------------------------------------------------------- explain
  function pct(x) { return Math.round(x * 100) + "%"; }
  function stepsText(s) {
    var more = s.nStepSizes > s.stepSizes.length ? " (+" + (s.nStepSizes - s.stepSizes.length) + " more)" : "";
    return s.stepSizes.map(function (x) { return "'" + x + "'"; }).join(", ") + more;
  }
  function explain(best, other) {
    var r = [];
    if (best.usesFileOrder && best.forwardShare - other.forwardShare >= 0.05) {
      r.push("row order is chronological for " + pct(best.forwardShare) + " of steps under " + best.order +
        " vs " + pct(other.forwardShare) + " under " + other.order);
    }
    if (best.topStepShare - other.topStepShare >= 0.05) {
      r.push("sorted dates step by '" + best.topStep + "' " + pct(best.topStepShare) + " of the time under " +
        best.order + " vs '" + other.topStep + "' " + pct(other.topStepShare) + " under " + other.order);
    }
    if (Math.abs(best.weekdayShareMonFri - other.weekdayShareMonFri) >= 0.05 || best.distinctWeekdays < other.distinctWeekdays) {
      r.push("weekdays: " + best.distinctWeekdays + " distinct, " + pct(best.weekdayShareMonFri) + " Mon-Fri under " +
        best.order + " vs " + other.distinctWeekdays + " distinct, " + pct(other.weekdayShareMonFri) + " Mon-Fri under " + other.order);
    }
    if (best.nStepSizes < other.nStepSizes) {
      var steps = function (s) {
        var more = s.nStepSizes > s.stepSizes.length ? ", +" + (s.nStepSizes - s.stepSizes.length) + " more" : "";
        return s.stepSizes.map(function (x) { return "'" + x + "'"; }).join(", ") + more;
      };
      r.push("sorted dates use " + best.nStepSizes + " distinct step size(s) under " + best.order + " (" + steps(best) +
        ") vs " + other.nStepSizes + " under " + other.order + " (" + steps(other) + ")");
    }
    if (!r.length) r.push("combined calendar regularity (see bit counts)");
    return r;
  }

  // ---------------------------------------------------------------- resolve
  function resolveColumn(values, opts) {
    opts = opts || {};
    var threshold = opts.thresholdBits !== undefined ? opts.thresholdBits : DEFAULT_THRESHOLD_BITS;
    var minZ = opts.minZ !== undefined ? opts.minZ : MIN_Z;
    var nSur = opts.nSurrogates !== undefined ? opts.nSurrogates : N_SURROGATES;
    var acceptLikely = !!opts.acceptLikely;
    var raws = [], rawText = [], nMissing = 0, nUnparsed = 0, unparsedExamples = [];
    for (var i = 0; i < values.length; i++) {
      var v = values[i];
      if (isMissing(v)) { nMissing++; continue; }
      var r = parseRaw(String(v));
      if (!r || !layoutOf(r)) {
        nUnparsed++;
        if (unparsedExamples.length < 5) unparsedExamples.push({ row: i, value: String(v) });
        continue;
      }
      raws.push(r); rawText.push(String(v).trim());
    }
    var res = { verdict: "AMBIGUOUS", method: "", evidenceBits: 0, evidenceZ: 0, components: {},
      nValues: raws.length, nMissing: nMissing, nUnparsed: nUnparsed, unparsedExamples: unparsedExamples,
      examples: [], reasons: [], notes: [], likely: null, stats: {} };
    var total = raws.length + nUnparsed;
    if (total === 0) { res.verdict = "EMPTY"; return res; }
    if (raws.length / total < MIN_DATE_SHARE) { res.verdict = "NOT_DATE"; return res; }
    var layouts = {}, seps = {};
    raws.forEach(function (r) { var l = layoutOf(r); layouts[l] = (layouts[l] || 0) + 1; seps[r.sep] = (seps[r.sep] || 0) + 1; });
    if (Object.keys(layouts).length !== 1 || Object.keys(seps).length !== 1) {
      res.verdict = "INCONSISTENT";
      res.reasons.push("mixed layouts " + JSON.stringify(layouts) + " / separators " + JSON.stringify(seps));
      return res;
    }
    var layout = Object.keys(layouts)[0];
    res.layout = layout; res.separator = raws[0].sep;
    var cands = layout === "Y-last" ? YEAR_LAST : YEAR_FIRST;
    res.candidates = cands;
    if (layout === "Y-last" && raws.some(function (r) { return r.cLen === 2; })) res.notes.push("two-digit years were read as 1969-2068");
    var parsed = {}, invalid = {};
    cands.forEach(function (o) {
      parsed[o] = raws.map(function (r) { return toDate(r, o); });
      invalid[o] = parsed[o].filter(function (x) { return x === null; }).length;
    });
    res.invalidCounts = invalid;
    var seen = new Set(), order = [];
    raws.forEach(function (r, j) { if (r.a !== (layout === "Y-last" ? r.b : r.c)) order.push(j); });
    for (var q = 0; q < raws.length; q++) order.push(q);
    for (var e = 0; e < order.length && res.examples.length < 3; e++) {
      var ix = order[e];
      if (seen.has(rawText[ix])) continue;
      seen.add(rawText[ix]);
      var readings = {};
      cands.forEach(function (o) { readings[o] = parsed[o][ix] ? isoDate(parsed[o][ix]) : null; });
      res.examples.push({ value: rawText[ix], readings: readings });
    }
    var valid = cands.filter(function (o) { return invalid[o] === 0; });
    if (!valid.length) {
      res.verdict = "INCONSISTENT";
      res.reasons.push("no single order reads every value as a real date: " +
        cands.map(function (o) { return o + ": " + invalid[o] + " impossible"; }).join(", "));
      return res;
    }
    if (valid.length === 1) {
      var other = cands[0] === valid[0] ? cands[1] : cands[0];
      res.verdict = valid[0]; res.method = "validity";
      res.reasons.push(invalid[other] + " value(s) are impossible dates under " + other);
      return res;
    }
    var o1 = cands[0], o2 = cands[1];
    var same = parsed[o1].every(function (x, j) { return x.key === parsed[o2][j].key; });
    if (same) {
      res.verdict = o1; res.method = "identical";
      res.reasons.push("both orders give identical dates (day equals month in every value)");
      return res;
    }
    var keys = raws.map(function (r) { return canonicalKey(r, layout); });
    var ev = signedEvidence(parsed[o1], parsed[o2], keys, o1, o2);
    res.stats[o1] = ev.s1; res.stats[o2] = ev.s2;
    var tot = ev.seq + ev.wd;
    var best = tot >= 0 ? ev.s1 : ev.s2, oth = tot >= 0 ? ev.s2 : ev.s1;
    res.evidenceBits = Math.abs(tot); res.evidenceZ = Math.abs(ev.z);
    res.components = { sequenceBits: ev.seq, sequenceZ: ev.z, weekdayBits: ev.wd };
    var conflict = ev.seq * ev.wd < 0 && Math.min(Math.abs(ev.seq), Math.abs(ev.wd)) >= threshold;
    var why = null, competing = false, prefix = [];
    if (res.evidenceBits < threshold) {
      why = "it favours " + best.order + " by only " + res.evidenceBits.toFixed(1) + " bits (< " + threshold + ")";
    } else if (conflict) {
      why = "row order/grid and weekday pattern point in opposite directions (" + ev.seq.toFixed(1) + " vs " + ev.wd.toFixed(1) + " bits)";
    } else {
      var sb = surrogateBestBits(raws, layout, o1, o2, nSur);
      var bBest = best === ev.s1 ? sb.b1 : sb.b2, bOther = best === ev.s1 ? sb.b2 : sb.b1;
      var wdBest = best === ev.s1 ? sb.wd : -sb.wd;
      var floor = Math.min.apply(null, sb.nul), maxWd = Math.max.apply(null, sb.nulWd);
      var retained = floor > bBest ? (floor - bOther) / (floor - bBest) : 1;
      res.components.bestBits = bBest; res.components.otherBits = bOther; res.components.surrogateMinBits = floor;
      res.components.surrogates = sb.nul.length; res.components.retainedStructure = retained;
      res.components.otherStepEntropy = oth.stepEntropy; res.components.weekdayTowardsBest = wdBest;
      res.components.surrogateMaxWeekday = maxWd;
      var selfEvident = Math.abs(ev.z) >= minZ && ev.seq * tot > 0;
      if (!(selfEvident || bBest < floor)) {
        why = "the column is no more regular than " + sb.nul.length + " scrambled copies of itself (" +
          bBest.toFixed(1) + " vs best scrambled " + floor.toFixed(1) + " bits), so the " +
          res.evidenceBits.toFixed(1) + "-bit lean towards " + best.order + " may be chance";
      } else if (retained >= COMPETING_SHARE || oth.stepEntropy <= REGULAR_STEP_ENTROPY) {
        if (wdBest >= threshold && wdBest > maxWd) {
          prefix = ["row order and sampling grid are regular under both orders (" + best.order + ": " + stepsText(best) +
            "; " + oth.order + ": " + stepsText(oth) + "), so the decision rests on weekdays (" + wdBest.toFixed(1) +
            " bits, more than any of " + sb.nulWd.length + " scrambled copies)"];
        } else {
          competing = true;
          why = "both orders form regular calendar patterns: under " + best.order + " the sorted dates step by " +
            stepsText(best) + "; under " + oth.order + " by " + stepsText(oth) + ". " + best.order + " is simpler by " +
            res.evidenceBits.toFixed(1) + " bits, which is a preference, not proof";
        }
      }
    }
    if (why === null) {
      res.verdict = best.order; res.method = "structure"; res.reasons = prefix.concat(explain(best, oth));
    } else if (competing) {
      res.likely = best.order;
      if (acceptLikely) {
        res.verdict = best.order; res.method = "likely-accepted";
        res.reasons.push(why + "; " + best.order + " applied because likely answers were accepted");
      } else {
        res.verdict = "AMBIGUOUS"; res.method = "competing";
        res.reasons.push(why + "; likely " + best.order + ", but not applied without confirmation");
      }
    } else {
      res.verdict = "AMBIGUOUS"; res.method = "abstained";
      res.reasons.push("calendar structure is not conclusive: " + why + "; refusing to guess");
    }
    return res;
  }

  function parseWithOrder(values, order) {
    return values.map(function (v) {
      if (isMissing(v)) return null;
      var r = parseRaw(String(v));
      return r ? toDate(r, order) : null;
    });
  }

  function isoWithOrder(values, order) {
    return values.map(function (v) {
      if (isMissing(v)) return null;
      var r = parseRaw(String(v));
      return r ? isoText(r, order) : null;
    });
  }

  var api = {
    VERSION: "1.1.0", isoWithOrder: isoWithOrder, DEFAULT_THRESHOLD_BITS: DEFAULT_THRESHOLD_BITS,
    resolveColumn: resolveColumn, parseWithOrder: parseWithOrder, isoDate: isoDate,
    _pyTupleHash: pyTupleHash, _MT: MT
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.dmguard = api;
})(typeof window !== "undefined" ? window : this);
