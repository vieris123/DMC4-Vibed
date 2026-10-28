# EFL → Blender import — implementation plan

Status: **plan only, nothing implemented.** Written 2026-10-05. It builds on `RE/uEffectVFR_findings.md`,
`RE/efl_generator_struct.md`, `RE/particle_type_structs.md` and `RE/particle_move_param.md`. All offsets here
are **DX9** offsets taken from DX9 code unless marked otherwise. Do not borrow SE offsets: the two builds diverge
(see the SE cross-check notes in `particle_type_structs.md`).

**Corpus run 2026-10-05** (`RE/scripts/efl_corpus_stats.py`) checked §3 against every `.efl` under
`E:\DMC mod stuffs`. Corrections from it are marked *(corpus)* below.

---

## 1. Goal and scope

Read DMC4 DX9 `.efl` effect lists into an engine-independent data model. Then:
1. dump that model as JSON for inspection and diffing;
2. regenerate `RE/efl.bt` (010 Editor) from the same layout definitions;
3. import it into Blender, in two levels:
   - **Static** (M1): every generator becomes an Empty with all parameters attached. PrimModel particles become real
     meshes, and particles get materials with texture references.
   - **Dynamic** (M2): Geometry Nodes simulations that approximately replay emission, motion and lifetime.

**Non-goals for now:** exact runtime fidelity (the game simulates on the CPU with its own RNG table), export back to
`.efl` (kept possible by design, see §9), and effects that only exist as post-processing (Filter, LensFlare, Hit).

---

## 2. Architecture

> **Decision 2026-10-05: built inside Albam**, not as the separate packages sketched below. The parser lives in
> `albam/engines/mtfw/efl/` (pure Python, relative imports). The Blender import will register as a dmc4 `efl` import
> function, so it reuses the Game Files browser, `.tex` conversion, `rfs.get_vfile` path lookup and the armature
> (`ParentNo` = the joint number Albam stores as `bone['mtfw.anim_retarget']`; see §6). There is no `.arc` extractor
> (§5 M0). The layout below remains a guide for responsibilities.

```
efl/                         pure Python 3.10+, no Blender / no third-party deps
  schema.py                  single source of truth: every struct, field, offset, type, evidence tier
  binio.py                   little-endian reader/writer helpers, MtRangeF/MtRangeU16/MtColor/MtVector types
  container.py               header + 16-byte record table + block slicing
  blocks/                    generator.py, particle.py (common chain + per-type), life.py, move.py, keyframe.py
  model.py                   dataclasses: EffectList, Generator, ParticleParam, LifeParam, MoveParam, Keyframe
  parse.py                   bytes -> model (unknown regions preserved as raw bytes)
  write.py                   model -> bytes (round-trip; see §9)
  export_json.py             model -> JSON (with evidence tier per field)
  gen_bt.py                  schema -> RE/efl.bt
  tools/arc.py               MT Framework .arc extractor (sample acquisition)
  tests/                     corpus round-trip + invariants (§7)

io_import_efl/               Blender add-on (thin layer over efl/)
  __init__.py                bl_info, operator, import options
  build_static.py            collection, empties, custom props, materials
  primmodel_mesh.py          Ring/Sphere/Grid mesh builders (port of the DX9 builders)
  nodes/                     Geometry Nodes groups for the dynamic import (built in code, versioned)
  build_dynamic.py           wires generators to the node groups, keyframes -> F-curves
  coords.py                  axis/unit/quaternion conversion
```

Rules:
- **One schema drives everything.** `schema.py` describes each struct as rows of
  `(offset, name, type, evidence, note)`. The parser, the JSON exporter, the 010 template generator and the docs all
  read from it, so a correction is made once.
- **Evidence tiers are carried through:** `dx9` (verified in DX9 code), `se` (name from the SE PDB, DX9 layout
  agrees), `prior` (inherited name, unverified) and `unknown` (raw bytes). JSON and Blender custom properties keep the
  tier so nobody mistakes a guess for a fact.
- **Unknown bytes are never dropped.** Every block keeps its full byte span. Typed fields are views onto it, and gaps
  are stored as raw bytes, so round-tripping is exact even before the format is fully understood.

---

## 3. Format specification (current knowledge)

### 3.1 File header — DX9-verified (`rEffectList::load`)

| Off | Type | Field | Notes |
|---|---|---|---|
| 0x00 | char[4] | magic | `'EFL\0'` (dword `0x004C4645`) |
| 0x04 | u32 | version | must equal `0x20070801`, otherwise the load fails |
| 0x08 | u32 | contentSize | passed to the content allocator (`sub_A3DC50`); the copy length is `rEffectList+0x68` |
| 0x0C | u32 | EffectListNum | number of 16-byte records |
| 0x10 | u32 | unitGenRecord | packed `(off<<8)\|type` → child/unit generator block (`rEffectList.GeneratorType`) |
| 0x14 | u32 | unitMoveRecord | packed `(off<<8)\|type` → child/unit move block (`mGeneratorMoveType`) |
| 0x18 | f32 | mBaseFPS | base frame rate of all frame counts in the file |
| 0x1C | u32 | ? | unread by `load`; 0 in every DX9 file *(corpus)* |
| 0x20 | — | content | copied verbatim to `ContentPtr`; **all offsets below are relative to file+0x20** |

*(corpus)* In every DX9 file, `contentSize` = file size − 0x20. `mBaseFPS` is 60.0, except 30.0 in 10 files. The unit
records at 0x10/0x14 are non-zero in only 4 files. Other versions exist: `0x20120306` is SE (all of `Demo/` and
`arc files/`), and `0x20080415` appears in 5 files in `arctool/uPl01ShebaCos2`. Only `0x20070801` is in scope.

### 3.2 Record table — DX9-verified (`create_resource_infos`, `createGenerator`)

`EffectListNum` records of 16 bytes at content+0. Each is four dwords, `dword = (offset << 8) | typeByte`, and an
offset of 0 means the slot is absent:

| Slot | Block | Type byte | Consumer |
|---|---|---|---|
| 0 | `EFL_GENERATOR` | (to verify: group/generator selector). Only 1 (6,604) and 2 (10,756) occur *(corpus)* | `initGenerator`, `createGeneratorResources` |
| 1 | particle param | **particle type** (0–17, enum below) | `initGeneratorParam`, `create_particle_resources` |
| 2 | life param | life type. Only 1 (17,068) and 2 (75) occur; absent in 217 records *(corpus)* | `initGenerator` (layout not yet reversed) |
| 3 | move param | **move type** (0–6) | `create_move_resources`, the move dispatchers |

- **Record filter (DX9-verified 2026-10-06).** `createGenerator` builds a record only when
  `uEffectVFR::matchGeneratorFilter` (0x9DD560) passes: `(gen+0x00 GroupFlag & this->mGroupFlag) != 0 &&
  (gen+0x04 MaterialFlag & this->mMaterialFlag) != 0` (`mMaterialFlag`, uEffectVFR+0x19C, was `mpParamBlock`).
  It runs once per build, so changing the masks later has no effect until the generator is rebuilt. If no record
  passes, the effect fails to build and isn't shown at all.
  - The masks come from the spawn call: `sDevil4Effect::setEffectConst(listNo@eax, fileNo@edx, parent, groupMask,
    materialMask, unitLine, owner)` -> `setParamConst`, and the `SetEffectStay(Dir)` -> `setParamStay(Dir)` variants
    (0x96A100 / 0x96A210). The constructor defaults both to 0xFFFFFFFF.
  - Over 1,246 `setEffectConst` call sites: 864 pass 0xFFFFFFFF / 0xFFFFFFFF (all records). The rest pick a variant
    by group (1, 2, 4, 8, 0x10, 0x20, 3, 7, ...), e.g. Dante's Gilgamesh attacks pass group 7 or 3.
  - The material mask is usually computed: `uPlayer::getEfctMtrlFlg` / `uEm000Base::getMtrlInfo` cast a ray down
    from the character and pass the hit face to `cUtil::getEfctMtrlFlg` (0x45F780), which maps the face's surface
    dword (+0xC, probably SBC `surface_attr`) to one bit:

    | Surface ids | Bit |
    |---|---|
    | 1-8, 0x18, 0x1F-0x21 | 0x01 |
    | 9-0xC, 0x1E | 0x02 |
    | 0x10-0x11 | 0x04 |
    | 0x12-0x17 | 0x08 |
    | 0xD, or any face in wet jungle weather (attr+8 & 0x7F00, not attr+0x14 & 0x1000) | 0x10 |
    | 0x19, 0x1A, 0x1D | 0x20 |
    | 0x1B | 0x40 |
    | 0xE-0xF | 0x80 |
    | no hit / other | 0 (no record matches) |

  - *(corpus, 1,109 files)* GroupFlag: 0xFFFFFFFF in 12,803 generators, then 1 (1,734), 2 (1,233), 4, 0x20, 8, 0x10,
    combinations. MaterialFlag: 0xFFFFFFFF in 14,781, then 0x80, 0x10, 0x7F, 0x6F, 0x0F, 0x60, 0x90. 301 files mix
    group values and 165 mix material values (e.g. Dante's `ec005_*` landing effects carry one record set per
    surface: 0x0F / 0x10 / 0x60 / 0x80).
- Block lengths aren't stored. Infer each one as the distance to the next block offset in the file and cross-check
  it against the schema size (§7). The last block ends at `contentSize`. An inferred length includes any
  self-relative keyframe/culling data stored after the block, so only the **minimum** per type is the struct size.
- *(corpus)* Blocks are laid out grouped by slot: all generators, then particles, life and move blocks. No block is
  referenced by more than one record, and no offset is shared between slots, so the model can own blocks per record.

**Particle types** (writer-verified):

| Value | Type | Value | Type | Value | Type |
|---|---|---|---|---|---|
| 0 | Billboard | 6 | PrimModel | 12 | PolygonStrip |
| 1 | Polyline | 7 | LensFlare | 13 | Texline (alt) |
| 2 | Polygon | 8 | MassBillboard | 14 | Line (alt) |
| 3 | Texline | 9 | Filter | 15 | PolygonStrip (alt) |
| 4 | Line | 10 | Light | 16 | LiteBillboard |
| 5 | Model | 11 | Hit | 17 | SizeBillboard |

**Move types:** 0 None, 1 Add, 2 Mul, 3 PathStrip, 4 PathChain, 5 PathKeyframe, 6 PathLine.

### 3.3 `EFL_GENERATOR` (0x1E0 on disk) — slot 0

*(corpus + dx9, 2026-10-05)* The size is **0x1E0**, not the IDB type's 0x1E4.
- 16,000 of 17,360 generator blocks are followed directly by the next block at +0x1E0.
- Longer blocks (up to 0x550) carry keyframe data after +0x1E0, reached through the five self-relative offsets at
  0x1CC–0x1DC.
- `initGeneratorParam` (0x96AEC0) reads up to 0x1DC and never reads 0x1E0.

**The IDB type `rEffectList::EFL_GENERATOR` was retyped to this layout on 2026-10-05** (now 0x1E0). Before that it was
shifted by 2–4 bytes between 0x74 and 0xAF and was wrong at 0xB8. The old declaration is saved in
`RE/type_backups/EFL_GENERATOR_0x1E4_before_2026-10-05.h`. IDB names for the uncertain fields: `SetNum` @0xA8
(probable), `uknRangeU16_0xac`, `LoopFrameDist` @0xB8, `KeyframeScaleParamOffset` @0x1CC and
`KeyframeParamOffset_1d0/1d4/1d8/1dc`. Each member comment carries its evidence.

| Off | Type | Field | Tier |
|---|---|---|---|
| 0x0B | u8 | RandomNoNum | dx9 (read) |
| 0x10 | ?[8] | RandomNo | dx9 |
| 0x30 | MtFloat3 | Pos | dx9 (`moveUnitGenerator` → `setQuatParentOfs`) |
| 0x3C | s32 | ParentNo (joint index) | dx9 |
| 0x40 | MtVector4 | Quat | dx9 |
| 0x70 | bitfield u32 | Order / AxisType / RelationType | IDB names, unverified |
| **0x74** | MtRangeU16 | WaitFrame | **dx9**: `initGeneratorParam` 0x96B1C0–0x96B1E9 computes `word[0x74] + rand % (word[0x76]+1)` → Generator +0xCE. (IDB: 0x76) |
| **0x78** | MtRangeF[3] | Scale | **dx9**: 0x96B339–0x96B395, `rand × [0x7C] + [0x78]`, likewise {0x80,0x84}, {0x88,0x8C} → Generator +0x44/+0x48/+0x4C. Skipped when the 0x1CC keyframe offset is set. (IDB: 0x7C) |
| **0x90** | MtRangeF[3] | Range (spawn-shape extents) | **dx9**: `uknGenBehaviorFunc2` 0x998F5F passes `&gen[0x90]` to the spawn-shape function `sub_999040`, which uses `[0]`, `[2]`, `[4]` as x/y/z extents per `RangeType`. (IDB: 0x94) |
| **0xA8** | MtRangeU16 | ? (SetNum?) | corpus: base 1 in 60%, up to tens; range almost always 0. No reader found yet |
| **0xAC** | MtRangeU16 | ? (SetNum?) | corpus: base 1 in 62%, 0 in 12%; range almost always 0. No reader found yet. IDB calls this SetNum |
| 0xB0 | MtRangeU16 | LoopNum | dx9 |
| 0xB4 | MtRangeU16 | SetFrame | dx9 |
| **0xB8** | **f32** | (LoopNum distribution; IDB: `SetInterval` u16 + `LoopInterval` u16) | **dx9**: `movss [esi+0B8h]` in `uknGeneratorTimerFunc` 0x9DE25C and `comiss` in `Generator::restart` 0x9DF253. It is the float twin of `SetFrameDist` @0xBC |
| 0xBC | f32 | SetFrameDist | dx9 |
| 0xC0 | MtRangeF | (particle-scale range → Gen.mParticleScaleBase) | dx9 |
| 0xC8 | u8 | RangeType (spawn shape switch) | dx9 offset, se name |
| 0xC9 / 0xCA / 0xCB | u8 | RangeDirType / RangeOptionFlags / uknRangeFlag | dx9 offset |
| 0xCC / 0xCD / 0xCE | u8/u8/s16 | RangeStripType / Flag / PartsNo | dx9 offset |
| 0xD0 | char[64] | RangeStripPath (`.efs`) | dx9 |
| 0x110 | MtRangeF[4] | spawn-range ranges ([0] = {0x110, 0x114}) | dx9 |
| 0x130 | u32 | RangeDivideNum | dx9 |
| 0x13C / 0x13E / 0x13F | u8 | mVibReqType / mVibReqArg0 / mVibReqArg1 | dx9 |
| 0x140 | char[64] | ExtVibrationPath (`.vib`) | dx9 |
| 0x180 | char[64] | SoundRequestPath (`.srq`) | dx9 |
| 0x1C0 / 0x1C2 / 0x1C4 | u16/u16/u32 | VibReqNo / VibOptionFlag / VibPriority | dx9 |
| 0x1C8 / 0x1CA | u16/u16 | SeReqNo / SeOptionFlag | dx9 |
| 0x1CC–0x1DC | s32×5 | Keyframe param offsets (self-relative, 0 = none) | **dx9**: `initGeneratorParam` 0x96B2BE–0x96B496 tests each one and sets Generator `mStatus` (+0x16) bits 0x10/0x20/0x40/0x80/0x100 |
| | | 0x1CC → **Scale** (bit 0x10) | dx9: when set, the Scale range evaluation is replaced by raw randoms (3 floats) |
| | | 0x1D0 → ? (bit 0x20) | dx9: draws one random u32 → Generator +0x13C. Scalar keyframe (SetNum?) |
| | | 0x1D4 → ? (bit 0x40) | dx9: flag only |
| | | 0x1D8 → ? (bit 0x80) | dx9: draws 3 randoms → Generator +0x130..+0x138. Vector keyframe (Range?) |
| | | 0x1DC → ? (bit 0x100) | dx9: draws 3 randoms → Generator +0x140..+0x148. Vector keyframe (Ofs?) |
| ~~0x1E0~~ | — | — | **dx9 + corpus**: does not exist; the IDB's `member_0x1e0` is the start of the next block |

The IDB previously named 0x1D0–0x1DC as Keyframe{Scale,SetNum,Range,Ofs}ParamOffset and 0x1CC as a "matrix source".
The Scale gating places KeyframeScale at **0x1CC**, so those names were probably shifted by 4 as well. The names for
0x1D0–0x1DC are not confirmed.

### 3.4 Particle param — slot 1

The base chain is DX9-verified after the 2026-10-05 fix and SE-cross-checked.

`EFL_PARTICLE_COMMON` (0x14): 0x00 TransMode u8 · 0x01 EntryType u8 · 0x02 CullingFlag u16 (bit 0 = culling draw
variant, bit 0x40 = culling block present) · 0x04 ParticleOptionFlag · 0x08 LightGroupFlag · 0x0C zOfs ·
0x10 FixOtDepth u16.

`EFL_PARTICLE_DRAW_COMMON` (0x50):

| Off | Field | Off | Field |
|---|---|---|---|
| 0x14 | PrimMaterialFlags | 0x40 | ColorFlag u8 |
| 0x18 | Intensity MtRangeF | 0x41 | bit0 KeyframePatSpeedParamFlag |
| 0x20 | Scale MtRangeF | 0x42 | KeyframeColorParamOffset u16 |
| 0x28 | ScaleAdd MtRangeF | 0x44 | KeyframePatNoParamOffset u16 |
| 0x30 | KeyframeIntensityParamOffset s32 | 0x46 | **CullingParamOffset** u16 (→ culling block) |
| 0x34 | KeyframeScaleParamOffset s32 | 0x48 | colors MtColor[2] |
| 0x38 / 0x3C | s32 ? | | |

`EFL_PARTICLE_PRIM_COMMON` (0x170):

| Off | Field | Off | Field |
|---|---|---|---|
| 0x50 | AnimFlag u16 | 0x5C | PatNoMax |
| 0x52 / 0x53 | SeqNoMin / SeqNoRange u8 | 0x60 | PatCenter MtPoint |
| 0x54 / 0x56 | PatNoMin / PatNoRange u16 | 0x68 / 0x6C | TextureInvW / H |
| 0x58 | PatSpeed f32 | 0x70 / 0xB0 / 0xF0 | BaseMapPath / NormalMapPath / MaskMapPath char[64] |
| | | 0x130 | AnimPath char[64] (`.ean`) |

*(corpus)* **All paths are stored without an extension,** as backslash paths relative to the arc root. This is the
same convention as texture paths in `.mod`. Examples: `effect\tex\com\ec032_16_BM`, `effect\ean\com\ec032_16`,
`effect\efs\scr\st405_00`, and `effect\mod\…` for ModelPath. Ten particles use `id\item\…`. NormalMap and MaskMap
are almost never set (9 and 8 records).

*(corpus)* Only Billboard, Polyline, Polygon, Texline, PrimModel and both PolygonStrips have blocks long enough for
PRIM_COMMON. The other types have shorter blocks (see the per-type table).

**Per-type tails, from 0x170.** Records and minimum block lengths are from the corpus. Inferred lengths include
trailing keyframe data, so the minimum is the struct size:

| Type | DX9 records | Min len | Status |
|---|---|---|---|
| Billboard | 6,878 | 0x1A0 | Angle 0x170, AngleAdd 0x178, AspectRatio 0x180, AspectRatioAdd 0x188 (dx9 offsets, prior names) |
| Polyline | 4,514 | **0x1B0** | LineType 0x170, LineOfsNum 0x171, ColorPlace* 0x172–0x173, PlaceColor 0x178, HeadSize 0x180, … (prior names, dx9 offsets). *(corpus)* 541 blocks are shorter than the previously assumed 0x1E0, so the tail is at most 0x40 |
| Polygon | 2,082 | 0x1E0 | Rot 0x170, RotAdd 0x188, … (prior) |
| **PrimModel** | 1,825 | 0x260 | see §3.5 (0x25C + padding) |
| PolygonStrip(alt) (15) | 670 | 0x1D0 | untyped → R4 |
| Model (5) | 666 | 0x130 | ModelPath char[64] **@0x50** (resource loader). Type has a different base, **not** PRIM_COMMON; rest untyped |
| Line (4) | 306 | **0x60** | *(corpus)* DRAW_COMMON + 0x10, **not** PRIM_COMMON → R4 |
| Filter (9) | 142 | 0x80 | *(corpus)* not PRIM_COMMON; post-process (non-goal) |
| PolygonStrip (12) | 113 | 0x210 | untyped → R4 |
| Light (10) | 99 | 0x80 | *(corpus)* not PRIM_COMMON → R4 |
| MassBillboard (8) | 32 | **0xE0** | resource path at 0x60 (loader). *(corpus)* not PRIM_COMMON |
| Hit (11) | 28 | 0x50 | *(corpus)* exactly DRAW_COMMON, no tail; non-goal |
| Texline (3) | 3 | 0x1D0 | negligible |
| LensFlare (7) | 2 | 0x370 | resource path at 0xA0 (loader); non-goal |
| 13, 14, 16, 17 (Texline/Line alt, LiteBillboard, SizeBillboard) | **0** | — | *(corpus)* never used in DX9 files; drop from R4 |

### 3.5 PrimModel tail (0x170–0x25B) — DX9-verified, SE-cross-checked

| Off | Field | Notes |
|---|---|---|
| 0x170 | PrimFlags u32 | nibbles: [0–3] PrimModelType (0 Ring, 1 TexRing, 2 Sphere, 3 TexSphere, 4 Grid, 5 TexGrid) · [4–7] Axis · [8–11] RotOrder · [12–15] DirAxisType · [16–19] ColorPlaceType · [20–23] ? (SE padding) · [24–27] ModelBillboardType · [28–31] NormAttenuateFlag (bit 29 = one-sided) |
| 0x174 | HoriColorPlaceNo u16 | gradient split |
| 0x176 | u16 | SE: RotResetFlag / ModelBillboardOrder / LookAt; ProjectionType @0x177 (no DX9 reader yet) |
| 0x178 / 0x17C | PlaceColor1 / 2 | MtColor |
| 0x180–0x18E | RotDivNum, RotTexDivNum, RotDrawStart, RotDrawEnd, HoriDivNum, HoriTexDivNum, HoriDrawStart, HoriDrawEnd | u16 each |
| 0x190 | ModelScale MtRangeF[3] | → mScaleVec |
| 0x1A8 | ModelScaleAdd [3] | → mScaleVecVel |
| 0x1C0 | Rot [3] | → mRot |
| 0x1D8 | RotAdd [3] | → mRotVel |
| 0x1F0 | Radius [2] | → shape.x / .y |
| 0x200 | RadiusAdd [2] | → shapeVel |
| 0x210 | Height [2] | → shape.z / .w |
| 0x220 | HeightAdd [2] | → shapeVel |
| 0x230 / 0x234 / 0x238 | NormAttenuateAngleStart / End, NormAttenuateCurve (MtEaseCurve) | |
| 0x240–0x258 | Keyframe{PlaceColor,Rot,ModelScale,Radius0,Radius1,Height0,Height1}ParamOffset | s32, self-relative |

The shape vector means `(r0, r1, h0, h1)` for Ring, `(R, –, H, offset)` for Sphere and `(w0, w1, d0, d1)` for Grid.

*(corpus)* PrimModelType usage: TexRing 1,257, TexSphere 506, Sphere 41, TexGrid 17, Ring 4, Grid 0. Port the Tex
variants first.

### 3.6 Life param — slot 2

**Not reversed.** The old template guessed `fadein[2], transition[2], fadeout[2]` (s16 pairs) plus
`KeepHoldFlag:1 / KeyframeKeepFrameParamOffset:15 / KeepHoldFrame:16`. Treat that as a hypothesis → RE task R2.

*(corpus)* The block is **always exactly 0x10 bytes**, which matches the guess (12 bytes of s16 pairs + one dword).
Sampled values look like (base, range) frame counts, e.g. `(0,0, 1,0, 1,0, 0)` and `(5,0, 0,0, 5,0, 0)`. Since it
never carries trailing keyframe data inline, the keyframe offset bits in the dword (if real) point elsewhere.

### 3.7 Move param — slot 3 (mapped 2026-10-05)

The full tables are in `RE/particle_move_param.md` → "On-disk move param". Summary:

| Type | Layout |
|---|---|
| `EFL_MOVE_COMMON` (0x10) | `MoveOptionFlag`, `ForceType`, `RotAxisOrder`, `CollParamOffset` (u16 → collision block), `ForceRate`. *(corpus)* **Move None is this block alone** (min length 0x10, no `MOVE_BASE`) |
| `EFL_MOVE_BASE` (0x40) | `Rot[3]`, `Speed`, `Gravity`, keyframe offsets (Rot / Speed / FallSpeed) |
| Add (0x48) | `Acceleration` @0x40 |
| Mul (0x48) | `SpeedCoef` @0x40 |
| Path common (0x70) | `ReleaseType` / `OptionFlag` / `KeyframeReleaseFrameParamOffset`, `ReleaseFrame`, `Acceleration`; 0x50–0x6F (`Path3DScale*`, `PathLengthScale`) unconfirmed in DX9 |
| Strip (0xC0) | `Distance`, `PathStripType` / `Flag` / `PartsNo`, `PathCurveDivideNum`, `PathStripPath` (`.efs`) |
| Chain (0x110) | `Distance`, `ChainPosNum`, `EFL_PARAM_CHAIN` @0x80 |
| Keyframe (0x74) | `KeyframeOfsParamOffset` |
| Line (0x7C) | `Distance`, `PathLength` |
| `EFL_PARAM_COLLISION` (≥0xB0) | `CollFlag`, `CollCancelFrame`, `CollRadiusAdd`, `CollRadius`, bounce/finish params, modes and callback flags, `BounceNum`, `BounceRate`, `BounceEffectPath` @0x30, `FinishEffectPath` @0x70 |

*(corpus)* Move usage (DX9 records): None 6,357, Add 6,293, Mul 3,485, PathKeyframe 421, PathChain 386, PathLine 330,
PathStrip 88. The three simple types cover 93%.

Blender mapping notes:
- `CollRadiusAdd` means the collision radius grows each frame (clamped at `CollRadius` s+r).
- Bounce count = `BounceNumBase + rand % (BounceNumRange+1)`.
- The bounce and finish effects are other `.efl` files, so the importer can resolve them as linked collections.

### 3.7a Enums (SE PDB, imported into the DX9 IDB 2026-10-05)

49 effect enums were imported from the SE PDB as DX9 types (`rEffectList::*`, `rEffectStrip::*`, `rEffectAnim::ANIM_FLAG`,
`cParticle::*`, `cParticleManager::*`). Twelve DX9 struct fields carry them where DX9 masks/compares were verified (table
in `particle_move_param.md`). For the parser: use these enums for display and Blender enum properties, but treat
values outside the verified bits as raw.

Useful for the importer:
- `LIFE_TYPE` (NONE, FRAME_ALPHA/COLOR, KEYFRAME_*, HIDEFRAME_*, CURVEFRAME_*) and `cParticle::PTCL_LIFE_RNO_TBL`
  (HIDE/APPEAR/KEEP/VANISH/FINISH) are the starting point for **R2 (life block)**.
- `PARTICLE_OPTION_FLAG` covers blend and depth flags (DEPTH_BLEND, NO_ZTEST, NO_FOG, BACKFACE_CULLING, BOTHFACE_DRAW…),
  which map to Blender material settings.

### 3.8 Self-relative blocks

| Block | How it's reached | Status |
|---|---|---|
| Keyframe block | `param + s32/u16 offset`, offset 0 = none | header dword: bit 30 = flag (loop?), bits 27–29 = interpolation type, low bits = count (**to verify**); data from +4. Readers: `calcKeyframeF32/Vector/Color`, `calcKeyframeFixAngleVector3`, `getKeyframeTimer` → RE task R1 |
| Culling block | `DRAW_COMMON+0x46` | +0 flags (`>>8` / `>>12` = `calcDir` modes), +4 dir vec3, +0x10–0x1C near/far ranges, +0x2C sort param (SE: `EFL_PARAM_CULLING`) |

---

## 4. Outstanding RE work (ordered by import value)

| ID | Task | Entry points (DX9) | Unblocks |
|---|---|---|---|
| R0 | Pin record type-byte semantics and the group filter bits. *(corpus)* The gen type byte is only ever 1 or 2, and the life type byte 1 or 2 | `createGenerator` 0x96A770, `matchGeneratorFilter` 0x9DD560 | correct per-group import |
| R1 | **Keyframe block format** (header bits, key layout per value type, timer modes). *(corpus, 2026-10-05)* **Key sizes are settled:**<br>• The header is `EFL_KEYFRAME_INDEX` (KeyframeNum bits 0–7, SingleParam 9, FixAngle 8, InpType 27–29, Loop 30), followed by SE `nEffect::KEYFRAME_*` keys (`Frame` u32 + Param), padded to 16 bytes.<br>• F32 and COLOR keys are 12 bytes, U32 8, VECTOR3 28. Every typed keyframe field fits exactly.<br>• Generator 0x1D0 uses U32 keys (likely SetNum); 0x1D4, 0x1D8 and 0x1DC use VECTOR3; PatNo keys are 12 bytes.<br>Remaining: the `Frame` semantics and the interpolation/timer modes (InpType, RefType, `getKeyframeTimer`) | `calcKeyframeF32`, `calcKeyframeVector`, `calcKeyframeColor`, `getKeyframeTimer`, `getKeyFrameSmthOffset` | F-curves (M2) |
| R2 | **Life block** layout and the life-type enum. *(corpus)* Smaller than expected: the block is a fixed 0x10, consistent with the old guess (§3.6) | `initGenerator` 0x96ACA0 (slot-2 reader), Generator `mLifeType` @0xC2, `mLifeWorkOffset` | alpha/scale over age |
| ~~R5~~ | **Done 2026-10-06**: spawn shapes, see M2. | - | - |
| ~~R3~~ | **Done 2026-10-05.** Move param tails + collision block mapped (§3.7). Flag/type fields now carry DX9-verified SE enums. `EFL_PARAM_CHAIN` header verified. Path3DScale block and SE tail extras have no DX9 reader (treat as raw). Residual: collision nibble pair (attach/relation?) | — | motion (M2) |
| R4 | Remaining particle-type tails. *(corpus)* Order by usage: Billboard/Polyline/Polygon names, then PolygonStrip(alt) 670, Model 666, Line 306 (own base, 0x60), PolygonStrip 113, Light 99. Skip types 13/14/16/17 (unused) and Texline/LensFlare (≤3 records) | `initParticle<Type>` per type; renderers already named | non-PrimModel geometry |
| R5 | Spawn-range shapes (`RangeType` cases) | `sub_999640`, `uEffectVFR::Funcx90` | emitter shapes |
| R6 | Child/unit generator records (header 0x10/0x14). *(corpus)* Low priority: used in only 4 DX9 files | `initChildGenerator` 0x96BB70, `moveUnitGenerator` 0x96FF00 | unit effects |
| R7 | ~~WaitFrame exact offset; Scale/Range~~ **Done 2026-10-05** (§3.3): WaitFrame @0x74, Scale @0x78, Range @0x90, 0xB8 is f32. IDB retyped (0x1E0). Remaining: confirm that 0xA8 is SetNum and identify 0xAC; name the keyframe offsets 0x1D0–0x1DC | `uknGenBehaviorFunc1`, `initGeneratorParam` | emission schedule |
| R8 | Coordinate conventions (Y-up? handedness, unit scale, quaternion order). Albam already uses Y-up cm → Blender `(x*.01, -z*.01, y*.01)` and quaternions `(w,x,y,z)` for `.mod`/`.lmt`. Only confirm that effects use the same units | any known model + effect pair in game; `calcParticleMatrix` | correct placement |

Do the RE in IDA first. Then add schema rows with `evidence='dx9'` and a note naming the function/address that proves
each one.

---

## 5. Milestones

### M0 — Samples and corpus — **done 2026-10-05**

1. ~~`tools/arc.py`~~ Not needed. Extracted samples already exist, and Albam has an `.arc` parser
   (`engines/mtfw/structs/arc.ksy`) if more are needed.
2. Corpus: **1,109 unique DX9 `.efl` files** (17,360 records; 1–113 per file, median 11). They come mostly from
   `E:\DMC mod stuffs\arctool\*` (vanilla extractions), plus `000 laser test` and 34 in `Dante Cyber porting`. The
   folders keep arc-root-relative paths, so the referenced `.tex`/`.ean`/`.efs`/`.mod` files sit alongside.
   `Demo\` and `arc files\` are **SE only** (`0x20120306`, 3,802 unique files).
3. Stats: `python RE/scripts/efl_corpus_stats.py "E:\DMC mod stuffs"`. Results are folded into §3 and §4 as
   *(corpus)* notes.

**Exit (met):** every DX9 header passes the magic/version check, and every block offset is in range and 4-aligned.

### M1a — Parser core and round-trip — **done 2026-10-05**

Implemented inside Albam rather than as a separate package: `blender_addon/addons/albam/engines/mtfw/efl/`
(`schema.py`, `model.py`, `check.py`, `export_json.py`). It is pure Python with relative imports only, so it runs
with or without Blender. Runner: `python engines/mtfw/scripts/efl_check.py "E:\DMC mod stuffs" --coverage`.

**Exit (met):**
- Byte-identical round-trip for **1,109/1,109** DX9 files (17,360 records).
- **Zero** §7 issues.
- It also imports and round-trips inside Blender 4.2.
- The writer recomputes offsets, so edited or resized blocks are supported (tested).

Schema corrections the run forced (now in `schema.py`):
- **Hit (11) has no `DRAW_COMMON`.** Its 0x40–0x4F is not the draw layout: what would be `KeyframeColorParamOffset`
  reads 0x3F80, the high half of 1.0f.
- **`EFL_PARAM_CHAIN` keyframe offsets (move 0x100–0x10C) are relative to the move block,** not to the chain param
  at 0x80.
- **The IDB's `EFL_PARTICLE_*` types were 4 bytes short from 0x14 on.** They lacked the always-zero dword at 0x14.
  `initParticleBillboard` 0x977E60 reads the file offsets used here: keyframe offsets at 0x30/0x44, SeqNo at 0x52,
  PatNo at 0x54, PatSpeed at 0x58. The u16 at 0x12 supplies `calcPrimMaterial`'s two nibble arguments.
  - **Retyped 2026-10-05.** `COMMON` is now 0x14 and holds `PrimMaterialFlags` @0x12. `DRAW_COMMON` is 0x50 with
    `uknDraw_0x14`. `PRIM_COMMON` is 0x170. Billboard is 0x1A0 (`KeyframeAngleParamOffset` is now an int @0x190),
    Polygon 0x1E0, Polyline 0x1B0, PrimModel 0x25C, `EFL_DUMMY` 0x300.
  - `initParticlePrimModel` now decompiles with the PatNo/SeqNo/PatSpeed names.
  - The old declarations are in `RE/type_backups/EFL_PARTICLE_types_before_2026-10-05.h`.

Field-usage findings (`--coverage`):
- The generator's vibration and sound fields (0x13C–0x1C4, `SeOptionFlag`) are **never set** in DX9 effects.
- `DRAW_COMMON` 0x38/0x3C are always zero.
- Unknown data remains in the generator at 0x08–0x0A (always) and 0x0C–0x0F, in Polyline 0x174 (flag bytes, not an
  offset) and in the untyped tails (PolygonStrip, Texline, Line, Filter, Light, MassBillboard, LensFlare).

### M1b — 010 template regeneration

`gen_bt.py`: schema → `RE/efl.bt` (header, record table, per-slot dispatch on the type byte, the common chain,
per-type tails, and self-relative blocks followed via `FSeek`). Replace the hand-written template.

**Exit:** the template opens every corpus file without errors, and its field values match the JSON dump.

### M1c — Blender static import — **first version done 2026-10-05**

Implemented in `albam/engines/mtfw/effect.py`, registered as the dmc4 `efl` import function (category EFFECT). It
uses Game Files → select an `.efl` → EFL Options (armature, build geometry, load textures) → Import.
- **Objects:** one collection `EFL_<file>` per import, holding a root Empty plus one Empty per record. Each Empty sits
  at its generator's `Pos`/`Quat` (scaled by `Scale`) and is attached to its joint when an armature is picked. All
  block fields are stored as custom props `efl_gen` / `efl_ptcl` / `efl_life` / `efl_move`.
- **Geometry:**
  - PrimModel meshes come from `efl/primmodel.py`, a pure-Python port of the ring/sphere builders, with draw ranges,
    UV repeat and edge alpha. Grid is an approximation.
  - Polygon particles get a Width × Height quad.
  - Billboard particles get a quad of Scale × 100 cm (an assumption) that tracks the scene camera.
- **Materials:** Emission + Transparent, with the base texture loaded through Albam's `.tex` path, tinted by
  `Color0`, and alpha = texture × `Color0.a` × edge alpha. TransMode 1 → additive, 0 → alpha blend (assumed).
- **Test:**
  - All 110 Nero DX9 effects import with Nero's `pl000.mod`: 0 failures, 2,526 generators, 1,059 attached, 1,619
    meshes, 394 textures, 8 s.
  - The unresolved joints (155–163) aren't in `pl000.mod`; they are probably weapon joints.
  - A Cycles preview of `ec001_54v1` shows the expected red/white swept slash rings.
- **Flipbooks (2026-10-06):** `efl/ean.py` reads `.ean`.
  - Header: `EAN `, version, data size (= file size − 0x10), sequence count.
  - Then 32-byte sequences: pattern-table offset relative to 0x10, u16 count, 26 bytes not yet decoded, ending
    in the cell size.
  - Patterns are `s16 (x, y, w, h)` pixels.
  - UV rule from `sub_9632F0`: x/texW, y/texH; AnimFlag 0x100 flip U, 0x200 flip V, 0x1000 rotate.
  - All 176 DX9 + SE `.ean` parse. All 14,488 corpus SeqNo/PatNo references are in range.
  - The import crops UVs to frame `SeqNoMin`/`PatNoMin`: 1,617/1,619 Nero meshes.
- **Still open:**
  - Flipbook animation over time (PatSpeed semantics), and the 26 undecoded sequence-header bytes.
  - TransMode / PrimMaterial-nibble blend mapping (R-task).
  - The Billboard size unit.
  - Polyline/Line/Model/strip particles have no geometry.
  - The R8 visual check against in-game footage.
  - Euler order mapping is assumed.

The original plan below is kept for reference.

1. **Operator** `import_scene.efl`. Options: unit scale, axis conversion, FPS handling (use the file's `mBaseFPS` or
   rescale to the scene), group filter, texture search roots, "dynamic" toggle (off in M1).
2. **Collection** per file, with header fields as custom properties.
3. **Generators:** one Empty per record (`Gen_<index>_<ParticleType>_<MoveType>`):
   - location ← `Pos`, rotation ← `Quat` (quaternion mode);
   - all schema fields go into custom properties grouped by block (`gen.*`, `ptcl.*`, `move.*`), including tiers;
   - `MtRangeF` is stored as `[s, r]` with a note on the semantics (`s + rand × r`).
4. **`ParentNo`:** if an armature is selected when importing, bone-parent the Empty to joint `ParentNo` (**the
   joint-index → bone-name map needs the `.mod` skeleton**). Otherwise store it as a property.
5. **PrimModel meshes** (`primmodel_mesh.py`). Port the six builders:

   | Builder | Shape |
   |---|---|
   | `buildPrimModelRing` 0x9CD670, `TexRing` 0x9CEFC0 | angle step 2π/N, centred offset N/2, two rings (r0,h0)/(r1,h1), M stacks lerped (`lerp_cell_corners`), quads |
   | `buildPrimModelSphere` 0x9D11C0, `TexSphere` 0x9D4250 | latitude π/M, longitude 2π/N, pole triangle fans, band quads |
   | `buildPrimModelGrid` 0x9D83C0, `TexGrid` 0x9D8C70 | trapezoid between edges (w0,d0)/(w1,d1) |

   All six honour the draw ranges (`*DrawStart/End`), the axis nibble (`>>4`), UV repeat (`*TexDivNum`) on the Tex
   variants, and the edge-alpha flag (`ParticleOptionFlag & 0x80000`, written as a vertex attribute). Build one mesh
   per generator from the **base** values (`s`) of each range, and store the ranges as properties.
6. **Materials:**
   - one per particle param; Image Texture nodes for Base/Normal/Mask when the files resolve (`.tex` → DDS/PNG
     conversion is a separate tool, or a user-supplied folder);
   - blend mode from `TransMode` (mapping table to be pinned down; additive = Emission + Transparent);
   - colour from `colors[0..1]` and `PlaceColor` → Color Ramp along a mesh attribute (`ColorPlaceType`);
   - `.ean` flipbook: frame grid from `TextureInvW/H` and `PatNo*`, a Mapping-node offset driven by
     `frame × PatSpeed`. This needs the `.ean` sequence table (`rEffectAnim`: table at +0x68, 32-byte entries,
     pattern count at +4), which is a small RE task alongside R4.
   - Rim fade (`NormAttenuate*`) → Layer Weight → alpha. Culling variant (`CullingFlag` bit 0) → Camera Data
     distance → alpha.
7. **Strip sidecars:** `RangeStripPath` / move `.efs` → Curve objects (format: `rEffectStrip`, still to be
   reversed; builders `sub_B256D0` / `sub_B26060`).

**Exit:** every corpus file imports without errors, PrimModel effects look plausible next to in-game captures, and
every field is visible as a custom property.

### M2 — Dynamic import (Geometry Nodes simulation)

**First version done 2026-10-06.** It's implemented as a Python simulation + Geometry Nodes instancing, not a
GN simulation zone: `albam/engines/mtfw/efl/sim.py` (pure) and `albam/engines/mtfw/effect_sim.py` (Blender
playback). The runtime behaviour it ports (DX9):

| Part | Behaviour | Source |
|---|---|---|
| Emission | State machine:<br>• wait `WaitFrame`;<br>• a burst spawns `SetNum` (0xA8) particles per frame for `LoopNum` frames (1 in 99%);<br>• pause `SetFrame` frames;<br>• repeat `BurstNum` (0xAC) times, 0 = forever (12%).<br>All values are `s + rand%(r+1)`. `KeyframeSetNumParamOffset` (0x1D0) replaces SetNum when set. | `uknGenBehaviorFunc1` 0x9DDCB0, `sub_95FD00` |
| Spawn shape | `RangeType`: 0 point, 1-3 box (`t` along X/Y/Z), 4-6 cylinder around X/Y/Z (radius `s + r*(1-sin(rand*pi/2))`, length `s + rand*r`), 7 sphere, 8 hemisphere, on `Range[3]` = (x.s, x.r, y.s, y.r, z.s, z.r). Then scaled by `UknRangeThing[1..3]`. `t` is evenly spread when `RangeDivideNum` is set, else random. | `sub_999040` |
| Direction | The `getAxisVector(RotAxisType)` axis (0 +X, 1 -X, 2 +Y, 3 -Y, 4/6 +Z, 5 -Z) rotated by move `Rot` with `setMatFromAngle(RotOrder)` (0 ZYX, 1 ZXY, 2 YZX, 3 YXZ, 4 XZY, 5 XYZ). For RangeDirType diffuse/converge it is blended toward +/- the spawn offset by `UknRangeThing[0]`. | `calcDir` 0x9DEC60, `movevel_transform` 0x9750B0 |
| Motion | `pos += vel - (0, fall, 0)`. Add: `vel += dir*Acceleration`, `fall += Gravity`. Mul: `vel *= SpeedCoef`. Speed is along dir. | `initParticleMoveAdd`, `moveParticleMoveAdd` |
| Life | Types 1/2 (FRAME_ALPHA/COLOR): Appear / Keep / Vanish frames, each `s + rand%(r+1)`. Keep may come from a keyframe at bits 1-15 of the dword at 0x0C. | `sub_9729B0` |
| Flipbook | Start at `PatNoMin + rand%(PatNoRange+1)`, clamped to `PatNoMax`. With `ANIM_FLAG_MOVE` the pattern advances by `PatSpeed` per frame; LOOP wraps, FINISH kills, REVERSE runs backwards. The sequence is `SeqNoMin + rand%(SeqNoRange+1)`. | `initParticleBillboard`, `sub_961DB0`, `getAnimFlag` |

Test: all 110 Nero effects simulate, giving 1,633 particle systems. The renders of `ec024_60v2` show the
expected streams, sparks and bursts. A frame update takes about 0.15 s with all 110 loaded. Playback survives
save/reload.

**Second round (2026-10-06):**

| Topic | Finding | Source |
|---|---|---|
| Blending | `PrimMaterialFlags` (0x12) holds D3D9 enums minus 1: low nibble of 0x12 = SRCBLEND, **high nibble of 0x12 = DESTBLEND**, low nibble of 0x13 = BLENDOP. Corpus: alpha blend (SRCALPHA, INVSRCALPHA, ADD) 17,352; additive (SRCALPHA, ONE, ADD) 15,050; darkening (REVSUBTRACT) 2,271; rare ONE/ONE and premultiplied. Particles never write depth; ParticleOptionFlag 0x80 = no depth test, 0x4 = soft (depth blend), 0x1000 = no fog. | `calcPrimMaterial` 0x9DEBF0, `sub_A35610`, `sRender::dispatchCommands` 0x8F48A6; SE `nPrim::Material::AlphaType/AlphaOpType` |
| TransMode | Not a blend mode: a scene-pass mask (1 = main view, 2 = mirror/water, 8 = shadow cast, ...). 0 = never drawn in the main view (805 particles). | `initGeneratorParam` 0x96B52E, `sUnit::draw` 0x8DC130 |
| Colours | `MtColor` is a D3DCOLOR: bytes B, G, R, A. The shader multiplies rgb by Intensity (clamped 0..127). | XfPrim.bfx `tXfPrimStandard` |
| Billboard size | width = S x pattern width (px) x AspectRatio, height = S x pattern height (px), in cm; S = particle scale x generator ParticleScale (x mean world scale with ParticleOptionFlag 0x200). Angle rotates in the screen plane (radians). No constant, no texture size. | `sub_961250`, `renderBillboard` 0x99DE40, the XfPrim vertex shader |
| Emission space | Move None: re-placed from the current generator matrix every frame (follows). Add/Mul: world space after spawn. MoveOptionFlag 8 (ALWAYS_CORRECT) with the generator's 0x4000 flag (MoveOptionFlag 4 or any generator keyframe) adds the generator's translation delta each frame. | `moveParticleMoveNone` 0x995E60, `moveParticleMoveAdd` 0x996160, `moveParticleMoveVel` 0x99BEA0 |
| Keyframes (R1) | Key `Frame` = absolute frame of the RefType timer (0/5-7 particle age, 1 generator timer, 2 effect, 3 parent effect, 4 global). Segment search clamps (no loop) or wraps (loop). InpType 0 linear, 1 Hermite (tangents = neighbouring differences), 2 4-point Lagrange cubic; 3-7 give zero. Values: F32 `s + r*rate`; COLOR lerp(A, B, rate); VECTOR3 three rates; U32 `s + rnd%(r+1)`; FixAngle int ranges x 2pi/4096. Rates are drawn once per particle. InitOnly (bit 31) = evaluated once at spawn. SingleParamFlag is unused in DX9. | `getKeyframeTimer` 0x963F10, `KeyframeTag::calcTag` 0xA9E820, `calcKeyframeF32` 0xA3C1C0, `MtSpline` 0x8D4390 |

Implemented:
- `efl/keyframe.py`.
- Keyframes in `efl/sim.py`: intensity, scale, colour, flipbook frame, billboard angle, PrimModel/Polygon rotation and model scale, move direction/speed/fall speed, and SetNum emission.
- Per-particle sequence choice and the flipbook rotate flag.
- Materials built from the blend equation, plus a per-particle tint.
- World-space emission: the generator matrix at each particle's birth frame is recorded during playback.
  `albam.efl_record_motion` records a whole range at once.
- TransMode-hidden particles get no geometry.

Corpus run: 17,094 records simulate with 0 errors. All 110 Nero effects import both simulated and static.

**Third round (2026-10-06): paths and ribbons**

| Topic | Finding | Source |
|---|---|---|
| Path moves (3-6) | The particle rides a path in **current** generator space: `pos = Wmat * (Lscale * (spawn + R(mRot) * offset))`. Path3DScale/PathLengthScale (move 0x50-0x6F) are rolled once per generator start; this is their DX9 reader. Release timer = ReleaseFrame (or its keyframe). At the path end: OptionFlag 2 kills, 1 releases immediately. On release the particle becomes an Add particle in world space, with velocity from the last step (ReleaseType 1), a fresh `Speed` (type 5, ReleaseType 2) or the current path speed (types 3/4/6), plus acceleration and gravity. | `initGeneratorParam` 0x96B9C3, init 0x9739D0.., move 0x996D60.. |
| 5 PathKeyframe | Offset = VECTOR3 keyframe (0x70) in cm, generator-local, scaled by Path3DScale, rotated by mRot. | 0x974560 / 0x977070 / 0x997BF0 |
| 6 PathLine | `d0 = Distance`, `d += speed; speed += accel`; offset = axis * d (axis = getAxisVector(RotAxisType) rotated by mRot); clamped to `PathLength * LengthScale` (the end). | 0x974A50 / 0x977240 / 0x998490 |
| 3 PathStrip | Like PathLine, along an `.efs` curve (`efl/efs.py`: 'EFS\0', parts of 32-byte vertices, pos f32[3]). PathStripFlag 0x08 loops. | `sub_AD9810`, 0x9739D0 |
| 4 PathChain | A generator-owned rope; approximated here as an unclamped PathLine. | `moveChain` 0x994C20 |
| Polyline / Line | `LineOfsNum` points per particle by LineType (SE `LINE_TYPE`): 0 FOLLOW = the last N positions; 2 FIX_END = the trail pulled to the spawn point by t^2; 4 LENGTH = a rigid stick (extension at block+struct size: Rot/RotAdd/axis/Length/LengthAdd + 2 keyframes, 0x50 bytes); 1 FIX = stored points (0x70 + 16 N); 3 CHAIN = a rope (approximated as FOLLOW). Half-width HeadSize -> PlaceSize x Scale (cm), colour head -> PlaceColor, both by `calc_color_gradient` (type 1 linear, 2 peak at No, 3 from No, 4 up to No; InpType 0 linear, 1 sin, 2 1-cos, 3 smooth). Camera-facing ribbon; the .ean frame spans across (U) and along (V). Line particles have the same points but are drawn as untextured 1-pixel strips. | `sub_98E3E0`, `renderPolyline` 0x99E5B0, `calc_color_gradient` 0x9B52A0 |

Implemented:
- `efl/efs.py`;
- path moves in `efl/sim.py`, with per-state anchors: None while on a path (current generator), else the release/birth frame;
- polyline/line points, widths and colours in `efl/sim.py`;
- ribbons rebuilt per frame in `effect_sim._update_lines`.

Corpus: every record simulates with 0 errors. All 110 Nero effects import simulated (2,282 systems) and static.

**Fourth round (2026-10-06): the remaining particle types and generator features**

| Topic | Finding | Source |
|---|---|---|
| Type names | 12 = **ClothPolyline** (Polyline init, LineType 5), 13 = ClothTexline, 14 = ClothLine, 15 = **PolygonStrip**. The earlier "PolygonStrip / alt" labels were wrong. | `initParticle` 0x970F10, SE `PARTICLE_TYPE` |
| Chain rope | Per-node velocity, one root-to-tip Gauss-Seidel pass per frame: `vel = vel*FrameInf + accel(i)`; a stretch spring into velocity (VertexInf); then an exact segment-length correction fed back into velocity. Pull = `Acceleration` along `calcDir(Rot)`, blended toward BlendRot by BlendRate per node. No gravity; the wind force is 0 unless the stage sets it. `PreUpdateLoopNum` is the **u16 at +6** (schema fixed); StretchScale/ShrinkCoef aren't read. CHAIN trails root at the particle. PathChain ropes are generator-owned and the particle rides them by distance. | `moveChain` 0x994C20, `initChain` 0x984350, `calcParticleMovePathChainPos` 0x975BA0 |
| PolygonStrip | Sword trail: the last LineOfsNum edge pairs `P +/- axis*Width` (pivot WidthPlaceRate), axis rotated by Rot(+RotAdd) and scaled by the particle scale. Uniform-cubic smoothed (SplineDivideNum), plain 3D quads, texture stretched once along the arc length, colour head -> PlaceColor. Tail layout is in `schema.py`. | 0x97E800, 0x98D240, 0x9D99A0 |
| Texline | A textured 1-pixel line with Polyline's point types; tail at 0x170 with the extension at 0x180. | 0x97A0B0 / 0x9A1BB0 |
| Model | One mesh per particle: the first with `idx_group == PartsNoMin + rand % (PartsNoRange+1)` (ModelFlags 0xF0). ModelScale/Rot (+Add, keyframes) as PrimModel. AnimSpeed advances the part. ModelZofs pushes along camera->particle. UV scroll 0x100/0x108. No motion is played. | 0x97AF80, `renderModel` 0x9A20C0 |
| Light | Point lights. DRAW_COMMON up to 0x3F, then LightAttribute 0x40, LightType nibble 0x45, colour keyframe 0x46, colours 0x48/0x4C; AttenuateStart/End (+Add) 0x50-0x6F in cm, linear falloff. | 0x97DE80, `updateParticleLight` 0x99C120 |
| Generator keyframes | 0x1D8 = position, 0x1DC = Euler rotation (AxisFlags order), 0x1CC = scale (x effect scale), 0x1D4 = spawn extents, 0x1D0 = SetNum. Generator timer; RefType 1 subtracts 1. | `updateWorldMatrix` 0x96BE10 |
| RangeStripPath | Spawn on the generator's .efs strip: RangeStripType 0 picks a vertex, 1-3 a segment + t. Selection by serial / RangeDivideNum and flags (0x01 sequential, 0x02 reversed, 0x08 closed, 0x10 midpoint, 0x20 random part). Uniform in vertex parameter, not arc length. | `sub_99B270`, `sub_963220` |
| Collision | Line cast against the stage collision. A hit bounces (`reflect(d) * |d| * BounceRate`) while bounces remain, then CollType 0 kills / 1 stops / 2 carries on. One frame of cooldown; CollCancelFrame is a u16 at 0x02. Bounce/Finish child effects spawn at the hit. | `moveParticlePosCollision` 0x99A210 |
| Unit generator | Header 0x10/0x14: a repeater that spawns whole copies of the same effect list on the generator schedule (4 DX9 files). **Not implemented.** | `initChildGenerator` 0x96BB70, `moveUnitGenerator` 0x96FF00 |
| PAT_CENTER | ParticleOptionFlag 0x10000: the billboard's pivot is pixel PatCenter (0x60/0x64) of the cell. | `sub_961620` |

Implemented:
- The rope (`sim.Rope`, `GeneratorRope`).
- PolygonStrip meshes (`effect_sim._update_strips`).
- Texline/cloth ribbons.
- Model particles: the `.mod` is imported once through Albam into an off-scene collection in game axes; a GN group (`ALBAM_EFL_Models_v1`) picks the mesh by `instance_index`.
- Light pools.
- Generator keyframes baked as F-curves on the generator Empty.
- RangeStripPath spawning.
- PathStrip `.efs` loading (it was never wired before).
- Ground-plane collision (plane = world z 0 measured in generator space at import).
- PAT_CENTER pivots.

Tests: every DX9 record simulates with 0 errors. 15 sample effects and all 110 Nero effects import and play; a save/reload replays the same.

**Fifth round (2026-10-06): cloth (types 12-14)**

Types 12-14 always run as cloth (`AllocMemory` / `particleHandling` hardcode LineType 5). ClothType (0x176) picks
one of three algorithms, each with its own extension after the struct (Polyline 0x1B0). Points live in
`gen+0xE8` `cClothVertex[mSetNo]` (N vec4 positions, plus N velocities for CHAIN/ZIGZAG); the gatherer `sub_9B32E0`
draws them head first: point 0 = the particle P0, point N-1 = the tail P1 = `gen.mParticleScaleWmat` . SubOfs
(SubOfs drawn once at spawn with the `sub_999040` shape function on SubRange/SubRangeType/SubRangeDivideNum).

| ClothType | Algorithm | Ext size | init / move / vertices | Corpus |
|---|---|---|---|---|
| 0 CHAIN | rope P0 -> P1 under a constant pull | 0xC0 | 0x981530 / 0x992EC0 / 0x9DFFE0 (force 0x9E0D00) | 82 |
| 1 CURVE | analytic bend, no state | 0x60 | 0x9820D0 / 0x993560 / 0x9E1B80 | 7 |
| 2 ZIGZAG | curve + random per-vertex jitter | 0x90 | 0x983330 / 0x9944D0 / 0x9E2570 | 50 |

| Topic | Finding |
|---|---|
| CHAIN extension | 0x00-0x8F = EFL_PARAM_CHAIN (OptionFlag u16, Rot/BlendRot nibbles 0x04/0x05, PreUpdateLoopNum 0x06, Length 0x08, LengthAdd 0x10, Acceleration 0x20, FrameInf 0x28, VertexInf 0x30, Rot 0x38, BlendRot 0x50, ForceRate 0x68, ForceVertexAttenuateRate 0x70, keyframes Length/Rot/BlendRot/BlendRate 0x80-0x8C relative to the particle block); 0x90 ConstOffFrame u16+rand, 0x94 DistConvFrame u16+rand, 0x98 DistExpansion, 0xA0 SubRange[3], 0xB8 SubRangeType, 0xBC SubRangeDivideNum. |
| CHAIN status | starts 0xC0: 0x80 tail pinned, 0x40 head pinned too; 0x80 clear = head only. ClothParam (0x177, SE ClothOptionFlag) bit 0/1 release the head/tail after ConstOffFrame, bit 2 = distance-driven length (L = D if D/(N-1) > |D-L|, else L += (D-L)/(DistConvFrame+1); D = |P0-P1| + DistExpansion). Otherwise the Length keyframe, or L += LengthAdd. Lengths are cm, **not** scaled by the particle scale in DX9. |
| CHAIN pull | dir0 (Rot / its keyframe, or the particle velocity with OptionFlag 4) and dir1 (BlendRot, OptionFlag 8) times Acceleration. OptionFlag 1 / 2 = world-fixed (only the generator's local scale applies), else rotated by the generator. |
| CHAIN step | V *= FrameInf; relax(k, j, g): V += g, stretch spring into V (VertexInf), P += V, exact segment-length correction fed back into V. Head only: k = 1..N-1 toward k-1; both: N-2..1 toward k+1 (g1) then 1..N-2 toward k-1 (g0); tail only: N-2..0 toward k+1. Spawn: a rest shape (straight P0 -> P1, or P0 + dir*L) then PreUpdateLoopNum steps. Force mode (OptionFlag 0x10) adds a game-set wind vector (`gen+0x120`). |
| CURVE | Rot 0x00 (+RotAdd 0x18 per frame, or keyframe 0x34); 0x30 Order/AxisType nibbles; 0x31 low = DirAxisType (6 fixed, else aligned to the velocity), high = CurveType; 0x32 CurveOptionFlag (1 = amplitude x |P1-P0|); 0x38 CurveCoef; SubRange 0x40. CurveType != 0: lerp + dir*amp*sin(pi*u); 0: two Hermite halves through M = mid + dir*amp. |
| ZIGZAG | CURVE + VertexAmplitude rangef[3] 0x60, VertexUpdateFrame u16+rand 0x78: every interval (once with flag 0x400) J[k] = (U-.5)*Amp for the interior vertices, in a frame whose +Z runs P[0] -> P[N-1]; 0x200 limits Amp to the mean segment length; 0x100 an ease-in weight (not modelled). |

Implemented in `sim.py` (`_ClothChain`, `_cloth_curve`, `_cloth_zigzag`, `_cloth_points`). The cloth lives in generator
space (all but 8 corpus records are move None). World-fixed pulls use the generator's world axes measured at import
(`effect.world_axes`, like the ground plane). `Block.has` now accepts bit-field names. Tests: every DX9 record
simulates with 0 errors over 400 frames; 812 cloth states are finite, median arc 101 cm (113 have zero length:
distance-driven cloth whose ends coincide). Samples: `em021` ee021_52v0 / ee021_62v0 (CHAIN veils), `em012`
ee012_01v0 (ZIGZAG lightning), ee012_07v0 (CURVE).

**Export, stage 1 (2026-10-06)**

`engines/mtfw/effect_export.py`: the root Empty is an Albam exportable; export re-parses the stored source and writes
back changed `efl_*` custom properties (`efl/edit.py`), generator transforms (Pos/Quat/Scale base, in the joint's
head frame) and re-parenting (`ParentNo`). Untouched files are byte-identical (corpus: 1,079 unique files through the
prop round-trip; Blender: 110/110 Nero effects). "Apply Edits to Preview" replays the simulation with the edits.
Stage 2 (2026-10-06, done): the Effect Editor panel (`effect_editor.py`): schema-driven field widgets (tiers,
enums, colour pickers, hex words with their bit-fields), keyframe editing (in place, or appended at the block end
and repointed when it grows; new keyframes on any typed offset field), collision / culling sub-structs, and record
duplicate / remove / copy-to-another-effect (structural edits rebuild the effect from the edited bytes). Not
editable: the unit generator, untyped keyframes (`uknKeyframeOffset`), keyframes reached through raw extension
offsets (cloth / LENGTH line extensions), adding collision/culling where a block has none, changing block types.

**Sixth round (2026-10-06): keyframes everywhere**

| Topic | Finding | Source |
|---|---|---|
| Timers | Particle tracks: getKeyframeTimer 0x963F10 (RefType 0 particle age, 1 generator, 2 effect, 3 parent, 4 global). Generator tracks: 0x963EC0 (RefType 0 and 1 = generator timer). Keyed values are absolute and re-evaluated every frame; InitOnly = evaluated once at spawn, then the *Add field applies. | 0x963F10, 0x963EC0 |
| Polygon tail | All fields confirmed (dx9). 0x1A8 = **KeyframeWidth** (f32, was "uknKeyframeOffset"), 0x1AC = **KeyframeHeight** (new); keyed sizes clamp at 0. Width/Height are **half-extents**; WidthAdd/HeightAdd per frame, a non-keyed size <= 0 kills. PolygonFlags: 0-3 plane (corner (a,b) -> 0 (0,a,b), 1 (0,-a,b), 2 (-a,0,b), 3 (a,0,b), 4/6 (a,b,0), 5 (-a,b,0)), 4-7 RotOrder, 8-11 DirAxisType, 16-19 pivot (0 centre, 1-8 corners/edges, 9 PatCenter), 20-23 billboard, **24-31 DivideNum** (strips). DistortRate scales each corner (c0 a0b1, c1 a1b1, c2 a0b0, c3 a1b0). | initParticlePolygon 0x9792F0, sub_98EAA0, sub_9B54C0, sub_9CCDB0 |
| Range keyframe 0x1D4 | Sets mStatus 0x40 only; at spawn sub_999640 evaluates it (generator timer) and **replaces Range s and r**; the spawn-shape scale still applies; the keyed path skips the burst smear. | sub_999640 |
| PrimModel shape keys | 0x24C/0x250/0x254/0x258 replace Radius0/1, Height0/1 (RadiusAdd/HeightAdd otherwise), no clamp; the vertex builders run per draw on the per-particle shape. | 0x97BE70, sub_990310, 0x962BC0 |
| Model UV scroll | ScrollU/V (and keyframes 0x128/0x12C) are **speeds**: offset += speed per frame, wrapped to [-1, 1], uploaded to gXfUVScroll. | 0x97AF80, sub_98F9C0, renderModel 0x9A20C0 |
| Rope keyframes | Length = **total** length (/ (n-1) per segment, clamp 0); Rot / BlendRot replace the angles and calcDir runs every frame (bytes +4 / +5 give order/axis); BlendRate replaces the rate (0 skips blending). PathChain: offsets relative to the move block, generator timer; CHAIN trails: particle block, particle timer. | initChain 0x984350, moveChain 0x994C20 |

Implemented: the trail/cloth extensions are schema fields (`schema.struct_for_data`, e.g. `EFL_PARTICLE_Polyline+CHAIN`), so their 292 keyframes are editable; generator keyframes renamed Range/Pos/Rot (aliases kept); Polygon half-extents, pivot, plane, distort and W/H keyframes; PrimModel shape keyframes (per-vertex basis rebuilt in Geometry Nodes); Model UV scroll; the Range keyframe; rope keyframes; InitOnly + Add semantics.

**Not modelled yet:**
- unit generators (effect repeaters); Bounce/Finish child effects; collision with real stage geometry;
- external wind on ropes and cloth; cloth inertia from emitter motion; Model tint/alpha on materials,
  ModelBillboardType;
- the game's RNG table.

One shared node-group library, created from code with a version stamp and reused across imports:

| Node group | Inputs | Implements |
|---|---|---|
| `EFL_Emit` | WaitFrame, SetFrame, LoopNum, SetNum, SetInterval, RandomNo seed | emission schedule (port of the `updateSingleGenerator` / `uknGenBehaviorFunc1` state machine, incl. the loop reseed `base + rand % (range+1)`) |
| `EFL_SpawnShape` | RangeType, ranges, RangeDivideNum | point/sphere/box/cylinder/strip distribution (after R5) |
| `EFL_Range` | s, r, seed | per-point `s + rand × r` |
| `EFL_Move_None/Add/Mul` | speed, accel, gravity, fall speed, rate | velocity integration per step (Add: `v += a`; Mul: `v *= rate`; both: `fall += gravity`) |
| `EFL_Move_Path*` | curve, distance, reach frame, sub-mode | Sample Curve by age; clamp (Line) vs wrap (Strip) |
| `EFL_Life` | life block (after R2) | age → alpha/scale curves |
| `EFL_Instance_*` | particle type | Billboard (camera-aligned quad), PrimModel (instanced M1c mesh with per-instance shape/scale/rot velocities), Model (linked object), Polyline/Line/Texline (trail curves → Curve to Mesh) |

- Keyframe blocks (after R1) → F-curves on the matching node-group inputs, or on per-particle curves sampled by age.
  `MtEaseCurve` → F-curve easing.
- RNG: the game uses a 4096-entry table (`sDevil4Effect::mpInstance + 0x20 / +0x4020`) indexed by a running counter.
  Optionally dump the table from a live process to get deterministic, game-matching randomness. Otherwise use Blender's
  hash-based Random Value node and accept the divergence.

**Exit:** a chosen set of reference effects (1–2 per particle/move type) visually matches in-game footage in timing
and shape.

### M3 — Optional

- **Export** (Blender → `.efl`): only for edited parameters on imported effects. Write through the raw-preserving
  model, so unknown bytes survive.
- **Live validation:** x64dbg (sandbox skill) breakpoint after `initGenerator` / `initParticle*` to compare runtime
  Generator/Particle values with what the parser predicts.

---

## 6. Blender conventions (decide in R8, then freeze in `coords.py`)

- **Axis:** MT Framework content is Y-up. Albam maps `.mod`/`.lmt` with `(x, y, z) → (x, -z, y)`. **Verify** that
  effects match, using an effect attached to a known joint.
- **Units:** Albam imports models in cm × 0.01 (metres). Use the same default, and keep a scale option until R8
  confirms it.
- **Joints (verified 2026-10-05):** `ParentNo` is the MT **joint number** (`idx_anim_map` in the .mod), which Albam
  stores per bone as `bone['mtfw.anim_retarget']`. It is **not** the hierarchy index, even though Albam names bones
  `str(index)`. Nero's hand effects use joints 150/151, which are bones 25/52 (the hands, x = ±0.79 m in bind pose).
- **Joint frames (verified):** Albam's bone matrix is `swap @ inverse(bind matrix)`, i.e. the game joint frame in
  Blender axes. So a generator's `Pos`/`Quat` apply unchanged in the bone head frame, with `Pos` × 0.01.
  Unattached generators sit under a root rotated +90° about X (game Y-up → Blender Z-up).
- **Quaternion:** the file stores `MtVector4 (x, y, z, w)`; Blender expects `(w, x, y, z)`.
- **Frames:** keep EFL frame counts as-is in properties. Map to scene time by `scene_fps / mBaseFPS`.
- **Naming:** collection `EFL_<file>`; objects `Gen_<i>_<Ptcl>_<Move>`; property keys mirror schema names.

---

## 7. Validation and tests

1. **Round-trip** (M1a gate): byte-identical rewrite for the entire corpus.
2. **Structural invariants**, checked for every file:
   - block offsets fall inside the content and are 4-aligned;
   - blocks don't overlap (unless shared on purpose; record which ones are). *(corpus)* None are shared in DX9;
   - inferred block size ≥ the schema size for the slot's type byte;
   - self-relative offsets land inside their parent block's span;
   - char[64] paths are NUL-terminated printable ASCII **without** an extension, under the expected folder
     (`effect\tex`, `effect\ean`, `effect\efs`, `effect\mod`; `id\item` also occurs). Resolve them by appending the
     extension, as Albam does for `.mod` texture paths;
   - enums are in range (particle 0–17, move 0–6, PrimModelType 0–5);
   - floats are finite.
3. **Field-usage coverage:** for each schema field, the percentage of corpus records where it is non-zero. Fields that
   are always zero are candidates for "unused"; varying unknown spans are RE priorities.
4. **Cross-check with the IDB:** each `dx9` schema row carries the function/address that proves it, and a
   script can re-verify the offsets against the live IDB after future struct edits.
5. **Visual references:** capture 10–20 in-game effects (screenshots or video) for M1c/M2 sign-off.

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| ~~No samples yet~~ | Resolved: 1,109 DX9 files (M0) |
| SE files mixed into the sample folders | Filter on version `0x20070801`; `Demo\` and `arc files\` are SE only |
| Keyframe/life formats are harder than expected | M1 doesn't depend on them; ship static import first |
| Coordinate/unit conventions wrong | Isolated in `coords.py`; validate with R8 before mass import |
| SE names leak into DX9 offsets | Schema evidence tiers; never copy SE offsets (the tail and other places differ) |
| Exact visual parity impossible (runtime RNG, sort/blend specifics) | Treat M2 as an approximation; optional RNG-table dump |
| Shared/overlapping blocks between records | Discovered by the §7 invariants; the model keeps blocks by offset and records reference them |
| Blender API churn (Geometry Nodes) | Build node groups from code with a version stamp; target one Blender LTS |

---

## 9. Design for later export

- The model holds each block as `(offset, raw bytes)` plus typed views, and edits write back into the raw bytes.
- Record/block topology (shared offsets, ordering, padding) is preserved exactly. Adding new generators means
  appending blocks and rewriting the table and header counts (`EffectListNum`, `contentSize`).
- No sidecar (`.efs`/`.ean`/`.tex`) writing is planned.


## Refraction particles (DX9-verified 2026-10-07)

- `uEffectVFR::initGeneratorParam` 0x96B612: `if (CullingFlag & 0x200) attr |= 0x20 (occlusion); else if
  (ParticleOptionFlag & 0x10) attr |= 1; ...`. attr = Generator+0xDC (mPrimAttribute), put into material word 1 by
  `calcPrimMaterial` (0x978123). Bit 1 = nPrim ATTR_REFRACT (SE's enum calls 0x10 ALPHA_BLUR). Occlusion wins (181
  corpus refract particles).
- `sPrim::setPrimitiveTechnique` (0xA35746, renamed) maps attr & 1 to FUNC_PRIM_EX = 3 = PRIM_EX_REFRACT in
  tXfPrimStandard (XfPrim.bfx). Permutation key `mode + 2 base + 6 normal + 12 mask + 24 bilinear + 48 ex + 384 fog`;
  3D + base map: VS 14, PS 45. `sPrim::setBlendState` (0xA35610) still uses the material's blend nibbles.
  `sPrim::drawTags` (0xA36F31) puts attr & 1 batches in sort layer 8 at half depth. XfPrimSceneSampler =
  cContext+0x218 (mpSceneTexture; main view sRender+0x17000 mpScreenTexture, 0x8E7B10).
- VS: colour = vertex colour (no Intensity tint); `uv.z = 1.28 x v2.w` = Intensity / 100 (v2.w = Intensity x 256,
  written at vertex+0x26 by sub_961250 0x9614F1 for billboards; assumed for the other prim builders).
- PS 45: `offset = (BaseMap.rg - 0.5) x Intensity/100` (screen UV, +v down); `out.rgb = Scene(pixel/size + offset)
  x Color.rgb`; `out.a = BaseMap.a x Color.a`. No fog. Normal/mask variants (47/48) are unused by the corpus.
- Corpus: 1,304 of 34,703 particles; all BaseMap only (mostly ec032_*); Intensity 1-30; 928 alpha blend, 315
  SRCALPHA/ONE/REVSUBTRACT, 61 additive; PrimModel 302, Billboard 270, Polygon 258, Polyline 238, PolygonStrip 214.
- Unknown: when mpScreenTexture is copied relative to layer 8 (whether refraction particles see each other).
- Albam: `effect._build_refract_material` (tinted transparency, no offset; see CLAUDE.md).


## .ean / .efs layouts, DX9 vs SE (checked 2026-10-08)

Names from the SE PDB (IDB on port 13338): rEffectAnim::EAN_HEADER / SEQ_INDEX / SEQ_PAT / ANIM_FLAG and
rEffectStrip::EFS_HEADER / PARTS_PARAM / VERTEX_PARAM / INDEX_PARAM / STRIP_TYPE / STRIP_FLAG. Full layouts are in
the docstrings of `albam/engines/mtfw/efl/ean.py` and `efl/efs.py`.

- **.ean**: DX9 0x20060501 (822 files), SE 0x20120224 (3,305). Header and SEQ_INDEX are identical; SE's SEQ_PAT
  appends f32 U0, V0, U1, V1 to the s16 (U, V, W, H) rect, so SE patterns are 24 bytes and DX9 ones 8. Every file of
  both versions parses exactly.
  - Header +0x0C: SeqNum : 24, OptionFlag : 8 (always 0).
  - SEQ_INDEX: SeqPatTopOffset, SeqPatNum : 16, DefaultAnimFlag : 16 (ANIM_FLAG: 0 / 8 FINISH / 3 MOVE|LOOP / 9 / 1),
    MtPoint DefaultPatCenter (the frame pivot, e.g. the cell centre), MtPoint ConPatBasePoint,
    ConPatColNum / ConPatTotalNum / ConPatSizeW / ConPatSizeH : 16. The ConPat fields are the grid the frames were cut
    from: in all 5,931 DX9 sequences with ConPatTotalNum == SeqPatNum, the patterns are exactly that grid.
  - Of 2,997 same-name DX9/SE pairs, 2,503 have identical sequences and rects; 494 differ in content.
- **.efs**: DX9 0x20060725 (53), SE 0x20080912 (2); byte-identical apart from the version.
  - VERTEX_PARAM (32 bytes): Pos f32[3], BlendIndex0-3 u8, Norm f32[3] (unit length in all 1,209 points),
    BlendWeight0-3 u8 (all 0).
  - Header EfsHeader320c, JointNum and TotalIndexNum are 0 in every file. INDEX_PARAM triangles (u16 x3 + u16)
    follow the vertices only for STRIP_TYPE_MODEL, and no file has any.


## TransMode = cTrans::MODE (from the user, 2026-10-08)

`enum cTrans::MODE { MODE_WORLD = 0x1, MODE_REFLECTION = 0x2, MODE_SHADOW_RECV = 0x4, MODE_SHADOW_CAST = 0x8,
MODE_ENV = 0x10, MODE_MOTIONBLUR = 0x20 }`. Particle TransMode (ptcl +0x00) is this pass mask. In the corpus (17,360
particles): 1 in 17,096, 0 in 263, 3 once. Albam builds no geometry without MODE_WORLD.


## Draw gate and passes (2026-10-08)

- `uEffectVFR::isGeneratorVisible` (0x53D460, renamed, not saved to the IDB yet) gates every generator in
  renderGenerators: `Generator+0x16 & 2`, then `(view CONTEXT.mMode @+0x1FC & Generator+24) != 0`, then a
  sphere-vs-frustum test.
- Generator+24 (initGeneratorParam 0x96AEC0): ptcl dword 0 (TransMode byte = cTrans::MODE mask, ...) with bits 8-11
  replaced by PassBits (`PrimMaterialFlags >> 12`, i.e. `ptcl dword +0x10 >> 20 & 0xF00`). PassBits is therefore a
  second mask (view mode bits 8-11), not a cTrans::PASS number. `cTrans::beginSubScene` (0xA585A2) sets the view's
  mMode = MODE byte, clears bits 8 and 9, and sets a 4-bit field at bit 10 to 1. Which views set bits 8 / 9 is not
  found yet. A TransMode-0 particle can still draw in a view with its PassBits bit (corpus: 257 have TransMode 0 +
  PassBits 1); Albam builds no geometry for them.
- `cTrans::PASS` (from the user): 0 BEGIN, 1 ZPASS, 2 SOLID, 3 OVERLAP, 4 NUKI, 5 TRANSPARENT, 6 EFFECT,
  7 TRANSPARENT_NZ, 8 FILTER, 9 SCREEN, 10 END. It's the sort layer of a draw's TAG: refraction batches go to layer 8
  = PASS_FILTER (sPrim::drawTags 0xA36F31), after the screen copy. SE's engine has 25 passes (nDraw::PASS_TYPE),
  with a separate PASS_DISTORTION.


## ColorFlag = nEffect::COLOR_FLAG (verified 2026-10-08)

- SE PDB enum, as the user gave it: R_BLEND 0x1, G_BLEND 0x2, B_BLEND 0x4, A_BLEND 0x8, EACH_RANDOM 0x10, CHOICE 0x20,
  BLEND 0xF, DUAL 0x2F.
- DX9 `uEffectVFR::calcSrcColor` (0x9801B0, called from initParticle* with &Color0 and the ColorFlag byte at ptcl
  +0x40): colour = Color0; if flag & 0xF, t = random; each set blend bit mixes that BGRA byte to
  `(1 - t) * Color1 + t * Color0` in the order R, G, B, A, re-rolling t after R / G / B when EACH_RANDOM is set.
  CHOICE is not handled in DX9.
- Corpus: ColorFlag 0 in 15,778 draw particles (Color0 == Color1 in all but 2); 0xF 433, 0x7 334, 0x8 268, 0x1F 139,
  0x10 113 (always with equal colours, so it does nothing), 0x17 18; CHOICE never.
- Albam: `sim._src_color` reproduces it; the Effect Editor shows ColorFlag (and TransMode) as checkboxes.
- Side find: initParticleBillboard (0x977E60) line ~383 calls effect vtable slot 42 with the particle position when
  the generator's PassBits (mFlags & 0xF00) are non-zero, storing two results in the particle. Not followed yet.


## AnimFlag / ModelAnimFlag (2026-10-08)

- `AnimFlag` (ptcl 0x50, u16) = SE `rEffectAnim::ANIM_FLAG`: 0x1 MOVE, 0x2 LOOP, 0x4 REVERSE, 0x8 FINISH (pattern step
  `sub_961DB0`: forward past the end loops with LOOP, else holds at last + 0.9, and FINISH kills; reverse below 0
  loops, else 0, FINISH kills), 0x100 HFLIP / 0x200 VFLIP / 0x1000 ROT (`sub_9632F0`).
- `uEffectVFR::getAnimFlag` 0x980140 (called by initParticleBillboard / Polyline / Polygon / Texline / PrimModel /
  PolygonStrip / SizeBillboard / LiteBillboard): `flag = ptcl.AnimFlag; if (flag & 0x800 && rand & 1) flag |= 0x200;
  if (flag & 0x400 && rand & 1) flag |= 0x100;` stored per particle at +0x70. VFLIP_RAND is rolled first.
- REVERSE_RAND 0x10 isn't handled in DX9. KEYFRAME 0x8000 is OR'd in at runtime together with MOVE when the particle
  has a PatNo keyframe (initParticleBillboard 0x978026), so it isn't a file flag. NO_INP 0x2000: no DX9 reader found
  (4 particles in the files set it).
- Files: 0xC00 is the most common AnimFlag (7,989 particles), then 0, 0x600, 0xC09, 0xC08, 0xC03.
- `ModelAnimFlag` (Model 0xFC, u32) = SE `nEffect::MODEL_ANIM_FLAG` for 1 MOVE, 2 LOOP, 4 REVERSE, 8 FINISH, but in DX9
  bit 0x10 gates the UV scroll (ScrollU keyframe +0x128 in initParticleModel 0x97BB04, move 0x99008D, renderModel
  0x9A228B / 0x9A2978): SE renamed it REVERSE_RAND. Files: 0x10 set on 180 records, 179 of them with non-zero
  ScrollU/V; no record without it has any scroll. 0x10000 = ModelZofs; 0x10000000 / 0x20000000 / 0x40000000 /
  0x80000000 are per-particle runtime state written by init / move.


## Particle header flags (2026-10-08)

SE layout (`rEffectList::EFL_PARTICLE_COMMON`): 0x00 DrawMode (u8; DX9 TransMode), 0x01 EntryType, **0x02 CullingFlag
(u8)**, **0x03 BlendState (u8)**, 0x04 ParticleOptionFlag, 0x08 LightGroupFlag, 0x0C Zofs, 0x10 OtDepthBias (f32 in SE;
DX9 has FixOtDepth u16 here and the bias float at 0x14), ... The addon schema used to treat 0x02-0x03 as one u16.

DX9 `uEffectVFR::initGeneratorParam` (0x96B55F..0x96B655), prim attribute word Generator+0xDC (SE
`nPrim::Material::AttributeType`) and generator status Generator+0x18:
- ParticleOptionFlag 0x4 -> ATTR_DEPTHBLEND 0x100; 0x20 -> ATTR_NOREDUCTION 2; 0x80 -> ATTR_NOZTEST 8; 0xC00000 ->
  ATTR_CULLING 0x20000; 0x1000 -> ATTR_NOFOG; 0x40000 -> status 0x10000 (MDLSCL_AFTER, calcParticleMatrix 0x98A77F /
  0x98B090: scale applied after the rotation); 0x200 -> status 0x80000 (WMAT_SCALE); 0x100000 -> status 0x100000
  (ROT_LOCAL: calcParticleMatrix 0x98B3FE skips the turn toward the motion direction); 0x200000 -> status 0x300000
  (ROT_INIT: initParticlePolygon 0x979C40 / Model / PrimModel / PolygonStrip / SizeBillboard turn once at spawn via
  sub_98C800).
- LightGroupFlag != 0 -> ATTR_LIGHTING 0x80. Resource +0xC != 0 -> ATTR_FRESNEL 0x10000.
- CullingFlag & 2 (OCCLUSION) -> ATTR_OCCLUSION 0x20, and refraction is skipped. Else ParticleOptionFlag 0x10 ->
  ATTR_REFRACT 1. Else if byte 0x03 != 0: option 0x400 -> ATTR_PARALLAX 0x800, else 0x800 -> ATTR_DEPTHVOLUME 0x400,
  else ATTR_VOLUME 0x200.
- `sPrim::setPrimitiveTechnique` 0xA35670 picks the extended pixel shader from those (SE `FUNC_PRIM_EX`):
  0x20 -> OCCLUSION (1) or OCCLUSION_NOVTF (7 without vertex texture fetch), 0x800 -> 6, 0x400 -> 5, 0x200 -> VOLUME
  (2), 1 -> REFRACT (3). (The SE enum has 5 PARALLAX and 6 OCCLUSION_NOVTF, so DX9's indices 5/6 may be ordered
  differently; not checked in the shader table.)
- Byte 0x03 (SE BlendState, called VolumeBlendRate in the addon) is passed to every vertex by all particle builders
  (`sub_961250` etc.: byte 15 of each 32-byte vertex). Values 1-100; non-zero on 26,626 of 34,703 particles.
- CullingFlag & 1 -> the culling draw variant (mTransType 0x11+); & 0x80 (ANGLE) without & 4 (PARTICLE) -> one
  direction per generator (0x96B6A2). Corpus bits: 0x1 1,911, 0x2 2, 0x4 105, 0x80 772.
- Bug found: the addon's refraction check tested 0x200 of the u16 (a byte-0x03 bit); 324 of the 1,304 refraction
  particles were previewed without refraction. Fixed (`sim.OCCLUSION_FLAG = 0x2`).

`uEffectVFR::setPrimEnv` 0x99DB60 (draw-order key): option 0x1 OT_DEPTH -> 0x8000 = each particle keyed by its own
position (sub_961250); `TransType == 5` -> 0x7FFF; 0x2 OT_FIX -> FixOtDepth (movzx word +0x10); 0x100 OT_UNIT ->
the cUnit position (+0x30) instead of the generator's; sign bit -> position minus camera axis x float +0x14
(OtDepthBias); a negative key is dropped unless 0x40 NO_CLIP (then 0).

ParticleOptionFlag 0x20000 EXT_LINE_POS is read only by renderPolyline / Texline / Line (+ Culling, _interp);
0x10000 PAT_CENTER by renderBillboard*. 0x8 INV_VOLUME: no DX9 reader found. Usage: 0x100 26,312, 0x40 9,113, 0x8 4,879,
0x4 4,521, 0x20000 1,807, 0x40000 1,351, 0x10 1,304, 0x200000 1,209, 0x10000 568, 0x2 538, 0x200 431, 0x1 369,
0x80000000 165, 0x100000 126, 0x80000 99.

Light (2026-10-08): `uEffectVFR::updateParticleLight` 0x99C19E: light attr byte = ptcl Light +0x40 (`LightAttribute` =
SE `rEffectList::LIGHT_ATTR`: 2 SH, 8 PERPIXEL, 0x10 SIMPLE) | 0x40, with 0x8 cleared when light+0x19 == 0; light+0x1C
= ptcl +0x08 `LightGroupFlag` (light-group mask, the same concept as a uModel's light group, per the user; TransMode
is likewise the uModel cTrans mode). Files: LightAttribute 0x10 on all 177 Light particles; LightGroupFlag 0xFFFFFFFF
on 153 of them; on other particles non-zero on 337 Model and 21 Polygon (-> ATTR_LIGHTING).

Groups on uModel (DX9, 2026-10-08): `uModel` +0x130 mLightGroup, +0x134 mShadowCastGroup, +0x138 mShadowRecvGroup
(uModel::uModel 0x9E68BD: 3, 1, 1). `uModel::setModel` 0x9E6ED5 copies rModel+0xF8 into mLightGroup; rModel load
(vtable slot 8, 0xA53F50) fills rModel+0xF8 from the .mod header +0x88 (Albam mod-153.ksy `model_info.light_group`;
+0x8C is strip_type / memory). 837 DX9 .mod files: 0x3 184, 0x2 117, 0x2001 117, 0x0 104, 0x1 70, 0x20 36, ...
The shadow groups aren't loaded from the .mod. SE's EFL Model particle adds ShadowCastGroup / ShadowReceiveGroup
(nibbles at 0x10E / 0x10F); the DX9 Model block has no such fields.


## Particle orientation and culling fade (2026-10-08)

`uEffectVFR::calcParticleMatrix` 0x98A6A0 (Model init / move / render, PrimModel init / render, strips), row vectors:
`M = S . R(Euler, order) . G`, or `R . S . G` with generator status 0x10000 (ParticleOptionFlag 0x40000 MDLSCL_AFTER).
G = Generator+0x150: updateWorldMatrix 0x96E8AF builds it every frame as mWmat rows x particle scale, or as identity x
scale with status 0x100000 (ROT_LOCAL, option 0x100000; option 0x200000 sets 0x300000). When the move result flags
have 0x80 (CALC_DIR; Add / Mul / paths return 0x180, None 0x80 / 0x180) and DirAxisType != 6 and not ROT_LOCAL, G is
replaced by the shortest-arc rotation getAxisVector(DirAxisType) -> move direction (0x100 = world direction, else
times mWmat rows), scaled. Add's direction = normalize(speed - fall) (moveParticleMoveAdd 0x996160).
ROT_INIT (status 0x200000): initParticlePolygon / Model / PrimModel / PolygonStrip / SizeBillboard call sub_98C800 with
mPtclFlagBase (0 or 0x10000, never 0x80), so it takes the generator branch: quaternion of mWmat -> Euler (sub_95FD70,
the particle's order) added to Rot (initParticlePrimModel 0x97CBCC).

`uEffectVFR::calc_culling_fade` 0x963BD0 (renderBillboardCulling etc., once per generator with v = camera - generator
position, or per particle with block flag 0x4); block word +2 = CULLING_OPTION_FLAG:
- 0x2000: d <= NearStart or d >= FarEnd -> 0; d < NearEnd -> (d - NearStart) / (NearEnd - NearStart), 0 with 0x4000;
  d > FarStart -> 1 - (d - FarStart) / (FarEnd - FarStart), 0 with 0x8000.
- block byte & 0x80: c = dir . normalize(v) clamped to [-1, 1], a = acos(c); 0x800: a <= AngleStart -> 1, a >= AngleEnd
  -> 0, else 1 - (a - AngleStart) / Rate; without 0x800: a < AngleEnd -> 1 - a / AngleEnd, else 0. 0x1: also with
  -dir (constant -0.0 - dir), combined by max, or min with 0x1000. Result = distance fade x angle fade.
- dir: calcDirWrapper 0x962510 (generator, `calcDir(CullingRot, word >> 12, word >> 8 & 0xF)` x mWmat rows) or
  init_culling_dir 0x962F40 (per particle, x the particle matrix).
Files: 900 particles use option 0xA000 (distance, far cut), 196 0x800, 172 0x1801, 147 angle with no options.


## Rotation orders (2026-10-09)

`setMatFromAngle` 0x95FF70 (angles at ecx, order in eax, out matrix): 0 setRotateZYX 0x8B6DD0, 1 setRotateZXY 0x8B6F60,
2 setRotateYZX 0x8B74E0, 3 setRotateYXZ 0x8B7A40, 4 setRotateXZY 0x8B7F90, 5 setRotateXYZ 0x8B8530, else identity.
Emulated with Unicorn (angles at edi, matrix at esi; ___libm_sse2_sin / cos hooked) and compared with Blender
`Euler(angles, order).to_matrix()` transposed (MT matrices are row-vector, v' = v . M): RotOrder 0-5 = Blender orders
XYZ, XZY, YXZ, YZX, ZXY, ZYX (max error 1e-7, next best 0.29), i.e. the axes are applied in alphabetical order of the
enum, not in the order of the function names. Callers inside the effect code: calcDir 0x9DEC60 (move direction,
culling direction, LensFlare, chains), calcParticleMatrix 0x98AAFC, calcParticleMovePath{Strip,Chain,Keyframe,Line}Pos,
sub_9600A0 (Euler -> quaternion; updateWorldMatrix 0x96C325, the generator rotation keyframe), sub_988B00 (Polygon /
SizeBillboard / PolygonStrip / Light matrices). Script: `scripts/rot_order_emulate.py` (+ `scripts/rot_dump.json`, the code / data pages from the IDB; needs `pip install unicorn`).

Polygon orientation (2026-10-09): sub_988B00 (initParticlePolygon / SizeBillboard, renderPolygon(+Culling, _interp),
buildStripVertsInterp, buildPolygonStripEdgeVert, updateParticleLight) = calcParticleMatrix without MDLSCL_AFTER:
setMatFromAngle at 0x988F2C, then status 0x100000 (0x9894F2) / DirAxisType == 6 (0x989502) / move flags 0x80 (sign of
the byte, 0x98950E) / 0x100 world direction (0x989516) -> getAxisVector + shortest arc, else Generator+0x150.
renderPolygon passes the particle's stored move flags (word +0xEE) and direction. Corpus: ~111 Polygon particles with
DirAxisType != 6 (PolygonBillBoardType 0).

Camera facing (2026-10-09): `uEffectVFR::build_view_basis` (mode eax, matrix = copy of the view-inverse at render
context +0x100): mode 2 / 3 / 4 = keep world X / Y / Z (row n2 = unit axis), row n2_2 = normalize(L x camera row n2_1)
(2: camY, 3: camZ, 4: camX), row n2_1 = L x row n2_2, fallback through row n2_2 when degenerate; any other mode returns
the view-inverse untouched (mode 1 = camera rotation). renderModel reads ModelFlags >> 8 & 0xF (0x9A2270), renderPolygon
PolygonFlags >> 20 (0x99E9F6), renderPrimModel* likewise; the result multiplies the calcParticleMatrix output
(0x9A2A31). Billboard type 0 never touches the camera on the CPU (corner codes, vertex shader expansion).

Billboard composition (2026-10-09): renderPolygon (mode = PolygonFlags >> 20 & 0xF, 0x99EA06): V = view-inverse
copy -> build_view_basis(mode, V) (0x99F160); per particle P = sub_988B00(..., generator, ...) and the drawn matrix rows
are P.row_i . V (0x99F8AD-0x99FCB2), translation = the particle position. P contains Generator+0x150 (or the alignment
or identity with ROT_LOCAL), so the billboard is V . G . R in column form. build_view_basis modes 2-4 give a basis with
determinant -1 (row n2_1 = L x (L x camera axis)).

Generator transform (2026-10-09): `uEffectVFR::setQuatParentOfs` 0x9687B0 (moveUnitGenerator passes Quat at gen +0x40,
Pos): rotation rows from (x, y, z, w) = (1 - 2(y^2 + z^2), 2(xy + zw), 2(xz - yw)) ... = Blender's
Quaternion((w, x, y, z)).to_matrix() transposed (row-vector); rows scaled by Generator+0x50..0x58 (scale before
rotation); translation = Pos. Parent cases by Generator+0x110 (= AxisFlags >> 8 & 0xF, initChildGenerator 0x96BC3F):
3 -> no parent (world); joint (vtable +60 of the parent model) -> (R . J), Pos . J; 2 -> same position, rotation rows
reset to the plain quaternion (world axes). RelationType in the files: 0 32,074, 2 2,609 (1,059 on joints), 1 20.

## Life frames and the keep hold (verified 2026-10-10, DX9)

- `uEffectVFR::initParticleLifeFrame` 0x9729B0 (was sub_9729B0): Appear / Keep / Vanish = s + rand % (r + 1);
  Keep comes from the u32 keyframe at KeepFlags bits 1-15 when set. Work block (Generator+0xCA, 0x10 bytes for life
  types 1-4): +0 appear, +2 keep, +4 vanish, +6 counter, +8 u16 = life+0xE (KeepHoldFrame), +0xA phase (0 appear,
  1 keep, 2 vanish, 3 dead), +0xB bit 0 = Generator mFlags 0x40000 at spawn (held), +0xC alpha.
- `uEffectVFR::moveParticleLifeFrame` 0x998C30 (was sub_998C30), life types 1 / 2 (types 3 / 4: keyframe alpha,
  `initParticleLifeKeyframe` 0x972B70 / `moveParticleLifeKeyframe` 0x998E20): appear alpha = counter / appear; at the
  end of Appear go to Keep (counter = KeepFrame), or with keep 0 and held, Keep with counter 1. In Keep, while the
  generator flag and the particle's held bit are set the counter doesn't move; the hold limit (if non-zero) counts
  down and at 0 sets counter 0 (Vanish next). Move result bit 2 clears the particle's held bit.
- Generator mFlags 0x40000 = life `KeepHoldFlag` (bit 0 of 0x0C), copied by `uEffectVFR::Generator::restart`
  0x9DF230 for life types 1 / 2; cleared by `uEffectVFR::doFinish` 0x96A280 and `doKeepHoldOff` 0x96A410, which
  `uEffectVFR::checkEnd` 0x9DD690 calls when the effect's owner ends it (end mode +0x111: 0 finish, 1 keep running,
  2 keep-hold off). Move result bit 2: path moves with PathOptionFlag 4 (KEEP_HOLD_OFF_PATH_END) at the path end
  (moveParticleMovePathStrip 0x997121 etc.), moveParticlePosCollision 0x99A210 with CollFlag bit 2 (bit 0 -> 4,
  bit 1 -> 8).
- Corpus: 1,506 held particles in 236 files; HoldFrameLimit 0 on 1,433 (others 200, 23, 240, 20, 92, 50, 60);
  KeepFrame 1 (569) or 0 (460) mostly; no life keyframes. Life types 1 (16,802) and 2 (75).
- Albam names: KeepFlags -> KeepOptions, KeepHoldFlag -> HoldUntilEffectEnds, KeepHoldFrame -> HoldFrameLimit.

## Spawn flags: MoveOptionFlag, RangeOptionFlag, RangeDisperseType, RangeStripType / Flag (verified 2026-10-10, DX9)

- SE enums (SE IDB): MOVE_OPTION_FLAG 1 COLLISION, 2 GRAVITY_NO_SCALE, 4 HIGH_ACCRACY, 8 ALWAYS_CORRECT, 0x10 ROT_LOCAL,
  0x20 ALWAYS_CORRECT_RELEASE, 0x40 LITE_COLLISION; RANGE_OPTION_FLAG 1 EACH_FRAME, 0x10 COLLISION, 0x20 COLL_NORM;
  RANGE_DISPERSE_TYPE 0 NONE, 1 OLD, 2 SUB; rEffectStrip::STRIP_FLAG 1 ORDER, 2 REVERSE, 4 NORM_OFF, 8 PATH_LOOP,
  0x10 CENTER_FIX, 0x20 ALL_PARTS, 0x40 SKINING. SE EFL_GENERATOR 0xC8 dword = RangeType, RangeDirType,
  RangeOptionFlag, RangeDisperseType; 0xCC StripType, StripFlag, PartsNo; then RangeDirBlendRate + RangeScaleX/Y/Z
  (Albam's UknRangeThing).
- MoveOptionFlag readers (all 428 effect functions decompiled): only 2 (initParticleMoveAdd / Mul,
  moveParticleMovePathLine), 4 (initGeneratorParam, sub_967850), 8 (initParticleMoveAdd / Mul). Bit 1 has no reader:
  Generator::AllocMemory sets mpCollParam (+0xD4) = get_coll_param (CollParamOffset) for move types 0-2, 4, 6 and
  setupMoveParamCommon turns collision on when it's set.
- RangeOptionFlag: initGeneratorParam 0x96AFA9 copies bit 0 to Generator mFlags 0x20000; openParticle 0x9DF333 then
  gives the particle serial (+0x10) mSetFrameTotal (+0x2C, +1 per spawning frame) instead of mSetParticleTotal (+0x28,
  +1 per particle). The serial picks calcRangeShape's RangeDivideNum slot (t = serial % (n + 1) / n), the keyframed
  range (sub_999640) and the strip ORDER / REVERSE index. Corpus: 63 records, none with a strip, RangeDivideNum or
  range keyframe.
- RangeDisperseType (0xCB): calcSpawnOffset 0x998F00 (was uknGenBehaviorFunc2) adds (Generator+0x200 prev world pos
  - +0xA0 current) x burstT for 1, (+0x1C0 - +0xA0) x burstT for 2 (burstT = i / count in moveGenerator); 2 also sets
  mFlags 0x8000. Corpus: 3 records with 1.
- Strip sampling: calcRangeStrip 0x963220 switches on RangeStripType: 0 calcRangeStripPoint (point index, also the
  point's normal), 1 calcRangeStripLine, 2 calcRangeStripCurve3 (3 points), 3 calcRangeStripCurve4 (4 points, cubic
  through them, sub_ADC660 basis + sub_ADC1E0), 4 calcRangeStripTriangle (random barycentric, CENTER_FIX = 1/3 each;
  the part's second count = triangles). pickRangeStripSegment 0x99B270: ALL_PARTS = random part, or with
  RangeDivideNum part = slot x parts / n and the fraction runs along that part; ORDER = serial % count, REVERSE =
  count - 1 - serial % count, else random; PATH_LOOP adds the closing segment; CENTER_FIX t = 0.5. SKINING (0x40) with
  an owner model (param+0x18, flag 0x200 at +0x10C) evaluates the points through its skinning (sub_AD9B60 /
  sub_ADA120 / sub_ADA360 / sub_ADA7E0 / sub_ADAB80). Corpus: types 0 (114), 3 (18), 2 (1); flags ORDER 99, SKINING 17,
  ALL_PARTS 1 (never with RangeDivideNum).

## ChainOptionFlag (verified 2026-10-10, DX9 moveChain 0x994C20)

- SE rEffectList::CHAIN_OPTION_FLAG: 1 NO_MAT_DIR, 2 NO_MAT_BDIR, 4 REF_RANGE_DIR, 8 REF_RANGE_BDIR, 0x10 FORCE_BLEND,
  0x20 MUL_MAT_BDIR, 0x40 STRETCH. The option word is *param_4 (the EFL_PARAM_CHAIN).
- Main pull (param_3+0x50): if the caller's flags (parama) have 0x80 and option & 4: the caller's direction vector
  (Polyline / Texline / Line move loops sub_98E3E0 / 98F0C0 / 98F5D0 pass the particle's move output and move flags
  through sub_992B70 -> sub_994590; PathChain movePathChain passes AxisZ and flags 0) - with 0x100 (world velocity,
  Add / Mul) scaled by Generator +0x60.., else with option & 1 scaled by +0x50.. (no rotation), else turned by the
  generator matrix. Otherwise the keyed / rolled ChainRot direction (calcDir), scaled (option & 1) or turned by the
  matrix. Blend pull: the same with 8 / 2 and BlendRot. 0x20: blend pull turned by the shortest arc from the ChainRot
  axis to the main pull. 0x10 picks the force solvers (sub_9863D0 / 986AC0 / 988320, wind at Generator+0x120).
  0x40 has no reader here.
- Corpus (particle CHAIN ropes / PathChain moves): 1 on 137 / 4, 2 on 206 / 19, 4 on 519 / 0, 8 on 77 / 0, 0x10 on 4,
  0x20 on 0 / 3.

## AxisFlags, EXT_LINE_POS, CollFlag (verified 2026-10-10, DX9)

- AxisFlags (generator 0x70): Order (bits 0-3) = rotation order of the generator rotation keyframe (updateWorldMatrix
  0x96BE10 -> sub_9600A0(rot, AxisFlags & 0xF)); AxisType (bits 4-7) is read only in moveUnitGenerator (0x97004E) for
  the header unit generator: 6 = its Quat (setQuatParentOfs / sub_969990), else identity + sub_967950 axis tracking.
  RelationType (8-11) confirmed again in updateWorldMatrix (3 = ignore parent, 2 = position only).
- ParticleOptionFlag 0x20000 (SE EXT_LINE_POS): renderPolyline / Texline / Line (+ their Culling / _interp variants)
  use sub_9B2900 instead of sub_9B2700; it calls sub_B0FEE0(points): skip leading segments with squared length <= 0.1,
  then keep points until the next such segment; only that range is drawn (nothing when there is none). The 0xC00000
  option copy to Generator+0xDC 0x20000 in initGeneratorParam is a different thing (IDA shows the mask as a string).
- CollFlag (collision 0x01): moveParticlePosCollision, on a hit with no bounces left, ORs bit 0 -> result 4, bit 1 ->
  result 8, bit 2 -> result 2. Move loops (e.g. sub_98E000 Billboard): result 4 clears particle status 0x20 and the anim
  word bit 0 at +0x70 (flipbook stops); result 8 clears status 0x2000 and sets +0xA0 (angle add) = 0 (spin stops);
  result 2 clears the held bit of the life work (moveParticleLifeFrame). Corpus: 1 on 39, 2 on 64, 4 on 30 records
  (20 with a held life).

## EntryType (verified 2026-10-10, DX9)

- SE EFL_PARTICLE_COMMON byte 1 = EntryType (nEffect::ENTRY_TYPE 0 WORLD, 1 SCREEN, 2 REDUCTION, 3 OVERLAP, 4
  ACCUMULATION, 5 NONE, 6 MIX); byte 0 is SE DrawMode (Albam TransMode), byte 2 CullingFlag, byte 3 BlendState.
- DX9 initGeneratorParam: switch (ptcl+1) -> Generator+0x1C: 1 -> 10 END, 2 -> 7 TRANSPARENT_NZ, 3 -> 5 TRANSPARENT,
  else 6 EFFECT (cTrans::PASS). Every renderer passes Generator+0x1C to sPrim::getcPrim, so it is the draw pass of the
  particle's batch. Corpus: 0 on 16,692, 2 on 388, 1 on 14, 3 on none.

## AxisFlags upper nibbles, LineRotFlags / FixFlags (verified 2026-10-10, DX9)

- Generator AxisFlags (0x70) bits 20-23: updateWorldMatrix tests [esi+70h] & 0xF00000 == 0x200000 (0x96F925: own
  rotation in world axes written into Generator+0x190 mParticleScaleWmat) and (>> 20 & 0xF) == 3 (0x96EBDB: ignore the
  parent), mirroring RelationType (bits 8-11 -> mWmat +0x70 at 0x96E3FD / 0x96C54F). The second matrix is built after
  the World Scale test (mFlags 0x80000 <- ParticleOptionFlag 0x200). Bits 12-15 (4 in every file) and 16-19 (6) have
  no reader. 110 records have bits 20-23 = 2.
- sub_98C800 (ROT_INIT spawn rotation, used by initParticlePolygon / Model / PrimModel / PolygonStrip /
  SizeBillboard / FIX init sub_980620 / LENGTH init sub_981050): args (direction, move flags, out Euler, generator,
  order, axis): axis == 6 or no move flag 0x80 -> the generator matrix as a quaternion -> Euler; else the shortest arc
  from the axis to the movement (turned by the generator unless flag 0x100). Lines pass (word >> 4) & 0xF and
  (word >> 8) & 0xF of LineRotFlags (LENGTH ext +0x30) / FixFlags (FIX ext +0x60).
- LENGTH move sub_993560: if (LineRotFlags & 0xF00) == 0x600 or no move flag 0x80: stick = calcDir(LineRot or its
  keyframe, order bits 4-7, axis bits 0-3) turned by the generator; else stick = the movement direction (world velocity
  through the inverse generator matrix x mWscale when 0x100, else the spawn direction turned by the generator) and the
  particle's LineRot becomes the Euler of the arc axis (bits 0-3) -> movement. Corpus LineRotFlags bits 8-11: 6 on 1,839,
  4 on 510, 2 on 132, 0 on 65, 5 on 19, 3 on 17, 1 on 5. FixFlags bits 8-11: 6 everywhere; bits 0-3 have no reader.

## Light groups, OcclusionRadius, DrawFlags_0x41 / AnimFlag 0x2000 (2026-10-10, DX9)

- uModel::transDefault (0x9F2544 / 0x9F2EB2) passes uModel+0x130 mLightGroup to sub_A66180 (the model's light list
  build): both loops skip a light unless (light+0x1C group mask & mLightGroup) != 0; the light's attr byte +0x18:
  0x2 -> SH ambient accumulation, 0x8 -> per-pixel list (count capped by sShader +0x68F4), 0x10 -> simple list (point
  lights only, cap +0x68F8), (attr & 0x18) == 0 -> skipped; +0x19 light type 1 directional, 2 point, 3 spot. A Light
  particle hands LightGroupFlag to its light, so it lights a model when the masks share a bit.
- Culling OcclusionRadius (+0x2C): no reader in calc_culling_fade / init_culling_dir; 0 in all 893 culling blocks;
  CullingFlag 0x2 OCCLUSION is on 2 particles (it suppresses refraction, initGeneratorParam).
- DrawFlags_0x41 bits 0x2 / 0x40 (dword 0x40 & 0x200 / 0x4000) and AnimFlag 0x2000 (the particle's copy at +0x70):
  no reader anywhere in the effect code. 2 and 4 particles set them.

## PassBits (2026-10-10, DX9)

- isGeneratorVisible 0x53D460: (view CONTEXT +0x1FC mMode & Generator mFlags) != 0 (and the culling planes). mFlags low
  byte = TransMode, bits 8-11 = PassBits. cTrans::beginSubScene 0xA58560 sets mMode low byte = the view's TransMode
  mask, clears 0x100 / 0x200, sets bits 10-13 = 0x400 (sub_8E6830 / sub_A58CF0 rewrite bits 10-13 one-hot: 0x400,
  0x800, 0x1000, 0x2000 by their flags). Mode 0x100 is set by uModel::transReflection (0x9F4835 / 0x9F562C),
  sub_A9A730, sub_AC51E0, sub_ACDE00; no code sets 0x200. So PassBits 1 = also drawn in those reflection-type views,
  2 = no extra view. Corpus: 1 on 15,118, 0 on 1,889, 2 on 87.


## Preview gaps closed (2026-10-10, DX9)

- PrimModel colour gradient: every build*PrimModel* (Ring 0x9CD670 ... TexGrid) calls calc_color_gradient 0x9B52A0
  (eax = row k, ecx = HoriDivNum, edi = ColorPlaceInpType, push place no = HoriColorPlaceNo +0x174, push type =
  PrimFlags bits 16-19) for rows k and k + 1 of each cell and colours them sub_960400(colour, colour B, t) = A (1 - t) +
  B t per byte. Colour A = particle +0xC0 (mColor0), B = +0xC4 (mColor1), via fetch_primmodel_shape 0x962BC0.
  initParticlePrimModel 0x97BE70: only with ColorPlaceType != 0, mSrcColor2 = calcKeyframeColor of the 0x240 keyframe
  or calcSrcColor(PlaceColor1/2, ColorFlag); then sub_980340 (life fade: types 1 / 3 scale the alpha, 2 / 4 the rgb).
  Polyline 0x9786D0, Texline 0x97A0B0, Line 0x97A990 and PolygonStrip 0x97E800 roll their PlaceColor pair with
  calcSrcColor the same way.
- calc_color_gradient exact: type 1: i == 0 -> 0, i == last -> 1, else i / last; 2: 0 at both ends, 1 at place no,
  i / p or (last - i) / (last - p); 3: i <= p -> 0, i == last -> 1, (i - p) / (last - p); 4: i >= p -> 1, i == 0 -> 0,
  i / p; other types 0. Easing 0 linear, 1 sin(t pi/2), 2 1 - cos(t pi/2), 3 (1 - cos(t pi)) / 2, others 0; the 0 / 1
  end values skip the easing.
- Rim fade: renderPrimModelRing 0x9B5D20 picks buildPrimModelRingAttenuate 0x9CDF70 when PrimFlags & 0xF0000000 (also
  TexRing / Sphere / TexSphere; grids have no Attenuate builder). Per column it builds the frustum normal (sin, cos) x
  |r1 - r0| with axial dr^2 / |dh| (signs: outward; |dr| < 0.01 -> radial, |dh| < 0.01 -> +axis), turns it by the
  particle matrix, dot with normalize(eye - vertex) clamped, |.| unless PrimFlags 0x20000000, a = acos; a <= Start -> 1,
  a >= End -> 0, else MtEaseCurve::easeIn 0x8EE7E0 of (End - a) / (End - Start) = Bezier with control values 0, p1, p2,
  1 (NormAttenuateCurve). sub_963720 lerps the two edge values along the rows and multiplies the vertex alpha byte.
- World scale: updateWorldMatrix 0x96E480..: Generator+0x60 = own Scale (+0x50) x row lengths of the world matrix
  +0x70 (rows then normalised); +0x40 = effect scale (+0x108) x ParticleScale (+0x3C) x (mFlags 0x80000 WMAT_SCALE ?
  mean(+0x60) : 1); +0x150 basis = rows of +0x70 (or identity with mFlags 0x100000) x the scaled vector. initParticle
  0x970F28: spawn = mWmat . (mLscale * offset) + T, so the generator's scale moves spawn points; velocities go through
  movevel_transform 0x9750B0 (mWscale * dir, then the rotation rows); Gravity x mWscale.y unless MoveOptionFlag 2
  (initParticleMoveAdd 0x972F00); moveParticleMoveAdd subtracts the fall from world Y.
- Effect end: checkEnd 0x9DD690 -> doFinish 0x96A280 (every generator: mStatus |= 0x8000, state nibble -> 5 = no more
  spawning in uknGenBehaviorFunc1 0x9DDCB0, mFlags &= ~0x40000 hold) or doKeepHoldOff 0x96A410 (hold only).
- Strip samplers: calcRangeStripLine 0x99AAB0 -> sub_ADBD40 (lerp), Curve3 0x99ABE0 -> sub_ADBED0 (hermite on seg,
  seg + 1, tangents P1 - P0 / P2 - P1; open strip with (seg + 1) % n >= (seg + 2) % n -> line), Curve4 0x99ADF0 ->
  sub_ADC1E0 (window of 4 at offset 0 / 1 / 2 open, 1 closed, Lagrange cubic sub_8D40F0 at u = offset + t). sub_ADC660
  reads positions x the UknRangeThing scale and the vertex normals; each sampler outputs the normal interpolated the
  same way and normalised. initParticle 0x97121A: without RangeStripFlag 4 NORM_OFF the normal becomes the target
  direction (particle flag 0x80); movevel_transform blends calcDir toward it by UknRangeThing[0] and normalises.
  Skinned variants (sub_ADA120 / ADA360 / ADA7E0 -> sub_ADB980 / ADB120) need the owner model, RangeStripFlag 0x40 and
  owner flag 0x200: with .efs JointNum (0 in every DX9 file) they skin per vertex (sub_ADC930), else the whole strip
  goes through the owner's joint matrix (ParentNo, or the owner's joint, map 255 -> the model matrix) into world space.
- PathStrip moves: calcParticleMovePathStripPos 0x975440 switches on PathStripType: sub_ADA2B0 linear, sub_ADA680
  hermite (open last segment linear), sub_ADAA50 Lagrange; calcPathStripLength 0x9DE470 builds the arc-length table
  with PathCurveDivideNum steps per segment (sub_AEC030 / sub_AEC2C0), sub_AE5100 turns a distance into a fractional
  step; PATH_LOOP adds the closing segment.
- RangeDisperseType: calcSpawnOffset 0x998F00 (named uknGenBehaviorFunc2 in the IDB): offset += (Generator+0x200 (1) or
  +0x1C0 (2) - +0xA0 current translation) x burstT, before mLscale and mWmat.
- PolygonStrip: buildPolygonStripEdgeVert 0x98D240: M = sub_988B00(Rot, generator, scale, RotOrder, DirAxisType,
  direction, flags); axis = getAxisVector(RotAxisType) through M; edges P +/- axis x Width (1 - WidthPlaceRate / it).
  The history holds world-space vertices, one pair per move tick.
- MDLSCL_AFTER: calcParticleMatrix 0x98A6A0 multiplies the scale before setMatFromAngle (S . R) without it and after
  (R . S) with it (Generator mFlags byte +0x1A bit 0), before the generator basis: column form G . S . R.
- Model particles: renderModel 0x9A20C0 -> sub_A38780(..., particle colour +0xA0 / +0xA4, intensity x 256, part,
  ...) after getcPrim / setPrimEnv: the model is drawn with the particle's colour and the record's blend state.
