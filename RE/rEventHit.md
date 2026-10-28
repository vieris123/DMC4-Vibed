# rEventHit (`.evh`): room event volumes and spawn points

Researched 2026-10-26 in the SE IDB (PDB names), with DX9 matches. Read-only, nothing renamed.

## Verdict: does it use collision?

**No for the stage / hitbox systems; it does its own point-in-volume math.** No sCollision, sDevil4Collision,
`.sbc`, uCollisionMgr, cCollision or kCollPrim code runs on it. Every volume is the same shape: a **vertical prism**,
a convex quad footprint `Pos0..Pos3` in the XZ plane from `PosY` up to `PosY + Height`.
- **Containment** is plain float math. `cEventHit::checkShape` SE 0x58E6F0 / DX9 0x4497A0 and its copy
  `checkInPos` SE 0x58F5E0 / DX9 0x449500 check that `PosY <= p.y <= PosY + Height` and run four 2D edge-side tests
  on the XZ quad.
- **The only geometry primitive used** is `MtCollision::intersect(MtTriangle, MtLineSegment)` (DX9 0x8C4AF0), a
  math-library triangle / segment test. `cEventHit::checkPenetrate` SE 0x58E920 / DX9 0x449CB0 calls it to catch a
  player who passed through a volume within one frame: 12 triangles (4 walls x 2, the bottom quad x 2, the top quad
  x 2) against the segment from the previous position to the current one.
- **The test point** is the player's `mPos` + 5 on Y. A few callers pass another position (enemies, uHugeStatue
  stage sets); see Consumers.
- The `Shape` field (always 1) is never read.

## Class / file

| | |
|---|---|
| Class | `rEventHit : cResource`, size 0x88; DTI hash **0x6125D9CD**; arc file-type id `~crc32 & 0x7FFFFFFF` = 0x2EDEF027 |
| Extension | `getExt` SE 0x5C9D70 -> `"evh"` (old arctool names the files `.rEventHit`) |
| load (vtbl slot 8) | SE 0x5C8D50 / DX9 0x469CB0: `MtSerializer::deserializeBinary(stream, 3, this)`, i.e. an **XFS v5** file like `.phs` / `.col`. dmc4xml `xfs.py` reads and writes all 13 extracted files byte-identically |
| save | SE 0x5C8DB0 (stub) |
| Path | `aRoom::setRoom` SE 0x534FC0 (DX9 0x40D4F0, call to setHitData at 0x40D5A2) loads `scr\stNNN\etc\stNNN` (NNN = `aRoom::mDataNo`), right after the room's `.sbc` `scr\stNNN\etc\stNNN-a-00`. One file per room |
| Files on disk | `E:\DMC mod stuffs\arctool\st{001,008,105,200,209,300,305,307,400,401,405,406,705}\scr\stNNN\etc\stNNN.evh` (st001 / st405 as `.rEventHit`). Also `dmc4_xml\tests\st008.evh` and Revil XML dumps in `RevilToolset-v2.8.163-win64\` |

## File layout (XFS property lists)

Root object `rEventHit` (layout 0, from `rEventHit::createProperty` SE 0x5C9540):

| Property | XFS type | Meaning |
|---|---|---|
| mQuality | u32 (0x06) | From `cResource::createProperty`; 2 in the files |
| mpTable | u8 array (0x04, getter / setter) | Hit **index table**: `mpTable[No]` = 1-based index into mpDataList, 0 = none. Identity (1..n) in every file |
| mTableNum | s32 | Its count |
| mpDataList | classref array of `cEventHitData` | The volumes |
| mDataNum | s32 | Their count |
| mpPosTable | u8 array | Pos index table, the same scheme over mpPosList. Identity in every file |
| mPosTblNum | s32 | Its count |
| mpPosList | classref array of `cEventPosData` | Spawn / warp points |
| mPosDataNum | s32 | Their count |

`cEventHitData` (DTI 0x3572CDF6, 160 B in memory; `createProperty` SE 0x590080, defaults from `clear` SE 0x58FEE0):

| Off | Property | Type | Meaning (reader) |
|---|---|---|---|
| 0x04 | Shape | u32 | Default 1, 1 in all 156 entries. **No reader** |
| 0x08 | PosY | f32 | Bottom of the prism (checkShape) |
| 0x0C | Height | f32 | Prism height: inside if `PosY <= y <= PosY + Height` |
| 0x10 | Pos0 | vec3 | Quad corner 0. checkShape reads x / z only; checkPenetrate uses each corner's own y as the bottom (equal to PosY in every file) |
| 0x20 / 0x30 / 0x40 | Pos1 / Pos2 / Pos3 | vec3 | Quad corners. The test needs a convex quad in this winding: XZ shoelace sum negative in all 156 entries (counter-clockwise seen from +Y) |
| 0x50 | Cond | u32 | Extra conditions for `checkHitPl` (`checkCond` SE 0x58E560 / DX9 0x449610), see below |
| 0x54 | CondAngY | f32 | Degrees: the facing that Cond 0x1 wants |
| 0x58 | CondRangeAngY | f32 | Degrees: full cone width (passes if \|delta\| <= range / 2); default 120 |
| 0x60 | CondCenter | vec3 | Point the player must face (Cond 0x10; x / z used) |
| 0x70 | Exec | u32 | 1 = room change. Read only by `cEventHit::succeed` SE 0x58F6F0 -> `succeedChgRoom` 0x58E7E0 (`cEventChgRoom` request with ExecPlPos), which **has no callers**. Data: 52 x 1, 104 x 0 |
| 0x80 | ExecPlPos | vec3 | Player position used when this entry is a room's entry door / a script warp |
| 0x90 | ExecPlAng | f32 | Player yaw, degrees (x 1/360 x 2 pi) |
| 0x94 | ExecCmrAng | f32 | Camera yaw that goes with it |

`cEventPosData` (DTI 0x5AFF5818, 48 B; `createProperty` SE 0x5908C0): `PlPos` vec3 (+0x10), `PlAng` f32 (+0x20,
degrees), `CmrAng` f32 (+0x24).

**Cond bits** (`checkCond`; the test fails if any set bit fails):

| Bit | Test |
|---|---|
| 0x01 | Player yaw within CondAngY ± CondRangeAngY / 2 |
| 0x02 | An action button triggered this frame (pad `trg & 0x6000`, or keyboard trg bits) |
| 0x04 | `uPlayer::canMoveStage(player)` |
| 0x08 | Pad `on & 0x200` held and `trg & 0x2000` (replaces the 0x02 test) |
| 0x10 | Player faces CondCenter: atan2(center - pos) vs yaw, within CondRangeAngY / 2 |

Values in the files: 0 (102), 3 (19, doors: facing + button), 7 (14), 0x12 (10), 0x16 (9), 1, 4.

## Runtime: cEventHit

- **Construction.** `aRoom::init` SE 0x539060 creates a `cEventHit` (size 0x28) at `aRoom::mpEventHit` (+0x120). The
  current room is `sArea + 0x3838`.
- **Binding.** `cEventHit::setHitData` SE 0x58E870 / DX9 0x449890 addRefs the resource and copies its 8
  table / list pointers and counts. `move` 0x58E550 is empty: **nothing is evaluated per frame by cEventHit itself**.
  Volumes are polled by whoever asks.
- **Two ways to index.**
  - Direct data index `mpHitData[Id]`: `checkInPl`, `checkHitPl`, `checkHitPassPl`, `checkInPos`.
  - Through the tables, 1-based, 0 = none: `getHitData` SE 0x58E8C0 / DX9 0x4498E0 (**the DX9 IDB names it
    `cEventHit::getPosData`; it is getHitData**, stride 160, +8 / +0x10) and `getPosData` SE 0x58E8F0 / DX9 0x449910
    (stride 48, +0x18 / +0x20).
  - Every shipped table is the identity, so both give the same entry.

| Function | SE | DX9 | Test |
|---|---|---|---|
| checkInPl(Id) | 0x58F550 | inlined? | checkShape(player pos + 5 y) |
| checkHitPl(Id) | 0x58F4A0 | inlined? | checkCond && checkShape |
| checkInPos(Id, pos) | 0x58F5E0 | 0x449500 | Prism test on any point |
| checkHitPassPl(Id, Status) | 0x58F720 | 0x449940 | Previous point = room's stored point (aRoom +0x100, if byte +0x110) else `mPosOld`, +5 y. Status 0 = **entered** (out -> in); 1 = **left** (in -> out). Also true if both points are outside, the move is >= 100 cm and `checkPenetrate` hits (tunnelled) |
| checkPenetrate | 0x58E920 | 0x449CB0 | 12 triangles vs segment (MtCollision::intersect) |

## Consumers

- **`cEventScript::checkCondition`** SE 0x59106E (room event-script bytecode; opcode = `mpData[0]`, operand
  `mpData[1]` = data index):

  | Opcode | Condition |
  |---|---|
  | 0x00 | Player in volume (checkInPl) |
  | 0x06 / 0x07 | Player entered / left the volume (checkHitPassPl 0 / 1) |
  | 0x09 | canMoveStage, not sealed, then checkHitPl |
  | 0x0B | checkHitPl |
  | 0x0C | Not dead, not sealed, then checkHitPl |
  | 0x14 | A uHugeStatue stage set (mpData[1]) is in volume mpData[2] |
  | 0x18 / 0x1E | A uHugeStatue entered volume mpData[2] (now in, old position out) |
  | 0x17 | At least mpData[2] live `uEnemy` units are in volume mpData[1] |

  (Opcode 0x11 does an `sCollision::isIntersect` line test to a stage set, unrelated to evh.)
- **`cEventScript::executeCode`** SE 0x592F82: the evh supplies **positions**; the operand byte >= 0 picks pos data,
  bit 7 picks hit data (& 0x7F):
  - 0x16: set the player start (ExecPlPos / PlPos + angles into `sMediator::mPlParamSave` and the room-change record
    `sArea + 0x3830` +0x60..+0x74). -1 = the player's current position, -2 = the last landing position.
  - 0x2B: `uHugeStatue::reset` there.
  - 0x32: boss orb position (-1 = the boss).
  - 0x40: `uHugeStatue::stop` there.
- **Room entry** (`aRoom::setRoom`, when the record's +0xA0 flag is 1): entry number `rec + 0x8C`. Bit 7 clear ->
  `getHitData(n)` (the door volume's ExecPlPos / Ang / CmrAng = arrival point); bit 7 set -> `getPosData(n & 0x7F)`.
  The result is copied to `mPlParamSave`. **The bit-7 sense is the opposite of the scripts'** (checked in the
  disassembly at 0x534FFC). `uStageSetGodHand` return writes +0x88 room / +0x8C door / +0xA0 = 1.
- **Stage sets.** In each case the volume number is a property of the stage set:
  - `uStageSetSnatch::main` (`mEventHit`): state 3, player in volume or entered it -> sets two player flags and
    advances.
  - `uStageSetGodHand::main` (`mEventBoxNo`): while the player is inside, a downward line cast.
  - `uStageSetStatueEfc::main` (`mEventNo`): statue in volume -> a stay effect at that entry's ExecPlPos.
  - `uStageSetToken::setHexPos`: hex position from pos / hit data, bit 7 as in the scripts.
- **`sMediator::getFloorWorldMap`** SE 0x605860: which floor the map shows, from checkInPl on fixed entries per
  room (rooms 200, 203, 204, 209, 212, 217, 409).
- **Debug.** `uEventHitView` (draw modes LINE..., cycle the current hit) and `sDevil4Debug::ctrlEventHitView`
  SE 0xADA140.

## What happens on a hit

Nothing automatic. A volume test only returns a bool to the caller. Event scripts turn it into flags, room loads,
demos and spawns; stage sets act on it themselves. Exec = 1 marks the door entries whose ExecPlPos is the arrival
point when the room is entered through that door. The direct `succeed` -> `cEventChgRoom` path is dead code in SE.

## Uncertain / not done

- **Pad bits.** Which buttons 0x6000 / 0x200 / 0x2000 are wasn't mapped.
- **Who sets the room-change record's entry number** for ordinary doors: the scripts / `aMission`, not traced.
- **DX9 checkInPl / checkHitPl** weren't found as separate functions (probably inlined).
- **checkCondition / executeCode opcodes** were read in SE only.
- **Untested:** whether a volume whose quad is wound the other way never matches (it should, given the edge tests).
