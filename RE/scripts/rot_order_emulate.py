"""Run the DX9 MtMatrix::setRotate* functions under Unicorn and compare them with Blender's Euler orders."""
import base64, json, math, struct
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_XMM0, UC_X86_REG_EIP

D = json.load(open(__file__.replace("rot_order_emulate.py", "rot_dump.json")))
SIN, COS = int(D["sin"], 16), int(D["cos"], 16)
STACK, DATA, RET = 0x00100000, 0x00200000, 0x00300000


def run(func, angles):
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    for page, blob in D["pages"].items():
        mu.mem_map(int(page, 16), 0x1000)
        mu.mem_write(int(page, 16), base64.b64decode(blob))
    for base in (STACK, DATA, RET):
        mu.mem_map(base, 0x10000)
    for stub in (SIN & ~0xFFF, COS & ~0xFFF):
        try:
            mu.mem_map(stub, 0x1000)
        except Exception:
            pass
    mu.mem_write(DATA, struct.pack("<3f", *angles))
    esp = STACK + 0x8000
    mu.mem_write(esp, struct.pack("<I", RET))
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.reg_write(UC_X86_REG_EDI, DATA)
    mu.reg_write(UC_X86_REG_ESI, DATA + 0x100)

    def hook(uc, address, size, _):
        if address in (SIN, COS):
            x = struct.unpack("<d", struct.pack("<Q", uc.reg_read(UC_X86_REG_XMM0) & (2 ** 64 - 1)))[0]
            y = math.sin(x) if address == SIN else math.cos(x)
            uc.reg_write(UC_X86_REG_XMM0, struct.unpack("<Q", struct.pack("<d", y))[0])
            sp = uc.reg_read(UC_X86_REG_ESP)
            ret = struct.unpack("<I", uc.mem_read(sp, 4))[0]
            uc.reg_write(UC_X86_REG_ESP, sp + 4)
            uc.reg_write(UC_X86_REG_EIP, ret)
        elif address == RET:
            uc.emu_stop()

    mu.hook_add(UC_HOOK_CODE, hook)
    mu.emu_start(func, RET, count=200000)
    m = struct.unpack("<16f", mu.mem_read(DATA + 0x100, 64))
    return [list(m[0:3]), list(m[4:7]), list(m[8:11])]   # rows; row-vector convention v' = v . M


def rot(axis, t):
    c, s = math.cos(t), math.sin(t)
    return {"X": [[1, 0, 0], [0, c, -s], [0, s, c]], "Y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "Z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def blender(angles, order):   # Blender Euler(angles, order).to_matrix(): axes applied in string order
    r = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    for axis in order:
        r = mul(rot(axis, angles["XYZ".index(axis)]), r)
    return r


ORDERS = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
for enum, name in enumerate(("ZYX", "ZXY", "YZX", "YXZ", "XZY", "XYZ")):   # setMatFromAngle cases 0-5
    func = int(D["funcs"]["MtMatrix::setRotate" + name][0], 16)
    errs = {}
    for angles in ((0.3, -0.7, 1.1), (-1.2, 0.4, 2.5)):
        game = run(func, angles)
        col = [list(r) for r in zip(*game)]   # transpose: column-vector matrix
        for order in ORDERS:
            b = blender(angles, order)
            errs[order] = max(errs.get(order, 0.0), max(abs(col[i][j] - b[i][j]) for i in range(3) for j in range(3)))
    best = min(errs, key=errs.get)
    print(f"RotOrder {enum} setRotate{name}: Blender '{best}' (max error {errs[best]:.1e}; next {sorted(errs.values())[1]:.2f})")

# end to end: the preview's sim.rotate (v' = rotate(v)) against the game's v . M
import sys
sys.path.insert(0, r"E:\DMC mod stuffs\blender_addon\addons\albam\engines\mtfw")
from efl import sim
worst = 0.0
for enum, name in enumerate(sim.ROT_ORDER_NAMES):
    func = int(D["funcs"]["MtMatrix::setRotate" + name][0], 16)
    for angles in ((0.3, -0.7, 1.1), (-1.2, 0.4, 2.5), (2.0, 1.0, -0.5)):
        game = run(func, angles)
        for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0.3, -0.5, 0.8)):
            want = [sum(v[k] * game[k][j] for k in range(3)) for j in range(3)]
            got = sim.rotate(v, angles, enum)
            worst = max(worst, max(abs(a - b) for a, b in zip(want, got)))
print(f"sim.rotate vs game v . M, all 6 orders: max error {worst:.1e}")
