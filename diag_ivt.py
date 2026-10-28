import idc, ida_segment, ida_bytes, ida_funcs, idautils

def is_code(ea):
    s = ida_segment.getseg(ea)
    return s is not None and s.type == 2

def find_init(fea):
    ea, seen = fea, False
    for _ in range(60):
        if ea == idc.BADADDR: break
        m = idc.print_insn_mnem(ea)
        if not m: break
        if m == 'call':
            c = idc.get_operand_value(ea, 0)
            direct = c and c != idc.BADADDR and is_code(c)
            if not seen:
                seen = True
            elif direct:
                return c
        ea = idc.next_head(ea)
    return None

def find_ivt(iea):
    fn = ida_funcs.get_func(iea)
    st = fn.start_ea if fn else iea
    lv = None
    ea = st
    while ea < st + 0x2000 and ea != idc.BADADDR:
        if idc.print_insn_mnem(ea) == 'mov':
            t0 = idc.get_operand_type(ea, 0)
            t1 = idc.get_operand_type(ea, 1)
            v1 = idc.get_operand_value(ea, 1)
            if t0 == 3 and t1 in (2, 5) and v1 and v1 != idc.BADADDR:
                sg = ida_segment.getseg(v1)
                if sg and sg.type != 2:
                    f = ida_bytes.get_wide_dword(v1)
                    if f and is_code(f): lv = v1
        ea = idc.next_head(ea)
    return lv

items = [(n, ea) for ea, n in idautils.Names()
         if n.startswith('MtDTI_') and not n.startswith('MtDTI_vt_')]

print(f"Total MtDTI_ labels: {len(items)}")

nv = nd = ni = no = ok = 0
e_ni, e_no = [], []

for nm, dea in items[:300]:
    vea = idc.get_name_ea_simple(nm.replace('MtDTI_', 'MtDTI_vt_', 1))
    if vea == idc.BADADDR:
        nv += 1; continue
    dr = ida_bytes.get_wide_dword(vea + 4)
    if not dr or not is_code(dr):
        nd += 1; continue
    inf = find_init(dr)
    if not inf:
        ni += 1
        if len(e_ni) < 8: e_ni.append((nm, hex(dr)))
        continue
    ivt = find_ivt(inf)
    if not ivt:
        no += 1
        if len(e_no) < 8: e_no.append((nm, hex(inf)))
        continue
    ok += 1

print(f"\nok={ok}  no_vt_label={nv}  no_dtor={nd}  no_init_fn={ni}  no_ivt={no}")

print("\n--- no_init_fn: factory found but push eax+call not detected ---")
for nm, dr in e_ni:
    # Show first 6 instructions of the factory
    ea = idc.get_name_ea_simple(nm.replace('MtDTI_', 'MtDTI_vt_', 1))
    dr_addr = ida_bytes.get_wide_dword(ea + 4)
    insns = []
    a = dr_addr
    for _ in range(8):
        if a == idc.BADADDR: break
        insns.append(f"{idc.print_insn_mnem(a)} {idc.print_operand(a,0)}")
        a = idc.next_head(a)
    print(f"  {nm}  factory={dr}  -> {' | '.join(insns)}")

print("\n--- no_ivt: init found but no vtable write detected ---")
for nm, inf in e_no:
    ea = idc.get_name_ea_simple(inf)
    insns = []
    a = ea if ea != idc.BADADDR else int(inf, 16)
    for _ in range(6):
        if a == idc.BADADDR: break
        insns.append(f"{idc.print_insn_mnem(a)} {idc.print_operand(a,0)}")
        a = idc.next_head(a)
    print(f"  {nm}  init={inf}  -> {' | '.join(insns)}")
