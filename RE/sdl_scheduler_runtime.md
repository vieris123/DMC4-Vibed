# DMC4 DX9 scheduler (`.sdl`) runtime evaluation

Read-only RE of `DevilMayCry4_DX9.exe` (IDB on port 13337), 2026-10-10. Nothing in the IDB was changed.
Confidence: **H** = read directly from code/disasm, **M** = inferred from code plus file data, **L** = guess.
File statistics are over the 2,658 unique `SDL\0` v16 files under `E:\DMC mod stuffs` (SE v22 files skipped).

## Functions

| Address | Name (IDB) | Role |
|---|---|---|
| 0x9E4E70 | `rScheduler::decompress` | Load: checks `SDL\0` + u16 version 16, relocates offsets, resolves DTIs, loads resources |
| 0x9E4CF0 / 0x9E4D00 / 0x9E4D20 | rScheduler vtbl +0x34/+0x38/+0x3C | track count (u16 +6) / frame count (`[+8] & 0xFFFFFF`) / floor flag (byte +0xB bit 0) |
| 0x90A660 | `uScheduler::uScheduler` | defaults |
| 0x90A920 | `uScheduler::setData` | sets the rScheduler, frame = 0, prev = -1, builds the track-state array (0x90AD50) |
| 0x90A980 | uScheduler vtbl +0x0C (`createProperty`) | property names for the fields below |
| 0x90A850 | uScheduler vtbl +0x18 (`move`) | per-tick: evaluate, then advance frame |
| 0x90BFA0 | (unnamed) `update` | binds units/properties for every track, calls `keying` |
| 0x90AF00 | `rScheduler::keying` | evaluates one track at a frame |
| 0x90BED0 / 0x90BDD0 / 0x90BE70 / 0x90BC90 / 0x90BCF0 | marker helpers | MarkerAdjust, get/set `mMarkerNo`, get/set `mMarkerFrame` |

uScheduler fields (names from 0x90A980): +0x10 `mDeltaTime` (cUnit), +0x18 track count, +0x1C current frame
(float; `Frame`/`FrameF`), +0x20 previous frame (float), +0x24 `mSpeed` (1.0), +0x28 `mPause` (**default 1**),
+0x29 `mLoop` (default 1), +0x2A `mFloorFrame` (copied from the header flag every tick), +0x2B `mMarkerAdjust`
(default 1), +0x2C track-state array (0x34 bytes per track), +0x38 `mpScheduler` (rScheduler). **H**

Per-track state (0x34 bytes, built at 0x90AD50): +0 pointer to the file's 0x18-byte track, +4 dword = track type in
the low byte and the cached key index in bits 8-31, +8 bound object (the created unit, or the owner object of a
property), +0xC a copy of the 40-byte `MtProperty` found by name. **H**

## Header corrections (0x9E4E70, 0x9E4D00, 0x9E4D20, 0x90BED0)

- +0x08 u32: bits 0-23 = frame count, **bit 24 = floor flag** (`mFloorFrame`, rScheduler vtbl +0x3C 0x9E4D20). When
  set, both the current and previous frame are floored before evaluation (0x90BFD5..0x90C044). 2 files set it,
  e.g. `st105.sdl`. **H**
- +0x0C u32 is **not a DTI-table offset**. It is the **marker track index**: `track[hdr+0xC]` is read as a list
  of marker (cut) frames from its timing array. 446 files have 0 (the keyless Root). 2 files point to an int track
  named `mCut` (e.g. `m01_100s_B.sdl`: track 24, keys 0, 123, 223, ...; the values are the cut numbers 11..22). **H**
- +0x10 = name area offset, relocated to a pointer (0x9E4EE4). Tracks start at +0x14. **H**

## Load (0x9E4E70)

| Track type | Fix-up | Confidence |
|---|---|---|
| 1, 5 | name += name area | H |
| 2, 3 | name += name area; `dti` replaced by `MtDTI*` (`get_DTI(hash)`) | H |
| 6-14 | name += name area; timing and data offsets += file base | H |
| 11 (resource) | each non-zero u32 value is an offset into the name area of `(u32 dti hash, char path[])`. It is replaced by `sResource::create(dti, path, 1)` (0x9E4FBA), so **every referenced resource is loaded when the .sdl loads**. | H |
| 12 (string) | values relocated to `char*` into the name area | H |
| 4 | not touched; ignored at runtime as well (not in the update or keying switches) | H |

**DTI hashes are not CRC32.** `MtCRC::getCRC` (0x8B6B40) XORs, for every character pair `(c[i], c[i+1])`
(including the trailing NUL as `c[n]`), the first tempered output of an MT19937 seeded with
`((c[i]-32) << 6) | (c[i+1]-32)`. The seed uses the old Knuth `sgenrand` (`MtRandom::init` 0x8BD2A0: each word =
`seed & 0xFFFF0000 | (next >> 16)`, with `seed = 69069*seed + 1` applied twice per word). The result is masked
`& 0x7FFFFFFF`.
- Checked: uDevil4Model = 0x239AF7FE, uSe = 0x464A0BFE, uInfiniteLight = 0x74695027, sCamera = 0x5C1CB015. **H**
- Unit classes in the files: uDevil4Model 516, uScheduler 324, uCustomDemoActor 152, uHemiSphereLight 114,
  uDevil4Effect 104, uInfiniteLight 89, uSe 84, uPointLight 58, uCnsChain 50, filters, uStageSet*, and others.
  Type 3 tracks: sCamera, sShader, sVibration. **H**

## Per-tick flow (`move` 0x90A850, `update` 0x90BFA0)

1. Get `mFloorFrame` from the header.
2. If `prev != cur`: `update(keying = 1)`, then `prev = cur`. Otherwise `update(keying = 0)`, which only binds
   objects. **H**
3. If `!mPause`: `cur += mSpeed * mDeltaTime`. **H**
4. If `cur >= frames` (header): `cur = 0` if `mLoop` is set, else `cur = frames`. On a wrap, the excess is
   dropped. **H**

So evaluation happens at the frame reached in the previous tick: frame 0 first, with prev = -1. The defaults are
**paused** and **looping**; the owner unpauses it (e.g. a `bool mPause` track in a parent .sdl, or game code).

Inside `update`:
- Frames used: `f = cur` (floored if `mFloorFrame`). With `mMarkerAdjust`, if `floor(f) + 1` equals a marker
  frame, `f = floor(f)` (0x90BED0), so the last fraction of a frame before a cut doesn't interpolate into the
  cut. **H**
- The integer key-lookup frame is `F = trunc(f)` (x87 with rounding mode 0xC00, 0x90C06D). **H**
- `prev` is also floored when `mFloorFrame` is set. **H**

**Frame unit: 1/60 s.**
- `sMain::move` (0x90D69E...) sets `mDeltaTime` = elapsed time × `mFps` / counter frequency, and `sMain::sMain`
  sets `mFps = 60.0` (0x90C5CE).
- So `mDeltaTime` is 1.0 per 1/60 s, and at `mSpeed` 1 the scheduler advances 1 frame per 1/60 s.
- **M**: the unit's own `mDeltaTime` (+0x10) also passes through sUnit's move-line rate, which is normally 1.

## Binding (0x90BFA0 switch on track type)

- **2 unit:**
  - If it has no unit yet: `obj = dti->newInstance()` (vtbl +4 of the `MtDTI` stored in the track's dti field),
    then `sUnit::addBottom(obj, track.parent)`. **So `parent` of a unit track is the sUnit move line. H**
  - If the unit's current line (`(unit[1] >> 3) & 0x7F`) differs from `parent`, the unit is moved to that line
    (0x90C308-0x90C331). **H**
  - Units are killed when the scheduler is reset or destroyed (vtbl +0x30, 0x90A7A0 / 0x90A700). **H**
- **3 system:** binds once. It walks the class-pointer properties (type 2) of `sDevil4Main` and takes the first
  object whose class is the track's DTI or derives from it (`checkDTI`, 0x90C371-0x90C39D). Seen: Camera/Fog_Camera
  → sCamera, CM → sShader, Vibration → sVibration. No unit is created. **H**
- **5 object (class member):**
  - Owner = `state[track.parent].object`, so `parent` is a **track index** (of a unit, system or object track).
  - The owner's `createProperty` list is searched for a property with the track's name and `MtPropertyType`
    (track byte 1) (0x8BC0F0), falling back to the name alone (0x8BC140). The property is copied into the state.
  - **If the property is an array (attr & 0x20), its index is set to the track's `dti` field** (0x90C26x:
    `prop+0x1C = track.dti`). That field holds the small numbers 0-10.
  - The track's object = the property's value (the member object pointer, `sub_8BF420`).
  - **H** (array semantics: the same attr bit drives indexing in the getters/setters 0x8BF420 / 0x8C08A0).
- **6-14 property:**
  - Same lookup on `state[track.parent].object`. It is redone only when the owner changes.
  - The dti field is again the array index for attr 0x20. Example: 10 `mpArchive` resource tracks with dti 0..9 in
    `m01_100s_B.sdl`.
  - Then `keying` runs, but only when `prev != cur`. **H**
- 1 and 4: nothing. **H**

## `rScheduler::keying` (0x90AF00)

Arguments: track state, the scheduler, `F` (int frame), `f` (float frame), `prev` (float).

### Key selection (0x90AF26-0x90AF72). H

- If the cached key's frame is greater than `F`, the cache is reset to 0.
- It then scans forward: `i` = the last key with `frame_i <= F`. If even key 0 is later than `F`, `i = 0`.
- **The mode byte of key `i` (`timing[i] >> 24`) governs the segment `i → i+1`.**
- `t = (f - frame_i) / (frame_{i+1} - frame_i)`, using the float frame, so playback is sub-frame smooth.
- Before the first key, `t < 0`, so mode 3/5 extrapolate. Only 9 tracks don't start at frame 0 (st300_snd,
  st705-m12-suimen).

### Mode 2 gate, applied before the type switch, for every type (0x90AF87-0x90AFBB). H

If key `i` has mode 2, the track is written **only when `prev < frame_i <= f`**, i.e. on the tick that crosses the
key. Otherwise nothing is written and the property keeps its value. In other words, a one-shot trigger:
- Only the current key is tested, so if one tick crosses two mode-2 keys, only the later one fires.
- With prev = -1 at the start, a key at frame 0 fires.
- After a loop wrap (prev = the last frame, cur = 0), a mode-2 key at frame 0 does **not** fire again.

### Per type (the switch is on the track type, then on the key's mode)

| Type | Mode 0 | Mode 1 / 4 | Mode 2 | Mode 3 | Mode 5 | Evidence |
|---|---|---|---|---|---|---|
| 6 int | step `v[i]` | **counter** `v[i] + (F - frame_i)` | step (after gate) | linear `(1-t)v[i] + t v[i+1]`, truncated to int (`cvttss2si`) | same as 3 (linear, truncated) | 0x90AFF5, 0x90B0B1, 0x90B009 (H) |
| 8 float | step | **counter** `v[i] + (f - frame_i)` (float) | step | linear | **Catmull-Rom** (below) | 0x90B0D3 switch: 0x90B16C, 0x90B0F2, 0x90B1A1, default 0x90B2D4 (H) |
| 7 vector (4 floats) | step | counter: `(f - frame_i)` added to **all 4** components | step | per-component linear on x, y, z, w (**no slerp, no normalise**) | per-component Catmull-Rom on all 4 | 0x90B6EC: 0x90B81F, 0x90B70B, 0x90B88F, default 0x90BABC (H) |
| 9 bool | `v[i] & 1` (any mode; the 1-byte values) | | gated | | | 0x90BAD4 (H) |
| 10 ref | step (see below) | | gated | | | 0x90BB2E (H) |
| 11 resource | set if different | same as 0 | set only on crossing | | | 0x90BBB2 (H) |
| 12 string | step (builds an MtString) | | gated | | | 0x90BB69 (H) |
| 13 event | fire (see below) | | fire once on crossing | | | 0x90BAEE (H) |
| 14 custom (64 bytes) | step | step | gated | linear on 16 floats | step | 0x90B2F8 (H) |

- At the last key (`i + 1 >= count`), modes 3/5 hold `v[last]` (H).
- Modes 1/4 have no end check, so the counter keeps running past the last key (H).
- "Step" means the key's value is written every evaluated frame (except under mode 2).

**Catmull-Rom (mode 5), float 0x90B1A1 and vector 0x90B88F (H):**

```
p0 = v[i], p1 = v[i+1]
m0 = (v[i+1] - v[max(i-1,0)]) * 0.5
m1 = (v[min(i+2, i+1 if i+2>=count)] - v[i]) * 0.5     # i+2 clamped to i+1 at the end
value = (2p0 - 2p1 + m0 + m1) t^3 + (3p1 - 3p0 - 2m0 - m1) t^2 + m0 t + p0
```

- This is uniform Catmull-Rom: the tangents ignore the segment lengths, and `t` is 0..1 within each segment.
- At the ends: at i = 0, m0 = (p1 - p0)/2; at the last segment, m1 = (p1 - p0)/2.

**Use in the files** (mode counts per key): float 0: 1,112, 1: 799, 2: 10, 3: 2,527, 4: 1, 5: 14. Vector 0: 739,
3: 2,861, 5: 464. Int all 0. Modes 1/4 are the "frame counter" modes. Examples: `mFrame` tracks use modes 0/1,
i.e. a motion frame that starts at the key value and advances 1 per frame (M on the purpose, H on the math).
`mAngle` vector tracks use mode 5 (Euler radians interpolated per component).

Blender mapping:

| Mode | Interpolation |
|---|---|
| 0, 2 | CONSTANT (2 = only when reached) |
| 3 | LINEAR |
| 5 | Catmull-Rom (Bezier handles at p ± m/3, m as above, scaled by the segment length if baked to frames) |
| 1, 4 | value + elapsed frames |

## Resource tracks (type 11), modes 0/1/2

- Modes 0 and 1 behave the same: if the property's current resource (`sub_8BF420`) differs from `v[i]`, then
  (for a plain field) the old one is `release`d, the new one `addRef`'d, and the property set. A getter/setter
  property (attr 0x80) skips the ref-counting.
- Mode 2 does the same, but only on the crossing tick.
- 0x90BBB2-0x90BC13. **H**
- Files: mode 0: 2,043 keys, 1: 18, 2: 16 (e.g. `st307-rc00.sdl`).

## Ref tracks (type 10, TYPE_CLASSREF)

- Value `v` = **a track index** in the same .sdl. The property is set to `state[v].object`, i.e. the unit created
  (or the system bound) by track `v`; `v == 0` sets null (0x90BB31-0x90BB5B: `imul v, 0x34` into the state
  array, +8). **H**
- Files: 235 values point at type 2 unit tracks, 137 are 0.

## Event tracks (type 13)

- With the key's value `v` (0x90BAEE + `sub_8BF040` 0x8BF040):
  - Plain property: `v` is stored as the event argument (`MtProperty+0x10`).
  - Property with attr 0x80: its setter is called with `(owner, v)`.
  - Then the event is invoked: `TYPE_EVENT` (0x18) calls `func(owner)` and **ignores `v`**. `TYPE_EVENT32` (0x1C)
    calls `func(owner, v)`.
  - **H**
- Every event key in the files is mode 2, so it fires once on the tick that crosses its frame. Examples:
  `ClearAverage` (0x1C, v = 1), `ClearAllRT` (0x1C, v = 31), `Finish` / `GlareTypeDefault` (0x18, v = 0).

## Header `frames`

- It is the loop length. The frame wraps to 0 at `cur >= frames` if `mLoop` (default on), or sticks at `frames`.
- Frames are 1/60 s (see Per-tick flow).
- The scheduler starts **paused** (`mPause` = 1, 0x90A660); something must clear `mPause` or drive `Frame`/`FrameF`.
  `uStageSetMoveFloor::moveScheduler` 0x881F20 sets the frame itself, for example.
- **H** for the logic; **M** that a loaded demo/stage scheduler is normally unpaused by its owner.

## Placement (`.pla` v17): rotations

- **`mRotY` is degrees** about the game's +Y (up) axis. It is a field of the enemy create data (property list
  0x448720, `mRotY` at +0x20; the data sits at `uEnemy+0x1370`, so `uEnemy+0x1390`).
  - `uEnemy::setup` 0x7303F6 multiplies it by 0.017453292 (`dword_C0ED00`), halves it, and builds `mQuat` (+0x40)
    from sin/cos.
  - Values in the files: 0, ±90, 180, -37, ... **H**
  - Other classes register an `mRotY` too (uEmRange +0x54, 0x4C20C0 +0x474, 0x8AFF90 +0x440, 0x414EF0 +0x260);
    those weren't traced (L that they are degrees too).
- **`mAngle` is radians** (Euler angles):
  - uStageSet → uActor → uDevil4Model → uModel → uCoord. `mAngle` is uCoord's virtual property (type 0x14
    vector3, attr 0x82, registered at 0xA32746) with setter `uCoord::setAngle` 0xA32930.
  - The setter calls `MtMatrix::setRotate*` with no degree conversion (sin/cos directly, e.g. `setRotateZYX`), then
    converts the matrix to `mQuat`, forcing w >= 0. **H**
  - Values in the files: 0, ±π/2, π, ±π/8, ±π/4, ... **H**
- **Rotation order:**
  - Chosen by `uCoord::mOrder` (+0x20, int property): 0 `setRotateZYX`, 1 ZXY, 2 YZX, 3 YXZ, 4 `setRotateXZY`,
    5 XYZ. These are the same six functions, in the same index order, as EFL `setMatFromAngle` 0x95FF70.
  - Effective application order (the order verified for EFL by emulation, see CLAUDE.md "Rotation orders"):
    0 = Blender 'XYZ', 1 'XZY', 2 'YXZ', 3 'YZX', 4 'ZXY', 5 'ZYX'.
  - Spot checks:
    - Index 0's matrix (row-vector) has row 0 = (cz cy, sz cy, -sy), i.e. Rz·Ry·Rx in column form, X first.
    - Index 4 (0x8B7F90) builds the Z matrix first, then multiplies by X, then Y, i.e. Z first.
  - **Default `mOrder` = 4** (`uCoord::uCoord` 0xA325E0). No .pla file stores `mOrder`, and the uModel /
    uDevil4Model / uActor constructors don't change it.
  - **So .pla `mAngle` = Euler (radians) in game axes, Blender order 'ZXY'** (H for the default; M that no subclass
    overrides it later at runtime).
  - Every non-zero `mAngle` in the files has only a Y component, so the order doesn't matter for the current data.
  - Convert game Y-up to Blender Z-up as for the meshes. A pure yaw `a` about game +Y becomes a yaw `a` about
    Blender +Z.
