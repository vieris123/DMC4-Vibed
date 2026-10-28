"""
phase3_ivt.py — Label instance vtables for all already-discovered MT classes.

Reads MtDTI_vt_* labels → factory → init function → instance vtable write.

find_instance_vtable uses a byte-level scan for the x86 pattern
  C7 (00|01|02|03|06|07) imm32   =  mov [reg], imm32
instead of per-instruction IDA API calls, making it ~100x faster.
"""
import idc, idautils, ida_funcs, ida_bytes, ida_name, ida_segment

RENAME_FLAGS = ida_name.SN_NOWARN | ida_name.SN_NOCHECK

def is_code(ea):
    s = ida_segment.getseg(ea)
    return s is not None and s.type == 2

def read_dword(ea):
    return ida_bytes.get_wide_dword(ea)

def ida_auto_name(ea):
    n = idc.get_name(ea)
    if not n:
        return True
    prefixes = ('sub_', 'off_', 'dword_', 'word_', 'byte_', 'qword_', 'unk_',
                'loc_', 'flt_', 'dbl_', 'asc_', 'stru_', 'vtable_')
    return any(n.startswith(p) for p in prefixes)

def try_label(ea, name):
    if ea and ea != idc.BADADDR and ida_auto_name(ea):
        idc.set_name(ea, name, RENAME_FLAGS)
        return True
    return False

def find_init_fn(factory_ea):
    """First call=allocator; next direct call or direct jmp = init function."""
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
            if not seen_alloc:
                seen_alloc = True
            elif callee and callee != idc.BADADDR and is_code(callee):
                return callee
        elif m == 'jmp' and seen_alloc:
            callee = idc.get_operand_value(ea, 0)
            if callee and callee != idc.BADADDR and is_code(callee):
                return callee
        ea = idc.next_head(ea)
    return None

# ModRM bytes for mod=00 r/m in {eax,ecx,edx,ebx,esi,edi} — no displacement
_VT_MODRM = frozenset([0x00, 0x01, 0x02, 0x03, 0x06, 0x07])

def find_instance_vtable(start_ea):
    """Byte-scan first 0x500 bytes for mov [reg], imm32 that looks like a vtable ptr."""
    fn = ida_funcs.get_func(start_ea)
    ea = fn.start_ea if fn else start_ea
    raw = ida_bytes.get_bytes(ea, 0x500)
    if not raw:
        return None
    last_vt = None
    i = 0
    end = len(raw) - 5
    while i < end:
        if raw[i] == 0xC7 and raw[i + 1] in _VT_MODRM:
            imm = int.from_bytes(raw[i + 2 : i + 6], 'little')
            if imm and imm != 0xFFFFFFFF:
                seg = ida_segment.getseg(imm)
                if seg and seg.type != 2:
                    first = read_dword(imm)
                    if first and is_code(first):
                        last_vt = imm
        i += 1
    return last_vt

n_ivt = 0
n_no_factory = 0
n_no_ivt = 0

# Only singleton classes (s-prefix, sCamelCase) have global instances worth labeling.
# 'MtDTI_vt_' is 9 chars, then class name starts; filter for sUpper pattern.
vt_items = [(n, ea) for ea, n in idautils.Names()
            if n.startswith('MtDTI_vt_s') and len(n) > 10 and n[10].isupper()]
print(f"Processing {len(vt_items)} singleton DTI vftables...")

for vt_name, vt_ea in vt_items:
    class_s = vt_name[len('MtDTI_vt_'):]
    factory_ea = read_dword(vt_ea + 4)
    if not factory_ea or not is_code(factory_ea):
        n_no_factory += 1
        continue

    init_fn = find_init_fn(factory_ea)
    ivt = find_instance_vtable(init_fn) if init_fn else None
    if not ivt:
        ivt = find_instance_vtable(factory_ea)

    if ivt:
        if try_label(ivt, f"vtable_{class_s}"):
            n_ivt += 1
    else:
        n_no_ivt += 1

print(f"Done: labeled={n_ivt}  no_factory={n_no_factory}  no_ivt={n_no_ivt}")
