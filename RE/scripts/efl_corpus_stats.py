"""EFL corpus stats (efl_import_plan.md M0.3). Plain Python, read-only; not an IDA script.

usage: python RE/scripts/efl_corpus_stats.py [root ...] [--json out.json]

Dedupes files by SHA-1 and reports versions per folder. For DX9 files (0x20070801) it checks the
container, histograms the per-slot type bytes, infers block lengths (distance to the next block
start) and compares them with the minimum sizes below.
"""
import argparse
import hashlib
import json
import os
import struct
import sys
from collections import Counter, defaultdict

MAGIC = b"EFL\0"
DX9_VERSION = 0x20070801
HDR = 0x20

PTCL = ["Billboard", "Polyline", "Polygon", "Texline", "Line", "Model", "PrimModel", "LensFlare",
        "MassBillboard", "Filter", "Light", "Hit", "PolygonStrip", "Texline(alt)", "Line(alt)",
        "PolygonStrip(alt)", "LiteBillboard", "SizeBillboard"]
MOVE = ["None", "Add", "Mul", "PathStrip", "PathChain", "PathKeyframe", "PathLine"]
SLOTS = ["gen", "ptcl", "life", "move"]

# minimum block sizes (efl_import_plan.md §3, corrected by the 2026-10-05 corpus run)
GEN_SIZE = 0x1E0       # IDB type says 0x1E4; on disk the next block starts at +0x1E0
LIFE_SIZE = 0x10       # always exactly 0x10
PTCL_SIZE = {0: 0x1A0, 1: 0x1B0, 2: 0x1E0, 6: 0x25C}   # Polyline: corpus min (plan said 0x1E0)
MOVE_SIZE = {0: 0x10, 1: 0x48, 2: 0x48, 3: 0xC0, 4: 0x110, 5: 0x74, 6: 0x7C}   # None = MOVE_COMMON only
# Types whose blocks are long enough for PRIM_COMMON (0x170) and carry valid paths there.
# Line (0x60+), MassBillboard (0xE0+), Filter/Light (0x80+) and Hit (0x50) do not.
PRIM_COMMON_TYPES = {0, 1, 2, 3, 6, 12, 15}

GEN_STRINGS = {0xD0: "RangeStripPath", 0x140: "ExtVibrationPath", 0x180: "SoundRequestPath"}
PTCL_STRINGS = {0x70: "BaseMapPath", 0xB0: "NormalMapPath", 0xF0: "MaskMapPath", 0x130: "AnimPath"}


def cstr(buf, off, n=64):
    raw = buf[off:off + n]
    if len(raw) < n:
        return None, "short"
    s = raw.split(b"\0", 1)[0]
    if b"\0" not in raw:
        return None, "unterminated"
    if not s:
        return "", None
    if not all(0x20 <= c < 0x7F for c in s):
        return None, "nonprintable"
    return s.decode("ascii"), None


def path_kind(path):
    """Paths are stored without extension (like .mod texture paths), so bucket by folder."""
    parts = path.replace("\\", "/").split("/")
    kind = "/".join(parts[:2]) if len(parts) > 2 else "(flat)"
    return kind + (" +EXT?" if "." in parts[-1] else "")


class Stats:
    def __init__(self):
        self.files = 0
        self.dupes = 0
        self.versions = Counter()
        self.version_dirs = defaultdict(Counter)
        self.errors = Counter()
        self.error_examples = defaultdict(list)
        self.records_per_file = Counter()
        self.type_hist = {s: Counter() for s in SLOTS}
        self.absent = Counter()
        self.combo = Counter()                      # (ptcl, move)
        self.block_len = defaultdict(list)          # (slot, type) -> inferred lengths
        self.undersized = Counter()
        self.shared_same_slot = Counter()           # slot -> count of offsets used by >1 record
        self.shared_cross_slot = 0
        self.unit_records = Counter()
        self.unk_1c = Counter()
        self.fps = Counter()
        self.size_mismatch = 0
        self.strings = defaultdict(Counter)         # field -> ext counter
        self.string_errors = Counter()
        self.prim_type = Counter()
        self.ptcl_examples = defaultdict(list)

    def err(self, kind, path):
        self.errors[kind] += 1
        if len(self.error_examples[kind]) < 3:
            self.error_examples[kind].append(path)


def top_dir(path, roots):
    for r in roots:
        rel = os.path.relpath(path, r)
        if not rel.startswith(".."):
            parts = rel.replace("\\", "/").split("/")
            return "/".join(parts[:2]) if len(parts) > 2 else parts[0]
    return "?"


def analyse(path, data, st, roots):
    if data[:4] != MAGIC:
        st.err("bad magic", path)
        return
    version, content_size, n, unit_gen, unit_move, fps, unk = struct.unpack_from("<IIIIIfI", data, 4)
    st.versions[hex(version)] += 1
    st.version_dirs[hex(version)][top_dir(path, roots)] += 1
    if version != DX9_VERSION:
        return
    st.fps[fps] += 1
    st.unk_1c[unk] += 1
    st.records_per_file[n] += 1
    content = data[HDR:]
    if content_size != len(content):
        st.size_mismatch += 1
        st.err(f"contentSize != file-0x20", path)
    end = min(content_size, len(content))
    for name, rec in (("unitGen", unit_gen), ("unitMove", unit_move)):
        if rec:
            st.unit_records[name] += 1

    table_end = n * 16
    if table_end > end:
        st.err("record table past content", path)
        return

    recs = [struct.unpack_from("<4I", content, i * 16) for i in range(n)]
    starts = {table_end, end}
    users = defaultdict(set)   # offset -> {(slot, type)}
    refcount = defaultdict(int)
    for rec in recs:
        for si, dw in enumerate(rec):
            off, typ = dw >> 8, dw & 0xFF
            if off == 0:
                st.absent[SLOTS[si]] += 1
                continue
            st.type_hist[SLOTS[si]][typ] += 1
            if off < table_end or off >= end:
                st.err(f"{SLOTS[si]} offset outside content", path)
                continue
            if off % 4:
                st.err(f"{SLOTS[si]} offset unaligned", path)
            starts.add(off)
            users[off].add((si, typ))
            refcount[(si, off)] += 1
        p, m = rec[1], rec[3]
        st.combo[(PTCL[p & 0xFF] if p and (p & 0xFF) < len(PTCL) else ("-" if not p else p & 0xFF),
                  MOVE[m & 0xFF] if m and (m & 0xFF) < len(MOVE) else ("-" if not m else m & 0xFF))] += 1

    for (si, off), c in refcount.items():
        if c > 1:
            st.shared_same_slot[SLOTS[si]] += 1
    st.shared_cross_slot += sum(1 for u in users.values() if len({s for s, _ in u}) > 1)

    ordered = sorted(starts)
    nxt = {o: ordered[i + 1] for i, o in enumerate(ordered[:-1])}
    for off, us in users.items():
        length = nxt.get(off, end) - off
        for si, typ in us:
            st.block_len[(SLOTS[si], typ)].append(length)
            want = (GEN_SIZE, PTCL_SIZE.get(typ), LIFE_SIZE, MOVE_SIZE.get(typ))[si]
            if want and length < want:
                st.undersized[(SLOTS[si], typ)] += 1
            blk = content[off:off + length]
            if si == 0:
                for so, name in GEN_STRINGS.items():
                    s, e = cstr(blk, so)
                    if e:
                        st.string_errors[f"gen.{name}:{e}"] += 1
                    elif s:
                        st.strings[f"gen.{name}"][path_kind(s)] += 1
            elif si == 1:
                if len(st.ptcl_examples[typ]) < 3:
                    st.ptcl_examples[typ].append(os.path.relpath(path, roots[0]) if roots else path)
                if typ == 5:
                    s, e = cstr(blk, 0x50)
                    if e:
                        st.string_errors[f"ptcl.ModelPath:{e}"] += 1
                    elif s:
                        st.strings["ptcl.ModelPath"][path_kind(s)] += 1
                elif typ in PRIM_COMMON_TYPES:
                    for so, name in PTCL_STRINGS.items():
                        s, e = cstr(blk, so)
                        if e:
                            st.string_errors[f"ptcl.{name}[{PTCL[typ]}]:{e}"] += 1
                        elif s:
                            st.strings[f"ptcl.{name}"][path_kind(s)] += 1
                if typ == 6 and len(blk) >= 0x174:
                    st.prim_type[struct.unpack_from("<I", blk, 0x170)[0] & 0xF] += 1


def tname(slot, typ):
    if slot == "ptcl" and typ < len(PTCL):
        return f"{typ} {PTCL[typ]}"
    if slot == "move" and typ < len(MOVE):
        return f"{typ} {MOVE[typ]}"
    return str(typ)


def report(st):
    out = []
    p = out.append
    p(f"files: {st.files} unique ({st.dupes} duplicates skipped)")
    p("\nversions (folder breakdown):")
    for v, c in st.versions.most_common():
        dirs = ", ".join(f"{d} {n}" for d, n in st.version_dirs[v].most_common(6))
        p(f"  {v}: {c}   [{dirs}{', ...' if len(st.version_dirs[v]) > 6 else ''}]")
    p(f"\n--- DX9 ({hex(DX9_VERSION)}) only below ---")
    p(f"mBaseFPS: {dict(st.fps)}   header+0x1C: {dict(st.unk_1c.most_common(5))}")
    p(f"unit records (header 0x10/0x14) non-zero: {dict(st.unit_records)}")
    p(f"contentSize != filesize-0x20: {st.size_mismatch}")
    rpf = sorted(st.records_per_file.elements())
    if rpf:
        p(f"records/file: min {rpf[0]}, median {rpf[len(rpf)//2]}, max {rpf[-1]}, total {sum(rpf)}")
    p(f"absent slots: {dict(st.absent)}")
    for s in SLOTS:
        p(f"\nslot {s} type bytes:")
        for typ, c in sorted(st.type_hist[s].items()):
            lens = st.block_len.get((s, typ), [])
            rng = f"len {min(lens):#x}..{max(lens):#x}" if lens else ""
            und = st.undersized.get((s, typ))
            p(f"  {tname(s, typ):<22} {c:>6}   {rng}{'   UNDERSIZED x%d' % und if und else ''}")
    p("\nblocks referenced by >1 record (same slot): " + str(dict(st.shared_same_slot)))
    p(f"offsets shared across slots: {st.shared_cross_slot}")
    p("\ntop (particle, move) combos:")
    for (a, b), c in st.combo.most_common(15):
        p(f"  {str(a):<18} {str(b):<14} {c}")
    p("\nPrimModelType (PrimFlags & 0xF): " + str(dict(sorted(st.prim_type.items()))))
    p("\nstring fields (folder histogram; +EXT? = name has a dot, unexpected):")
    for k in sorted(st.strings):
        p(f"  {k:<26} {dict(st.strings[k].most_common(8))}")
    if st.string_errors:
        p("string field errors: " + str(dict(st.string_errors.most_common(12))))
    if st.errors:
        p("\nerrors:")
        for k, c in st.errors.most_common():
            p(f"  {k}: {c}  e.g. {st.error_examples[k][0]}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("roots", nargs="*", default=[r"E:\DMC mod stuffs"])
    ap.add_argument("--json")
    a = ap.parse_args()
    st = Stats()
    seen = set()
    for root in a.roots:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if not fn.lower().endswith(".efl"):
                    continue
                path = os.path.join(dp, fn)
                with open(path, "rb") as f:
                    data = f.read()
                h = hashlib.sha1(data).digest()
                if h in seen:
                    st.dupes += 1
                    continue
                seen.add(h)
                st.files += 1
                try:
                    analyse(path, data, st, a.roots)
                except Exception as e:  # keep going; report
                    st.err(f"exception {type(e).__name__}: {e}", path)
    print(report(st))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({
                "versions": st.versions, "type_hist": {s: dict(c) for s, c in st.type_hist.items()},
                "block_len": {f"{s}:{t}": [min(v), max(v), len(v)] for (s, t), v in st.block_len.items()},
                "combo": {f"{a}|{b}": c for (a, b), c in st.combo.items()},
                "ptcl_examples": {PTCL[t] if t < len(PTCL) else t: v for t, v in st.ptcl_examples.items()},
                "errors": {k: [c, st.error_examples[k]] for k, c in st.errors.items()},
            }, f, indent=1, default=str)


if __name__ == "__main__":
    sys.exit(main())
