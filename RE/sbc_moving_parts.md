# DMC4 DX9 moving collision ("dynamic SBC"): `uStageSetMoveFloor` and the moving-part mechanism

Source: DX9 IDB (port 13337), names from the SE PDB (13338) only where noted, plus the `.sdl` / `.pla` / `.sbc` files under
`arctool\st405` and `arctool\st406`. 2026-10-10. **Nothing in the IDB was changed** (see the end of the file).
Confidence: **H** = read in code (and matching the data), **M** = code plus inference, **L** = guess.

## Summary

- Any registered `.sbc` can have moving parts. A part (= a group record of the `.sbc`) gets a world matrix through
  `sub_946E60(sbcHandle, sCollision, partsId, MtMatrix*, reset)`, which sets **every group whose `group_id` == partsId**.
  The geometry stays in the file in **local space**; queries are transformed into it by the inverse matrix. **H**
- `uStageSetMoveFloor` is a `uStageSet` (uActor / uDevil4Model) whose matrix is simply its own `mWmat` (`mPos` / `mAngle` /
  `mScale` composed with `mpParent`). The `.sdl` that contains it animates `mPos` / `mAngle`. **H**
- Characters are carried because `SetScrAttribute(rColl, 1)` marks every triangle with surface flag **0x40**, and the
  ground check applies `inverse(mCoordOld) * mCoord` of the part it stands on. **H**

## 1. `uStageSetMoveFloor`

| Item | DX9 | Notes |
|---|---|---|
| ctor | 0x881970 | `uActor` base, `mActorType` 4, `mSetNo` -1, `mDisp` 1, `mSbcHandle` -1, the rest 0 (incl. `mPartsId` 0, `mMode` 0) **H** |
| dtor | 0x881A40 | `unregistResourceFromIndex(mCollHandle)`, releases `mpCollision` and the scheduler **H** |
| createProperty (vtbl +0x0C) | `sub_881AD0` | see the table below **H** |
| setup (vtbl +0x14) | 0x881CB0 | **H**, below |
| sync (vtbl +0x20) | 0x882520 | modes 2/3 call `moveSt303X/Z`; if `mReleaseColl`: `activateParts(mPartsId, 0)` **H** |
| kill (vtbl +0x30) | 0x882570 | kills the scheduler, marks the unit dead **H** |
| main (vtbl +0x78) | 0x881E10 | `updateLocalMatrix`, `updateWorldMatrix`, camera transparency, then mode 0 -> `moveNormal` 0x881E50, mode 1 -> `moveScheduler` 0x881F20 **H** |
| moveSt303X / Z | 0x8821E0 / 0x882410 | st303-only movers (static globals `startX/Z`, `targetX/Z`, 20 cm per frame) **H** |
| vftable / DTI | 0xBF60A0 / `getDTI` 0x8818F0 | |

### Properties (DX9 offsets)

| Property | Off | Type | Set by | Meaning |
|---|---|---|---|---|
| `mSetNo` | +0x1370 | int | `uStageSet::createProperty` `sub_860A50` | Stage-set ID, shared by all `uStageSet*`. **MoveFloor's own code never reads it.** Other set code matches units by it (e.g. `sub_887990` uStageSetTimeSlow pairing); `uStageSetScheduler` in the `.pla` has its own `mSetNo`. **H** (not read) / **L** (purpose) |
| `mpChild` | +0x1374 | unit ptr | uStageSet | not used here |
| "Custom Param" group | | | | |
| `mMode` | +0x138C | u32 | | 0 = normal (the `.sdl` drives it), 1 = hard-coded st302/st303 scheduler, 2/3 = st303 X/Z movers. **Use 0.** **H** |
| `mType` | +0x1390 | u32 | | mode 1 only: index into the path tables 0xE169E8 (`.sbc`: st302-a02, st303-a01) and 0xE16A00 (`.sdl`: st302-md45e240, st303-md45e300 ... md49e1500) **H** |
| `mDisp` | +0x1380 | bool | | collision + draw on/off. Rising edge: `activateParts(mPartsId, 1)` and unit flag 0x800 set. Falling edge: flag cleared, `mReleaseColl` -> `sync` deactivates the parts. Keyable in the `.sdl` (st406 elv00D: `mDisp` 1 -> 0 at frame 184). **H** |
| `mpCollision` | +0x1398 | rCollision resource | `sub_8BEE50` | the `.sbc` (class hash 956357328 in the files) **H** |
| `mPartsId` | +0x1388 | u32 | | the `group_id` of the `.sbc` groups this unit moves and switches **H** |
| `mDispOld` +0x1381, `mAttr` +0x1382, `mTimer` +0x1384, `mReleaseColl` +0x1394, `mCollHandle` (Sbc*) +0x139C, `mSbcHandle` +0x13A0, `mCollMgr` +0x13B0, `mpScheduler` +0x17A0, `mFrameMax` +0x17A4 | | | runtime | |

Inherited (uModel / uCoord, not MoveFloor-specific): `mpModel` (render only; may be omitted: the st406 child floors and
`ev405_00.pla` have no model), `mPos` (cm), `mAngle` (radians), `mpParent` (= `uCoord::mParent` +0x18), `mTransMode`,
`mLightGroup`, `Trans`. **H**

### setup (0x881CB0) **H**

1. Mode 2/3: initialise the st303 globals. Mode 1 without `mpCollision`: load `off_E169E8[mType]`, `mCollMgr.mEnable = 0`.
2. `sCollisionGame::SetScrAttribute(mpCollision, 1)` (0x881D6C): rebuilds `runtime_attr` and **ORs surface 0x40 into
   every triangle** (the "moving floor" mark that enables carrying, §4).
3. `sCollision::registResource(sCol, mpCollision, 16, 1)` (0x881D83): type mask **16** (`Sbc.mType`; the stage SBC uses
   1, `uStageSetCatapult` 64), and `a4 = 1` = **always a new Sbc**, even when another unit registered the same
   `rCollision`. That is how blade02 ... blade06 share `st405-a-03` with separate matrices.
4. Every part of that Sbc: `mActive = 0` (0x881DCC).
5. `sub_946E60(mSbcHandle, sCol, mPartsId, &mWmat, reset = 1)` (0x881E03).

### moveNormal (mode 0, 0x881E50) **H**

Shape and motion update, `updateLocalMatrix` / `updateWorldMatrix` again (vtbl +0x34 / +0x38), the `mDisp` edge
handling, then **every frame** `sub_946E60(mSbcHandle, sCol, mPartsId, &mWmat, reset = 0)` (0x881EE0) while `mDisp` is
set.

So with `mDisp` = 1 (the default), the first frame activates the `mPartsId` groups. Groups with any other `group_id`
stay inactive for this Sbc forever. **H**

### moveScheduler (mode 1, 0x881F20) **H**

- Loads `off_E16A00[mType]` as an rScheduler, makes a `uScheduler` (loop off, unpaused) and re-parents every unit in it
  that derives from `uCoord` to this floor (`mParent = this`, `ParentJoint = -1`).
- Parts on from frame 60 to `mFrameMax - 30`, released at `mFrameMax - 15`; the scheduler is killed at `mFrameMax`.
- Hard-wired to st302/st303. Not useful for new content.

## 2. How a part moves

### Registration (`registResource` 0x946750) **H**

Allocates a 76-byte `sCollision::Sbc` and calls `sub_942540` (Sbc set resource: `setPartsNum(num_groups)`, so one
`Parts` per group).

Sbc layout (DX9, IDB type):
- +0x08 `mpResource`, +0x0C `PartsArray`, +0x10 `PartsNum`
- +0x18 `mType` (the a3 mask), +0x1C `mGroup`
- +0x20 `mMovingPartsArray` (ColArray: +0x24 count, +0x28 capacity, +0x2C `Parts**`)
- **+0x3C / +0x40 / +0x44 `mMoveX/Y/ZNum`**, +0x48 `mSbcHandle`

Note: `collision_findings.md` gives +16/+20/+24 for `mMoveX/Y/ZNum`, which is wrong.

### `Sbc::Parts` (DX9, 160 B, ctor `sub_942750`) **H**

| Off | Field | Meaning |
|---|---|---|
| +4 | mActive | switched by `activateParts` (by group_id); ctor 1 |
| +5 | (IDB "mEnable") | **"in the moving list"**: set when a matrix is given, cleared when it's removed. `enumSomeContacts` skips parts with it set, so they are tested only by `check_moving_parts`. |
| +6 | (IDB "mEnableRotate") | sticky: set once the matrix's 3x3 isn't identity |
| +0xC | | index in `mMovingPartsArray` |
| +0x10 | mCoord | **inline** MtMatrix (current) |
| +0x50 | mCoordOld | inline MtMatrix (previous) |
| +0x90..0x92 | MoveX/Y/Z | per-axis "moved" flags that feed `Sbc.mMoveX/Y/ZNum` |
| +0x93 | mMatResetSet | the last `reset` argument; ctor 1 |

`collision_findings.md` calls `mCoord` / `mCoordOld` pointers; they are inline matrices.

### Setters

`sub_946E60` (by ID) loops over the groups and calls `sub_946AE0(matrix, partIndex, sCol, sbc, reset)` for each
`group_id == partsId`. Under the sCollision critical section, `sub_946AE0` does:

- **First time:** append the part to the moving list (+5 = 1).
- **+6:** set when the 3x3 isn't identity.
- **Per axis:** MoveX = !(column x == (1,0,0) && tx == 0), etc. (MT row-major), keeping the `Sbc.mMove*Num` counters in step.
- **`mMatResetSet = reset`.**
- **`mCoordOld = reset ? new : old mCoord`** (`sub_9405C0`), then **`mCoord = new`** (`sub_940560`).
  - **reset = 1 is a teleport:** no delta, so nothing is swept or carried. It is used for the first placement (setup) and
    for warps (`moveSt303X` reset branch).
  - **reset = 0 is continuous motion:** the delta is the previous frame's matrix to this one.
- **A NULL matrix** removes the part from the moving list and resets both matrices to identity.

### Which matrix

| User | Matrix | Part ID | SetScrAttribute arg2 | Sbc type |
|---|---|---|---|---|
| `uStageSetMoveFloor` | own `mWmat` | `mPartsId` | 1 | 16 |
| `uStageSetBreak` (`sub_8629C0` setup, `sub_863000` main; property `mIsMoveColl` +0x18C8) | own `mWmat` when `mIsMoveColl`, else static | 0 | 1 / 0 | 16 / 1 (`registResource(...,1,0)` like the stage) |
| `uStageSetButou` (`sub_8676F0` / `sub_867CD0`, `scr\ware\ko904\ko904-a00/a01`) | own `mWmat` / a built matrix at +0x1450 | 0 | 1 | 16 |
| `uStageSetCatapult` (`sub_869CA0` / `sub_869F00`, ko903-a00) | own `mWmat` (+0xA0) | 0 | 1 | **64** |
| `uEm030GroundParts` setup / move (0x70D870 / 0x70D9D0) | own `mWmat`, on the **owner's** Sbc (the stage's, handle at +0x1370) | 27 + n | — | — |
| `uEm019::setup` 0x64AB80 / `ctrl_em019_scr_hit` | **a joint's world matrix** (`mpJoint[n].mWmat`; the joint is chosen in code) | 0 | **0** | 16 |
| `uEm021_Leaf::setup` 0x69B1A0 (`em21-c00_dome`, `em21-c00_ground`) | a joint's world matrix | 0 | **0** | 16 |
| `sub_8764E0` / `sub_880870` (Em025 stage-set area) | one matrix for every group (loops over all IDs) | each group's own | | |
| `uScrCollMoveTest::move` (`sub_8B5AB0`, debug class) | a matrix at +0xD00 | its own ID | | |

- **The mechanism is shared (H):** register (mask 16, a new Sbc), deactivate or activate by ID, call the matrix setter every
  frame.
- **There is no data-driven joint mapping (H):** a part never follows a model joint by itself. The code picks one matrix
  (the unit's `mWmat` or one hard-coded joint) per part ID.
- Enemies pass `SetScrAttribute(...,0)`, so their SBCs **push but don't carry**.

### World matrix of the floor

- `uModel::updateWorldMatrix` 0x9EA8B0 first calls the uCoord update `sub_A33070`:
  - `mWmat = mLmat * parent.mWmat`
  - or `mLmat * parent.getJointMatrix(ParentJoint)` when `ParentJoint >= 0`
  - `mParent` is `uCoord` +0x18, `ParentJoint` +0x1C. **H**
- `mLmat` comes from `mPos` / `mQuat` (`mAngle`) / `mScale`.
- So a floor parented (`mpParent`) to another floor rides with it. st406 `elv00D` parents two collision-only
  MoveFloors (`st406-a01` id 1, `st406-a03` id 3) to the elevator unit.

## 3. Space of a moving `.sbc` and its boxes

**Query path for a moving part (H):**
1. `query_all_sbcs` 0x95E350: if `mMoveX+Y+ZNum > 0`, the header bbox cull is skipped (0x95E506).
2. `check_moving_parts` 0x95F050, then `moving_part_aabb_test` 0x95E5E0, then `check_part_narrow` 0x95F0C0:
   - `fill_contact_packet` copies `mCoord` to packet +0x30 and `mCoordOld` to +0x70.
   - The shape's bounds callback **inverts the matrix** and returns the query AABB **in part-local space**.
     - `collBounds_LineSeg` 0x9532C0: a general 4x4 inverse of `mCoord`, +-0.1 margin.
     - `collBounds_DualMatrix` 0x951880: inverts both `mCoord` and `mCoordOld`, so a capsule moves from the old local
       frame to the new one. This is the relative sweep that makes a rising floor push a character up.
   - That local AABB is tested against **`bbox_this`** (vMinThis / vMaxThis).
   - Then `checkAttr` walks the group's own BVH with it.

So for authoring:
- **Vertices** are in the unit's local space: the same space as its `.mod`, game units (cm, Y up). **H** (code) and
  matching data:
  - `st405-a-02` (blade01, `mPos` (0, 0, 2100), spun about Y by `mAngle`) spans x +-1000, z +-1308, centred on the
    pivot.
  - `st406-a02` (elevator, `mPos` 0 at frame 0, then up to 3500) sits where the elevator is at rest.
- **`bbox_this`** must hold the group's geometry in that local space. It's the only broad-phase box for moving parts.
  **H**
- **Header bbox:** skipped while any axis moves. When the matrix is exactly identity (all axis flags 0, e.g. an elevator
  at rest at `mPos` 0 with no rotation), the cull **is** applied with the file bbox, and local == world at that moment.
  So write the union of the groups' local boxes as usual. **H**
- **Top-tree AABBs** (`boxes[k]` / the group records' vmin / vmax) are used only by `enumSomeContacts`, i.e. for parts
  that are not moving. Every group of a moving floor is in the moving list, so they're unused at runtime. Write them as
  for any file. **H**
- **Scale:** the inverse is general, so `mScale` != 1 should work for queries. Unverified for normals and contact
  response. **L**

## 4. Riding (carry)

**Carry code:** in `sub_510D20` (DX9, 0x510D20; the SE equivalent is `uCollisionMgr::checkGround`, which calls
`getRelativeMatrixById`). After the downward ground ray hits:

- **Moving-floor test** (0x511667): `LineResult.pTriangle->surface_attr & 0x40`.
- **The carry** (0x5117A8, when 0x40 is set and the actor was already on moving land last frame, `mOldMoveLand` +0x2E):
  - `sub_946EE0(result.sbc.mSbcHandle, sCol, result.partsInfo->group_id)`. This is `getRelativeMatrixById`: it finds the
    first part with that ID and calls `sub_942D70`.
  - `sub_942D70` returns `inverse(mCoordOld) * mCoord` (row-vector: `p_new = p_old * inv(Old) * New`).
  - The result is multiplied into `uCollisionMgr.mCorrectMat` (+0x80).
- **Flags:** `mMoveLand` (+0x1E) is set. `uCollisionMgr` also keeps `mOldMoveLandSbcHandle` +0x34 and
  `mOldMoveLandPartsNo` +0x38.

**H** (code path and matrix math). **M** (how `mCorrectMat` is applied to the actor afterwards: `uCollisionMgr::checkScr`
0x50E290 hands it to the caller).

Authoring consequences:
- Surface 0x40 is set at runtime by `SetScrAttribute(...,1)`, so you don't need to write it.
  - Writing it in the file is harmless: the relative matrix of a static part is identity.
- Because the delta is old -> new, the matrix must be set **exactly once per frame** with reset = 0. The game does this;
  it's not a file concern.
- Walkable faces must have **+Y normals in local space** (the ground ray is one-sided, `collNarrow_LineSeg`, tested in
  local space) and the usual floor rules (n.y > sin 40°, or surface 0x20). See `sbc_dx9_format.md` §5-6.
- Parts with the same `group_id` share one matrix, and the carry looks up the first part with that ID.

## 5. Data check

| File | Used by | Groups / group_id |
|---|---|---|
| `st405-a-02` | blade01 (`mPartsId` default 0) | 1 group, id 0 |
| `st405-a-03` | blade02-06 (shared, 5 Sbcs) | 1 group, id 0 |
| `st405-a-01` | `ev405_00.pla` MoveFloor (no model, no `mPos`: an event-only toggled collision) | 3 groups, all id 0 |
| `st406-a00` | elevator `elv00D` (`mPartsId` 0) | 5 groups, all id 0 |
| `st406-a01` / `a03` | child floors, ids 1 / 3 | 1 group each |
| `st406-a02` | `elv01U` (`mPartsId` 2) | 1 group, id 2 |
| `st405-a-00` (stage) | static | all 18 groups id -1 |

- **Rule in the data:** every group of a moving-floor `.sbc` has `group_id == mPartsId`.
- The attributes are ordinary: surface 0x10 / 0x20 / 0x13, special 0x10000000 / 0x20000000 / 0x3400 / 0x4B00, type
  0 / 4 / 5.

**How they're played:**
- `blade0N.sdl`: 60-frame loop keying `mAngle.y` 0 -> -pi -> -2pi (mode 3 linear). It's loaded by `st405blademove.pla`
  (`uStageSetScheduler`: `mpSdlRes`, `mLoop` 1, `mStartFrame`, `mSetNo` 101-107).
- That `.pla`'s name is in a hard-coded stage table at 0xDF1E88 (with `ev405_*`, laser, ...), not data-driven.

## 6. Authoring recipe (new moving platform)

1. **`.sbc`:**
   - Mesh in the platform's own local frame (origin = pivot; the same frame as its `.mod`; cm, Y up).
   - Every group's **`group_id` = the unit's `mPartsId`** (use 0, the default).
     - Albam's `sbc_bvh.py` writes **-1** for new meshes. A floor with `mPartsId` 0 would then activate nothing; -1 only
       matches `mPartsId` 0xFFFFFFFF.
   - `bbox_this` and the header bbox in local space; everything else as for a static file (`runtime_attr` 0x3FFFFF00;
     floors face +Y).
2. **`uStageSetMoveFloor` unit**, usually in an `.sdl`:
   - `mpCollision` = the `.sbc`; `mpModel` = the visible `.mod` (optional); `mPartsId` (0).
   - Keyed `mPos` (cm) / `mAngle` (rad) tracks for the motion; leave `mMode` 0.
   - Optional: `mDisp` keys to switch the collision; `mpParent` to ride another unit.
   - The MoveFloor itself never reads `mSetNo` (any value).
3. **Make the game load it** (at least one of):
   - Put the unit, or a `uStageSetScheduler` (`mpSdlRes` = your `.sdl`, `mLoop` 1) into the room's always-loaded files.
     `aRoom::setRoom` 0x40D4F0 loads `scr\stXXX\etc\stXXX` (rPlacement, `uPlacement`) and `scr\stXXX\sdl\stXXX`
     (rScheduler, unpaused and looping). **H** (loads); **M** (that units added there behave like the game's).
   - Or reuse an existing `.pla` / `.sdl` the stage code already loads (e.g. `st405blademove`). New file names can't be
     added to the hard-coded tables.
4. **Limits:**
   - A part follows exactly one matrix (the unit's `mWmat`).
   - Per-part-ID switching only.
   - No joint following for stage sets (only hard-coded in enemy code).
   - u16 vertex / triangle limits per group as in `sbc_dx9_format.md`.
   - Each unit makes its own Sbc (the array is growable; no fixed cap was seen).
   - Queries filter on `Sbc.mType & ContactDefine.type`: the ground check uses 127, which includes 16. Queries with type
     1 only (stage-only) ignore moving floors. **M**

## Function / address index

| DX9 | IDB name today | What it is |
|---|---|---|
| 0x946E60 | sub_946E60 | set the parts matrix by group_id (handle, sCol, id, MtMatrix*, reset) |
| 0x946AE0 | sub_946AE0 | set the parts matrix by part index (the moving list, axis counters, old/new) |
| 0x946EE0 | sub_946EE0 | getRelativeMatrixById (SE name `sCollision::getRelativeMatrixById`) |
| 0x942D70 | sub_942D70 | Parts: `inverse(mCoordOld) * mCoord` |
| 0x9405C0 / 0x940560 | sub_ | Parts set mCoordOld / set mCoord |
| 0x942540 / 0x942750 | sub_ | Sbc set resource / Parts ctor |
| 0x881AD0 / 0x860A50 / 0x861C50 | sub_ | createProperty of uStageSetMoveFloor / uStageSet / uStageSetBreak |
| 0x8629C0 / 0x863000 | sub_ | uStageSetBreak setup / main |
| 0x8676F0 / 0x867CD0 | sub_ | uStageSetButou setup / main |
| 0x869CA0 / 0x869F00 | sub_ | uStageSetCatapult setup / main |
| 0x8B5AB0 | sub_ | uScrCollMoveTest move |
| 0xA33070 | sub_ | uCoord world-matrix update (parent / parent joint) |
| 0x510D20 | sub_ | uCollisionMgr ground check with the moving-floor carry (SE `uCollisionMgr::checkGround`) |
| 0x40D4F0 | aRoom::setRoom | stage SBC (type 1, `SetScrAttribute(,0)`), room `.sdl` and `.pla` |

## IDB edits

The research pass couldn't edit the IDB (the permission system denied the call). These 20 renames were applied
afterwards, on 2026-10-10 (IDB not saved); nothing was commented or retyped:

| Address | Old name | New name |
|---|---|---|
| 0x946E60 | sub_946E60 | `sCollision::setPartsMatrixById` |
| 0x946AE0 | sub_946AE0 | `sCollision::setPartsMatrix` |
| 0x946EE0 | sub_946EE0 | `sCollision::getRelativeMatrixById` |
| 0x942D70 | sub_942D70 | `sCollision::Sbc::Parts::getRelativeMatrix` |
| 0x9405C0 | sub_9405C0 | `sCollision::Sbc::Parts::setCoordOld` |
| 0x940560 | sub_940560 | `sCollision::Sbc::Parts::setCoord` |
| 0x942540 | sub_942540 | `sCollision::Sbc::setResource` |
| 0x942750 | sub_942750 | `sCollision::Sbc::Parts::Parts` |
| 0x881AD0 | sub_881AD0 | `uStageSetMoveFloor::createProperty` |
| 0x860A50 | sub_860A50 | `uStageSet::createProperty` |
| 0x861C50 | sub_861C50 | `uStageSetBreak::createProperty` |
| 0x8629C0 | sub_8629C0 | `uStageSetBreak::setup` |
| 0x863000 | sub_863000 | `uStageSetBreak::main` |
| 0x8676F0 | sub_8676F0 | `uStageSetButou::setup` |
| 0x867CD0 | sub_867CD0 | `uStageSetButou::main` |
| 0x869CA0 | sub_869CA0 | `uStageSetCatapult::setup` |
| 0x869F00 | sub_869F00 | `uStageSetCatapult::main` |
| 0x8B5AB0 | sub_8B5AB0 | `uScrCollMoveTest::move` |
| 0xA33070 | sub_A33070 | `uCoord::updateWorldMatrix` |
| 0x510D20 | sub_510D20 | `uCollisionMgr::checkGround` |

Suggested comments: 0x881D6C (surface 0x40 = carry mark), 0x881D83 (type 16, a new Sbc per unit), 0x881E03 / 0x881EE0
(reset 1 / 0), 0x511667 / 0x5117A8 (the carry).

Struct notes:
- `sCollision::Sbc::Parts` +5 is "in the moving list", not `mEnable`.
- `mCoord` / `mCoordOld` are inline matrices.
