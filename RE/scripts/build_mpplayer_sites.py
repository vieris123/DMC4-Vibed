"""
build_mpplayer_sites.py  --  Enumerate every mpPlayer (sMediator+0x24) reference in
DevilMayCry4_DX9.exe and emit an authoritative per-call-site JSON for the multiplayer
dispatcher patch (see RE/mpplayer_dispatcher_patch_plan.md).

Run inside IDA via the ida-pro-mcp `py_exec_file` tool (shared-globals scope; do NOT use
py_eval -- nested-function name lookups fail under its split globals/locals).

Regenerate after ANY database change that defines/retypes functions -- the output is keyed
to live instruction addresses and function prototypes and goes stale otherwise.

Output: RE/mpplayer_call_sites.json  (schema documented in that file's schema_note and in
        RE/mpplayer_dispatcher_patch_plan.md).

Design notes / gotchas learned this session:
  * `this` is NOT uniformly ecx. ~65% of sites pass `this` in eax/esi/edi/edx or on the
    stack (__usercall/__stdcall/__userpurge). We resolve it from the function prototype,
    falling back to a Hex-Rays decompile for untyped functions.
  * func_type_data_t exposes the CC via .get_cc() in IDA 9.3 and .get_explicit_cc() in
    IDA 9.2 (neither has a .cc attribute); _this_from_tif handles both. Argless prototypes
    such as `uPlayer *()` report cc "unknown".
  * FP-return functions misreport arg0 as an FP/return slot (st0/xmm0); we skip to the
    first GP-register (or stack) argument for those.
  * The deref is matched by OPERAND, not disassembly text: the [reg+24h] base register must
    still hold the loaded pointer (followed through in-function jmps, <= SCAN_WINDOW insns).
    The old "+24h" text match over a 6-insn window (2026-10 baseline, 1048 sites) recorded 16
    non-player reads ([esp+24h+var] stack slots, [vtbl+24h] calls, getPlayerMat's returned
    matrix +24h, camera +24h writes), one wrong deref (0x51BAC1), and missed 92 real sites.
  * The site instruction (the mpInstance load) is 5 bytes only for mov eax (opcode A1) and
    6 bytes for every other dest register, ecx included (8B /r + disp32) -- both >= 5 so a
    jmp rel32 fits.
"""
import idc, ida_nalt, ida_typeinf, idaapi, ida_idp, ida_hexrays, idautils, ida_funcs, ida_name
import json, re, os

# ---- targets ---------------------------------------------------------------
MPINST = 0xE558B8          # sMediator::mpInstance (global singleton pointer)
PLAYER_OFF = 0x24          # sMediator::mpPlayer field offset
GPP, GPM = 0x493240, 0x493350   # sMediator::getPlayerPos / getPlayerMat
# the .i64 sits at the workspace root, next to RE/
OUT_PATH = os.path.join(os.path.dirname(idc.get_idb_path()), "RE", "mpplayer_call_sites.json")
SCAN_WINDOW = 40           # insns to look ahead from the mpInstance load for a [reg+24h] deref

# ---- category maps (function start EA -> category), from session analysis ----
# CAMERA = the 15 functions deep-dived in the 2026-07 session ([MP/camera] comments). Every other
# function owned by a camera class (qualifier or vtable class containing "cam", e.g. cCameraPlayer,
# uCameraBoss*, cCameraRail*, uCameraCtrl) is camera-per-player too — see is_camera_class().
CAMERA = {0x417390,0x417690,0x418770,0x4188E0,0x419110,0x419130,0x419840,0x41F120,
          0x4223B0,0x422AC0,0x4255B0,0x4F7C50,0x4F90B0,0x4F9D50,0x532430}
NERO_GRAB = {0x603950,0x6037D0,0x614DF0,0x614EE0,0x5E9080,0x640540,0x640F00,0x678D00,0x720DA0,0x72EA50}
DAMAGE = {0x51BE10,0x51BAB0,0x7345B0,0x7346B0,0x726B00,0x5CBF50,0x5D90B0,0x6E4390,
          0x6B5AE0,0x864AF0,0x8701F0,0x886A90,0x891B40}
DAMAGE_REVIEW = {0x50CC40,0x735FB0}   # aggro/lock-on reads, not pure message-sender

def is_camera_class(fn, cls):
    # names come from the 2026-10-14 SE->DX9 camera pass (RE/cam_se_dx9_map.md)
    nm = idc.get_func_name(fn)
    qual = nm.rsplit("::", 1)[0] if "::" in nm else ""
    return "cam" in qual.lower() or "cam" in (cls or "").lower()

def category(fn, cls=None):
    if fn in DAMAGE: return "damage-message-derivable"
    if fn in DAMAGE_REVIEW: return "damage-review-aggro"
    if fn in CAMERA or is_camera_class(fn, cls): return "camera-per-player"
    if fn in NERO_GRAB: return "nero-grab"
    return "uncategorized"

# ---- helpers ---------------------------------------------------------------
def regname(r):
    return ida_idp.get_reg_name(r, 4) or ("r%d" % r)

_CC = {ida_typeinf.CM_CC_THISCALL:"thiscall", ida_typeinf.CM_CC_FASTCALL:"fastcall",
       ida_typeinf.CM_CC_STDCALL:"stdcall", ida_typeinf.CM_CC_CDECL:"cdecl",
       ida_typeinf.CM_CC_ELLIPSIS:"cdecl_va", ida_typeinf.CM_CC_SPECIAL:"usercall",
       ida_typeinf.CM_CC_SPECIALP:"userpurge", ida_typeinf.CM_CC_SPECIALE:"usercall_e",
       ida_typeinf.CM_CC_VOIDARG:"voidarg", ida_typeinf.CM_CC_UNKNOWN:"unknown",
       ida_typeinf.CM_CC_INVALID:"invalid"}
def cc_name(cc): return _CC.get(cc, "cc_%X" % cc)

_GP = {"eax","ecx","edx","ebx","esi","edi","ebp"}

def _this_from_tif(tif):
    fi = ida_typeinf.func_type_data_t()
    if not tif.get_func_details(fi):
        return None
    cc = (fi.get_cc() if hasattr(fi, "get_cc") else fi.get_explicit_cc()) & ida_typeinf.CM_CC_MASK
    out = {"cc": cc_name(cc), "this_reg": None, "arg0": None}
    # first GP-register or stack argument = this (skip FP/return slots)
    for i in range(fi.size()):
        loc = fi[i].argloc
        if loc.is_reg1():
            rn = regname(loc.reg1())
            if rn in _GP:
                out["this_reg"] = rn; out["arg0"] = fi[i].name or None; break
        elif loc.is_stkoff():
            out["this_reg"] = "stack"; out["arg0"] = fi[i].name or None; break
    return out

def func_this(ea):
    tif = ida_typeinf.tinfo_t()
    if ida_nalt.get_tinfo(tif, ea) or idaapi.guess_tinfo(tif, ea):
        r = _this_from_tif(tif) if tif.is_func() else None
        if r and (r["this_reg"] is not None) and r["cc"] not in ("voidarg","unknown","invalid"):
            return r
    # fall back to Hex-Rays for untyped / voidarg functions
    try:
        cf = ida_hexrays.decompile(ea)
    except Exception:
        cf = None
    if cf:
        r2 = _this_from_tif(cf.type)
        if r2: return r2
    return {"cc": None, "this_reg": None, "arg0": None}

_VFT_RE = re.compile(r'^(.*?)::(?:vftable|vtable|DTI|`vftable)')
def func_class(fea):
    nm = idc.get_func_name(fea)
    if "::" in nm:
        return nm.split("::")[0], "name"
    classes = set()
    for x in idautils.XrefsTo(fea):
        if ida_funcs.get_func(x.frm) is not None:
            continue                                   # code ref -> not a vtable slot
        a = x.frm
        for _ in range(256):                            # walk back to the vtable label
            lbl = ida_name.get_name(a)
            if lbl:
                m = _VFT_RE.match(lbl)
                if m: classes.add(m.group(1))
                break
            a -= 4
    if len(classes) == 1: return next(iter(classes)), "vtable"
    if len(classes) > 1:  return "|".join(sorted(classes)), "vtable-multi"
    return None, None

# ---- pass 1: inline reads ([mpInstance] load then [reg+24h] deref within window) ----
# Operand-based: the deref's base register must still hold the loaded mpInstance pointer
# (tracked through reg-reg copies, dropped on clobber). Text matching on "+24h" produced
# false positives on [esp+24h+var] stack slots, vtable slot +24h calls, and other objects.
import ida_ua

def _insn(ea):
    i = ida_ua.insn_t()
    return i if ida_ua.decode_insn(i, ea) else None

def _clobbers(i):
    m = i.get_canon_mnem(); out = set()
    if m == "call": out |= {"eax", "ecx", "edx"}
    if m == "cdq": out.add("edx")
    if m in ("mul", "div", "imul", "idiv") and i.ops[1].type == ida_ua.o_void: out |= {"eax", "edx"}
    if m == "xchg":
        for k in range(2):
            if i.ops[k].type == ida_ua.o_reg: out.add(regname(i.ops[k].reg))
    o = i.ops[0]
    if o.type == ida_ua.o_reg and m not in ("push", "cmp", "test", "call", "jmp") and not m.startswith("j"):
        out.add(regname(o.reg))
    return out

def find_deref(ea, f):
    i = _insn(ea)
    if not i or i.get_canon_mnem() != "mov" or i.ops[0].type != ida_ua.o_reg:
        return None
    held = {regname(i.ops[0].reg)}
    cur = ea + i.size
    for _ in range(SCAN_WINDOW):
        if cur >= f.end_ea or not held:
            return None
        ci = _insn(cur)
        if ci is None:
            return None
        for op in ci.ops:
            if op.type == ida_ua.o_void:
                break
            if op.type in (ida_ua.o_displ, ida_ua.o_phrase) and op.addr == PLAYER_OFF and regname(op.reg) in held:
                return cur
        m = ci.get_canon_mnem()
        if m == "mov" and ci.ops[0].type == ida_ua.o_reg and ci.ops[1].type == ida_ua.o_reg and regname(ci.ops[1].reg) in held:
            held.add(regname(ci.ops[0].reg))
        else:
            held -= _clobbers(ci)
        if m == "retn":
            return None
        if m == "jmp":
            if ci.ops[0].type != ida_ua.o_near or not (f.start_ea <= ci.ops[0].addr < f.end_ea):
                return None
            cur = ci.ops[0].addr          # follow unconditional in-function jumps
        else:
            cur += ci.size
    return None

sites = []
for x in idautils.XrefsTo(MPINST):
    ea = x.frm
    f = ida_funcs.get_func(ea)
    if not f:
        continue
    deref_ea = find_deref(ea, f)
    if deref_ea is None:
        continue
    sites.append({
        "ea": "0x%X" % ea, "deref_ea": "0x%X" % deref_ea,
        "fn": "0x%X" % f.start_ea, "fn_name": idc.get_func_name(f.start_ea),
        "kind": "inline",
        "load_insn": idc.GetDisasm(ea), "deref_insn": idc.GetDisasm(deref_ea),
        "ea_len": idc.get_item_size(ea), "load_dst": idc.print_operand(ea, 0),
        "deref_len": idc.get_item_size(deref_ea), "deref_dst": idc.print_operand(deref_ea, 0),
    })

# ---- pass 2: accessor call sites ----
for tgt, tag in ((GPP, "getPlayerPos"), (GPM, "getPlayerMat")):
    for x in idautils.XrefsTo(tgt):
        if idc.print_insn_mnem(x.frm) not in ("call", "jmp"):
            continue
        f = ida_funcs.get_func(x.frm)
        fs = f.start_ea if f else None
        sites.append({
            "ea": "0x%X" % x.frm, "deref_ea": None,
            "fn": ("0x%X" % fs) if fs else None,
            "fn_name": idc.get_func_name(fs) if fs else "<none>",
            "kind": "accessor:" + tag,
            "load_insn": idc.GetDisasm(x.frm), "deref_insn": None,
            "ea_len": idc.get_item_size(x.frm), "load_dst": None,
        })

# ---- enrich: category + class + this-register (cache per function) ----
cache = {}
for s in sites:
    fn = s.get("fn")
    if fn is None:
        s.update(category="uncategorized", **{"class":None,"class_src":None,"this_reg":None,"cc":None,"arg0":None})
        continue
    if fn not in cache:
        fea = int(fn, 16)
        cls, src = func_class(fea)
        cache[fn] = {"category": category(fea, cls), "class": cls, "class_src": src, **func_this(fea)}
    c = cache[fn]
    s["category"] = c["category"]; s["class"] = c["class"]; s["class_src"] = c["class_src"]
    s["this_reg"] = c["this_reg"]; s["cc"] = c["cc"]; s["arg0"] = c["arg0"]

sites.sort(key=lambda s: int(s["ea"], 16))

from collections import Counter
doc = {
    "total": len(sites),
    "by_kind": dict(Counter(s["kind"].split(":")[0] for s in sites)),
    "by_category": dict(Counter(s["category"] for s in sites)),
    "this_reg_dist": dict(Counter(s["this_reg"] for s in sites)),
    "ea_len_dist": dict(Counter(s["ea_len"] for s in sites)),
    "schema_note": (
        "One entry per player-resolution call site. ea = site instruction (mpInstance load "
        "for inline, or the call for accessor). deref_ea/deref_insn/deref_len/deref_dst = the "
        "[reg+0x24] instruction (inline only). fn/fn_name/class/class_src = owning function & "
        "class (class via Class::method name or vtable membership; class_src name|vtable|"
        "vtable-multi|null). this_reg = register holding this/arg0 ('stack' or null if untyped); "
        "cc = calling convention; arg0 = first-arg name (per-function, repeated per site). "
        "category = camera-per-player|nero-grab|damage-message-derivable|damage-review-aggro|"
        "uncategorized. kind = inline|accessor:getPlayer{Pos,Mat}. ea_len = bytes of the site "
        "instruction (5=mov eax (A1) or call, 6=mov any other reg incl. ecx). load_dst = register "
        "receiving the mpInstance ptr. deref = first [load_dst+24h] operand reached from the load "
        "while the register still holds the pointer (operand-based, follows in-function jmp, "
        "<=40 insns). All addresses are absolute VAs, imagebase 0x400000; for dmc4_hook use "
        "install_hook_offset(ea - 0x400000, hook, detour, &jmp_ret, ea_len). "
        "Regenerate after any DB change (addresses are live)."),
    "sites": sites,
}
with open(OUT_PATH, "w") as fh:
    json.dump(doc, fh, indent=1)

print("wrote %s" % OUT_PATH)
print("total=%d  kind=%s  category=%s" % (doc["total"], doc["by_kind"], doc["by_category"]))
print("this_reg=%s" % doc["this_reg_dist"])
print("ea_len=%s" % doc["ea_len_dist"])
