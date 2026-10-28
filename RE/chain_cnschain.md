# DMC4 DX9 soft-body chains: rCnsChain / cCnsChain / rCollisionShape

Researched 2026-10-10 in the DX9 IDB (`DevilMayCry4_DX9.exe`) through ida-pro-mcp. The solver core, the resource copy and
the collision helpers were read later the same day (the first pass was refused by the permission check); the names in
"Renames" below were applied then, with comments at the solver steps (IDB not saved).

Confidence: **H** = read in the code, **M** = read but with part of the context missing, **L** = inference.

## 1. Classes, files and attachment

| Item | Address / value | Conf. |
|---|---|---|
| `rCnsChain` vtable | 0xB9B3A4 (dtor 0x465B40, createProperty **0x465B90**, getDTI 0x465A00, ext 0x465A10, load 0x466510, save 0x466540, defaults **0x466250**) | H |
| `rCnsChain` native extension | `"clt"` (0xB9B2EC; the ext slot holds `"col"` for rCollisionShape). `.phs` is the arc tool's name for the type. The cCnsChain member is called `mpCltRes` | H |
| `rCnsChain` load | `MtSerializer::deserializeBinary` (XFS), 0x466510. Save 0x466540 (alloc 1408 = 0x580 bytes) | H |
| `cCnsChain` vtable | 0xB98DF4. createProperty **0x42C840**, slot 5 = 0x430A00 → **0x430A20 (per-joint solver)**, slot 13 = **0x42DB00 (per-frame move)**, slot 12 = 0x42BB80 (sets byte +0x18) | H |
| `uChain` (uCloth) | vtable 0xC09E04, a separate cloth system (pl_cloth_param); **not** what `.phs` drives | H |
| `rCollisionShape` vtable | 0xB9B674. createProperty 0x468470, **load 0x4684F0**, **save 0x468780**, ext `"col"` | H |
| `cCollPrim` properties | 0x4678F0; `cCollGroup` properties 0x467CE0 | H |
| Chain collision test | **0x438DB0** (segment vs every prim of the shape) | H |

**Players (Nero, `uPlayerNero::setup` 0x7E2C10):** the paths are hard-coded, not built from the model name (H):
- `rCollisionShape "model\game\pl000\pl000_03"` (the `.col` next to the coat model) is loaded once and shared.
- A string table at 0xE15E58 lists `"model\game\pl000\pl000_03_00"` … `"_05"`. Each entry is loaded as `rCnsChain` into one of 6
  chain units (stride 0x11D0; the first cCnsChain is at player+0x6200).
- Per chain: `mpCltRes` (+0xFB0) = the rCnsChain. `mpModel` (+0xFB4) = player+0x52C0, the coat sub-model `pl000_03`,
  which `uPlayerNero::initModel` 0x7E3760 creates. `mpCollisionModel` (+0xFB8) = the player body. `mpCollisionShape`
  (+0xFBC) = pl000_03.col. vtable slot 12 is then called with 1, which sets +0x18: a fixed step of 1.0 (see §2).
- The `.col` capsules therefore sit on **body** joints, while the chain bones are **coat-model** joints.
- Dante (pl006) uses the same pattern (`pl006_03_00..05` at 0xBE366C…, `Collision\pl006`). Enemies use their own
  setup code, e.g. `uEm010::setup` 0x5A46D0 with `model\game\em010\em010_00..06`. Not followed further (M).
- `Collision\pl000` (`rCollisionShape` + `rAttackStatusData` + `rCollisionIdxData`) is the separate hit and attack
  collision. The chain uses only the `_03` shape (H for Nero).

**Chain file names are not a scheme (2026-10-27, H):** every path is a literal in its owner's code (the player string
tables above; `uEm009::setup`, `uEm010::setup`, `uEm011/013/014/018::setup`, `uEm030::setup` for Sanctus,
`uEm021_Snake::setup` `model\game\em021\chain`) or a resource track of a cutscene `.sdl` (`uCnsChain` units: pl001's
hair, the m20_100s pl023). The numbers in the names mean different things per owner (joint lists read from all the
DX9 files):

| Names | Number | Model the joints belong to |
|---|---|---|
| `pl000_03_00..05`, `pl006_03_00..05` | index 0-5 (one coat tail each) | the coat model `pl000_03` / `pl006_03` |
| `em010_00..06`, `em011_00..07`, `em013/014_NN`, `em018_00/01`, `em027_000..005` | index (2 or 3 digits) | the body (joints in no order: em010_03 = 15-25) |
| `em009_00..20`, `em009_000..007`, `em009_100..108` | three index series | `em009_00` holds joints 101-104 although `em009_00.mod` exists (one path string serves both) |
| `pl023_036`, `pl023_02_007`, `pl023_03_010` ... (Sanctus) | **the first joint** (3 digits) | the model in the prefix (`pl023`, `pl023_02`, `pl023_03`) |
| `pl001_hair02_06`, `pl001_hair15_17_18_20` (cutscene) | the joint range / list | `pl001` |
| `em021\chain` | none | em021's snake |

So a loader can't infer a chain's model or slot from its name; the model and the collision come from the owner (its
setup code, or the `uCnsChain` unit's `mpModel` / `mpCollisionModel` refs).

## 2. rCnsChain layout and defaults (0x465B90, 0x466250), cCnsChain copy (0x42C840)

| Field | rCnsChain off | cCnsChain off | Type | Default (0x466250) |
|---|---|---|---|---|
| mBone[32] | 0x60 | 0x20 | s16, -1 padded | -1 |
| mBoneData[32] (cBONE_DATA, 0x24 each) | 0xA0 | 0x60 | | 0 |
| mBlend | 0x520 | (cConstraint blend, see below) | f32 | 1.0 |
| mDir | 0x524 | 0x4E0 | u32 | 4 |
| mUp | 0x528 | 0x4E4 | u32 | 2 |
| mTailLength | 0x52C | 0x4E8 | f32 | 10.0 |
| mGravity | 0x530 | 0x4F0 | vec3 | (0, -1, 0) |
| mWind | 0x540 | 0x500 | vec3 | 0 |
| mWindSoftCtrl | – | 0x510 | vec3 (runtime / cutscene) | |
| mTurbulence | 0x550 | 0x530 | f32 | 0 |
| mSpring | 0x554 | 0x538 | f32 | 0.01 |
| mDamping | 0x558 | 0x53C | f32 | 0.98 |
| mMaxSpeed | 0x55C | 0x540 | f32 | 10.0 |
| mFloorLevel | 0x560 | 0x544 | f32 | -9999 |
| mStretch | 0x564 | 0x548 | bool | 0 |
| mStretchLimit | 0x568 | 0x54C | f32 | 100.0 |
| mCollisionSize | 0x56C | 0xFC0 | f32 | 5.0 |
| mParentMode | 0x570 | 0xFC4 | u32 | 0 |
| mPosLocal / mPosLocalY / mRotLocal / mWindLocal / mGravityLocal | 0x574..0x578 | 0xFC8..0xFCC | bool | 0 |
| mMuteCollision / mMuteWind | – | 0xFCD / 0xFCE | bool | |
| mChainReset | – | 0xFCF | bool | |
| mAutoInDemo / mInDemo | – | 0xFD9 / 0xFDA | bool | |

`mQuality` isn't in the DX9 property list. It may belong to the base `rResource` properties (sub_8E1C60), which
weren't checked (L).

`cBONE_DATA` (properties at 0x4665B0; an MtObject, so +0 is its vtable): +0x04 `mBoneAdjustGrid` u32, +0x08
`mBoneAdjust` bool, +0x0C/0x10/0x14 `MinX/Y/Z`, +0x18/0x1C/0x20 `MaxX/Y/Z` (f32, **degrees**) (H).

cCnsChain runtime state (H):
- matrices: `mat[k]` at +0x560 + 64k, k = 0..32 (node k's position is the translation row, +0x590 + 64k).
- velocities: `vel[k]` at +0xDA0 + 16k.
- parent frame: previous at +0xFF0, current at +0x1030; the delta (see §3) at +0x1070.
- step `t`: +0x10B0.
- cConstraint header: +0x04 current blend, +0x0C blend speed, +0x10 target blend, +0x14 time scale, +0x18 "fixed
  step" flag, +0x19 enable.

The copy rCnsChain → cCnsChain is `cCnsChain::setResource` 0x42D160 (called right after the load in
uPlayerNero::setup) (H): mBlend → +0x10 (the target blend), mDir / mUp / mTailLength → 0x4E0..0x4E8, mGravity → 0x4F0,
mWind → 0x500, mTurbulence → 0x530, mSpring → 0x538, mDamping → 0x53C, mMaxSpeed → 0x540, mFloorLevel → 0x544,
mStretch → 0x548, mStretchLimit → 0x54C, mCollisionSize → 0xFC0, mParentMode → 0xFC4, the five Local flags →
0xFC8..0xFCC, mBone → +0x20 and each cBONE_DATA through its copy method. No value is converted.

## 3. Per-frame simulation

### 3.1 `cCnsChain::move` (0x42DB00), once per frame (H)

- **Step:** `t = timescale x deltaTime x this+0x14`, clamped to ≤ 2.
  - `deltaTime` is in 60 fps frames (1.0 per frame). In mission 80 it is first clamped to 2.
  - `timescale` is a global at offset +0x20.
  - In the solver, `t = 1.0` when byte +0x18 is set (players set it).
- **Blend fade:** `blend (+4)` moves toward `target (+0x10)` by `speed (+0x0C) x t` per frame (t = 1 if +0x18 is set).
- **Wind:** `W = mWind + mWindSoftCtrl`.
- **Turbulence** (0x42DCF6): a timer (+0x534) accumulates t.
  - When it reaches ≥ 1, it resets to 0 and a new `r = (rand - 0.5) x mTurbulence` is drawn per axis (MtRandom
    table); nothing is added that frame.
  - Otherwise `W += r x t`. The result is stored at +0x550.
  - So at a steady t = 1 (60 fps, or the players' fixed step) the timer reaches 1 every frame and **the turbulence
    never applies**; it only shows when frames are shorter than one step (slow motion).
- **Joint registration:** every joint `mBone[i]` (a **joint ID**, mapped through the model's ID → index byte table at
  model+0x2E8; joints at model+0x2E4, stride 0x90) gets `joint+0x0C = this`. That is how the model's world-matrix pass
  calls the solver for those joints, in hierarchy order.
- **Parent frame** (only if some Local flag is set):
  - `mParentMode` 0 uses the world matrix of `mpModel` (model+0xA0); 1 uses the world matrix of `mpModel`'s parent unit
    (model+0x18 → +0xA0).
  - It keeps prev/cur and builds the row-vector delta `D` (+0x1070):
    - `mRotLocal` + `mPosLocal`/`mPosLocalY`: `D = inv(prev) . cur`, full rigid motion.
    - Only `mPosLocal`/`mPosLocalY`: `D` = identity with translation `cur.t - prev.t`.
    - `mPosLocalY` zeroes the x and z of that translation, so only vertical motion is carried.
    - Only `mRotLocal`: rotation delta about the parent origin, translation removed.
- **Reset:** state +0xFD0 == 1 lasts until a timer (+0xFD4, += time scale +0x14, checked at the end of move,
  0x4309C0) reaches 3.0: 2 frames at time scale 1. During it, the solver copies the animated pose (see 3.2a).

### 3.2 Per-joint solver `0x430A20(chain, joint, model)` (H unless marked)

Called for each chain joint J_i, where i is its slot in mBone. "Node i+1" is the simulated point the bone aims at.
That is the next chain joint, or a virtual tail after the last bone.

a. **Reset / first frame:** `mat[i] = J_i world matrix` and `vel[i] = 0`. If i is the last bone (`mBone[i+1] == -1`):
   - `mat[i+1] = mat[i]` with its translation moved along the bone axis by `mTailLength`.
   - The axis is the **mDir** enum, from the jump table at 0x438D1C: **0 +X, 1 +Y, 2 -Z, 3 -X, 4 -Y, 5 -Z** (rows of
     the joint world matrix).
   - Value 2 really is -Z: it shares the case with 5. +Z can't be expressed.

b. **Paused** (t ≤ 0, or demo-driven with weight ≤ 0): `J_i` = stored `mat[i]`, return.

c. **Rest length L of segment i:**
   - Next bone exists: `L = |T_child|`, where T_child is the child's bind-local translation (rModel mLmat row 3).
     Unless `sMediator+0x131 == 1`, it's scaled: `|T_child ∘ modelScale| x avg(modelScale)`.
   - Last bone: `L = mTailLength` (x avg scale under the same condition).
   - Units: game units (cm).

d. **Carry with the parent frame:** if PosLocal / PosLocalY / RotLocal is set, `p[i+1] = p[i+1] . D` (point) and
   `vel[i+1] = vel[i+1] . D3x3`.

e. **Forces:**
   - `wind = mWindLocal ? W . R_parent : W`; it is 0 if `mMuteWind`.
   - `g = mGravityLocal ? mGravity . R_parent : mGravity`.
   - `R_parent` = the rotation of the current parent frame (+0x1030).

f. **Integration (semi-implicit Euler, per frame):**
   ```
   vel[i+1] += (g + wind) * t
   p[i+1]   += vel[i+1] * t
   d = p[i+1] - J_i.pos ;  dir = d / |d|
   ```
   With mGravity (0, -1, 0), the acceleration is 1 cm/frame².

g. **Constraint, floor, collision, spring, damping, speed limit** (0x431820-0x431CE3, H). `dist` and `dir` come
   from step f (before any of this):
   1. Length (0x431842): without `mStretch`, `p[i+1] = J_i.pos + dir x L`. With it, the node stays free unless
      `mStretchLimit >= 0` and `dist > L x mStretchLimit`; then `p[i+1] = J_i.pos + dir x L x mStretchLimit`.
   2. Floor (0x431921): if `mFloorLevel > p[i+1].y`, then `p[i+1].y = mFloorLevel` and `vel *= mDamping x 0.1`.
      Every file has -9999 (off).
   3. Collision (0x4319D1, skipped with mMuteCollision +0xFCD): `cCnsChain::collide(J_i.pos, p[i+1], radius
      mCollisionSize)`. On a hit, **both** `J_i.pos` (the joint's world translation) and `p[i+1]` move by the
      returned push, and `vel[i+1] = 0`. For i > 0 the pushed `J_i.pos` is later replaced by `p[i]` (step h), so only
      the root joint keeps its push, and a segment can still cross a shape near its start.
   4. Spring (0x431AE6): if `dist > L`, `vel += -(dist - L) x dir x mSpring x t`. It corrects the velocity for the
      overshoot that step 1 removed from the position; with mStretch on, it pulls a stretched chain back.
   5. Damping (0x431B7E): if t > 0, `vel *= mDamping`. Values above 1 occur (pl023: 5, 10, 20) and amplify the
      velocity, which step 6 then bounds.
   6. Speed limit (0x431BBD): if `|vel| > mMaxSpeed`, `vel = normalize(vel) x mMaxSpeed`.

h. **Bone rotation** (0x431DDC-0x43206A, H):
   - `aim = p[i+1] - J_i.pos`, negated if `mDir ∈ {3, 4, 5}`.
   - `up` = a row of J_i's **animated** world matrix, selected by **mUp**: **0 +X, 1 +Y, 2 +Z, 3 -X, 4 -Y, 5 -Z**.
     Here 2 is +Z: mUp uses its own switch.
   - A basis is built with the mDir axis along `aim` and the mUp axis as close as possible to `up` (Gram-Schmidt). The
     helper depends on the axis pair (dir axis, up axis):

     | dir \ up | X | Y | Z |
     |---|---|---|---|
     | X | – | sub_48BBD0 | sub_48C1D0 |
     | Y | sub_48C7D0 | – | `sMath::setOrientationYZ` |
     | Z | sub_48D3C0 | `sMath::setOrientationZY` | – |

     The same pair does nothing (the animated rotation is kept).
   - Translation: the chain root (i = 0) keeps its animated position. Bone i > 0 is placed at the simulated `p[i]`.
   - So **all bones but the root follow the simulated points**, and the bone's mDir axis points at the next point.

i. **Blend with animation** (0x434185, H): the new world matrix is converted to parent-local (parent joint at joint+5,
   rows normalised).
   - Then `local = sMath::blendMatrixZY(simLocal, animLocal, w = blend(+4), 1 - w)` (0x48DFB0).
     - The Z rows are lerped (`sim x w + anim x (1 - w)`), and so are the Y rows.
     - The basis is rebuilt by `sMath::setOrientationZY` (Z exact, X = Y x Z, Y = Z x X).
     - Each row is scaled by the lerped row lengths, and the translation is lerped.
   - animLocal is built from the joint's local quaternion (+0x20) and translation (+0x40).
   - The world matrix is then rebuilt with the parent's scale. `mat[i]` stores the result, which the next joint uses.
   - Blend 1 = fully simulated (H).

j. **mBoneAdjust** (only if `cBONE_DATA[i].mBoneAdjust`; off in all 1,312 shipped entries, which are grid 2, zeros)
   (H, read 2026-10-10). Run twice: on the simulated local matrix before the blend (0x433376..) and on the blended
   local after it (0x43418D..); "local" = relative to the parent (rows = the bone's axes in the parent's frame).
   `mBoneAdjustGrid` picks **the bone axis that is measured** (the getJointWMat calls in those branches only copy a
   matrix that isn't used for the angles):

   | grid | axis (row) | angle 1, clamped by | angle 2, clamped by | rebuild (row-vector order) |
   |---|---|---|---|---|
   | 0 | X | atan2(x, z): MinY / MaxY | atan2(y, x): MinZ / MaxZ | Ry(a1) then Rz(a2) |
   | 1 | Y | calcPitch = -atan2(y, sqrt(x^2 + z^2)): MinX / MaxX | atan2(y, x): MinZ / MaxZ | Rx(a1) then Rz(a2) |
   | 2 | Z | calcAngleXY pitch = -atan2(y, sqrt(x^2 + z^2)): MinX / MaxX | calcAngleXY yaw = atan2(x, z): MinY / MaxY | Rx(a1) then Ry(a2) |

   - `cUtil::calcAngleXY(d, origin)` 0x45EB40: out.y = atan2(d.x, d.z), out.x = -atan2(d.y, sqrt(d.x^2 + d.z^2)),
     out.z = 0; `cUtil::calcPitch` 0x45EAE0 = that out.x.
   - Angles in degrees; each: `if Min > a: a = Min`, then `if a > Max: a = Max`. Only if one was clamped is the
     rotation rebuilt from identity with the two rotations above (no roll), the translation kept.
   - Offsets (createProperty 0x4665B0): +4 grid, +8 adjust, MinX / MinY / MinZ +0xC / 0x10 / 0x14, MaxX / MaxY / MaxZ
     +0x18 / 0x1C / 0x20.
   - Grid 2's measure and rebuild are inverses (a clamped bone measures inside its limits); grids 0 and 1 aren't (the
     rebuilt axis measures differently), so with them a clamped bone can read outside its limits. Albam's preview
     reproduces this as decoded (`cns_chain_preview.limit_angles`).

### Units

Game cm, Y-up world, row-vector matrices. One step per 60 fps frame: forces are per frame², not per second.

## 4. Collision

### `.col` (rCollisionShape), from load 0x4684F0 and save 0x468780 (H)

```
0x00 char[4] "COL\0"   0x04 u16 version (2)   0x06 u16 numGroups   0x08 u32 -1   0x0C u32 -1
per group: u32 numPrims, u32 mKind, u32 flags, u32 -1, then numPrims x 64-byte cCollPrim
   flags: 1 mAtk, 2 mDmg, 4 mPsh, 8 mGrb, 0x10 (unnamed, +0x1C), 0x20 mFrdAtk
cCollPrim (64 bytes): 0x00 s32 mType, 0x04 s32 mBone0, 0x08 s32 mBone1, 0x0C f32 mRadius,
   0x10 vec4 mPos0, 0x20 vec4 mPos1, 0x30 ?, 0x34 u32 mID, 0x38 f32 mShrink (forced 0 when version < 2), 0x3C pad
```

In pl000_03.col the first prim starts at 0x20. The `-1` at 0x1C is the end of the group header.

### Chain test 0x438DB0(chain, seg, out) (H)

- It needs both `mpCollisionModel` and `mpCollisionShape`, and walks **every group and prim** (no flag filter).
- **Type 0 = sphere:** centre = `mPos0` transformed by the world matrix of `mBone0`, radius `mRadius`. Tested with
  `sCollision::segmentVsSphere` 0x8C1D20 (closest point of the segment to the centre).
- **Type 3 = capsule:** `mPos0` in the frame of `mBone0` to `mPos1` in the frame of `mBone1`, radius `mRadius`.
  Tested with `sCollision::segmentVsSegment` 0x8C2230 (closest points of the two segments, sub_8D0F00; a degenerate
  segment falls back to the sphere test).
- Both helpers return, for the chain side:
  - the normal from the chain segment toward the shape;
  - `depth = distance - (r_chain + r_shape)`.

  A hit is `depth <= 0`, and the push is `normal x depth` (away from the shape).
- Other types are ignored.
- mBone0/1 are **joint IDs of the collision model** (the body), 255 = none.
- The chain segment is a capsule: p0 at +0, p1 at +0x10, radius at +0x20 = `mCollisionSize` (+0xFC0, set at
  0x4319F4) (H).
- On each hit, both segment points are pushed along the contact normal by the penetration depth, and the tests
  continue from the pushed segment. It returns hit plus the total push of p0.
- `mMuteCollision` (+0xFCD) skips it (H, 0x431971).
- `mFloorLevel` is a world-y clamp in the solver, not part of this test (H, see 3.2g).

### Where Nero's coat hangs (H)

- **The coat model** (`pl000_03.mod`, player+0x52C0):
  - It has the player as its parent model and **no parent joint** (-1).
  - Its motions (`motion\pl000_03\*.lmt`) only rotate joints 1 and up.
- **Its joint 0 follows the body** through a `cCnsMatrix` constraint (kMdlCoat, player+0x6160):
  - `uPlayerNero::initModel` 0x7E3760 sets the constraint's source (+0x61C0) to the world matrix of **body joint ID 2**.
  - It installs the constraint on coat joint 0 (joint+0x0C), so coat joint 0's world matrix is body joint 2's.
- **The chains' parent frame** (mParentMode 1) is the player model's world matrix.
- **Dante's coat** (pl006_03) wasn't traced (L: the same pattern).

## 5. Exporter constraints

- `mBone` holds 32 slots: joint IDs (anim / retarget IDs) of the model the chain is attached to, with **-1 between
  tendrils** (H): move 0x42DE20 registers every slot that isn't -1 (all 32 are walked), the solver finds a joint's slot
  by scanning all 32, a joint whose next slot is -1 is a tip (its tail is stored in that -1 slot's mat / vel), and
  one whose previous slot is -1 (or slot 0) is a root that keeps its animated position (0x432079). So one file can
  hold several tendrils: 8 of the 41 DX9 files do (Sanctus pl023_02_007: 7 tendrils of 3, Berial em018_00: 3 of 3);
  Nero's / Dante's coat files hold one each. Node i+1 is the next slot whatever its parent, so within a tendril each
  joint should be the parent of the next.
- A tendril needs ≥ 1 bone. Each tip gets a virtual tail along mDir of length mTailLength.
- Players load exactly 6 chain files (`_00`..`_05`) from hard-coded paths; the count is fixed per character in code
  (the user loads new files with their own loader).
- 32 `cBONE_DATA` entries are always present (the serialized array is fixed).
- mDir: 0..5 with 2 == -Z (use 5). mUp: 0..5 with 2 == +Z.
- `.col` bone fields refer to the **collision model** (body for players), not to the chain's model.

## 6. Spawning a uCnsChain at runtime

Read 2026-10-27 (DX9 IDB, SE PDB for names; read-only). The `.sdl` path, the enemy pattern and the unit lifecycle.
Spawning the model a chain hangs on (a `.mod` attached rigidly to a joint, or skinned joint by joint through cCnsMatrix
like Nero's face / hair / coat): see `model_attachments.md`.

### The unit (H)

| Item | DX9 | Notes |
|---|---|---|
| `uCnsChain::DTI` | 0xE58538 (name 0xBC70AC, size field 0x10E0, parent cUnit::DTI) | DTI hash 0x4D990996 is rCnsChain's; the unit's is `dti_hash("uCnsChain")` |
| DTI vtable (MtDTI_vtbl81_) | 0xBC70B8: slot 0 dtor 0x410360, **slot 1 newInstance 0x4FC420** | only 2 slots (slot 2 is string data) |
| `newInstance` 0x4FC420 | ignores ecx, no stack args, `retn`; UnitAllocator (0xE1434C) memAlloc(0x10E0, 16) then ctor | returns the unit or 0 |
| ctor 0x42BCA0 | `__thiscall` (ecx = memory), returns eax = this, `retn` | cUnit header then `cCnsChain` ctor 0x42BBA0 (esi = this+0x20) + initMember 0x42D310 |
| size | 0x10E0 | SE 0x10F0 |
| vtable | 0xB98E30 | 0 deleting dtor 0x42BCF0 (`retn 4`), 3 createProperty 0x4FC450, 4 getDTI 0x42BC90, 5 +0x14 init (nullsub), **6 +0x18 move 0x4FC4C0** = `mCnsChain.vtbl[13]` (cCnsChain::move 0x42DB00), 7 / 8 moveEx / moveAfter nullsub, **12 +0x30 kill 0x42BAB0** (state 1/2 -> 3 unless attr FIX 0x2000), 13 +0x34 updatePtr 0x4FC4D0 (nulls dead mpModel / mpCollisionModel; caller not traced) |
| cUnit header after ctor | +4 low 16 bits = 0x4DF9: state 1 (INIT), line 63 (none), attr MOVE 0x400 / DRAW 0x800 / VISIBLE 0x4000; +7 = 0xF; +0x10 = 1.0 | |
| `mCnsChain` | unit **+0x20** (the only property of uCnsChain, class type 1) | all cCnsChain offsets below + 0x20 = unit offset |

`uCnsChain::setEnable` **0x4FC520** (SE `setEnable(bool)`): `__usercall`, **al = enable, edx = uCnsChain\***, no stack
args, `retn`; trashes eax / ecx / edx. Writes unit+0x39 (cConstraint mEnable); with false and mpModel set it zeroes
`joint+0x0C` of every mBone joint of mpModel (through mJointTable +0x2E8 / mpJoint +0x2E4, stride 0x90). (H)

### Fields to set (cCnsChain offsets; unit = +0x20) (H)

| Field | cCnsChain | How the game sets it | Default |
|---|---|---|---|
| cConstraint mBlendWeight (current) | +0x04 | runtime fade toward +0x10 | 1.0 |
| mBlendVel | +0x0C | `vtbl[6]` 0x42BB30 `setBlend(target, vel)` thiscall, 2 floats, `retn 8` | 1/60 |
| mBlend (target) | +0x10 | copied from the .clt by copyResource | 1.0 |
| rate (time scale) | +0x14 | `vtbl[10]` 0x42BB70 `setRate(float)` | 1.0 |
| fixed step | +0x18 | `vtbl[12]` 0x42BB80 `(bool)` | 0 |
| mEnable | +0x19 | plain bool, or setEnable 0x4FC520 | **1** |
| **mpCltRes** | +0xFB0 | setter **0x42D120** `__thiscall(ecx = cCnsChain, rCnsChain*)`, `retn 4`: releases the old one, stores, calls copyResource 0x42D160 (esi = cCnsChain), which **addRefs** and copies every .clt parameter | 0 |
| **mpModel** | +0xFB4 | plain pointer (a uModel-derived unit; ref track in .sdl) | 0 |
| mpCollisionModel | +0xFB8 | plain pointer | 0 |
| mpCollisionShape | +0xFBC | setter **0x4393D0** `__thiscall(ecx = cCnsChain, rCollisionShape*)`, `retn 4`: releases old, **addRefs** new | 0 |
| mChainReset | +0xFCF | property only: **no DX9 code reads it** (cutscene keys of it are no-ops) | 0 |
| reset state | +0xFD0 | **write 1 to reset**: the next 2 frames copy the animated pose into mat[] / zero vel (timer +0xFD4 to 3.0, cleared by move 0x4309C0). uEm008/009/010::main write it (0x580420, 0x5977E0, 0x5A5B13) | 0 |
| mAutoInDemo / mInDemo | +0xFD9 / +0xFDA | move sets mInDemo when mpModel's DTI name is `uCustomDemoActor`; then it follows the demo scheduler | 1 / 0 |

Without a reset the first solve starts from mat[] = identity (points at the world origin) and the chain snaps in from
there (M: from the solver's reset branch 0x430E5F; not watched in game).

### Per frame (H)

- `uCnsChain::move` = `cCnsChain::move` 0x42DB00. It first nulls `mpModel` / `mpCollisionModel` whose state isn't 1 or
  2 (dead or dying units), then, **only if mpModel != 0 and mEnable**, writes `joint+0x0C = this` on every mBone joint
  (every frame). The solve itself runs later, inside **mpModel's `uModel::updateWorldMatrix` 0x9EA8B0** (constraint
  vtbl[5] calcJoint 0x430A00 per joint), wherever the owner calls it: `uDevil4Model::move` 0x522CA0 (plain models,
  enemies) in the move pass, `uPlayer::updateMatrix` 0x7A8D40 from moveEx for players and their sub-models.
- Nothing has to be loaded before the first move except what the solve reads: no mpCltRes = no parameters (mBone all
  -1 = no joints registered). No preliminary vtbl[12] call is needed (players use it for a fixed step of 1).
- Frame: `sDevil4Main::move` 0x8AEE80 runs `sUnit` move for lines 0..31 in order (vtbl +0x18 `applyWorldOffset`
  0x8DC230 -> `sUnit::move(line)` 0x8DC290), then the moveEx pass (0x8DC3D0, unit vtbl +0x1C) for 0..31, then the
  moveAfter pass (0x8DC260, unit +0x20). In `sUnit::move`: state 1 -> 2 + vtbl[5] then move in the same pass; 2 + attr
  0x400 -> move; 3 -> 4; 4 -> unlink (0x8DC5D0) + deleting dtor(1).
- Lines start parallel (`sUnit::sUnit` 0x8DBF20 writes 0x1FD into every line's flags; bit 0 = parallel): units of one
  line may run as jobs on worker threads (`sMain::executeJob` 0x90DC80, when more than one job thread). Line flag bit
  1 = paused line (skipped). (H for the code; M for how many threads run on PC.)

### Lifetime and the destructor (H)

- `~cCnsChain` (DX9 0x42C7A0, esi = cCnsChain) **zeroes `joint+0x0C` of every joint of mpModel** (not only its own),
  then releases mpCltRes and mpCollisionShape. So deleting a chain while its model lives also drops the model's other
  constraints (leg IK cCnsIK, a coat's cCnsMatrix), and deleting it after the model was freed writes into freed memory.
- Cutscenes avoid the second case by putting the chain on a **lower line than its model** (chains on line 4, the
  hair model on line 5): on a mass kill (`aRoom::cleanRoom` -> `aRoom::killUnit` 0x40E100 kills lines 1, 7-11, 13-16,
  18-21, 23-25, 29, 31 from `GameMoveLineTbl` 0xDF3AD4 and then 0, 2-6, 12, 26, 31) every unit goes 3 -> 4 -> delete
  in line order, so the chain's dtor runs while the model is still allocated. `sUnit::reset` 0x8DC1E0 deletes in line
  order directly.
- A model killed first: the chain's next move sees state 3 / 4 and nulls mpModel (the model isn't freed until two of
  its line passes later), so it's safe while the chain's line keeps moving every frame. The chain unit itself stays
  alive (doing nothing) until killed.
- Kill: unit vtbl[12] (+0x30) 0x42BAB0 `__thiscall`, or `flags = (flags & ~7) | 3` (dmc4_hook `despawn` does that).

### The .sdl path (H, `rScheduler` 0x90BFA0; m01_100s_B.sdl / m20_100s.sdl)

1. Unit track (dti uCnsChain, parent = line **4** for all 50 chain units in the DX9 files): `dti->newInstance()` then
   `sUnit::addBottom(unit, 4)` (0x8DC540: **eax = sUnit, esi = unit, push line, `retn 4`**). Created during the
   scheduler's own move (line 7), so its first move is next frame.
2. Object track `mCnsChain` binds the embedded cCnsChain (unit+0x20).
3. Resource track `mpCltRes` (`model\demo\pl001\pl001_hair02_06`, DTI rCnsChain): a getter / setter property
   (0x42D300 / 0x42D120), so the scheduler calls the setter without its own ref counting; the scheduler's resource
   array keeps the load ref. Ref track `mpModel` -> the model unit (uCustomDemoActor on line 4 or 5). Resource
   `mpCollisionShape` (setter 0x4393D0), ref `mpCollisionModel`. Then keyed mBlend / mWind / mFloorLevel /
   mCollisionSize / mEnable (and mChainReset, unread).
4. Next frame: line 4 -> uCnsChain::move registers the joints; the model's world-matrix pass solves them.

`uCnsChainReset` (DTI 0xE58558, 0x1C bytes, `bool mReset` +0x18, empty move): nothing in the DX9 code references its
DTI or vtable besides its own DTI / newInstance, so it does nothing in DX9 (M). The demo reset is
`sMediator+0xD8` (mpDemoCutCtrl) +0x19 mClothReset, read by the solver when mInDemo.

### The enemy pattern (H, `uEm000::setup` 0x53F970, `uEm010::setup` 0x5A46D0, `uEm010::main` 0x5A5A90)

Enemies embed whole uCnsChain units (stride 0x10E0, ctor 0x42BBA0 from their constructors) and drive them without
sUnit: setup does `r = sResource::create(rCnsChain::DTI 0xE57538, path, 1)`, stores r at cCnsChain+0xFB0 (after
releasing the old one), copyResource 0x42D160 (esi = cCnsChain), `mpModel = this`, uEm010 also `setBlend(target,
0.02)`, then `cResource::release(r)`; then `setEnable(0, unit)`. Each frame main sets the reset byte when needed,
`setRate`, `setBlend`, calls the unit's vtbl +0x18 move, then `setEnable(on, unit)` (uEm010::main 0x5A5A90 from
0x5A5B13; uEm008::main 0x580300 and uEm009::main 0x597680 set the reset byte the same way).

### Joint binding (H)

mBone entries are joint **numbers** of mpModel: `mJointTable[(u8)no]` (+0x2E8) -> index into `mpJoint` (+0x2E4,
0x90 per joint), 255 = absent (skipped). Collision prims' mBone0 / mBone1 go through **mpCollisionModel's** table the
same way (0x438F0D-0x439233). One joint holds one constraint pointer: a chain overwrites whatever was on its joints
every frame.

## Albam preview

`engines/mtfw/cns_chain_preview.py` replays this solver (3.1, 3.2a-i, §4) on the armature in Blender; the module
docstring maps each step. Checked headless:
- **Rest pose:** with no forces it holds (each bone's mDir axis on the next joint, lengths exact).
- **Every DX9 chain** runs on its model.
- **Lengths:** non-stretch chains with mBlend 1 keep them, except where a joint's bind offset isn't along mDir.
  em010_04 / 05 are 58 degrees off, so the game's own formula drifts there too.
- **Collision** moves the coat out of the body capsules but leaves mid-segment overlaps during fast motion, as 3.2g
  step 3 predicts.

Not compared with the game itself.

## Gaps

- `sub_42D300` / `sub_42D120` are the mpCltRes getter / setter (§6). mBoneAdjust's grid meanings: see 3.2j.
- Not watched in the game: a runtime-spawned uCnsChain (§6) and the first-frame snap without a reset.
- Dante's coat attachment (see "Where Nero's coat hangs").

## Renames (applied 2026-10-10, IDB not saved)

| Address | Current | Proposed |
|---|---|---|
| 0x465B90 | sub_465B90 | rCnsChain::createProperty |
| 0x466250 | sub_466250 | rCnsChain::setDefault |
| 0x466510 | sub_466510 | rCnsChain::load |
| 0x466540 | sub_466540 | rCnsChain::save |
| 0x4665B0 | sub_4665B0 | rCnsChain::cBONE_DATA::createProperty |
| 0x42C840 | sub_42C840 | cCnsChain::createProperty |
| 0x42DB00 | sub_42DB00 | cCnsChain::move |
| 0x430A00 | sub_430A00 | cCnsChain::calcJoint (thunk) |
| 0x430A20 | sub_430A20 | cCnsChain::calcJointImpl |
| 0x438DB0 | sub_438DB0 | cCnsChain::collide |
| 0x42D160 | sub_42D160 | cCnsChain::setResource |
| 0x48DFB0 | sub_48DFB0 | sMath::blendMatrixZY |
| 0x8C1D20 | sub_8C1D20 | sCollision::segmentVsSphere |
| 0x8C2230 | sub_8C2230 | sCollision::segmentVsSegment |
| 0x4684F0 | sub_4684F0 | rCollisionShape::load |
| 0x468780 | sub_468780 | rCollisionShape::save |
| 0x468470 | sub_468470 | rCollisionShape::createProperty |
| 0x4678F0 | sub_4678F0 | cCollPrim::createProperty |
| 0x467CE0 | sub_467CE0 | cCollGroup::createProperty |
| 0xE15E58 | – | uPlayerNero::sChainPathTbl (proposed only: data, not renamed) |
