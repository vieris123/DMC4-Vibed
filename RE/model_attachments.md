# DMC4 DX9: spawning extra models at runtime and attaching them to a character

Read 2026-10-27 in the DX9 IDB (`DevilMayCry4_DX9.exe`), names from the SE PDB; read-only (nothing renamed). Goal: a
dmc4_hook unit that loads a `.mod` and follows an owner model, either **rigid** (one joint, like a weapon) or **skin**
(each joint follows the owner joint with the same number, like Nero's face / hair / coat sub-models).

Confidence: **H** = read in the code, **M** = read with part of the context missing, **L** = inference.
Related: `chain_cnschain.md` (sections 1 and 6: coat, chains, sUnit passes, lifetime), `ik_constraint_findings.md`
(cConstraint base), `uDevil4Model_skinmesh.md`.

## 1. The model unit: a bare uDevil4Model

| Item | DX9 | Notes | Conf. |
|---|---|---|---|
| `uDevil4Model::DTI` | 0xE58838 | size field 0xEA0, parent uModel::DTI 0xEADDC0. DTI vtbl slot 1 (newInstance) = 0xB2C9A0 `return 0`: **not creatable through its DTI**, allocate + ctor by hand | H |
| size | **0xEA0** | SE 0x11D0 | H |
| ctor | **0x5226F0** `uDevil4Model::uDevil4Model`, `__thiscall` (ecx = memory), no stack args, `retn`, returns this | calls uModel ctor (usercall edi) -> uCoord ctor 0xA325E0 | H |
| allocator | UnitAllocator (`*(MtHeapAllocator**)0xE1434C`, dmc4_hook `mt_allocate_heap(size, 16)`) | the deleting dtor frees with it | H |
| vtable | **0xBC8B38**, code slots 0..31 (slot 32+ is string data) | | H |
| vtbl[0] | 0x522980 deleting dtor `(flag)` thiscall `retn 4` -> 0x5229B0 (handlers, freeze textures) -> uModel dtor body 0x9E6AB0 (joint array, shader handles, 16 motion banks, materials, **releases mpRModel**), then UnitAllocator free if flag & 1 | H |
| vtbl[5] +0x14 | init = nullsub 0x507330 | H |
| vtbl[6] +0x18 | **move 0x522CA0** (`thiscall`, `retn`): freeze fade, moveJoint, moveMaterial, movePart, mShape, `uModel::moveMotion`, `updateLocalMatrix` 0x9E87E0, `updateWorldMatrix` 0x9EA8B0, plane clip, camera transparency | H |
| vtbl[7] / [8] | moveEx / moveAfter = nullsub 0x507330 | H |
| vtbl[9] +0x24 | draw 0x522DC0 (`thiscall(cTrans*)`, `retn 4`): skipped while `mTransparency` (+0xE20) <= 0; else uModel::draw | H |
| vtbl[12] +0x30 | kill 0x42BAB0: state 1/2 -> 3 unless attr FIX (flags & 0x2000) | H |
| vtbl[13] / [14] / [15] / [16] | updateLocalMatrix 0x9E87E0 / updateWorldMatrix 0x9EA8B0 / **getWorldMatrix 0x9EA870** / **setModel 0x9E6D70** | H |

dmc4_hook already does this: `BrainrotPalace.cpp` (uDevil4ModelCons 0x5226F0 + setModel via vtbl+0x40 + addBottom on line 8)
and `AfterImage.cpp` (uDevil4Models embedded in a custom uActor, parented with mpParent / ParentJoint, drawn from the
owner's draw slot).

### Header after the ctor (uCoord ctor 0xA325E0, uModel ctor) (H)

| Off | Field | Value |
|---|---|---|
| +0x04 | cUnit flags (bits 0-2 state, 3-9 line, 10-15 attr) | low 16 bits 0x4DF9: state 1 INIT, attr MOVE 0x400 / DRAW 0x800 / VISIBLE 0x4000 |
| +0x06 | TransMode byte (cTrans::MODE mask the view must share) | 0x27 (WORLD, REFLECTION, SHADOW_RECV, MOTIONBLUR; **no SHADOW_CAST 0x08**) |
| +0x07 | TransView byte | 0x0F |
| +0x10 | delta time | 1.0 (sUnit::move rewrites it every frame for every unit of the line) |
| +0x18 | uCoord mpParent | 0 |
| +0x1C | uCoord mParentNo (SE name; dmc4_hook `ParentJoint`) | -1 |
| +0x20 | mOrder (u16) / mParentFlags (u16, SE) | 4 / 0 (mParentFlags not read by the DX9 world pass) |
| +0x30 / +0x40 / +0x50 | mPos / mQuat (x y z w) / mScale | 0 / identity / 1 |
| +0x60 / +0xA0 | mLmat / mWmat | identity |
| +0x130 / +0x134 / +0x138 | mLightGroup / mShadowCastGroup / mShadowRecvGroup | 3 / 1 / 1 (setModel then sets mLightGroup from the .mod header, rModel+0xF8) |
| +0x13C | mPartsDisp[16] | 0xFF (all parts on) |
| +0x280 | RenderInfo: +0x284 mRenderMode 1, +0x288 mVFCullLevel 3, +0x28C mZPrepassDist 2000, +0x290 mMotionBlurDist 5000, +0x294 mPriorityBias 0, +0x298 mLOD -1, +0x2A0 mSOEnable 1, +0x2A4 mpModel = this | |
| +0x2E0 / +0x2E4 / +0x2E8 | mJointNum / mpJoint (0x90 each) / mJointTable (u8[256], joint number -> index, 255 = none) | 0 / 0 / a static 0xFF table |
| +0xA30 | mpRModel | 0 |
| +0xA38 | mpMotionListArr[16] | 0 |
| +0xD08 | mCameraTransparencyEnable | 1 (fades when the camera is close; AfterImage turns it off) |
| +0xE20 | mTransparency | 1.0 |

Joint (0x90, `uModel::Joint`): +0x04 mAttr, +0x05 parent index (0xFF = model root), +0x06 mType (0 after setModel),
**+0x07 mNo (joint number)**, +0x08 symmetry, **+0x0C mpConstraint**, +0x10 mOffset, +0x1C mLength, +0x20 local quat,
+0x30 local scale, +0x40 local trans, **+0x50 mWmat** (dmc4_hook's `UModelJoint` says 0x48 because its MtVector3 is
packed differently; the size 0x90 holds). (H, setModel / updateWorldMatrix / getWorldMatrix)

### Giving it the .mod: `uModel::setModel` 0x9E6D70 (H)

`__thiscall(ecx = model, rModel*)`, `retn 4` (vtbl[16]; dmc4_hook `uactor_sdk::get_model`).
- Releases the old rModel, frees the old joint array and shader handles, **addRefs** the new rModel (so the caller
  releases the ref sResource::create gave it, as `uPlayerNero::initModel` 0x7E3760 does).
- `mJointTable` = rModel+0x120 (inside the resource). `mLightGroup` = rModel+0xF8 (`model_info.light_group`).
- Allocates `mJointNum` joints (UnitAllocator, 32-aligned, count stored before the array) and fills each from the rModel:
  number, parent, offset, length, **bind pose** (quat from rModel mLmat, trans = offset, scale 1), mWmat = bind,
  **`mpConstraint = 0`**. So constraints must be installed **after** setModel, and a second setModel on the same
  model frees the joint array (every pointer into it dangles).
- Motion work buffers (one per blend slot, `mState |= 2` = rebind on the next moveMotion), envelope shader handles
  (SkinRemap), bounding sphere, then `uModel::setMaterials`.
- Textures: the rModel's own load (rModel vtbl[8] 0xA53F50) fetches its textures by path (sub_A53CC0: rTexture, then
  r2Texture / rRenderTargetTexture, 0x80 then 1 mode). Nothing else has to be loaded (H for the call, M for the
  full dependency list).

rModel (DX9 type): +0x60 mJointInfo (0x18 each), +0x64 **mJointNum**, +0x68 mLmat, +0x6C mImat, +0x80 / +0x84 envelopes,
+0xC0 bounding sphere, +0xF8 light group, +0x120 joint-number table. DTI **0xEADF48** (`rModel::DTI`). (H)

### What makes it draw (H)

No sRender registration. `sUnit::draw` 0x8DC130 walks lines 0..31 (line flag bit 2; every line has it, `sUnit::sUnit`
writes 0x1FD) and calls `unit->vtbl[9](cTrans)` when: state == 2, attr DRAW (0x800) and VISIBLE (0x4000),
`TransView byte (+7) & (1 << cTrans->mGeoBufferUsed)`, and `TransMode byte (+6) & context mMode`. So the ctor
defaults draw; clearing 0x4000 hides it. Shadows: set TransMode |= 0x08 to cast (L for the bit meaning, from
`cTrans::MODE` in `efl_import_plan.md`).

### Per frame without a motion (M)

`moveMotion` seeds each blend slot's work buffer from the joints' current local values (the bind pose after setModel)
and `updateLocalMatrix` blends only slots with `mInterCount != 0`, so a model with no motion bank holds its bind pose
(BrainrotPalace shows a static model in game). Joint types (mType 3..43, look-at / twist helpers) are all 0 after
setModel.

## 2. The frame order (H)

`sDevil4Main::move` 0x8AEE80: **move** pass (lines 0..31, `sUnit::move` 0x8DC290, units of a line may run as parallel
jobs), then **moveEx** (0x8DC3D0, same job rule), then **moveAfter** (0x8DC260 -> sUnit vtbl[9] 0x8DC480 per line:
**serial**, lines 0..31 in order, state 2 + attr MOVE -> unit vtbl[8] +0x20). Then draw.

Where the owners finish their matrices:
- **Players:** `uPlayer::moveEx` 0x7A8860 -> `uPlayer::updateMatrix` 0x7A8D40 (body updateLocal + updateWorld, then
  weapons' updateMatrix vtbl[79]); `uPlayerNero::moveEx` 0x7E4070 then updates face (player+0x3270), hair (+0x4340)
  and coat (+0x52C0). In **moveAfter**, `uPlayerNero::sync` 0x7E42F0 runs `uPlayer::updatePosConst` 0x7AF1F0 (when
  the player is position-constrained to another unit, e.g. grabs: moves it and calls updateMatrix vtbl[78] again) and,
  if player+0x20CC is set, updates the three sub-models again.
- **Enemies / plain models:** `uDevil4Model::move` in the move pass.

So an attached model has the owner's final pose only if it updates **in moveAfter on a higher line than the owner**
(players are on 13, enemies 15 / 16 / 18: from dmc4_hook's CnsChain notes, M). A model left on its default move slot
updates in the move pass, before the player's moveEx: one frame behind the player.

## 3. Rigid attachment: uCoord mpParent + mParentNo (H)

`uCoord::updateWorldMatrix` 0xA33070 (called first by uModel::updateWorldMatrix):
- If `mpParent` (+0x18) is set and its state is 1 or 2: `P = mpParent->vtbl[15](mParentNo)` (uModel::getWorldMatrix
  0x9EA870, `thiscall(int no)`, `retn 4`: `no < 0` or `mJointTable[no & 0xFF] == 255` -> the parent's mWmat +0xA0,
  else `&mpJoint[idx].mWmat` (+0x50)). **mParentNo is a joint number**, not an index. Then `mWmat = mLmat . P`
  (row vectors), or `mLmat . parent->mWmat` when mParentNo < 0.
- Else (no parent, or the parent dying / dead: state 0, 3, 4): **mpParent is nulled** and `mWmat = mLmat`.
- Then the rows of mWmat are scaled by mScale (+0x50).
- mLmat comes from mPos / mQuat only (uCoord::updateLocalMatrix 0xA32EF0, called from uModel::updateLocalMatrix).

So: `mpParent = owner`, `mParentNo = owner joint number`, `mPos` / `mQuat` = the offset in that joint's frame (cm,
quaternion x y z w), `mScale`. The model's root joints then compose from mWmat. The parent's matrix is read when the
child's world pass runs: see section 2.

Game users: weapons (`uPlWpRedQueen::update` 0x838A50 writes weapon+0x18 = player and +0x1C =
`dword_C3BB18[motion-sequence value]`, a joint number table; `uPlayer::updateMatrix` then runs the weapons' local +
world pass right after the body's), AfterImage (dmc4_hook: head / hair ParentJoint 4, jacket 2). Nero's face / hair
/ coat set `+0x18 = player, +0x1C = -1` (follow the player root) and attach their joints with cCnsMatrix instead.

## 4. Skin attachment: one cCnsMatrix per joint (H)

### cCnsMatrix (SE `cCnsMatrix : cConstraint`, 0x70 bytes, align 16)

| Off | Field | Default (owners' inline ctor, e.g. kMdlCoat ctor 0x7E2099, newInstance 0x4432E0) |
|---|---|---|
| +0x00 | vtable **0xB9919C** | |
| +0x04 | mBlendWeight | 1.0 |
| +0x08 | mRno u8[4] | 0 |
| +0x0C | mBlendVel | 0.02 |
| +0x10 | mBlend | 1.0 |
| +0x14 | mRate | 1.0 |
| +0x18 | mIgnoreRate | 0 |
| +0x19 | **mEnable** | 1 |
| +0x1C | mID | 0 |
| +0x20 | **mOfsMat** | identity (cCnsMatrix::cCnsMatrix 0x443350, `usercall eax = this`, sets only +0x20 and +0x60) |
| +0x60 | **mpMat** (source matrix pointer) | 0 |
| +0x64 | **mMode** (`CNS_MODE_ALL` 0, `CNS_MODE_ROT` 1) | 0 |

DTI `stru_E56EC8` (registered by 0xB6E630, size 112). vtbl: [0] 0x455B10 dtor (just resets the vtable, frees with
GlobalAllocator if flag & 1: owns nothing), [3] createProperty 0x447650 (mEnable, mBlend, mBlendVel, mBlendWeight),
[4] getDTI 0x4432D0, **[5] +0x14 adjust 0x443430** (SE `cCnsMatrix::adjust(uModel::Joint*, uModel*)`, `thiscall`,
`retn 8`), [13] move nullsub, [14] cConstraint::composeWorldMatrix 0x4477E0.

### adjust 0x443430

Runs only if `mEnable` and `mpMat`. Mode 0: `joint.mWmat = mOfsMat . *mpMat`. Mode 1: the same with the source's 4th
row replaced by the joint's own FK translation (rotation from the source, position from the joint's parent chain).
**No blend:** mBlendWeight / mBlend / mRate aren't read. With the identity offset, mode 0 copies the source verbatim.

### How the world pass uses it (uModel::updateWorldMatrix 0x9EA8B0)

For every joint in array order: FK `mWmat = local(quat, trans, scale) . parent.mWmat` (parent index 0xFF -> the model's
mWmat), then `if (joint->mpConstraint) mpConstraint->vtbl[5](joint, model)`. Children read their parent's mWmat when
their turn comes, so **they compose from the constrained result** (rModel joints are parents-first). Joints without
a constraint stay plain FK from their parent, so the joints the owner lacks (coat tails) follow the constrained ones
and a uCnsChain can drive them.

### What the game does (uPlayerNero::initModel 0x7E3760) (H)

```
r = sResource::create(sDevil4Resource, &rModel::DTI, "model\\game\\pl000\\pl000_01", 1);
face.vtbl[16](r)            // setModel
cResource::release(r)
// sources: body joints (by number) 2, 3, 4, 5, 9 -> cnsMtrx[0..4].mpMat = &bodyJoint.mWmat
// installs: face joints (by number) 0..4: joint+0x0C = &cnsMtrx[k]
face +0x134 / +0x138 = shadow groups from sMediator +0x84..0x87, Render.mPriorityBias = -100
face +0x18 = player, +0x1C = -1;  player+0x20C0 = &face;  uPlayer::setFaceModel(player)
```
Hair (+0x4340): joints 0, 1 follow **face** joints 1, 2. Coat (+0x52C0): joint 0 follows body joint 2. The sub-models
are `kMdlHead { uDevil4Model mdl; cCnsMatrix cnsMtrx[5]; }`, `kMdlHair { mdl; cnsMtrx[2]; }`, `kMdlCoat { mdl;
cnsMtrx[1]; cClothCtrl clthCtrl[6]; }` (SE types; DX9 offsets: matrices at +0xEA0, stride 0x70). The constraints are
installed **once** (the face / body joint arrays live as long as the player). So one cCnsMatrix per joint is the
game's own skin attachment.

### uCnsMatrix: the game's one-joint attach unit (H; not used by any DX9 `.sdl`, M)

DTI 0xE58598 (size 0xA0, SE 0xB0), newInstance 0x4FCD00 (UnitAllocator 0xA0, ctor inline: cUnit 0x4DF9 / +7 0xF,
cCnsMatrix at +0x20), vtable 0xBC71BC: +0x90 mpParentModel, +0x94 mpChildModel, +0x98 mParentJntNo, +0x9C mChildJntNo.
- `setParentJntNo` 0x4FD100 (`thiscall(int no)`, `retn 4`): needs mpParentModel; `mpMat (+0x80) = &parent joint(no).mWmat`.
- `setChildJntNo` 0x4FD170 (same convention): needs mpChildModel; clears the old child joint's +0x0C, installs
  `&mCnsMat` (+0x20) in the new one.
- move 0x4FCEA0: only nulls mpParentModel / mpChildModel that aren't state 1 / 2 (**mpMat keeps pointing into a dead
  parent's joints**).
- kill vtbl[12] 0x4FCE00: clears the child joint's +0x0C, zeroes mpMat and both models, state -> 3 unless FIX. Its
  dtor 0x4FCDD0 clears nothing, so it must be killed through vtbl[12].
One joint per unit, so a whole skeleton needs one unit per joint; the embedded array is simpler.

## 5. Motion (H unless marked)

- Skin mode: constrained joints are overwritten after FK each frame, so their motion is irrelevant; unconstrained joints
  hold the bind pose (M) or a chain's solve. No motion is needed.
- Rigid mode: bind pose, no motion needed (M).
- Playing the owner's motions later: load the LMT into the model's banks (`mpMotionListArr` +0xA38; dmc4_hook
  `load_motion_bank`) and request motions on it. The players do this for the coat: `uPlayer::requestSetMotion`
  0x821210 mirrors the request into the coat's controllers (dmc4_hook comment; not traced here, L).

## 6. Lifetime and safety

- Kill: unit vtbl[12] (respects FIX) or `flags = (flags & ~7) | 3` (dmc4_hook `despawn`). sUnit then goes 3 -> 4 ->
  unlink + `vtbl[0](1)` over the next two move passes; the deleting dtor releases the rModel, motion banks and
  materials and frees the joints and the unit. **Don't** also call the dtor or free the memory yourself (H).
- Pointers only go from the extra model to the owner (mpParent, cCnsMatrix mpMat); the owner holds nothing of ours, so
  killing ours is always safe (H).
- **Owner dies first:** its memory lives until two move passes after its kill (state 3, then 4, then deleted in the
  move pass). The uCoord world pass nulls mpParent on its own when the owner's state isn't 1 / 2, but **cCnsMatrix
  mpMat isn't checked**: our own update must see state 3 / 4 and clear the constraints before calling the world pass.
  Checking every frame in moveAfter always catches 3 or 4 before the free (H for the state sequence).
- **Owner re-runs setModel** (any model swap): its joint array is freed and reallocated (H), so re-point mpMat from the
  owner's `mJointTable` / `mpJoint` every frame instead of caching.
- **Room change** (`aRoom::cleanRoom` -> `aRoom::killUnit` 0x40E100): `sUnit::killAll(line)` 0x8DC6F0 calls every
  unit's vtbl[12] on lines 1, 7-11, 13-16, 18-21, 23-25, 29, 31, then 0, 2-6, 12, 26, 31 (`GameMoveLineTbl` 0xDF3AD4).
  The default kill respects FIX (0x2000), so a FIX unit survives (H). Lines 17, 22, 27, 28, 30 aren't killed (H).
- **Chains on the extra model** (uCnsChain): `~cCnsChain` and `setEnable(false)` zero `joint+0x0C` of every joint of
  the model, ours included (chain_cnschain.md section 6), and a chain re-registers its own joints every frame in the
  move pass. One joint holds one constraint, so reinstall ours every frame (before the world pass) and only on joints
  no chain uses (H for the mechanics).
- Visibility: the players draw themselves, their weapons and sub-models only while `uActor::mbActorTrans` (+0x12DC,
  bool) == 1 (`uPlayerNero::draw` 0x7E4440, `cWeaponCtrl::draw` 0x7B1130; weapons also with their own +0x1390), and each
  sub-model only when its TransMode byte & the context mode (H). What sets mbActorTrans (cutscenes, Devil Trigger)
  wasn't traced (L). A separately drawn model has to mirror it: clear attr VISIBLE 0x4000 when the owner's
  mbActorTrans is 0 or the owner lacks DRAW / VISIBLE.
- Culling: keep `mpParent = owner` in skin mode too (as the coat does), so the model's own mWmat and bounds follow the
  owner (mVFCullLevel 3 by default; the boundary code wasn't read, M).

## 7. dmc4_hook notes (read 2026-10-27)

- `devil4_sdk::sUnit_spawn(obj, line)` = `sUnit::addBottom` 0x8DC540 (eax = sUnit, esi = unit, push line, `retn 4`). H.
- `uactor_sdk::uDevil4ModelCons` (0x5226F0, ecx) and `get_model` (vtbl+0x40 setModel) are right. `uDevil4ModelDest`
  calls 0x5229B0, the non-deleting body (leaves the unit memory).
- `uactor_sdk::get_joint_from_index` is broken: `pushad` without `popad` and a `ret` inside inline asm.
- `BrainrotPalace::on_stage_end` destroys its model three ways (0x5229B0 body, despawn, `destructor_call` = vtbl[0](1)
  which already frees it, then `unit_deallocate`): a double free, and sUnit still holds the despawned unit. Despawn
  alone is enough.
- `cUnit.hpp`'s `UNIT_ATTR` values are the attr field (bits 10-15): MOVE 1, DRAW 2, SELECT 4, FIX 8, VISIBLE 0x10.

## Gaps

- Not run in the game: the moveAfter vtable swap, skin mode on a full body rig, the owner-death path.
- Which vanilla units sit on lines 14, 19-21, 23-25, 29 (a free line above the owner's is the only requirement).
- mbActorTrans writers; the Devil Trigger model handling (any owner setModel is covered by re-pointing every frame).
- rModel inverse-bind convention (mImat +0x6C) for a body-space rigid offset (section 3 / spec): not checked.
