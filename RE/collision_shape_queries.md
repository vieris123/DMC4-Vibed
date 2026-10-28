# Stage collision shape queries (sphere, capsule, box) — callable entry points

Build: **DX9** (`DevilMayCry4_DX9.exe`) unless a line says SE. SE names / signatures come from the SE PDB (IDB on port
13338). Researched 2026-10-26 for dmc4_hook inline-asm wrappers (the line cast is in `collision_lineCast.md`; the
.sbc channel / triangle rules in `sbc_dx9_format.md`). Confidence: **H** = read from disassembly (prologue, epilogue,
a real call site), **M** = decompiler + one caller, **L** = inferred.

All positions are game space (cm, Y up). `sDevil4Collision::mpInstance` is the pointer at **0xE559D0** (pass
`*(void**)0xE559D0`). `MtVector3` = 16 bytes (x, y, z, pad); outputs write x, y, z only.

## Summary

| Query | DX9 entry | Convention (callee / caller clean) | Returns | Conf. |
|---|---|---|---|---|
| Sphere overlap, nearest contact | `sub_94B480` | ecx=inst, eax=filter; stack (sphere*, outPos*, outPlane*, typeMask); `retn 10h` | contact class 0/1/2/4/8 | H |
| Sphere overlap (bool) | `sub_9564E0` | esi=Param*; stack (inst, sphere*); `retn 8` | al = touches | H |
| Sphere move + slide (sweep A->B) | `sub_956750` | eax=Param*; stack (inst, pos*, old*, sphere*); `retn 10h` | OR of 1/4/8, pos* = corrected | H |
| Sphere move + slide, camera variant | `sCollision::adjustPosition` 0x95CBE0 | stdcall (inst, pos*, old*, sphere*, Param*); `retn 14h` | OR of 1/4/8 | H |
| Capsule move + slide (actor vs stage) | `cUtil::checkScrCollision` 0x45F650 | eax=to*, ecx=from*, edi=out*; stack (capsule*, filter); plain `retn`, caller `add esp,8` | OR of 1/4/8, out written only on hit | H |
| Capsule move + slide, with Param | `sub_956C90` | eax=Param*; stack (inst, pos*, old*, capsule*); `retn 10h` | as above, pos* = corrected | H |
| Capsule overlap (bool) | `sub_94F230` | esi=capsule*; stack (inst, typeMask, groupLo, groupHi, callback*); `retn 14h` | al = any triangle touches | H (conv.), M (semantics) |
| Capsule push-out (depenetrate) | `sCollision::multi_obb_query` 0x94EF30 | ecx=refCapsule*, edx=inst; stack (capsule* in/out, ContactDefine*, filter, bothSides); `retn 10h` | nonzero if moved (contact class bits) | H (conv.), M (semantics) |
| Line, any hit (bool, early out) | `sub_94B660` | eax=filter, edi=inst; stack (MtLineSegment*, typeMask); `retn 8` | al | H |
| Triangles in an AABB (custom callback) | `pHitCallback` 0x94B7C0 (= `query_all_sbcs` thunk) | thiscall ecx=inst; stack (MtAABB*, callback*, ContactDefine*); `retn 0Ch` | OR of the narrow callback's returns | H (conv.), M (moving parts) |
| OBB | none | — | — | — |

There is **no first-hit sweep ("castConvex") and no AABB / OBB narrowphase in DX9** (SE added `sCollision::castConvex`
for sphere / capsule / MtAABB and `isIntersect` for sphere / segment / capsule). The DX9 sweeps are MT's
move-and-slide (`originalScrCollision`, SE `sCollision::adjustPosition`): they move a shape from `old` to `pos`,
slide along what they hit and return the corrected position. With `Param.correctionNum = 1` the slide loop stops at
the first contact (speed zeroed after one correction, `sub_958160` "`if (!--n) cspeed = 0`"), which gives "position
just before the first hit" (M, not tested in game).

Every register an entry uses as input (eax, ecx, edx, esi, edi) is either an input or saved by the callee except eax
/ ecx / edx (scratch). Wrap like `collision::find_intersection` (save esp, pushad / popad) and nothing can go wrong.

## Common inputs

### Shape geometry

| Type | Layout | Notes |
|---|---|---|
| `MtSphere` | +0 x, y, z (MtFloat3), +0xC r | 16 B. Read with `movq` + `fld [+0Ch]`. |
| `MtCapsule` | +0 p0 (MtVector3), +0x10 p1 (MtVector3), +0x20 r | 0x24 B read (dmc4_hook's 0x30 struct fits). |
| `MtLineSegment` | +0 p0, +0x10 p1 | |
| `MtAABB` | +0 min (MtVector3), +0x10 max (MtVector3) | |

- **Overlap queries** (`sub_94B480`, `sub_94F230`, `multi_obb_query`, `sub_94B660`) take **world** coordinates.
- **Slide queries** (`sub_956750`, `sub_956C90`, `checkScrCollision`, 0x95CBE0) take the shape **relative to the moving
  point**: the swept bounds are `cpos + sphere.pos ± r` / `cpos + p0, cpos + p1 ± r` (`sub_941120` / `sub_9415C0`,
  H), the narrowphases add `cpos` (+0x60) too. The camera passes sphere (0, 0, 0, r = 10); an actor passes its
  local push capsule.

### sCollision::Param (DX9, 0x40 B; dmc4_hook `collision::CollParam`)

Ctor `sCollision::Param` 0x414E50: `this@eax, type@ecx`, stack (filter, hitCallback, hitCallback_data,
correctionNum), `retn 10h` — sets type, filter, +0xC, +0x10, +0x18/+0x1C = -1, +0x24, +0x2C/+0x30 = FLT_MAX, bytes
+0x28 = 1, +0x2A = 1, everything else 0. `collision::line_param()` builds the same block.

| Off | Field | Read by the shape queries |
|---|---|---|
| +0x00 | type | **SBC type mask** -> `ContactDefine.type` (`Sbc.mType & type`). 127 = all. No fallback to `mDefaultType` in the slide core: 0 = nothing collides. |
| +0x04 | filter | **channel mask** -> `callback_struct_t.group_filter` (the wrappers copy it) |
| +0x08 / +0x0C / +0x10 | hitCallback_this / hitCallback / data | slide core calls `hitCallback(this, &SbcInfo, data)` per correction if non-null. Use 0. |
| +0x18 / +0x1C | "handle_exclude_0/1" | really the **64-bit Sbc group mask** (`ContactDefine` +8/+0xC, tested as `1 << Sbc.mGroup`). Use -1, -1. |
| +0x24 | correctionNum | slide iterations; 0 = unlimited. Game: 10. 1 = stop at first contact. |
| +0x2A | bAdjAntiStop (u8) | copied into the work packet (`queryParams.w`). Game: 1. |
| +0x2B | u8 | non-zero runs an extra SphereOBB / SphereCapsule pre-pass each iteration (`sub_958160`). Game: 0. |
| +0x38 | partsFilter | -> `ContactDefine.mPartsFilter` (see below). 0. |

### Channel filter (`callback_struct_t.group_filter`)

Tested per triangle in `checkAttr` 0x95F602: `q = filter & 0x3FFFFF00; if (tri.runtime_attr < 0) q ^= 0x3FFFFF00;
hit if q & runtime_attr & 0x3FFFFF00` (full rules in `sbc_dx9_format.md`). dmc4_hook names: 0x10100 DEFAULT,
0x20000 WALL, 0x80800 GROUND, 0x404000 CAMERA, 0x10000000 FALLSTOP, 0x20000000 CAMERASTOP. Seen with shapes:
0x10100 / 0x100 (sphere contact), 0x307F7F00 / 0x207F7F00 (enemy warp / dodge capsule), 0x80000 (capsule overlap),
0x20000000 (camera sphere, camera capsule push-out).

### SBC type mask (`ContactDefine.type`, typeMask args)

`Sbc.mType` = the 3rd argument of `sCollision::registResource` 0x946750: **1** = room / stage (`aRoom::setRoom`),
**2** = boss / special (uEm018 house, sub_88CAC0), **0x10** = stage-set gimmicks (uStageSetMoveFloor, Butou, Break,
em021 leaves, em030 ground), **0x40** = catapult. 127 covers all. Where a typeMask argument exists, 0 means
`inst->mDefaultType` (+0x2C).

### sCollision::ContactDefine (0x14)

| Off | Field | Value |
|---|---|---|
| +0x00 | mode | `ContactDefine::Default` (0xE14380, = 0). Camera passes 2 to `multi_obb_query` (meaning unknown, L). |
| +0x04 | type | SBC type mask |
| +0x08 / +0x0C | group mask lo / hi | -1, -1 |
| +0x10 | mPartsFilter | 0 = static tree + every moving part; 1 = no static tree, moving parts without flag +0x93; 2 = static tree + moving parts with flag +0x93 (`query_all_sbcs`, `check_moving_parts`) |

### sCollision::callback_struct_t (0x58), filled by `ScrCollisionBeforeFunc` 0x50DFB0

`ScrCollisionBeforeFunc(this@eax, func_narrow@ecx; stack func_bounds, func_store, ctx, group_filter, flags)`, `retn
14h`. Filling it by hand is equivalent:

| Off | Field |
|---|---|
| +0x00 | MtMatrix world_matrix = identity |
| +0x40 | func_narrow: `int __cdecl(SbcInfo* tri, void* ctx)`, called per triangle that passes the channel test; result OR'd |
| +0x44 | func_bounds: `void __cdecl(ReqPacket*, SbcInfo*, void* ctx)`, moving parts only (moves the query AABB into part space); may be 0 |
| +0x48 | func_store: `int __cdecl(SbcInfo*, void* ctx)`, once per static group leaf before its triangles; may be 0 |
| +0x4C | ctx (`mContactInfo`): the shape's work buffer; the overlap wrappers overwrite it |
| +0x50 | group_filter (channel mask) |
| +0x54 | u8 flags: slide core transforms contact normals by the part matrix when set. 0. |

### Return codes

- **Slide** (`sub_958160`, `originalScrCollisionCore` 0x95CF20): OR over corrections of: **1** floor (|n.y| >=
  `inst->mWallSin` +0x40 and n.y >= 0), **8** ceiling (n.y < 0, |n.y| >= wallSin), **4** wall. 0 = no contact.
- **Sphere contact** (`sub_94B4E0`): single value from the kept plane's n.y: **1** n.y > `mSlopeSin` (+0x3C),
  **2** n.y > `mWallSin`, **4** |n.y| < wallSin, **8** n.y <= -wallSin. 0 = no contact.

## 1. Sphere overlap / nearest contact — `sub_94B480` (H)

```
int __usercall sub_94B480@<eax>(sDevil4Collision* inst@<ecx>, uint filter@<eax>,
        MtSphere* sphere, MtVector3* outPos /*nullable*/, float outPlane[4] /*nullable*/, uint typeMask);   // retn 10h
```
- Builds callback (`collNarrow_SphereA` 0x9496A0, `collBounds_Sphere`, `collStore_Qword2`, filter), returns 0 if no
  SBC is loaded (`count_unique_resources`), then `sub_94B4E0` queries the box `center ± r` (ContactDefine
  {Default, typeMask or mDefaultType, -1, -1, 0}).
- Narrow: plane of each triangle; rejects |signed distance| > r, then keeps the triangle whose |plane distance| is
  smallest **among those whose closest point is within r** (squared distance - r² <= 1e-8). Overlap test, not a
  sweep.
- `outPos` = closest point on the kept triangle, transformed by the part matrix (world). `outPlane` = that
  triangle's plane (nx, ny, nz, d) in **SBC-local** space (static stage parts: = world). Written only on a hit.
- Return = contact class (see Return codes).
- Callers: `sub_86C030` (filter 0x10100, typeMask 0x11, r = 100, sphere at the object + velocity; then again with
  0x100 and no outputs), `sub_88CC80` (0x10100, typeMask 2, sphere at the player + 100 up), `sub_88D850`.

**Sphere overlap, bool, with a Param: `sub_9564E0`** (H):
`bool __usercall sub_9564E0@<al>(sCollision::Param* q@<esi>, sDevil4Collision* inst, MtSphere* sphere /*world*/)`,
`retn 8`. Callback `collNarrow_SphereB` 0x94A810 / `collBounds_Sphere` / `collStore_Qword2` with `q->filter`;
`sub_956520` copies `q` into its work buffer, ContactDefine {Default, `q->type` (0 = default), `q`+0x18, +0x1C, 0},
first-hit traversal; true when some triangle is within r of the centre (squared distance - r² <= 1e-8, latched at
work +0x70). `q->hitCallback` (+0xC) is called on the hit if set. Caller `uEm025Shl00::main` 0x6EBAE8: Param(type
0x7F, filter 0x400, correction 10), sphere (shell pos, r = 100). Also `uEm025Shl01::main`.

## 2. Sphere move + slide — `sub_956750` (H)

```
int __usercall sub_956750@<eax>(sCollision::Param* q@<eax>,
        sDevil4Collision* inst, MtVector3* pos /*in: target, out: corrected*/, MtVector3* old, MtSphere* sphere /*offset from the point*/);  // retn 10h
```
- Callback `collNarrow_DynCapsuleA` 0x94F430 (swept sphere vs triangle), `collBounds_BoxHalfExt` 0x95BF00,
  `collStore_Qword16`, filter = `q->filter`, then `originalScrCollision_Sphere_v2` 0x9567B0 -> `sub_958160` with
  `pHitCallback` 0x94B7C0 as the query and flags 0.
- `pos` is always rewritten (= target when nothing is hit). `old == pos` gives a pure push-out of an overlapping
  sphere.
- Caller `sub_79D050` 0x79D1EC: Param(type 0x7F, filter 0x10100, correction 10, hit callback 0), sphere (0, 0, 0,
  r = obj+0x1388), old = pos = obj+0x30.
- Lower level: `originalScrCollision_Sphere_v2(sphere@eax, old@ecx, pos@esi; stack inst, Param*, callback*,
  queryFn, u8 flags)`, `retn 14h` (flags != 0 shortens each slide by the angle to the normal).
- SE equivalent: `sCollision::adjustPosition(MtVector3& pos, const MtVector3& old, const MtSphere&, const Param&)`
  0xD68D70.

**Camera variant `sCollision::adjustPosition` 0x95CBE0** (IDB name; stdcall, `retn 14h`):
`uint __stdcall (inst, MtVector3* pos, MtVector3* old, MtSphere* sphere, Param* q)`. Moves in two halves with
`correctionNum` 1 then `q`'s own, then a settle pass (`boxSweepQuery_Sphere` 0x95CE00, correction 2 if anything was
hit), narrow `collNarrow_BoxSweep` 0x95BCF0 (a swept-sphere test despite the IDB name, M). Copies 0x40 bytes of `q`.
Callers: `cCameraPlayer::checkHit` / `checkHitNormal`, `uCameraBoss::checkHit` (sphere (0, 0, 0, 10)). Easiest
convention of all (plain stdcall).

`uCameraBoss::camSphereHitCheck` 0x4C7DA0 (SE `bool camSphereHitCheck(MtVector3& afterPushPos, MtVector3& pos,
float radius) const`) is the same move with old = `this+0x410` (mEndTar), r fixed at 10 in DX9, filter 0x20000000:
`pos@eax, this@ecx, out@edi`, plain `retn`; returns al = **1 when nothing was hit**, 0 = hit (out written). Camera
specific; use `sub_956750` instead.

## 3. Capsule move + slide — `cUtil::checkScrCollision` 0x45F650 (H)

This is the actor push-capsule-vs-stage query (SE `uint cUtil::checkScrCollision(const MtCapsule& cap, const
MtVector3& start, const MtVector3& end, MtVector3& hit_pos, uint filter)` 0x5B0180 =
`sCollision::adjustPosition(end, start, cap, Param(type 127, filter, correction 10))`).

```
uint __usercall cUtil::checkScrCollision@<eax>(MtVector3* end@<eax>, MtVector3* start@<ecx>, MtVector3* out@<edi>,
        MtCapsule* cap /*offset from the point*/, uint filter);     // plain retn: caller does add esp, 8
```
- Copies `end` / `start`, fills its own Param (type 0x7F, filter, groups -1/-1, correction 10, bAdjMvRelSet 1,
  bAdjAntiStop 1, limits FLT_MAX), callback `collNarrow_CapsuleEdge4` 0x94FC10 / `collBounds_OBBAvg` /
  `collStore_TriDeref`, then `originalScrCollision_Capsule_v2` 0x958000.
- `out` (x, y, z) = corrected end position, **written only when the return is non-zero**; `end` / `start` untouched.
- Callers (12): `uEm012::adjustDodgePos` (start = enemy pos + 50 up, end = target, cap = enemy+0x1850, filter
  0x307F7F00; call site 0x5D9CB5), `uEm005::adjustWarpPos` (cap = enemy+0x1980, filter 0x207F7F00, `add esp, 8` at
  0x569851), `uEm010::adjustWarpPos`, `uEm012::adjustTeleportPos`.

**With a caller Param: `sub_956C90`** (same shape as `sub_956750`):
```
int __usercall sub_956C90@<eax>(sCollision::Param* q@<eax>,
        sDevil4Collision* inst, MtVector3* pos /*in/out*/, MtVector3* old, MtCapsule* cap);   // retn 10h
```
Callers: `sub_47FC00` (from `uCollisionMgr::checkGround` 0x512BB3 and `sub_513B60`: the uCollisionMgr movement) and
`sub_5159F0` (Param correction 10, flags 1/0/1/0). Lower level `originalScrCollision_Capsule_v2(cap@eax, old@ecx,
pos@esi; stack inst, Param*, callback*, queryFn)` `retn 10h` (flags fixed 0).

## 4. Capsule overlap (bool) — `sub_94F230` (H convention, M semantics)

```
bool __usercall sub_94F230@<al>(MtCapsule* cap@<esi> /*world*/,
        sDevil4Collision* inst, uint typeMask /*0 = default*/, uint groupLo, uint groupHi, callback_struct_t* cb);  // retn 14h
```
- The caller fills `cb` first: `ScrCollisionBeforeFunc(cb, collNarrow_Capsule 0x94B7E0, collBounds_CapsulePair
  0x94B830, collStore_AABBFields 0x94C4E0, 0, filter, 0)`; the function points `cb->ctx` at its own 0x2DE0-byte
  work buffer (`sub_940A10`; 0x2E18 bytes of stack via `__alloca_probe`).
- Box = AABB(p0, p1) ± r; first-hit traversal (`sub_95E0D0`, stops at the first non-zero narrow result). Narrow:
  `sub_8C4DC0` capsule-vs-triangle, latches byte +0x2DD5 of the work buffer. Returns al = some triangle touches
  the capsule; no contact data.
- Caller `sub_456BD0` 0x456DFB: filter 0x80000, typeMask 0x7F, groups -1/-1. Also `sub_575210`,
  `uEm006::isCoopCmdPosEnable`.
- SE counterpart (L): `sCollision::isIntersect(const MtCapsule&, const Param&)` 0xD39700.

## 5. Capsule push-out — `sCollision::multi_obb_query` 0x94EF30 (H convention, M semantics)

The IDB name is misleading: it is a capsule depenetration.
```
uint __fastcall multi_obb_query(MtCapsule* ref@<ecx>, sDevil4Collision* inst@<edx>,
        MtCapsule* cap /*in/out*/, ContactDefine* cd, uint filter, int bothSides);    // retn 10h
```
- Box = union of both capsules (`sub_940F10`). Narrow `collNarrow_MultiOBB` 0x94ECD0 collects up to **64**
  triangles whose distance to `cap`'s segment is < r (depth stored), they are sorted deepest first and resolved one by
  one (`sub_94C520`), moving the capsule. `cap` p0, p1, r are written back; the return ORs the resolver's results
  (non-zero = moved; contact class bits 1 / 2 / 4, M). `bothSides` 0 skips contacts whose normal faces along the
  reference direction (one-sided, M). `ref` = the capsule before the move (both the same for a pure push-out).
- Callers: `cCameraPlayer::checkHit` 0x41DF63 (ref = cap = {p0 = look-at, p1 = camera, r = 10}, cd = {2, 0x7F, -1,
  -1, 0}, filter 0x20000000, bothSides 1; reads back p1 as the camera position), `cCameraPlayer::checkHitNormal`,
  `uCameraBoss::checkHit`, `sub_515E80` / `sub_5167D0` (cd {2, 0x7F, -1, -1, 0}, bothSides 1).

## 6. Line, any hit — `sub_94B660` (H)

`bool __usercall sub_94B660@<al>(uint filter@<eax>, sDevil4Collision* inst@<edi>, MtLineSegment* seg, uint
typeMask /*0 = default*/)`, `retn 8`. `collNarrow_LineFirstHit` / `collBounds_LineSegB` / `collStore_NopA`,
first-hit traversal; no hit data. 29 callers (`uPlayerDanteBoss::isObstacle`, `uEm010::isScrFallStop`,
`sub_456BD0` with 0x80000 / 0x7F). Cheaper than `findIntersection` when only "blocked?" matters.

## 7. Triangles in an AABB — the traversal with your own narrow callback (H convention, M moving parts)

No DX9 AABB query exists, but `sCollision::query_all_sbcs` 0x95E350 (usercall `inst@edi`; stack AABB*, callback*,
ContactDefine*; `retn 0Ch`) is reachable through a clean thiscall thunk:
```
uint __thiscall pHitCallback_0x94B7C0(sDevil4Collision* inst@<ecx>, MtAABB* box, callback_struct_t* cb, ContactDefine* cd);  // retn 0Ch
```
- For each registered SBC with `cd->type & Sbc.mType`, `cd->group & (1 << Sbc.mGroup)` and resource bounds touching
  `box` (box padded by 1 cm): walks the BVH with `box`, and for every triangle in an overlapping leaf box whose
  `runtime_attr` passes `cb->group_filter` calls `cb->func_narrow(SbcInfo* tri, cb->ctx)` (cdecl, caller pops 8,
  0x95F635). Returns the OR of those results. **Triangles are not tested against `box` itself**: do it in the
  callback. `sub_95E0D0` (usercall `inst@edi`, same 3 stack args, `retn 0Ch`) is the first-hit version (stops at the
  first non-zero return).
- Set `cb->func_bounds = cb->func_store = 0` (both are null-checked). Callers normally call `count_unique_resources`
  0x948580 (stdcall, inst) first: it only counts loaded SBCs (0 = none), no side effects.
- Moving parts (`Sbc` with moving parts, e.g. uStageSetMoveFloor) are traversed in the part's local space: without a
  `func_bounds` that moves the query box into it, the world box is used as-is, so moved parts are found at their
  rest position only. `cd->mPartsFilter` can't skip them without also skipping the static tree (see ContactDefine).

**`SbcInfo` / TriangleInfo packet passed to the narrow callback (0xB0, built by `fill_contact_packet` 0x940270 +
`checkAttr`):**

| Off | Field |
|---|---|
| +0x00 | `sCollision::Sbc*` |
| +0x04 | SBC index in `inst->mSbcArray` |
| +0x08 | top-tree node index |
| +0x0C | part (group) index |
| +0x10 | triangle index relative to the group |
| +0x14 | `rCollision::SbcInfo*` (96-B group record) |
| +0x18 | triangle (28 B: u16 vert[3], +8 runtime_attr, +0x0C type = material, +0x10 special_attr, +0x14 surface_attr) |
| +0x1C | vertex base (16-B vertices, group-relative indices) |
| +0x20 | u8 part enable / moving flag |
| +0x21 | u8 mMatResetSet |
| +0x30 | MtMatrix mCoord (part's current matrix, row vectors: world = x·r0 + y·r1 + z·r2 + r3) |
| +0x70 | MtMatrix mCoordOld |

`getTriangle` 0x948660 (`float* __usercall(float out[12]@<eax>, SbcInfo* tri@<ecx>)`, plain `retn`) copies the three
vertices (part-local, 16-B stride) — transform by +0x30 as `collNarrow_SphereA` does. Normal = (v1-v0)x(v2-v0).

## 8. OBB

None. `collNarrow_OBBSimple` 0x94F360 and `collNarrow_CapsuleOBBAdapt` 0x94FAE0 are only used inside the slide core's
pre-pass (`originalScrCollision_SphereOBB` 0x957DB0 / `_SphereCapsule` 0x957100, enabled by Param +0x2B), not as
standalone queries. Approximate an OBB with a capsule / sphere, or use section 7 with an OBB-vs-triangle test in the
callback (box = the OBB's world AABB).

## Narrowphase / wrapper map (DX9)

| Narrow | Bounds | Store | Entry |
|---|---|---|---|
| SphereA 0x9496A0 | Sphere 0x94A8C0 | Qword2 | `sub_94B480` (sphere contact) |
| SphereB 0x94A810 | Sphere | Qword2 | `sub_9564E0` (sphere overlap bool), SphereOBB pre-pass |
| Capsule 0x94B7E0 | CapsulePair 0x94B830 | AABBFields | `sub_94F230` (capsule overlap) |
| MultiOBB 0x94ECD0 | Compound4 | NopB | `multi_obb_query` (capsule push-out) |
| DynCapsuleA 0x94F430 | BoxHalfExt | Qword16 | `sub_956750`, camSphereHitCheck, uCameraBoss checks (sphere slide) |
| BoxSweep 0x95BCF0 | BoxHalfExt | Qword16 | `adjustPosition` 0x95CBE0 (camera sphere slide) |
| CapsuleEdge4 0x94FC10 | OBBAvg | TriDeref | `checkScrCollision`, `sub_956C90` (capsule slide) |
| LineFirstHit 0x9498C0 | LineSegB | NopA | `sub_94B660` |
| LineSeg 0x955970 | LineSeg | LineInfo | `findIntersection` (see `collision_lineCast.md`) |

Address corrections: the line core `sCollision::ScrCollisionCore` is **0x95B370** (0x95CF20 is
`originalScrCollisionCore`, the slide core used by 0x95CBE0; `sub_958160` is the other slide core, used by the
`_v2` entries); `ScrCollisionBeforeFunc` is **0x50DFB0** (0x940470 is `scrCollisionInfo_setGeom`).

SE reference (PDB names): `sCollision::adjustPosition` sphere 0xD68D70 / capsule 0xD6DF40, `isIntersect` sphere
0xD394F0 / segment 0xD395F0 / capsule 0xD39700, `castConvex` sphere 0xD8BD40 / capsule 0xD8BE60 / MtAABB 0xD8C090.
