"""
label_dti_vtables.py — Auto-labels all MtDTI objects, DTI vftables, ctors/dtors,
and instance vtables in Devil May Cry 4 (DevilMayCry4_DX9.exe).

Registration pattern — each class has one small (~0x37-byte) initialiser:
  push 0                    ; flags (a5)
  push <size>               ; class size (a4)
  mov edi, <parent_dti>     ; parent DTI or 0 (a2)
  mov eax, <name_str>       ; class name string (a1)
  mov esi, <dti_base>       ; DTI global address (a3)
  call sub_8B69B0           ; register DTI
  mov [<dti_base>], <vftbl> ; write class-specific vftable into DTI[+0]
  push <cleanup>
  call atexit

Class vftable layout (the off_XXXXX stored at DTI[+0]):
  +0 : ctor    — simple constructor (sets MtObject vtable, registers w/ allocator)
  +4 : factory — allocates + fully inits the object (4000+ insns for large classes)
  ... more virtual functions ...
"""

import idc, idautils, ida_funcs, ida_bytes, ida_name, ida_segment

# ── config ────────────────────────────────────────────────────────────────────
DTI_REG_FUNC  = 0x8B69B0   # DTI registration function
RENAME_FLAGS  = ida_name.SN_NOWARN | ida_name.SN_NOCHECK
SCAN_BACK     = 40
SCAN_FORWARD  = 15

# ── helpers ───────────────────────────────────────────────────────────────────
def seg_type(ea):
    s = ida_segment.getseg(ea)
    return s.type if s else -1

def is_code(ea):
    return seg_type(ea) == 2   # SEG_CODE = 2

def is_data(ea):
    return seg_type(ea) in (3, 4)   # SEG_DATA=3, SEG_BSS=4

def read_dword(ea):
    return ida_bytes.get_wide_dword(ea)

def ida_auto_name(ea):
    """Return True if the current name is auto-generated (sub_/off_/dword_/etc.)."""
    n = idc.get_name(ea)
    if not n:
        return True
    prefixes = ('sub_', 'off_', 'dword_', 'word_', 'byte_', 'qword_', 'unk_',
                'loc_', 'flt_', 'dbl_', 'asc_', 'stru_')
    return any(n.startswith(p) for p in prefixes)

def try_label(ea, name):
    if ea and ea != idc.BADADDR and ida_auto_name(ea):
        idc.set_name(ea, name, RENAME_FLAGS)
        return True
    return False

def get_cstr(ea):
    b = idc.get_strlit_contents(ea, -1, idc.STRTYPE_C)
    if b:
        try:    return b.decode('ascii')
        except: return b.decode('latin-1', errors='replace')
    return None

def safe_name(s):
    """Convert 'sMediator::cFoo' to 'sMediator__cFoo' for IDA compatibility."""
    out = []
    for c in s:
        if c.isalnum() or c == '_':
            out.append(c)
        elif c == ':':
            if out and out[-1] != '_':
                out.append('_')
        else:
            out.append('_')
    return ''.join(out).strip('_')

# ── phase 1: find all DTI registrations ──────────────────────────────────────
dti_map = {}   # dti_base_ea -> dict
skipped = []

for call_ea in idautils.CodeRefsTo(DTI_REG_FUNC, 1):
    fn = ida_funcs.get_func(call_ea)
    if not fn:
        skipped.append(f"0x{call_ea:x}: not in a function")
        continue

    eax_val = None   # class name string addr
    esi_val = None   # DTI object base addr

    ea = call_ea
    for _ in range(SCAN_BACK):
        ea = idc.prev_head(ea)
        if ea == idc.BADADDR or ea < fn.start_ea:
            break
        if idc.print_insn_mnem(ea) != 'mov':
            continue
        dst  = idc.print_operand(ea, 0)
        styp = idc.get_operand_type(ea, 1)
        sval = idc.get_operand_value(ea, 1)
        if not sval or sval == idc.BADADDR:
            continue
        if dst == 'eax' and styp in (2, 5):
            eax_val = sval
        elif dst == 'esi' and styp in (2, 5):
            esi_val = sval
        if eax_val and esi_val:
            break

    if not eax_val or not esi_val:
        skipped.append(f"0x{call_ea:x}: could not extract eax/esi")
        continue

    class_name = get_cstr(eax_val)
    if not class_name:
        skipped.append(f"0x{call_ea:x}: eax=0x{eax_val:x} is not a string")
        continue

    # find post-call: mov [esi_val], offset <vftable>
    vftable_ea = None
    ea2 = call_ea
    for _ in range(SCAN_FORWARD):
        ea2 = idc.next_head(ea2)
        if ea2 == idc.BADADDR:
            break
        if idc.print_insn_mnem(ea2) != 'mov':
            continue
        op0t = idc.get_operand_type(ea2, 0)
        op0v = idc.get_operand_value(ea2, 0)
        op1t = idc.get_operand_type(ea2, 1)
        op1v = idc.get_operand_value(ea2, 1)
        if op0t == 2 and op0v == esi_val and op1t in (2, 5) and op1v and op1v != idc.BADADDR:
            vftable_ea = op1v
            break

    if not vftable_ea:
        skipped.append(f"0x{call_ea:x} ({class_name}): post-call vftable write not found")
        continue

    ctor_ea = read_dword(vftable_ea)
    dtor_ea = read_dword(vftable_ea + 4)

    dti_map[esi_val] = {
        'name':    class_name,
        'call_ea': call_ea,
        'vftable': vftable_ea,
        'ctor':    ctor_ea,
        'dtor':    dtor_ea,
    }

print(f"Phase 1: found {len(dti_map)} DTI registrations  ({len(skipped)} skipped)")

# ── phase 2: label DTI objects, DTI vftables, ctors, dtors ───────────────────
n_dti = n_vft = n_ctor = n_dtor = 0

for dti_ea, info in sorted(dti_map.items()):
    n   = info['name']
    s   = safe_name(n)
    vft = info['vftable']
    c   = info['ctor']
    d   = info['dtor']

    if try_label(dti_ea, f"MtDTI_{s}"):              n_dti  += 1
    if try_label(vft,    f"MtDTI_vt_{s}"):            n_vft  += 1
    if c and is_code(c) and try_label(c, f"{s}__ctor"): n_ctor += 1
    if d and is_code(d) and try_label(d, f"{s}__dtor"): n_dtor += 1

print(f"Phase 2: DTI={n_dti}  vftable={n_vft}  ctor={n_ctor}  dtor={n_dtor}")

# ── phase 3: instance vtable labeling ─────────────────────────────────────────
# The factory (dtor slot) allocates N bytes then calls the real init function.
# The real init sets the instance vtable as its last `mov [reg+0], offset DATA`
# assignment where DATA[0] is a code pointer.
#
# Factory pattern:
#   push 10h          ; alignment
#   push <size>       ; class size
#   call <allocator>  ; returns allocated ptr in eax
#   ...
#   push eax          ; pass ptr to init
#   call <init_fn>    ; real constructor
#
# We identify <init_fn> as the first CALL whose preceding sibling is PUSH EAX.

def find_init_fn(factory_ea):
    # Three factory patterns observed in DMC4:
    #   A) direct alloc:   push <size> / call <malloc> → push eax / call <init>
    #   B) indirect alloc: call edx (vtable dispatch)  → mov esi,eax / call <init>
    #   C) tail-call:      call edx (alloc) → mov [eax], vtable → jmp <init>
    #
    # Rule: first call = allocator; next direct call OR direct jmp = init.
    ea = factory_ea
    seen_alloc = False
    for _ in range(60):
        if ea == idc.BADADDR:
            break
        m = idc.print_insn_mnem(ea)
        if not m:
            break
        if m == 'call':
            callee = idc.get_operand_value(ea, 0)
            direct = callee and callee != idc.BADADDR and is_code(callee)
            if not seen_alloc:
                seen_alloc = True
            elif direct:
                return callee
        elif m == 'jmp' and seen_alloc:
            callee = idc.get_operand_value(ea, 0)
            if callee and callee != idc.BADADDR and is_code(callee):
                return callee
        ea = idc.next_head(ea)
    return None

def find_instance_vtable(start_ea):
    # Scan up to 500 instructions from start_ea; take the LAST data-segment
    # write to [reg+0] whose pointed DWORD is a code pointer.
    # 500 insns covers any vtable setup regardless of inheritance depth.
    fn = ida_funcs.get_func(start_ea)
    ea = fn.start_ea if fn else start_ea
    last_vt = None
    for _ in range(500):
        if ea == idc.BADADDR:
            break
        if idc.print_insn_mnem(ea) == 'mov':
            op0t = idc.get_operand_type(ea, 0)
            op1t = idc.get_operand_type(ea, 1)
            op1v = idc.get_operand_value(ea, 1)
            # [reg] only — sub-object vtable writes use [reg+disp] and are filtered out
            if op0t == 3 and op1t in (2, 5) and op1v and op1v != idc.BADADDR:
                seg = ida_segment.getseg(op1v)
                if seg and seg.type != 2:
                    first = read_dword(op1v)
                    if first and is_code(first):
                        last_vt = op1v
        ea = idc.next_head(ea)
    return last_vt

n_ivt = 0
for dti_ea, info in sorted(dti_map.items()):
    d = info['dtor']
    if not d or not is_code(d):
        continue
    init_fn = find_init_fn(d)
    # Try init function first; fall back to scanning the factory itself
    # (covers inline-init classes where no separate ctor is called)
    ivt = find_instance_vtable(init_fn) if init_fn else None
    if not ivt:
        ivt = find_instance_vtable(d)
    if ivt:
        s = safe_name(info['name'])
        if try_label(ivt, f"vtable_{s}"):
            n_ivt += 1
        info['instance_vtable'] = ivt
        info['init_fn']         = init_fn

print(f"Phase 3: instance vtable labels applied: {n_ivt}")

# ── summary ───────────────────────────────────────────────────────────────────
print("\n=== DTI Summary ===")
for dti_ea, info in sorted(dti_map.items(), key=lambda x: x[1]['name']):
    ivt = hex(info['instance_vtable']) if info.get('instance_vtable') else '—'
    print(f"  {info['name']:<42} DTI={hex(dti_ea):<12} "
          f"vt={hex(info['vftable']):<12} ivt={ivt}")

if skipped:
    print(f"\n=== Skipped {len(skipped)} ===")
    for s in skipped[:30]:
        print(f"  {s}")
    if len(skipped) > 30:
        print(f"  ... and {len(skipped) - 30} more")
