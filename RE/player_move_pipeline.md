# DMC4 DX9: how a player move runs (motion, contact / cancel bytes, effects, hitboxes)

Read-only RE of `DevilMayCry4_DX9.exe` (IDB on port 13337), 2026-10-17, for the MoveDef project
(`Vibed/MoveDef/`). Confidence: **H** = read from code, **M** = code plus file data, **L** = guess. Addresses are
DX9. The `.ctn` format itself is in `chartbl_ctn_hang.md`; the move table (`kAtckDefTbl`) and the hand-coded new
moves are documented in dmc4_hook (`MoveTable.cpp`, the user's).

## Functions

| Address | Name | Role |
|---|---|---|
| 0x821450 | `uPlayer::requestSetMotion_2` | request a motion: `al` forcible, `ecx` player, then motion_no, attr word, interpolation frames, start frame, speed (dmc4_hook wraps it as `indexed_anim_call(id, actor, mode, speed, startFrame, interp)`; mode 0x15 = looped per the SDK) **H** |
| 0x820F50 | `uPlayer::updateMotion` | on a motion change: clears the collision manager (unless `mMotionSetClsnNoClear`), `initMotCancel`, zeroes `mMotCont`, picks the `.ctn` script (`cCharTblMgr::set`, or the inlined grab-bank lookup at 0x821005 / 0x82107B) |
| 0x7AB720 | `uPlayer::updateCharTbl` | per tick: `cCharTblMgr::update` on both managers, then `updateContactInfoSub(BDY_UPPER)` if the upper motion isn't 0xFFFF, else `(BDY_LOWER)` if the lower isn't |
| 0x7AB770 | `uPlayer::updateContactInfoSub(BODY_ID)` | copies the chosen manager's contact bytes into `mMotCont` and the cancel states |
| 0x42B8E0 / 0x42BA50 | `cCharTblMgr::update` / `set` | the `.ctn` script interpreter / lookup (`chartbl_ctn_hang.md`) |
| 0x8032B0 / 0x803320 | `uPlayer::initMotCancel` / `updateMotCancel` | reset / advance `mMotCncl[8]` |
| 0x7AC4A0, 0x7AC6D0 | `uPlayer::checkAtckCancel`, `_2` | read the cancel states for the input checks |
| 0x480480 | `sDevil4Effect::setEffectConst` | spawn an effect by (list, file) |
| 0x81FD60 / 0x81FE00 | `uPlayer::setEffect` / `setEffect_2` | register a spawned effect in the player's effect list |
| 0xA47AA0 | `sDevil4Sound::requestSe` | queue a sound request (up to 0x400 pending, 60 bytes each) |
| 0x50CC40 | `uCollisionMgr::move` | per tick: LMT event bits -> collision groups on / off |
| 0x4A6CE0 | `uModel::getSequenceWork(motType, model, page, index)` | `events_params_0<page+1>[index]` of the current block |

## Body halves

`uPlayer::BODY_ID`: `BDY_UPPER` = 0, `BDY_LOWER` = 1, `BDY_ALL_OVER` = -1. **H**

| | Upper | Lower |
|---|---|---|
| `cCharTblMgr` | `mCharTblMgr[0]` +0x1DD4 | `mCharTblMgr[1]` +0x1DF8 |
| motion controller (`mMotionCtrl`, +0x2894, 7 x 0x3C) | index 1 | index 0 |
| `updateMotion` branch | `i == 1` -> manager 0 | `i == 0` -> manager 1 |
| `mMotionSetCharTblParam` (grab bank override) | [0] +0x2A3C | [1] +0x2A48 |

Both halves run their `.ctn` scripts every tick, but `updateCharTbl` copies only one manager's contact bytes into
`mMotCont`: the upper's while an upper motion is playing, else the lower's. **Upper dominates.** **H**

## The contact bytes (`cCharTblMgr::kContactData info[6]`, two sets)

`updateContactInfoSub` reads them as (file order of `info[0..5]`): **H**

**Contact[0]:** `[0]` atck -> `mMotCont.atck` (+0x1D7C), `[1]` free2, `[2]` camVib (`uDevilCamera::vibReq(camVib - 1)`
when it changes; 0xFF = none), `[3]` free1, `[4]` free0, `[5]` padVib (`uPlayer::setPadVibration(padVib)`; 0xFF stops,
0xFE holds). A zero byte leaves the previous value (`procCtContact` writes non-zero bytes only). `mMotCont`
(`uPlayer::kMotContInfo`, +0x1D7C: atck, camVib, free0, free1, free2, padVib; `mMotContOld` +0x1D82) is zeroed on
every motion change by `updateMotion`.

**free0 / 1 / 2 are stage triggers for move code.** Readers: free0 (+0x1D7E) in ~130 move functions (e.g. the
Buster grabs wait for `free0 == 1`, then `== 2`, between motion changes: `mvAtckSGFrostD` 0x7ED780 cases 6-7);
free1 (+0x1D7F) in `uPlayerNero::checkAutoFollowThrogh` / `checkBeforeAction`; free2 (+0x1D80) in
`uPlayerNero::main`. `atck` (+0x1D7C) has no reader outside `updateMotion` / `updateContactInfoSub` / ctor / reset
(what it drives is open). **H**

**Contact[1]:** six bytes, byte k is a cancel instruction: **H**
- low nibble n: the cancel = `uPlayer::cancelNoTbl[k][n]`. `cancelNoTbl` (0xC7781C) is six pointers into two
  arrays: `tbl[0]` -> {C_NORM0, C_NORM1, C_NORM2}; `tbl[k >= 1]` -> {C_COMMAND, C_JUMP, C_CHOUHATSU, C_GUN, C_ALL}
  starting at index k - 1 (one array at 0xC77808, pointers offset by 4 each). If n != 0, the cancels before index n
  in that table are reset (`mStat = 0`, `mIsReserve = 0`).
- high nibble: 0x10 -> `mMotCncl[cancel].mStat = 2`; 0x20 -> `mStat = 0`, `mIsReserve = 0`; 0x30 -> `mStat = 1`;
  0 -> nothing.

`uPlayer::CANCEL_NO`: C_NORM0 0, C_NORM1 1, C_NORM2 2, C_COMMAND 3, C_JUMP 4, C_CHOUHATSU (taunt) 5, C_GUN 6,
C_ALL 7. `uPlayer::mMotCncl` = `cMotCancel[8]` at +0x30C0, 0x2C bytes each (`MtObject`, `int mStat`, `bool
mIsReserve`, button / analog info, `mpParent`, `mpCheckFunc`): `mStat` sits at +0x30C4 + 0x2C k, which are exactly
the "permission bytes" dmc4_hook's SelectiveCancels pokes (0x30C4 melee = C_NORM0, 0x30F0 = C_NORM1, 0x3148 =
C_COMMAND, 0x3174 = C_JUMP, 0x31CC = C_GUN, 0x31F8 = C_ALL). **H**. What distinguishes `mStat` 1 from 2 is open
(SelectiveCancels calls them buffer / cancellable).

## Motion slots, `cMotionCtrl`, and the free `mReserved` word

`uModel::MotionArray[8]` (+0x330, `uModel::Motion` 0xE0 bytes each) are the blend slots: +0x04 u16 `mMotionNo`,
**+0x06 u16 `mReserved`**, +0x08 `mState` (2 on set; bit 0 = ended), +0x0A `mAttr` (`MOT_ATTR`; 0x10 = `A_STOP`
hitstop, 4 = looping from the block), +0x18 `mFrame`, +0x1C `mFrameMax`, +0x20 `mLoopFrame`, +0x24 `mSpeed`, +0x3C
`mpSeqInfo[2]`, +0x44 `mSequence[2]`. `uPlayer::mMotionCtrl` = `cMotionCtrl[7]` (+0x2894, 0x3C each) are the
request queues in front of them: `mpMotion` points at the slot, `mType` is the slot index, `mIsMotionSetReq` +
`mMotionNo` / `mStartFrame` / `mSpeed` / `mInterpolateTime` / `mAddAttribute` are applied by `cMotionCtrl::update`
0x455040 -> `uModel::setMotionEx` 0x9F9FD0, which also handles blend rate, speed changes, add / sub attribute bits
and hitstop (`mAttr |= 0x10`). `cCharTblMgr::mpMtn` points at a slot (upper = controller 1's, lower = controller 0's).
**H**

**`Motion.mReserved` (+0x06) is never read or written by the game.** `setMotionEx` is the only writer of a slot and
sets `mInterFrame`, `mInterCount`, `mInterRate`, `mMotionNo`, `mSpeed`, `mAttr`, `mState`, `mBlend`, `mLoopFrame`,
`mFrameMax`, `mFrame`, `mNextFrame`, `mpSeqInfo`, `mSequence` (no memset); every 16-bit `[+6]` read in motion code
(`setMotionEx` 0x9FA061, `setupMotionParam` 0x9F9095, `uPlayer::setMotionActRun` 0x822134) is the LMT header's
block count (`mpMotionListArr[bank]` -> `+0x60` -> `+6`), and `submitShapeBlendPasses` 0xA68DC0 reads another
struct. So a hook can keep a 16-bit tag per blend slot there (the user's idea for MoveDef: mark motions that use a
custom reader instead of the `.ctn`; a `cCharTblMgr::set` hook sees it through `mpMtn`). It is cleared by nothing,
so the hook must set or clear it on every `requestSetMotion`. **H**

## Tick order (`uPlayer::main` 0x7A7DC0, call order) **H**

`updateSctClsnInfo` -> **`updateCharTbl`** 0x7A7DF1 (the `.ctn` scripts step, contact bytes copied) -> `updateMotCancel`
-> input (`cPeripheral` / `cInterface::update`) -> **`moveAction`** 0x7A844E (the move state functions: motion
requests, effects) -> `cProcSpdCtrl`, `cRotateCtrl` -> **`updateMotion`** 0x7A869B (applies the queued requests:
`cMotionCtrl::update` -> `setMotionEx`; picks the `.ctn` script on a change) -> `cWeaponCtrl::update` ->
`updateCollision` -> **`moveMotion`** 0x7A86DB (`uModel::moveMotion` -> `updateFrame`: the frame advances, sequence
events are ORed) -> `uCollisionMgr::updateWorldMatrix`. So a script evaluated at the top of tick N sees the frame
advanced at the end of tick N - 1, and a motion requested in tick N starts playing in tick N's `updateMotion`.

## `requestSetMotion` and the body half **H**

`uPlayer::requestSetMotion(int type@edx, uPlayer *this@ecx, s16 attr@di, uint motion_no@esi, bool forcible, float
interpolate_frame, float start_frame, float speed)` 0x821210 writes the request into `mMotionCtrl[type]`: **`type` is
the body half** (0 = lower / whole body, 1 = upper, 2 = a third controller). It mirrors the request into controller
3 (the face model) when `type == 0` and into controller 4 (the coat model) always. `requestSetMotion_2(forcible@al,
this@ecx, motion_no, attr, interpolate_frame, start_frame, speed)` 0x821450 = `requestSetMotion(0, ...)` plus
requests of 0xFFFF (nothing) on controllers 1 and 2 with blend rate 0: the whole-body form every ground move uses.
`requestSetMotionAttribute(this, type, bits)` 0x8213B0 ORs attribute bits in. A hook on 0x821210 therefore sees
every request with its half in `edx`.

## Companion models: the Devil Bringer spawn and the weapon

Nero's moves also drive **uPlNeroDevil** (the Devil Bringer / spectral arm unit at uPlayer +0xCDF8, its own
motion banks `motion\pl020\pl020_01..04`): `uPlayerNero::setRedQueenMotion(motion_no, attr, start)` 0x7E6DF0
requests the motion on the player (controller 0) and, when Devil Trigger is active (vtbl +0x218 returns 1) and the
spawn isn't busy (`mActionNo != 7`, no pending DT reserve), `uPlNeroDevil::setAction(4)` with the same motion_no /
attr / start stored at spawn +0x22B4; `setShortGrabMotionSet` 0x7E7E90 calls `uPlNeroDevil::setMotion` 0x82B6A0
directly (it queues on the spawn's own controllers). So a data-driven stage needs a "mirror to the spawn" option,
and the spawn's LMT must have the same block. Weapons get their motions through `cWeaponCtrl` (not traced). **H**

## Worked example: Streak (`uPlayerNero::moveAtckRedQueenStinger` 0x7FDA80, atckId 28) **H**

| Stage | Does | Leaves when |
|---|---|---|
| 0 | `requestSetMotion_2(this, 0x315, attr 4, interp 3, start 0, speed 1)` (bank 3 = `pl000_04.lmt`, block 0x15); clears speeds; stinger-jump flag on | `mMotionFrameEnd[0]` |
| 1 | distance / speed from `mParamTbl` (+164..176, by `mAtckId == 28`); `setRedQueenMotion(0x316, attr 1, 0)`; effect `setEffectConst(1, 0x10, this, -1, getEfctMtrlFlg(), 20, this)` = `com\ec001_51v4`, `setEffect(.., type 0, id 5)` | at once |
| 2 | dash (`moveGround`) | distance timer < 0, `checkStingerWall`, or the hit flag (+0xCD81) |
| 2 -> 3 | `setRedQueenMotion(0x317, attr 4, 0)`; `finishEffectId(5)`; effects list 1 index 0xE (`ec001_51v2`, on self, ground mask) and 0xF (`ec001_51v3`, on the held weapon; killed unless exceed level >= 1) | |
| 3 | waits for **`mMotCont.free0 != 0`** (the `.ctn` script of 3:0x17 sets `free0 = 1` at frame 6) | -> 4 |
| 4 | on `mMotionFrameEnd[0]`: `setActionFootwork(10.0, 1)` | |

Every tick: if the stinger-jump flag is set and `checkStingerJump` -> `moveActStingerJump`. The vanilla `.ctn`
scripts (read with `dmc4xml.ctn`): 3:0x15 and 3:0x16 are empty (`FF`); 3:0x17 = pad vibration 3 at frame 5, `free0
= 1` at 6, camera vibration 17 at 7 with pad hold (0xFE), camera off (0xFF) at 9, `free1` = 1 / 2 at 12 / 20,
cancels: all five lower categories `open_alt` (0x30) at 26, C_JUMP `open` (0x10) at 31, the other four `open` at 36,
C_ALL at 56. In the files the low nibble is always 0, so contact-set-1 byte k means one category: 0 C_NORM0, 1
C_COMMAND, 2 C_JUMP, 3 C_CHOUHATSU, 4 C_GUN, 5 C_ALL (**M**: 401 + 540 scripts).

## Input commands and attack strings (`commandCheckSub`, `checkAtck`) **H**

Read 2026-10-18 in both IDBs (DX9 addresses; SE names from the PDB).

**`uPlayer::commandCheckSub(kSPlCmd *pPcw, kCmdHead *pCmdHead, kCmdData *pCmdData)`** 0x805A10 (SE 0xA071F0) is
the input-sequence recognizer for one command. It is a step machine: `pCmdData[mStep]` is checked by type
(`CMD_DATA_TYPE` 1 button: trigger / release / held, `checkCmdBtn`; 2 lever: direction relative to the lock-on target,
the camera or the player, `checkCmdLever`; 3 charge, `checkCmdTame`; 4 mash, `checkCmdRenda`), each returning
`CMD_CHECKSUB` 0 FALSE / 1 TRUE / 2 CONTINUE / 3 INIT. A step that passes arms the next step with its own `timer`
window (`mTimerF`); the window running out resets the command. When the last step passes, the command reports true
and stays true for the head's `Active` frames (`mActiveF`). `kSPlCmd` (20 bytes) = mStep, mStatus, mActiveF,
mTimerF, mCnt, mCmdFlag, mTame.

`uPlayer::executeCommandCheck` 0x805920 (SE 0xA073B0) runs every command of `uPlayer::commandTbl` (0xC3E328) each
tick: the head's `Condition` gates it (`CND_POSE` = lock-on held, `mBtnOn & 0x10`; `CND_DASH` 0x200; `CND_LASER`
0x400), and a true result sets bit `CMD_ID` in `uPlayer::mCmdFlag[]` (+0x2184). DX9 has 85 commands (3 flag words,
16-byte heads); SE has 0x66 (4 words) plus an `EndCondition` re-check and a per-command `isExecuteCommandCheckId`
gate. The DX9 ids are the first 0x55 of SE's `CMD_ID`: 0x00-0x02 lock-on + melee / gun / style, 0x03-0x14 lock-on +
forward / back lever (plain, 70 deg, screen-relative) + button, 0x15-0x1A any lever, 0x1B-0x2C charge release at
60..480 frames, 0x2D-0x50 mash levels, 0x51 `CMD_STYLE_SHORT` (dash), 0x52 `CMD_LOCK_BF_LEVER_SHORT` (back-forward,
4 steps), 0x53 `CMD_GRAB_SHORT`, 0x54 `CMD_PANDORA_LONG`. Readers of `mCmdFlag`: `checkAtckSubCommand`,
`checkAtckRenda`, `checkCmdBit` (e.g. `uPlayerDante::checkStyle`).

**Command layouts and a command of one's own (2026-10-21).** `kCmdHead` 16 B: u16 Num (steps), u32 Condition
(`CND_TYPE` 0 none, 1 POSE = `mBtnOn & 0x10` lock-on, 2 DASH = 0x200, 3 LASER = 0x400; failing it zeroes the
command's `kSPlCmd`), i16 Active, `kCmdData *`. `kCmdData` 16 B: u32 type (1 BTN, 2 LEVER, 3 TAME, 4 RENDA), u32
btn (`yBtnInfo`: 1 melee, 2 gun, 0x200 style, ...), u16 mode, u16 lever, i16 timer (frames allowed to reach the
next step, -1 none). BTN mode 1 = `mBtnTrg`, 2 = `mBtnRel`, 3 = `mBtnOn` (`checkCmdBtn` 0x805C20). LEVER
(`checkCmdLever` 0x805C80): lever 0 = stick centred (passes only while `mAnlgPow` = 0), 1 forward, 4 back, 15 any;
mode 1 = within 45 deg of the lock-on target's direction (else `mAngle`), mode 2 = 70 deg, mode 3 = screen
relative (`mAnlgRadian` minus the camera angle +0x5BD). Cmd 0x52 CMD_LOCK_BF_LEVER_SHORT = LEVER 1/0/-1, LEVER
1/4/15, LEVER 1/1/15, BTN 1/melee; cmd 0x02 = BTN 1/0x200 (lock-on + style). `commandCheckSub` 0x805A10 is a plain
`__stdcall(this, kSPlCmd *, kCmdHead *, kCmdData *)` (`retn 10h`, result in al; its helpers read the player from
esi), so a hook can run a command the table lacks: dmc4_hook's Gerb hooks 0x7A83B5 (`uPlayer::main`, right after
`call executeCommandCheck`, edi = this, 8 bytes `mov edx,[edi]; mov eax,[edx+248h]`), runs cmd 0x52's steps with
the style button through `commandCheckSub` with its own `kSPlCmd`, and sets bit 85 of `mCmdFlag` (85..95 are free:
`mPlCmd[85]` is followed by `mDash` +0x2834, so the table itself can't grow). A COMMAND row with `atckCommandNo`
85 then triggers on it (`checkAtckSubCommand` 0x7AC930 only tests `mCmdFlag[no / 32] & 1 << no % 32`).

**It knows nothing about strings.** Follow-ups are decided by `uPlayer::checkAtck` 0x803B70 over the move table.
The real row layout (SE `uPlayer::kAtckDefTbl`, 0x38 bytes; dmc4_hook's `uPlayer.hpp` names differ):

| Off | SE field | dmc4_hook name | Meaning |
|---|---|---|---|
| +0x00 | `atckAttr` (`ATCK_ATTR`) | atckAttr | 0 SHORT (melee button), 1 LONG (gun), 2 COMMAND, 3 END (terminator), 4 PROPER |
| +0x04 | `atckId` | atckId | the move id (-> `mAtckId` +0x1564) |
| +0x08 | `atckInfo` (u8, `ATCK_INFO` bits) | atckLevel | 1 AI_START (can start from neutral), 2 AI_CANCEL (can be entered by cancelling an attack), 4 AI_REPEAT (the current attack may chain into itself) |
| +0x0C | `atckCommand` (`COMMAND_TYPE`) | atckInfo | 0 none (plain button), 1 COMMAND (needs `mCmdFlag` bit `atckCommandNo`), 2 RENDA (mash: id from the table at 0xC3ED58 indexed by `atckCommandNo`) |
| +0x10 | `atckCommandNo` (int) | command.buffer | the `CMD_ID` |
| +0x14 | `atckConditionWp` | atckConditionWp | weapon (-1 any) |
| +0x18 | `atckConditionStyle` | atckConditionStyle | style (-1 any) |
| +0x1C | `atckConditionEtc` | ukn | extra condition (`checkAtckEtc`) |
| +0x20 | `atckAs` (u8) | atckAs | where: 1 ground, 2 air, 3 either, 0x40 flying (`checkAtackActionStatus` vs `mActStat` AST_STAND 1 / JUMP 2 / FLY 0x40) |
| +0x24 | `cancelId[5]` (`yCancelInfo`) | cancelId[5] | the string / cancel rules, below |

`yCancelInfo` = `kCancelInfoBit { cmdNo : 1; cmdId : 1; cmdOr : 1; dmy : 21; val : 8 (signed) }`. In
`uPlayer::checkAtckCancel(row, &reserve)` 0x7AC4A0 each non-zero entry is either
- **cmdNo**: `val` is a `CANCEL_NO`; the entry passes when `mMotCncl[val].mStat` is 2 (open) or 1 (open, and sets
  `reserve`). Every cmdNo entry without `cmdOr` must pass; one passing `cmdOr` entry is enough on its own.
- **cmdId**: `val` is a previous `atckId`; at least one cmdId entry must equal the current `mAtckId`.

So **a follow-up in a string is a row whose `cancelId` names the previous attack (cmdId) plus the cancel window
that must be open (cmdNo, opened by the previous motion's `.ctn` script)**. `checkAtck` walks the rows in order:
skill-unlocked bit, weapon, `atckAs`; while attacking (`AST_ATCK`) it skips the current move unless its row has
AI_REPEAT, requires AI_CANCEL and weapon continuity, then `checkAtckCancel` (or `isEnableAtckForceCancel`); from
neutral it requires AI_START. Then the character's `checkAtckSub` (vtbl slot 110) matches the input: atckAttr 0 /
1 = melee / gun trigger, or the command bit when `atckCommand` != 0; COMMAND rows need the bit.

**`mStat` 1 vs 2 (the `.ctn` high nibbles 0x30 vs 0x10) settled:** with `reserve` set (`mStat` 1), `checkAtckSub`
runs with `a3 = 1` and only stores the row's id in `mYoyakuAtckId` (the buffered next attack) and returns 0;
once the window reaches `mStat` 2, `mYoyakuAtckId == atckId` counts as the input and the move starts. So 0x30 =
buffer window (input accepted, held), 0x10 = cancel window (the move starts now).

Example: dmc4_hook's Luci Air Throw row `{2, 0x6D, 7, 1, 0x103, 6, -1, 1, 2, ..., 0x07000005}` = COMMAND,
AI_START | AI_CANCEL | AI_REPEAT, COMMAND_TYPE 1, command 0x103, Lucifer, air, cancel = cmdNo | cmdOr, val 7
(C_ALL open). Its "disable" trick (byte +0x11 = 1) turns `atckCommandNo` 3 into 0x103 = bit 3 of flag word 8,
which is past the three `mCmdFlag` words (it reads `mPlCmd[1].mStep`, always 0 for a one-step command): it works,
but by layout, not by design.

## Effects

`sDevil4Effect::setEffectConst(listNo@eax, fileNo@edx, uCoord *parent, uint groupMask, uint materialMask, int
unitLine, void *owner)` 0x480480 **H**: refuses `unitLine > 31`, null parent, `listNo >= 0x39`, `fileNo >=
counts[listNo]`; loads `rEffectList` for `paths[listNo][fileNo]` (`get_efl_from_file` 0x480460, table of path
arrays at 0xDEB8B8, counts at 0xDEB9A0), allocates a 512-byte `uDevil4Effect`, `sUnit::addBottom(unitLine)`,
`uEffectVFR::setParamConst(-1, 4, zero pos, effect, efl, groupMask, materialMask, identity quat, parent)`, sets the
owner, `mMode |= 0x800`. The spawn filter (GroupFlag & groupMask, MaterialFlag & materialMask) is in
`efl_import_plan.md` §3.2.

`uPlayer::setEffect(effect, player, type, id, syncA, syncB)` 0x81FD60 **H**: if `mEfctControlLevel < 0` the effect is
killed (vtbl +0x30) and nothing is stored; else `setEffect_2` appends (effect, type, id) to the player's 128-entry
list at +0x2A5C (12 bytes each) and clears effect bytes +468 / +469 when the bools are false. Kill / finish by id or
type: 0x81FAF0 .. 0x81FBC0.

**Stay effects** (no parent, a fixed pose): `sDevil4Effect::SetEffectStay(listNo@eax, fileNo@ecx, MtQuaternion *quat,
MtVector3 *pos, uint groupMask, uint materialMask, int unitLine, void *owner)` 0x4805D0 (6 stack dwords, `retn 18h`)
**H**: the same load / allocate / `addBottom` as `setEffectConst`, then `uEffectVFR::setParamStay(4, effect, pos, efl,
groupMask, materialMask, quat)` (`mpParent = 0`, `mAxisType = 6`). `setEffectStayDir` 0x4806A0 takes a direction
vector in place of the quaternion (WallRun's wall dust). **The air hike** (`uPlayer::moveActWJump` 0x8225D0 case 0 ->
vtbl slot 95 `setWJumpEffect`): Nero 0x7E8850 = `SetEffectStay(1, 0x28, &mQuat, &mPos, -1, -1, 0x14, this)` =
`effect\efl\com\ec000_00v2` at the feet in the player's orientation (`mQuat` +0x40, x y z w), stored as type 1
EFCT_TYPE_ERASE_RESET / id -1 (or killed when `mEfctControlLevel < 0`), then `sDevil4Sound::requestSe(sSoundN::mpInstance
0xE559D8, mSeCtrl.member_0x160 +0x1D60 (the player's SE resource), 40, this, &mPos, 1, 1, sSoundN::soundPositionUpdateCb
0x486640)` 0xA47AA0 (stdcall, 8 args: queues into a 0x400-entry ring under a critical section). Dante 0x7B9220 is the
same with list 2 index 0x14 (`com\ec005_20v1`) and SE 40. dmc4_hook's Gerb fires both at its launch frame
(`take_off_fx`), the quaternion rebuilt from the `mWmat` rows leaned toward the jump (2026-10-21).

Move code calls these inline at stage changes (116 `setEffectConst` + 108 `setEffect` calls in `uPlayerNero::mvAtck*`
alone), e.g. `mvAtckSGFrost` 0x7ECF30: `setEffectConst(0xC, 0x2F, this, -1, -1, 20, this)` then `setEffect(e, this,
0, -1, 1, 1)`. List 12 = `effect\efl\ene\ee010_*` (Frost): the grab effects live in the enemy's list. Player lists:
1 = `com\ec000_*` (111 files), 2 = `com\ec003_* .. ec023_*` (166), 0 = `com\ec032_*` (130). Sounds likewise:
`sDevil4Sound::requestSe` from move code (32 calls in `mvAtck*`), besides the LMT table-2 path.

### The effect list table (0xDEB8B8 paths, 0xDEB9A0 counts), first and last path per list

| List | Files | First | Last |
|---|---|---|---|
| 0 | 130 | `effect\efl\com\ec032_00v0` | `com\ec032_98v2` |
| 1 | 111 | `com\ec000_00v0` | `com\ec000_10v2` |
| 2 | 166 | `com\ec003_00v0` | `com\ec023_09v0` |
| 3 | 10 | `com\ec019_10v0` | (unused slots) |
| 4 | 26 | `ene\ee099_00v0` | `ene\ee099_01v3` |
| 5 | 15 | `ene\ee000_03v0` | `ene\ee000_06v1` |
| 6 | 1 | `ene\ee000_00v0` | |
| 7 | 30 | `ene\ee003_06v0` | `ene\ee003_04v2` |
| 8 | 60 | `ene\ee005_50v0` | |
| 9 | 50 | `ene\ee006_40v0` | |
| 10 | 53 | `ene\ee008_00v0` | `ene\ee008_03v1` |
| 11 | 10 | (empty) | |
| 12 | 66 | `ene\ee010_00v0` | `ene\ee010_11v4` (full dump below) |
| 13 | 37 | `ene\ee011_01v0` | `ene\ee011_60v0` |
| 14 | 59 | `ene\ee012_00v0` | |
| 15 | 20 | `ene\ee013_00v0` | |
| 16 | 50 | (empty) | |
| 17 | 30 | `ene\ee016_01v0` | |
| 18 | 19 | `ene\ee017_10v0` | `ene\ee017_21v1` |
| 19 | 72 | `ene\ee018_00v0` | `ene\ee018_90v8` |
| 20 | 110 | `ene\ee019_00v0` | `ene\ee019_60w1` |
| 21 | 89 | `ene\ee021_10v0` | `ene\ee021_97v5` |
| 22 | 68 | `ene\ee022_99v0` | |
| 23 | 43 | `ene\ee023_50v0` | `ene\ee023_00v1` |
| 24 | 70 | `ene\ee025_00v0` | |
| 25 | 10 | `ene\ee026_90v0` | |
| 26 | 10 | (empty) | |
| 27 | 93 | `ene\ee029_00v0` | `ene\ee029_33v0` |
| 28 | 12 | `ene\ee033_00v0` | `ene\ee033_90v1` |
| 29 | 10 | `scr\ek016_00v0` | |
| 30 | 10 | `ene\ee037_00v0` | |
| 31-43 | 10 each | `scr\es002_00v0`, `es004_00v0`, `es007_02v0`, `es009_05v0`, `ek105_00v0`, `ek105_00v0`, `es105_00v0`, `es200_20v0`, `ek201_00v0`, `es202_81v0`, `ek203_00v0`, `es204_00v0`, `ek207_00v0` | |
| 44 | 25 | `scr\es214_00v0` | `scr\es214_20v2` |
| 45 | 18 | `scr\es215_10v0` | `scr\es215_22v3` |
| 46-49 | 10 each | `scr\es301_90v0`, `es303_00v0`, `ek105_00v0`, `es409_20v0` | |
| 50 | 20 | `scr\es501_20v0` | `scr\es214_20v2` |
| 51 | 5 | `scr\es510_00v0` | `scr\es510_30v0` |
| 52-56 | 10 each | `scr\ek000_00v0`, `ek001_00v0`, `ek004_00v0`, `ek005_00v0`, `ek014_00v0` | |

List 12 (`ene\ee010_*`), index -> file: 0 00v0, 1 00v1, 2 01v0, 3 02v0, 4 03v0, 5 04v0, 6 04v1, 7 04v2, 8 05v0, 9 05v1,
10 00v2, 11 05v2, 12 05v3, 13 06v0, 14 06v1, 15 06v2, 16 06v3, 17 06v4, 18 07v0, 19 08v0, 20 09v0, 21 10v0, 22 11v0,
23 11v1, 24 01v1, 25 01v2, 26 12v0, 27 13v0, 28 13v1, 29 13v2, 30 14v0, 31 14v1, 32 01v3, 33 06v5, 34-37 (null),
38 07v1, 39 07v2, 40 00v3, 41 01v4, 42 90v0, 43 90v1, 44 15v0, 45 90v2, 46 80v0, 47 90v3, 48 90v4, 49 90v5, 50 90v6,
51 90v7, 52 90v8, 53 16v0, 54 16v1, 55 03v1, 56 90v9, 57 17v0, 58 70v0, 59 70v1, 60 70v2, 61 18v0, 62 60v0, 63 11v2,
64 11v3, 65 11v4. A full dump of every list is a one-line IDA script away (`ida_bytes.get_dword(0xDEB8B8 + 4 *
list)` -> path pointers).

## Hitboxes: LMT event table 1 -> `.idx` -> `.col` group + `.atk` entry

`uCollisionMgr::move` 0x50CC40 (mode 0, with `mpCollisionIdxData`): for i in 0..7, if bit i of `mSeqTrgOff` is set,
`removeCollisionGroupBySeqNo(i)` when `rCollisionIdxData::get(getSequenceWork(motType, model, 0, i))` exists; if
bit i of `mSeqTrgOn` is set, `setCollisionIdx(uniqueId, getSequenceWork(..., 0, i))`. `getSequenceWork(page 0,
index i)` = `events_params_01[i]` of the current block. So **slot bit i of table 1 switches `.idx` row
`events_params_01[i]`**; the row names the `.col` shape group and the `.atk` entry (`.idx` columns, from the data:
0, shape group (usually = row), `.atk` index, pair id or -1, first-of-pair flag; the row count equals the `.col`
group count in pl000 (205) and wp024 (111)). Then every active group's primitives are registered with
`sCollisionGame::setCollisionGroup` each tick. **H** (code) / **M** (the column meanings)

The files are loaded once: `uPlayerDante::setupCollisionData` 0x7BCBB0 creates `rAttackStatusData`,
`rCollisionShape`, `rCollisionIdxData` and `rDefendStatusData` from the hardcoded `Collision\pl006` paths and
`uCollisionMgr::init`s them. **H**

## The state-function pattern

Each `moveAtck*` / `mvAtck*` is a `switch` on a stage counter: on entry it requests the stage's motion (grabs use
`setShortGrabMotionSet` 0x7E7E90, which also writes the grab-bank override), fires effects, sends messages to the
enemy, sets speeds / physics; then it waits for the motion end flag (`mMotionFrameEnd`), a contact byte (`free0`),
input bits or hits before advancing. Everything timed inside a motion that is not an effect (cancel windows, camera
/ pad shake, stage triggers) is already in the `.ctn` script; effects and physics are the code-only parts. **H**

## Open items

See `Vibed/MoveDef/re_todo.md`.

## Motion banks: loading an LMT outside `setup` (2026-10-18)

Where the 16 motion banks live and how to add one at runtime (for moves shared by Nero and Dante). DX9.

- **Storage.** `uModel::mpMotionListArr[16]` at uModel +0xA38 (`rMotionList*`). `uModel::setMotionEx` 0x9F9FD0
  picks `mpMotionListArr[(motion_no >> 8) & 0xF]`, so a motion number is `bank << 8 | block`; a null bank slot or
  a block past `motion_num` leaves the request without data (no crash). Each uDevil4Model has its own array: the
  body, the coat (`uPlayerNero::mCoat` / `uPlayerDante::mCoat` at +0x52C0, a `kMdlCoat` whose model is at its
  start), Nero's `mpDevilStand` (+0xCDF8) and the stand's sub-model (+0x1374 inside it).
- **Setter.** `uModel::setMotionList(this, cResource* lmt, int bank)` 0xA26340, `__thiscall`: releases the slot's old
  list, `addRef`s the new one, stores it, and sets `MotionArray[i].mState |= 2` on every blend slot (re-bind).
  `setMotionList(model, 0, bank)` unloads.
- **Loader.** `uPlayer::loadMotionData(table@eax, model)` 0x821150 walks `{u32 motion_base, char* path}` pairs
  until -1: `sResource::create(sDevil4Resource, &rMotionList::DTI (0xEAE348), path, 1)` -> `setMotionList(model,
  rsrc, (base >> 8) & 0xF)` -> release the creating ref (the slot keeps its own).
- **Tables (`uPlayer::setup`):** Nero body 0xE15E08 = banks 0 `pl000_01`, 1 `pl000_02`, 3 `pl000_04`, 5 `pl000_06`;
  Nero coat 0xE15E30 = the same banks of `pl000_03_NN`. Dante body 0xE15948 = banks 0-9 `pl006_01..10`; coat
  0xE159A0 = `pl006_03_01..10`, same banks. **Free in both characters: banks 10-14.** Bank 15 is Nero's Buster bank:
  `uPlayerNero::setBusterMotionRsrc` 0x7E7F30 loads four LMTs (body, coat, stand, stand sub-model) into slot 15
  at grab time and `releaseBusterMotionRsrc` 0x7E8010 nulls them: the game's own precedent for a runtime load.
- **`.ctn` for a new bank.** `cCharTblMgr::set` derives the `.ctn` bank from the motion number, so bank 14 would read
  `.ctn` bank 14 (a Buster bank in `pl000.ctn`, absent in `pl006.ctn` -> the hang of `chartbl_ctn_hang.md`). The
  game's override: `uPlayer::mMotionSetCharTblParam[2]` at +0x2A3C (`kMotCharTblSetParam` 12 B: `bool isEnable`,
  `uint bank` +4, `uint idx` +8; [0] upper at 0x2A3C, [1] lower at 0x2A48). When `isEnable` is set, `updateMotion`
  0x820F50 points the half's `cCharTblMgr` at `.ctn` bank `bank` slot `idx` instead of calling `set`, then clears
  it (0x821005 / 0x82107B). `uPlayerNero::setShortGrabMotionSet` 0x7E7E90 writes both entries `{1, mCharTblBank
  (+0xD628), motion_no}` right before `requestSetMotion_2` for 0xF00 motions. A DLL move on bank 14 does the same
  with any existing script (`bank`, `idx` of a vanilla motion with the cancels it wants), or later with a script the
  DLL appended to the `.ctn` buffer (D11 in `MoveDef/decisions.md`).
- **Skeleton compatibility (from the `.mod` bone tables):** Nero (75 bones) and Dante (76) share all 75 body joint
  numbers (Dante adds 155); joints 153 / 154 hang under joint 7 on Nero and joint 2 on Dante; bone lengths differ by
  up to 6 cm (limbs 15-21 by 2-6 cm, 152-154 by 6-11 cm). One body LMT therefore plays on both; feet slide a little.
  The coats don't match (39 vs 46 joints, tails parented differently), so a shared move needs its own coat LMT per
  character in the same bank, or the coat keeps its last pose.
- **How the coat gets the motion.** `uPlayer::requestSetMotion` 0x821210 writes `mMotionCtrl[type]` (0 lower, 1
  upper, 2 third) and mirrors the same motion number, attr, speed, start and interpolation into `mMotionCtrl[4 +
  type]` when `mpCoatMdl` (+0x20C4) is set, and into `mMotionCtrl[3]` for `mpFaceMdl` (+0x20C0) on type 0.
  `uPlayer::setCoatModel` 0x7AC220 parents controllers 4-6 to the coat model, `setFaceModel` 0x7AC1C0 controller 3
  to the face model (`uPlayer::uPlayer` 0x7A5EFF nulls them). The coat therefore looks up the same `bank:slot` in
  **its own** `mpMotionListArr`: a runtime bank has to be loaded on the coat model as well (the Buster loader does
  this), with a coat LMT, else the coat takes the no-data path below.
- **Bound check and the no-data path.** `setMotionEx` 0x9FA065: `movzx eax, al; cmp eax, motion_num; jnb` -> the
  **low byte** is the block index, the bank nibble is `(no >> 8) & 0xF` (0x9FA049). A null bank slot, a block past
  `motion_num` or a null block entry jump to 0x9FA1AB: the motion number, attr (bit 0x40 cleared), speed and state 2
  are still stored, frame / interpolation / loop zeroed, return 0. No crash; the model simply gets no motion data.
- **Lifetime.** `uModel`'s destructor (vftable 0xC06730 slot 0 `sub_9E6A80` -> body `sub_9E6AB0`) walks all 16
  `mpMotionListArr` slots and releases them (refcount--, destroy at 0), then the materials and `mpRModel`. A bank
  loaded at runtime is freed with the model; `setMotionList(model, 0, bank)` is only needed to swap it out early.

## Upper-body gun shots: shooting while the lower body moves (2026-10-24)

Why a gun press while walking doesn't stop the walk, read for the wall run (dmc4_hook `WallRun` "Shoot while running").

- **Two halves, two action words.** `mBdyAction[0]` +0x14F8 is the upper body (`setActionUpperBdy`, vtbl 102, also
  `mActionNo`), `mBdyAction[1]` +0x1500 the lower (`setActionLowerBdy`, vtbl 103); `setAction` 0x7AA030 sets both
  and reloads `mActLimit` from the action tables. `moveActionUpper` 0x821880 runs the upper half each tick: action 12
  -> the character's `moveActAtckU` (vtbl 157; Nero 0x7F9E90 switches on `mAtckId` 44..51, Dante 0x7CD6A0 on 60..),
  13 -> `moveActPoseU`, 15 / 16 -> the pose-run upper functions; every other action does nothing up there.
- **The gun row starts the upper half only.** `checkAtckSub` 0x7AC710, attr 1 (gun) rows: the gun press (`mBtnTrg & 2`)
  or the reserved id, the weapon (vtbl 111), the style, `checkAtckEtc`, then the character hook vtbl 177; if the long
  weapon has `mIsPose` (uPlWeapon +0x137D: Blue Rose, Ebony & Ivory ...) -> **`setActionAtckGun(id)` 0x7AAE20**, else
  `setActionAtck(id, -1)` (both halves). `setActionAtckGun`: grip = `mEnableLongId` (unless `mIsWpChangeCancel`); if
  `isSeparatelySetAtckGun(id)` (vtbl 133; **Nero 0x7E8D50: only id 44**, the Blue Rose ground shot; Dante 0x7BB290:
  every gun id but 83-85, and only while `!(mActStat & AST_JUMP)`): `mPose.wpnId` = the weapon, **`setActionAtck(id,
  body 0)`** = `setActionUpperBdy(12)` alone, then unless the lower action is already 13-17 (the pose actions):
  `setLockOnTargetAngle` (vtbl 173) and **`setActionPoseLowerBdy` 0x7AA8C0** (lower -> 13 pose stand or 16 pose
  walk by the stick, `mPose.stat = 1`, the lower pose motion with 8 interpolation frames). Otherwise (not separable:
  the air shots) `setActionAtck(id, -1)`: the whole body.
- **The shot itself** (`uPlayerNero::moveAtckBlueRoseShot` 0x800DB0, upper phase word `mBdyAction[0].phase`): phase 0
  `mActLimit |= 0x301` (fall + poseWalkLo + poseWalkEndLo), gate on, `setLockOnTargetAngle(1, 1, 0, 0, 0.4189, 0)`
  (turn toward the target, 24 deg / frame), the gun motion on the UPPER controller `mMotionCtrl[1]` (`setGunShotMotion_2`,
  attribute 0x10 added on controllers 1 / 2 and the coat's 5 / 6), `mPose.stat = 1`, `holdTimer` from `.plp`
  mpData[98], 10 frames of draw unless `mPose.isHoldGun`. Phase 1 waits for the turn (`mRotate.mIsMove`) and the
  draw, fires (`initShotAutoRepeat`, pad vibration 0x11, SE). Phase 2 when the **lower** motion's frame >= 1: the
  bullet shell (`uPlNeroShl000::create` for 44), the muzzle effect, `atckGunPoseShotSub`. Phase 3 at upper frame 5:
  the second bullet (44). Phase 4: at the upper motion's end `setActionPoseUpperBdy` 0x7AA860 (upper -> 13 / 16 with
  the pose motion), and `setActionPoseLowerBdy` only when the lower action is 13 or the grip isn't Blue Rose (1):
  **a walking (16) lower body is left alone**, and so is any other lower action. `checkShotAutoRepeat` every tick.
- **The pose afterwards.** `moveActPoseU` 0x822EC0 keeps the arms in the gun stance (turns toward the target each
  tick, pose motions by `mPose.dir`); `checkPoseEnd` 0x8039F0 (in `checkAction`: `mActLimit & 0x20` AL_POSE_END, lock-on
  not held) ends it with **`setAction(14)` on both halves**; `checkPoseBegin` 0x803990 needs AL_POSE 0x10.
- **For a custom lower-body move that wants the gun** (the wall run): call `setPoseWeapon` 0x7AADE0 (this@edi) then
  `setActionAtck(44, 0)` yourself on the press, keep the facing (`face()` each tick defeats the turn), request later
  lower motions with the typed `requestSetMotion` 0x821210 (type@edx 0, this@ecx, motion@esi, attr@edi; stack
  forcible, interp, start, speed) so the upper motion survives, and clear AL_ATCK (0x400: the vanilla rows, which in
  the air are the full-body air shot), AL_POSE and AL_POSE_END every tick so neither the game's gun row nor the pose
  end takes the whole body. Dante's separable shots refuse while airborne (`isSeparatelySetAtckGun`), so his version
  needs more.
- **Why the first wall-run attempt dropped Nero, and the fix (2026-10-24, second attempt):** `setActionUpperBdy`
  0x7AA0B0 doesn't only set `mBdyAction[0]`: it writes the whole-player **`mActionNo` +0x14F0 = 12**, `mActLimit` from
  action 12's row (0), `setActionStatus` (12's status is 0 = inherit), `initActionCancel` + gate on, and resets
  `mPosConstInfo`, `mIsNoCliff`, `mFallHeight` 20, `mLockOn.mLockOnMode`, `mNoLandTime` ...; `setActionAtck` then
  clears the gate. **`uPlayer::checkAction` 0x8035A0 (Nero 0x7E4C10) switches on `mActionNo`**, and case 12's checks
  are `checkEmJumpBegin || checkWallJumpBegin || air hike (vtbl 142)` (+ run / pose begin): with the wall run's entry
  hooked on `checkWallJumpBegin`, every tick of the shot re-entered the run (the "cut-off"), and the shot's own
  `mActLimit |= 0x301` (fall) let the fall check drop him. `moveActionUpper` 0x821880 dispatches on
  `mBdyAction[0].no`, so the shot keeps running whatever `mActionNo` says. Fix (WallRun `post_action_tick`, the
  0x7A8453 tick after both halves' state functions): while the run is active and the upper action is 12 / 13 / 16,
  write back `mActionNo = 0x18`, the entry's `mActLimit` / `mActStat` (captured at phase 0), `face()` (the shot's
  `setLockOnTargetAngle` turned the facing), then clear AL_ATCK / AL_POSE / AL_POSE_END. `setActionPoseUpperBdy`
  0x7AA860 = `setActionUpperBdy(13 / 16)` + the upper pose motion, so the same restore covers the pose that follows
  the shot. On the run's exit the upper action is set back to the lower's (else `moveActPoseU` keeps the arms in
  the stance over the kick-off). The spine aim (`SpineAim`) is requested per tick by the run while the upper body is
  busy, not on every gun pose: on the ground the game turns the whole body and the twist showed during the turn.
- **Third pass (2026-10-24, after the first in-game test):** (1) the second shot / a held button cut the run:
  `checkShotAutoRepeat` 0x7A4CD0 -> `setActionAtckGun(mAtckId)` 0x7AAE20 -> for Nero's 44 `setActionAtck(44, 0)` +
  `setActionPoseLowerBdy` 0x7AA8C0 (the lower body into the pose; also called by `moveAtckBlueRoseShot` 0x8010AE,
  `moveAtckBlueRoseChargeShot` 0x801B84, Dante's E&I / Coyote shots, checkPoseRunBegin / End) -> hooked at 0x7AA8C0
  (this@esi, no stack args; 8 bytes `51 83 BE 1C 14 00 00 00`) to return while the run is active. (2) Nero's gun rows
  (`uPlayerNero::kAtckDefTbl` 0xC3EE40, attr 1): row 38 id 44 plain press ground (atckAs 1, wp 1), rows 35-37 ids
  47 / 46 / 45 charge shots by command bits 0x26 / 0x24 / 0x21 (charge-release commands), rows 39-42 the air versions
  ids 51 / 50 / 49 / 48 (atckAs 2), rows 43 / 44 ids 44 / 48 with field +0x1C = 0x12. `isSeparatelySetAtckGun` Nero =
  `id == 44` only, so every other id, including the air shot a run would normally match, is whole-body. WallRun now
  matches the GROUND gun rows itself in the pre-check tick (0x7A83B5: after executeCommandCheck set `mCmdFlag`
  +0x2184, before checkAction), starts the winner with `setActionAtck(id, 0)`, then clears the press, the C_NORM0 /
  C_GUN reserves (`mMotCncl[k]` +8) and the charge command bits, so `checkAtck` never sees a gun input; melee rows
  stay (an air attack cancels the run as before). (3) `moveAtckBlueRoseChargeShot` 0x801750 uses `setGunShotMotion`
  0x7E6C50, which requests controllers 0 (its own lower motion), 1 and 2, plus `requestSetMotionAttribute(0, 0x10)`
  = A_STOP on the lower (`cMotionCtrl` 0x3C: +4 mIsMotionSetReq, +0x14 mMotionNo, +0x28 mAttribute, +0x2A
  mAddAttribute, +0x2C mSubAttribute, +0x30 mBlendRate); the post-action tick drops a lower request that isn't the
  run's and clears the A_STOP add on controllers 0 / 3 / 4. Charge shots are therefore an off-by-default option.
  (4) Clearing AL_ATCK every run tick had left the kick-off uncancellable (the limit outlives the run): gone; the
  run's words are restored at the exit instead.
- **`uPlayer::updateMatrix` runs for more than the player.** The shells the player fires (`uPlNeroShl*`, `uPlDanteShl*`
  call `uPlayer::moveMotion` and vtbl slot 78 on their objects) go through the same hook, so a 4-slot per-player
  table in a hook there evicts the player while bullets fly. SpineAim therefore asks a PROVIDER callback for what a
  player wants at the moment of the pass (WallRun answers from its own run state) instead of carrying a request flag
  across the tick, and gives a slot only to a player that twists.
- **The game's own turn as the yaw source (2026-10-24, the user's angle):** the shot (phase 0) and `moveActPoseU`
  (every tick) call `setLockOnTargetAngle` -> `cRotateCtrl::request`: `mRotate.mTarget` +0x170C = the yaw the whole
  actor should face, `mIsMove` +0x1708 set. A move that holds its own facing (the wall run's `face()` writes mTarget =
  mNow = its yaw, mIsMove = 0 every tick) reads mTarget in the post-action tick whenever mIsMove is set again, and
  hands facing - mTarget to SpineAim (`Request::yaw_set / yaw_deg`), which applies it as a rotation about WORLD up
  expressed in each spine joint's own frame (`axis_mode` 1; a rotation about up leaves up invariant, so last tick's
  frames give every joint's axis exactly). No atan2 of our own, no bone-axis approximation; SpineAim's lock-point
  atan2 stays as the fallback when the game hasn't asked for a turn (age >= 30 ticks).
- **Tick order of the facing (2026-10-24):** `uPlayer::main` 0x7A862F, AFTER the post-action tick (0x7A8453) and before
  `updateMotion` (0x7A869B), runs `cRotateCtrl::update` 0x458070 on `mRotate` (+0x1704: +4 mIsMove, +8 mTarget, +0xC
  mNow, +0x10 speed; turns mNow toward mTarget by speed x dt, clears mIsMove on arrival) when byte +0x1508 is set,
  then builds the actor's `mQuat` (+0x40) as the rotation about the up vector +0x1F40 by mNow (cos at +0x4C, up x sin
  at +0x40..). So a facing written in the post-action tick with mIsMove = 0 is what renders; a facing written in the
  state function alone would be turned 24 deg/frame by the pose's request first. `moveActPoseU` 0x822EC0 every tick:
  `setLockOnTargetAngle(0, 1, 0, 0, 0.4189, 0)` and the pose motion by `mPose.dir` (set once by `setPoseDir` 0x7ABDF0
  from mRotate.mNow vs mMoveAngle with the .plp thresholds mpData[87] / [88]; only the lower pose functions and the
  pose setters call it) x the elevation column (`getPoseGunAngleOffset`), re-requested with 1 or 5 interpolation
  frames. SpineAim now derives each joint's axes by forward kinematics over this tick's mQuat chain (root = mQuat
  +0x40) instead of last tick's mWmat, which fed the twist and the lean into each other's axis with a tick's delay.
- **Reference = the chest, not the facing (2026-10-24):** the run cycles hold the torso at their own angle to the actor's
  facing (different per side), so a twist of (facing - wanted) landed differently per side and didn't follow a
  reversal. SpineAim now walks joints 0 -> 1 -> 2 by FK (mQuat +0x20, mTrans +0x40; root = the actor's mQuat +0x40 /
  mPos +0x30) before any poke, takes the right clavicle (5) and its mirror (`mSymmetryIndex` +8) positions, signs
  their line by the actor's right, and uses yaw(right x up) as the chest's yaw; the twist is chest yaw - wanted yaw
  (the game's mRotate.mTarget, handed over as an absolute yaw). Constraint: per-joint limits and an unwind threshold.
- **Option B (2026-10-24, chosen after the chest-reference build still missed):** the chest is not the gun: the firing
  poses hold the chest tens of degrees off the aim line, per pose / elevation / weapon, so twisting the chest to the
  target never lands. Instead the run LETS THE GAME TURN THE ACTOR to the target while the upper body shoots (its aim
  is exact by construction), clamping `mRotate.mTarget` to +-`aim_max_deg` off the run yaw in the post-action tick
  (cRotateCtrl::update runs after it), and asks for the turn back with `request_facing` (mTarget, speed +0x1714 =
  0.4189, mIsMove) when the shot ends; `face()` snaps only at the run's exit. SpineAim turns joint 0 (hips, so the
  legs) back by actor yaw - run yaw about world up, exactly every tick, and gives the same angle back along joints
  1-3 in shares within the joint limits (slewed at the turn speed), so the upper body ends where the game put it.
- **Option B dropped (2026-10-24, in-game: forward fine, a target behind flipped the legs):** `setLockOnTargetAngle_2`
  0x820CE0 writes BOTH `mRotate.mTarget` (+0x170C) and `mNow` (+0x1710) to the target's yaw before requesting the turn,
  so a clamp on mTarget alone never held the actor. Current scheme: the body faces the run (snapped in the run tick and
  again in the post-action tick after reading mTarget when mIsMove is set); SpineAim carries the aim along joints 1-3
  as the wanted yaw minus the run yaw measured toward the open side of the wall and clamped there (`turn_away_max`
  110 past straight out, `turn_into_max` 0; a climb symmetric), plus a per-character / per-wall hips `uncoil` for the
  cycle's own hips angle (Nero shoots left-handed, Dante right: the wall on the gun-hand side coils).
- **Arm aim (2026-10-24, SpineAim; tried in-game and DROPPED the same day: the firing poses aren't straight arms and
  the barrel direction is the hand's, so turning the whole arm moved the gun off the pose without landing it; a
  hand-level aim would need the barrel axis per weapon):** the idea was not a reach but an aim: the shoulder joint (6; the left arm through
  `Joint.mSymmetryIndex` +8, an index) is turned so the shoulder -> wrist (8) line points at the lock-on point,
  measured on last tick's `mWmat`s with last tick's correction undone, so it is a full re-aim each tick, slewed;
  applied as a world rotation through the shoulder's own frame (`mWmat` rows) and the local post-multiply.
  **`uPlayer::mpLockTarget` +0x2000 is a `cLockOnTarget*` (0x50), not a `uActor*`**: +4 mpNext, +8 `mpModel` (the
  uActor*), **+0x10 `mPos` = the lock-on point** that `setLockOnTargetAngle_2` 0x820CE0 turns the player toward (x at
  +0x10, z at +0x18), +0x20 mType, +0x28 / +0x2C mMaxHP / mHp, +0x30 mRange, +0x34.. mIsIn / mIsTarget / ..., +0x40
  mNearPos; `uPlayer::getLockOnTarget` 0x820AE0 picks `mLockOn.pTarget` (lock-on held) or the inter targets.
  Reading it as an actor (position at +0x30, a vtable at +0) put the first spine aim off the mark and crashed the
  arm aim. (`uActor::getCenterPos` 0x4559B0 is vtbl slot 33 (+0x84), __thiscall(this, float out[3]); slot 32
  (+0x80) is the no-argument `getCenterPos2`: for when an actor's centre is wanted.)
  Dante's long weapon ids: Coyote-A 7, Pandora 8, Ebony & Ivory 9 (`WP_*` in dmc4_hook
  ReClass_Internal.hpp); his E&I ground shot is row 61 id 60 (rows 55-60 are style variants, field +0x1C = 9 / 10),
  Coyote 71 / Pandora 83; `uPlayerDante::moveActAtckU` 0x7CD6A0 dispatches 60-63 EbonyIvoryShot, 64-67 the air
  version, 71-74 CoyoteAceShot, 75-78 air, 83-85 Pandora launchers.

- **The weapon's own motion and the hand attachment (2026-10-25):** `uPlWpBlueRose::setShot` 0x831FB0 =
  `uModel::setMotionEx(1, ...)` on the gun model (`model\game\wp000\wp000`, LMT `motion\wp000\wp000`, set up in
  `uPlWpBlueRose::setup` 0x831E40), called by the shot functions: the gun's recoil animation is independent of the
  player's motion. `uPlWpBlueRose::update` 0x831F50 takes the player's upper controller motion (`mMotionCtrl[1].mpMotion`
  +0x28E0; the lower's +0x28A4 when the upper number +0x28E4 is 0xFFFF) and, when `uActor::getNumberFromMotSeq` says
  sequence event **bit 33** is set at its frame, parents the gun to joint 151 (the hand). Ebony & Ivory
  (`uPlWpEbonyIvory::updateMotion` 0x832AC0) read the same bit for both guns and play their own motions 2 / 3 / 0x45.
  A custom upper-body shooting motion must therefore carry that event (copy it from the shot motions `cshotMot`
  0xE16374: bank 5 slots 0x2C / 0x2B / 0x2D, i.e. pl000_06.lmt blocks 44 / 43 / 45).

- **The pose tables (2026-10-25):** mPose (uPlayer +0x16C4, kPoseParam: +0 dir, +4 oldDir, +8 ang, +0xC stat, +0x10
  holdTimer, +0x14 wpnId, +0x18 motTbl, +0x1C blendWeight, +0x20 isUpSide, +0x24 maxRad, +0x28 minRad, +0x2C
  isPoseBeginSeCall, +0x2D isHoldGun). motTbl (+0x16DC) = 42 motion numbers, 7 elevation columns
  (getPoseGunAngleOffset) x 6 walk directions (moveActPoseU: dir 1 -> row 0, 2 -> 1, 6 -> 2, 12 -> 3, 8 -> 4, 0 -> 5),
  set per weapon: Nero uPlayerNero::initWeapon 0x7E3749 -> 0xC3F860 (Blue Rose: row 0 = 050B 050E 050A 050D 050C
  050F 0509); Dante uPlayerDante::setupLongWeaponChange 0x7B8750 by long weapon id: 7 Coyote-A -> 0xC41750 (row 0
  060B 060E 060A ...), 8 Pandora -> 0xC417F8 (070B FFFF 070A FFFF ... : no up / down variants), 9 Ebony & Ivory ->
  0xC416A8 (050B 050E 050A ...). The front-level entry, column 0 of row 0, is the stance to hold on the upper
  controller over other legs: the pose blocks are upper-body motions, while the shot motions (cshotMot 052C / 052B /
  052D) are full-body blocks and move the legs when played on the upper controller (seen in-game on the wall run).
  Row layout (setPoseMotion 0x7AB130, setGunShotMotion 0x7B7B60 / _2 0x7E6AC0): column 2 = the upper-body GUN POSE
  (controller 1, setPoseMotion's BODY 1 branch, interp 8), column 3 = the upper-body SHOT motion (controller 1, the
  shot setters), the column picked by getPoseGunAngleOffset = the elevation layer on controller 2 with
  mMotionBlendWeight as its blend rate (so columns 0 / 1 / 4 / 5 are the up / down extremes: holding column 0 on the
  upper controller pointed the gun up), column 6 = the lower-body pose-walk motion (controller 0 / setPoseMotion's
  BODY 0 branch); the shot setters request controller 0 only when the lower action is 13 (the standing pose).
  Coyote-A shot phases (uPlayerDante::moveAtckCoyoteAceShot 0x7D9B10): phase 2 at controller 1's frame >= 3, phase 3
  (the cartridges, uCartridge 2 / 3) at frame >= 36, phase 4 at mMotionFrameEnd[1] -> setActionPoseUpperBdy (and the
  lower only when it is 13), or setActionFootwork(5, 1) when the long weapon changed.
  **Row 5 (dir 0, the standing stance: 0502-0505 / 0602.. / 0702..) is FULL-BODY** on both characters (Dante 87
  tracks, Nero 92: joints 0-21.., root 255), while the walking rows 0-4 are upper-body blocks (68 / 64 tracks, joints
  1..). setActionPoseUpperBdy picks mRunMode NONE when the stick is centred (mAnlg.pow == PMODE_NONE) and setPoseDir
  then gives dir 0, so a pose started with the stick centred plays a full-body standing pose on the upper controller:
  over another lower motion the legs freeze (seen on the wall run). Pin mPose.dir (+0x16C4) to 1 for an upper-only pose.
  A pin from a tick hook isn't enough: the shot's last phase calls setActionPoseUpperBdy mid-moveAction, which calls
  `setPoseDir` 0x7ABDF0 (this@eax, returns this; mRunMode 0 -> dir 0, else from mRotate.mNow - mMoveAngle against
  `.plp` mpData[87] / [88] degrees; callers: setActionFootwork, setActionPose, setActionPoseUpper / LowerBdy,
  moveActPoseL, moveActPoseRunBeginL / RunL, Nero moveActODRun), so one tick plays the standing row and the next
  switches rows again. (WallRun hooked setPoseDir's entry, 6 bytes `push ebp; mov ebp, esp; and esp, -8`, while it
  still held the gun pose between shots; since it goes back to the run cycle instead, the per-tick pin is enough.)
  moveActPoseU 0x822EC0 itself never calls it: it re-runs setPoseMotion every tick with interpolation 1 (aim layer
  unchanged) or 5, and sets mPose.isHoldGun = (controller 2 not interpolating) while in battle.
- **The whole-body request cuts an upper-body shot (2026-10-25):** requestSetMotion_2 0x821450 sends 0xFFFF to
  controllers 1 and 2, so a lower motion change during a walking shot (the wall run's direction change) leaves action
  12 with no upper motion: mMotionFrameEnd[1] never comes, phase 4 never runs, and the shot never ends. Request the
  legs with the typed form (requestSetMotion 0x821210, type 0; it mirrors to the face and the coat's lower controller).
- **How a slot blends in (uModel::moveMotion 0x9F89D0 / updateLocalMatrix 0x9E87E0):** a slot given a new motion
  (setMotionEx sets mState 2) first copies every joint's current mQuat / mTrans / mScale into its work buffer
  (Motion.mJoint +0xD8), so the interpolation starts from the pose on screen, whatever drove it. Per joint, slot k's
  weight = its track weight x mBlend x the value at Motion +0x28 (mInterRate; slot 0 uses 1 x that), later slots scale
  the earlier ones by (1 - weight), and the joint is lerped from its current value toward each slot (uModel::Motion
  0xE0: +0x10 mInterCount, +0x14 mBlend, +0x18 mFrame, +0x28 mInterRate; uModel +0x324 mBlendNum, +0x330 MotionArray[8],
  slot = the controller's type). The setActionPoseUpperBdy callers are the shots' last phases only: Dante
  moveAtckEbonyIvoryShot 0x7D842B, moveAtckCoyoteAceShot 0x7D9DFD, Nero moveAtckBlueRoseShot 0x801098 and
  moveAtckBlueRoseChargeShot 0x801B7F; its first 8 bytes are `push ecx; cmp dword ptr [esi+141Ch], 0`, as in
  setActionPoseLowerBdy. WallRun replaces it on the run with "end the upper action, play the run cycle on controllers
  1 / 2 at the legs' frame".
- **Rapid shots (2026-10-25):** mashing is checkAtck's string path, not an auto-repeat: every gun row has atckInfo 7
  (AI_START | AI_CANCEL | AI_REPEAT) and cancelId `06000001` (cmdNo C_GUN) + `07000005` (cmdNo | cmdOr C_ALL), so a
  shot chains into the next one when the running shot's `.ctn` opens C_GUN or C_ALL (mStat 1 buffers the press in
  mYoyakuAtckId, 2 starts it). checkShotAutoRepeat 0x7A4CD0 is the Automatic mode only (mIsAutomaticEnable,
  mShotRepeatParam interval / count). checkAtck 0x803B70 per row: the unlocked-moves bitset (vtbl 120 checkAtckBit(this,
  buf) -> bits at +0x18; the test at 0x803C67), vtbl 111 (this, 2, wp) the weapon, checkAtackActionStatus, then
  mid-attack (mActStat & 4) the same id needs AI_REPEAT, AI_CANCEL, weapon continuity, checkAtckCancel or
  isEnableAtckForceCancel; then vtbl 110 checkAtckSub. Rows' `atckConditionEtc` (+0x1C) goes through vtbl 108
  checkAtckEtcSub(this, etc) (base: etc == 0). Dante (0x7B75A0): 9 = vtbl 134 or a charge level +0x5368 >= 2; 10 / 11 =
  vtbl 134, or E&I (9) / Coyote-A (7) equipped with the rapid timer +0x14DA4 > 0 (E&I shot case 2 also reads it); 14 /
  15 = Pandora's weapon +0x17CD free. Dante's ground gun rows: E&I 63 / 62 / 61 (etc 10, each after its charge row with
  etc 9) before the plain 60; Coyote-A 74 / 73 / 72 (etc 11) before 71; Pandora 83 (etc 14). Nero: 47 / 46 / 45 charge
  (commands 0x26 / 0x24 / 0x21), 44 plain, 43 / 44 again with command 0x20 and etc 0x12.
- **Where a gun's target comes from (2026-10-25, for a TPS mode):** one choke point, `uPlayer::getLockOnTarget` 0x820AE0
  (vtbl 170 in uPlayer / uPlayerNero / uPlayerDante alike; thiscall (this, a2, a3, uActor* exclude), returns
  `cLockOnTarget*`): mLockOn.pTarget (+0x3070 block) while the lock-on button is held (mBtnOn & 0x10) or a2 == 0, else
  mLockOn.pInterLongTarget (a3 == 1) / pInterTarget (the soft target). Readers: setLockOnTargetAngle 0x820BD0 (vtbl
  173; every shot's phase 0) copies it into mpLockTarget +0x2000 / mpLockTargetParent (its +8 mpModel), writes its +57
  (mIsInterTarget) and turns the actor toward its +0x10 position (setLockOnTargetAngle_2 0x820CE0: atan2 of +0x10 / +0x18
  minus the actor's position; snap or cRotateCtrl::request); getPoseGunAngleOffset / calcGunAimRate and the air-shot
  setters take the elevation from `calcTargetElevationAngle(target + 0x10)` 0x7AD5E0 (atan2 of the height difference
  over the level distance, from a joint's world matrix). The bullets: uPlNeroShl000 / 001 ::setup and uPlDanteShl000 ...
  006 / 010 / 014 / 015 read `*(player + 0x2000)`: velocity = normalize(target +0x10 - start) x speed, start = the
  player's position + 150 up + getStartRndPos; without a target, along the actor quaternion's forward (level). Other
  +0x2000 readers in player code: getStingerHitModel (returns its +8, null-safe), Pandora launcher / air motion,
  updatePtr doesn't touch it (it clears dead unit pointers elsewhere). So a fake cLockOnTarget (0x50 bytes, +0x10 =
  the aim point, +8 = null) returned by a getLockOnTarget hook aims the body, the elevation layer and the bullets.
  Cameras: uCamera::move 0xA52330 (vtbl 6, builds view / proj from mCameraPos / mTargetPos / mCameraUp; called at the
  end of uFreeCamera::move 0x919E50 and uMotionCamera::move); the gameplay camera is uCameraCtrl (vftable 0xBC6C20,
  setup 0x4F7490, sync 0x4F90B0; slots 6 / 7 are nullsubs, so its per-frame update comes from elsewhere; dmc4_hook
  CameraSettings hooks it around 0x418000-0x423000).
- **Interpolation on the controllers:** cMotionCtrl::update 0x455040 hands mInterpolateTime to uModel::setMotionEx
  0x9F9FD0, which sets the slot's mInterCount / mInterRate 1 (controller 0 only when its previous motion was 0xFFFF:
  no blend from nothing); a blend-rate request (mIsBlendRateSetReq) writes the slot's mBlend at once, unsmoothed.
  The shot setters (Dante setGunShotMotion 0x7B7B60, Nero setGunShotMotion_2 0x7E6AC0) set controller 1's rate to 1
  and 2's to mMotionBlendWeight every call; Dante's E&I shot starts at frame 15 unless a flag at +0x14D8D is 1.

- **A joint no playing motion tracks keeps its mQuat (2026-10-25, seen in-game):** updateLocalMatrix's blend writes a
  joint only from the slots that have a track for it (per-slot joint weights), so a joint outside every active block
  is left exactly as the previous pass left it. A per-tick procedural delta on such a joint therefore accumulates:
  SpineAim's 25 deg lean on joint 1 made Dante's pelvis spin about the run axis under his run cycle + gun pose, while
  Nero's run cycle tracks joint 1 and was fine. Anything that pokes mQuat between the passes must restore what it
  wrote when the joint still holds it (SpineAim does, per joint 0..3).
  The same pile-up happens on a TRACKED joint while any slot interpolates: the blend lerps from the joint's current
  value (see "How a slot blends in"), so part of last tick's poke survives and the poke is added again on top. Dante's
  rapid E&I shots keep a slot interpolating all the time, and his hips spun. Undoing the poke right before
  updateLocalMatrix was NOT enough (tried; still spun): the new-motion snapshot is taken earlier, in uModel::moveMotion
  at the top of the tick, from the joints as last tick left them, so every shot's crossfade started from a poked pose.
  The poke must not outlive its tick: undo it right after updateWorldMatrix. uPlayer::updateMatrix 0x7A8D40 = `push esi;
  mov esi, ecx; mov eax,[esi]; mov edx,[eax+34h]; call edx` (local), the 0x7A8D4A window, `call [+38h]` (world),
  0x7A8D53 `lea eax,[esi+1D88h]`, `pop esi; jmp cWeaponCtrl::updateMatrix` (the weapons follow the joints' world
  matrices). Both passes are only reached through vtables (plus sub_A5F3B0 for the world pass). Undoing the poke at
  0x7A8D53 was wrong too (seen in-game, TPS aim): while a shot plays the player's world matrices are built again later
  from the joints, so the drawn pose lost the twist. SpineAim now undoes at the entry of uModel::moveMotion 0x9F89D0
  (__stdcall(model), `push ebp; mov ebp, esp; and esp, -8`), the top of the next tick, before the snapshot.
  The window at 0x7A8D4A itself wasn't enough either (TPS aim: the twist showed, then the shot motion snapped the body
  back to the facing): the player's local pass also runs outside uPlayer::updateMatrix during a shot. updateLocalMatrix
  0x9E87E0 has no direct code callers (only vtable slot 13 / +0x34, the same in uPlayer, uPlayerNero 0xBE4FD4,
  uPlayerDante 0xBE3C84 and uPlayerDanteBoss), and uDevil4Model::move 0x522CA0 runs moveMotion + local + world
  itself, so SpineAim wraps the slot in both player vtables: the local pass, then the pokes, every time.
  (In the end the TPS "shot faces the body's heading" was SpineAim's own sign: its aim error was reference - wanted,
  i.e. the twist went away from the target; Flip lined it up. Fixed to wanted - reference; the wrapper and the
  moveMotion-entry undo stay as the sound places for the pokes and their undo.)
- **How the gun pose starts and ends (2026-10-25):** checkAction runs uPlayer::checkPoseBegin 0x803990: mLongId != -1,
  mPose.stat (+0x16D0, int) == 1, setPoseWeapon true, mActLimit & 0x10 -> mAtckLongCnt = 0, isHoldGun = 0,
  setActionPose 0x7AA800 (setPoseDir, setPoseMotion both bodies, setAction(13)). checkPoseRunBegin 0x803A40 (stick
  deflected, mActStat & 1, +0x31CC == 2 or mActLimit 0x40 / 0x100): setAction(13) then 15 = the pose walk (15 / 16 /
  17, moveActPoseRunBeginL / RunL / moveActPoseRunU: direction rows by stick vs facing, i.e. strafing), or
  setActionPoseLowerBdy with 0x100. checkPoseEnd 0x8039F0: stat == 0, mActLimit & 0x20, lock-on not held ->
  setAction(14); checkPoseRunEnd 0x803B10 (0x200, stick centred) -> setActionPoseLowerBdy. stat is set to 1 by the shots'
  first phase (with holdTimer +0x16D4 from the .plp) and atckGunPoseShotSub (locked on); uPlayer::main 0x7A8377 zeroes
  it when lock-on isn't held and holdTimer <= 0. A mod holds the pose by keeping stat 1 and the timer up.
- **The stick's world direction and the camera-cut latch (2026-10-25):** mInterface.mAnlg.radian (+0x1420) =
  mCamAngl.now (+0x16F4) + the stick's own angle (uPlayer::setInterfaceAnlgInfo 0x7A9550; pow +0x141C from the stick
  length: 1 at >= 80, 2 at >= 120). uPlayer::setCameraAngle 0x7ABCB0 (called at the top of uPlayer::main) sets
  mCamAngl.raw from sMediator::mpCamera's look direction (atan2 of uCamera +0x50 - +0x30: the target is +0x50 and up
  +0x40, as dmc4_hook's Cam.hpp has it; the IDB's labels are swapped) and now = raw, except while mCamAngl.isHold
  (+0x16FC) when now = holdAng (+0x1700); the stick angle is mPeripheral.mHoldAnlgL's while mPeripheral.mIsHold
  (+0x1404), else mAnlgL.radian (+0x13C4). That is how a held direction keeps running the same way through a camera
  cut; a mod that turns the camera itself (TPS aim) has to rebuild radian from its own yaw and drop the holds.
- **Turns toward enemies that bypass the lock-on target (2026-10-25):** uPlayerDante::setNearEmAngl 0x7BE300 (vtable)
  walks sLockOnTargetMgr's list (or the snatch list) for the nearest target within its mPILength range and, with a2 ==
  0, inside a cos 0.6 (53 deg) cone of the facing, then cRotateCtrl::request at 0.349 rad/frame; Nero's
  setBusterAngleNearEnemy 0x7FABA0 (Buster grabs). cRotateCtrl::request 0x458210 (this@eax, target@xmm3, max step on
  the stack; `push ebp; mov ebp, esp; and esp, -8`) has ~50 player callers (runs, jumps, damage, many moves).
- **Who reads "lock-on held" and the lock-on target (2026-10-26, for a virtual lock-on in TPS aim):** the bit
  (mInterface.mBtnOn +0x140C & 0x10) is tested in player code only by uPlayer::main 0x7A82FB / 0x7A8377 (mPose.stat),
  setInterfaceInfoKB, uPlayerDante::moveActTsDash 0x7CA196, Nero checkDevilTriggerAtck 0x7E5422 / checkAtckSub 0x7E5BC5 /
  checkAtckEtcSub 0x7E6161, changeAutoAtckIdGrab, setBusterAngleNearEnemy, checkPoseEnd, executeCommandCheck 0x805967
  (CND_POSE), updateLockOn 0x8208A7 and getLockOnTarget 0x820AE0. updateLockOn 0x820840 (vtbl 175, +0x2BC; called
  only from main 0x7A83A0, right before executeCommandCheck 0x7A83B0) acquires a real target only while mPose.stat
  and the bit: a bit set after it locks nothing. mLockOn (+0x3070 kLockOnParam): +8 isLockOn, +0xC mLockOnMode, +0x10
  pTarget, +0x14 pParent, +0x18 pInterTarget, +0x20 pInterLongTarget, +0x40 targetPos. pTarget is read outside the
  lock-on functions only by uPlayer::updatePtr and Dante atckGunPoseShotSub; isLockOn by the air shots, Pandora
  Meteor and setLockOnTargetAngle. The moves get the target through getLockOnTarget (vtbl 170, 36 player-code call
  sites): checkCmdLever 0x805C80 (lever modes 1 / 2 measure the stick against getTargetAngle(getLockOnTarget(0, 0, 0)
  + 0x10), else mAngle +0x1710), setLockOnTargetAngle, Nero evade / Hi-Time / Streak / Drive moves, Dante Air Trick
  (teleports to the target's +0x10), Revellion Hi-Time, Gilgamesh kick, Nunchaku, Lucifer (getLfShlAngle,
  setSmLfEmCnst read +0x10 / +0x20 only), the gun setters. Ones that keep the target's actor (+8 mpModel): the Snatch
  (moveAtckRightHandLongGrab 0x7F9FA0 / AirGrab 0x7FA190: setSnatchParam, setSnatchTargetPos, setLongGrabMotionSet),
  mpAtckTarget written by Nero checkAtckSub 0x7E5B00 and changeAutoAtckIdGrab 0x7EAB50 (checked with
  cLockOnTarget::checkTarget 0x451030 by the Snatch), setBusterAngleNearEnemy, uPlNeroShl003::updateCnst, and
  uPlDanteShl016 (sub_81E580 stores target +8). So a bit set from executeCommandCheck's entry 0x805920 (5 bytes
  `xorps xmm0, xmm0; push ebx; push ebp`) to the post-action tick, with a fake cLockOnTarget from getLockOnTarget,
  makes every lock-on command / row / maneuver use the fake point; the actor-keeping callers need a real target.
  Seen in-game: the rolls / back flips didn't follow, because they read a copy: uPlayerNero::checkJumpBegin 0x7E4D20
  needs mMotCncl[C_JUMP] (+0x3170) mStat 2 and mIsReserve, and tests that slot's **mBtnOn copy (+0xC, 0x317C) & 0x10**,
  then sub_7ABF40 (mPose.dir from the copied stick vs getLockOnTarget(0, 0, 0)): dir 2 / 8 -> setAction 18 (side roll,
  mJump +0x16B8 = 1 / 3), 4 / 6 / 12 -> 6 (back flip, 2), and 1 / 2 / 8 with +0xCE14 == 1 or action 36 -> 36. The copies
  are taken by uPlayer::updateMotCancel 0x803320 (main 0x7A7DF8, before cInterface::update) from the previous tick's
  mBtnOn / mAnlg when a cancel slot's check function reserves a press (cMotCancel 0x2C: +4 mStat, +8 mIsReserve, +0xC
  mBtnOn, +0x10 mAnlg). The Buster: uPlayerNero::changeAutoAtckIdGrab 0x7EAB50 (Buster rows): with lock-on held it
  takes getLockOnTarget(1, 0, 0) and, if that target is outside checkBusterAreaIn, picks the Snatch (+0xD674 = 1 / 2,
  mpAtckTarget = it) else the Buster (5 / 6); without lock-on, or with no target, getBusterAngleSub (the stick's
  direction, the facing) then getBusterAngleSub_2: an enemy in reach -> Buster, none -> Snatch. Trickster (Dante):
  lock-on + forward + style is Air Trick (row id 93, command 7; moveActTsAirTrick 0x7CAEA0 warps to getLockOnTarget(1,
  0, 0) + 0x10, distance capped by .plp [78]); the dash moveActTsDash 0x7CA170 with lock-on held calls
  setLockOnTargetAngle(0, ...) and then getLeverDirection 0x7AD670 (stick radian vs mRotate.mTarget +0x170C: 1 forward
  within 22.5 deg, 2 / 8 sides, 4 back; mAnlg.pow must be 2) -> motions 0x100 / 0x104 forward, 0x101 back, 0x102 /
  0x103 sides, so the turn it asks for must face the target for the directions to read right.

- **The pose out of battle (2026-10-25):** getPoseGunAngleOffset 0x7AAFC0 returns the elevation column (0 up / 4
  down, blend weight = elevation / mPose.maxRad or minRad) only while mAtckLongCnt is non-zero, sMediator's
  mEventBattleFlag is set or sMediator::isBattle(); otherwise column 6, which setPoseMotion turns into motion 0xFFFF
  on the upper controller (blend 1.0, 10 frames): the arms become the lower motion's (the gun lowered while walking
  with no enemy around). The shot then starts with mActTimerU[0] (the draw time, 0 once mPose.isHoldGun) as its
  interpolation: a cut, invisible from the aim stance, a snap from any other upper pose (seen on the wall run: both
  characters). WallRun now raises every upper / aim request's mInterpolateTime (cMotionCtrl +0x1C) to at least
  upper_blend_min (8) during the run.
  mAtckLongCnt +0x1E7A (u8): += by setActionAtck for gun attacks (capped at 100) and zeroed by it for melee ones, zeroed
  by setActionFootwork, setActionLand, setActionDamage, initJumpBegin, checkPoseBegin, moveActWallJump, moveActEmJump,
  Nero's evade / just escape, Dante's checkJumpBegin / TsDash / Gilgamesh rolling; read by getPoseGunAngleOffset,
  moveActPoseU / PoseRunU (isHoldGun), Dante's E&I shot (its parity alternates the hand), TwoSometime (== 1), TsAirTrick
  (== 2). WallRun keeps it at 1 while the pose runs on the wall (hold_aim_stance) so the aim stance is held between shots.

### The gun pose system and the aim (2026-10-24)

- **No procedural spine aim exists in the player code.** The horizontal aim of a walking shot is the whole actor
  turning toward the target: `setLockOnTargetAngle` 0x820BD0 (vtbl 173: `getLockOnTarget` vtbl 170 -> `mLockOn.pTarget`
  +0x3070 / the inter targets, then `setLockOnTargetAngle_2` 0x820CE0 = atan2 to the target's position into
  `cRotateCtrl mRotate` +0x1704, snapped or requested at `param_3c` rad/frame); the legs then play strafe cycles.
  `mPose` +0x16C4 (`kPoseParam`: dir 0, stat +0xC, holdTimer +0x10, wpnId +0x14, motTbl +0x18, blendWeight, maxRad
  +0x24, minRad +0x28, isHoldGun +0x2D). `setPoseDir` 0x7ABDF0: `mPose.dir` from facing minus `mMoveAngle`
  (`.plp` mpData[87] / [88] degrees): 1 front, 2 / 8 the sides, 6 / 12 the back diagonals, 0 standing. The vertical
  aim is a two-motion blend: `getPoseGunAngleOffset` 0x7AAFC0 turns the target's elevation (`calcTargetElevationAngle`,
  clamped to `mPose.minRad..maxRad`) into a motTbl column (0 up, 4 down, 6 = no target) and `mMotionBlendWeight`
  +0x1E90; `setPoseMotion` 0x7AB130 (`motTbl[7 * dirIndex + column]`, dirIndex 5 / 0 / 1 / 2 / 4 / 3 for dir
  0 / 1 / 2 / 6 / 8 / 12) requests the base pose motion on controller 1 and the aim-offset motion on controller 2
  with that weight as its blend rate (`cMotionCtrl` 0x3C each at +0x2894: mBlendRate +0x30, mIsBlendRateSetReq
  +0x05, mMotionNo +0x14); the air shots use `calcGunAimRate` 0x7AB090 the same way. `setGunShotMotion_2` 0x7E6AC0
  (Nero) does the same for the shot itself and sets controller 1's rate to 1 and 2's to the weight every call.
- **Joint post-processing** happens in the model's constraint pass: `cCnsIK` objects are updated by `sub_43B720`
  (`cCnsIK::update(this, ?, uModel*)`, which solves the 2-bone chain through `getJointFromNo` and calls the owner's
  vtbl 60 `IKMessage` 0xF0); a spine twist toward the target would be a constraint of that kind, or a hook after the
  pass. Not done.
- **A tick hook after `moveAction`** (dmc4_hook `input_commands::add_post_tick`, 0x7A8453: `mov edx, [edi]; mov eax,
  [edx+254h]` = the `checkAfterAction` vtable fetch) runs after both halves' state functions and before
  `updateMotion` consumes the controllers' requests: the place to rescale the blend rates a state function just set
  (tried for a wall-run shot that kept the run cycle's lean; the feature was dropped 2026-10-24, the hook stays in the SDK).

## Procedural spine aim: poking joints between the local and the world pass (2026-10-24)

Why: a sideways gun aim on the wall run can't come from pose blending (no sideways extreme poses, one spare blend
layer), and authoring them per weapon / charge / firing pose isn't feasible. The alternative is a post-motion
rotation of the spine joints, which composes with whatever the upper body plays. Where it can go:

**Per-tick order for a player** (all DX9):
1. `uPlayer::main` 0x7A7DC0: actions, `updateMotion` 0x820F50 (the 7 `cMotionCtrl::update`s consume requests), then
   `uPlayer::moveMotion` 0x8210E0 = `uModel::moveMotion` 0x9F89D0 on the body, `mpFaceMdl` (+0x20C0), `mpCoatMdl`
   (+0x20C4): `updateMotionParam` 0x9FA1E0 (decode + blend the layers into `Joint.mQuat/mTrans/mScale`) and
   `updateFrame` 0x9FCE60.
2. `uPlayer{Nero,Dante}::moveEx` (0x7E4070 / 0x7B4D40) -> `uPlayer::moveEx` 0x7A8860: position / collision
   correction, `updateLegIk` 0x7AB9B0 (writes the foot targets into the two `cCnsIK`), `mCheckIK = 1`, then
   **`uPlayer::updateMatrix` 0x7A8D40** = vtbl slot 13 (+0x34) `uModel::updateLocalMatrix` 0x9E87E0 then slot 14
   (+0x38) `uModel::updateWorldMatrix` 0x9EA8B0, then `cWeaponCtrl::updateMatrix`. After it the character's
   sub-models get the same two calls (Nero: three models at +12912 / +17216 / +21184 of the Nero object; Dante:
   `mHead`, `mHair`, `mCoat` or `mCoatDevil`), so they see the body's fresh world matrices.
   `uDevil4Model::move` 0x522CA0 does moveMotion + updateLocalMatrix + updateWorldMatrix back to back for a plain
   model; the player splits them as above.
3. `updateLocalMatrix`: per joint `switch (mType)` (constraint-type joints: cases 3-18, 21-43 call helpers
   `sub_A082D0` ... `sub_A2BB30`), then the blend of the per-layer joint work into `mQuat` with
   `mQuatParam.weight * mBlend`. **It rewrites `mQuat` every tick**, so a poke must come after it.
4. `updateWorldMatrix`: `mPrevWmat = mWmat`; per joint builds `Joint.mWmat` from `mQuat` / `mTrans` / `mScale` and the
   parent's `mWmat` (root joints: the model's own `mWmat`), then, when `Joint.mpConstraint` is set, calls the
   constraint's **vtbl slot 5 (+0x14) `apply(constraint, joint, model)`** right after that joint's matrix (before its
   children). For `cCnsIK` that is `sub_43B720` (vtable 0xB9914C: 0 455B10, 1 8FC2F0, 2 521BF0, 3 createProperty,
   4 getDTI, 5 **43B720 = the 2-bone solve on world matrices**, 6 42BB30 set(a2, a3), 7 8FB790, 8 42BB50 get, ...
   12 cConstraint::move 447780, 13 composeWorldMatrix 4477E0). It reads the joints' `mWmat` through
   `uModel::getJointFromNo` 0x42C730 (`mJointTable[no]` -> `&mpJoint[idx]`, 0 when 255).

**`uModel::Joint`** (0x90 B; `uModel.mpJoint` +0x2E4, `mJointNum` +0x2E0, `mJointTable` +0x2E8 (joint number ->
index, 255 = none), `mBlendNum` +0x324, `MotionArray[8]` +0x330, `mpRModel` +0xA30): +4 mAttr, +5 mParentIndex,
+6 mType, +7 mNo, +8 mSymmetryIndex, +0xC mpConstraint, +0x10 mOffset (MtFloat3, in the parent's frame), +0x1C
mLength, +0x20 mQuat (local, MtVector4 xyzw), +0x30 mScale, +0x40 mTrans, +0x50 mWmat.

**The hook window**: `uPlayer::updateMatrix` 0x7A8D4A..0x7A8D51, 7 bytes `8B 06 8B 50 38 8B CE` (`mov eax,[esi]; mov
edx,[eax+38h]; mov ecx,esi`) between the two virtual calls, `esi` = the player. Detour: `pushad; push esi; call
spine_tick; popad;` then the three instructions and `jmp 0x7A8D51`. Everything that writes `mQuat` has run; nothing
has read it yet; the leg IK still solves afterwards on the result. One hook covers both characters.

**The spine**: body joints 0 root -> 1 spine_lower -> 2 spine_upper -> 3 neck -> 4 head, joint 5 (clavicle) under 2,
identical numbers on pl000 and pl006 (bone table `idx_anim_map`, checked in the .mod files). Nero's coat
(pl000_03) is NOT a spine copy: its joints 0-7 are tail chains pinned to body joint 2 by a cCnsMatrix, so it follows
a twist of the body for free; Dante's head / hair / coat likewise hang on body joints.

**Recipe** (the twist stays anatomical with no frame conversion): for joint j in 1, 2, 3 rotate `mQuat` about the
bone's own axis = the child's `mOffset` (j+1's offset is expressed in j's frame) normalised, by a share of the
clamped yaw error (`L' = L * q_axis(theta)`, local post-multiply; the multiplication order of MT quaternions is
the one thing to settle in-game: two variants). Yaw error = angle between the player's facing and `mpLockTarget`
+0x2000 (what `setLockOnTargetAngle` turns the whole actor by), clamped to ~70 deg total, slewed per tick like the
leg IK's 0.1 blend, faded to 0 when the upper body leaves the shot / pose (mBdyAction[0].no not 12 / 13 / 16).
Elevation stays the game's controller-2 blend. A wall lean is the same poke on joint 1 about a fixed axis of the
hips frame (joint 0 is rigid to the body) for the whole run. Bullets are aimed by code, so this is visual only.
Implemented 2026-10-24 as dmc4_hook `mods/SpineAim.cpp` (hook 0x7A8D4A; aim toward `mpLockTarget` on upper action 12 / 13 / 16,
`spine_aim::lean(player, world_axis, deg)` for other mods, WallRun's `Torso lean` knob calls it); unbuilt and untested by me; the
quaternion order / sign are GUI toggles (`Quaternion order`, `Flip`, `Test angle`) to settle in-game.

## Hand-off between moves (2026-10-24)

How a vanilla move chains into another without a new row match, read from Dante's Stinger (`uPlayerDante::moveAtckRevellionStinger`
0x7CE470, `.ctn` script of its motions in bank 2 (`pl006_02`? motion words 0x20E / 0x20F / 0x210)):

- Phase 0 requests motion 0x20E, zeroes velocity / acceleration, `mActLimit.raw |= 1`, sets the cancel gate
  `mIsCancelCehckEnable = 1` at once (the Stinger has no startup lock), phase 1.
- Phase 1 waits for the turn (`!mRotate.mIsMove`) and `mMotionFrameEnd[0]`, then loads the dash speed from the `.plp`
  (`mParamTbl[1].mpData[0..3]`, pairs for atckId 8 vs the other Stinger row), requests the dash motion 0x20F, fires the
  dust (`setEffectConst(2, 1, this, group 1, ground material, 0x14)` registered as type 0 id 6) and the weapon trail
  (list 2 index 3 on the held weapon, id 5), phase 2. `mMotCont.free0 != 0` arms the Stinger jump (`mActFlag[0]`).
- Phase 2 counts `mActTimer[0]` down, ends on the timer, a wall (`checkStingerWall`) or a hit flag (+0x14D95), requests
  the finish motion 0x210, kills effect id 5, phase 3; a 2-frame timer re-fires the dust while dashing.
- **Phase 3 is the chain**: when `mMotCont.free0 == 2` (the `.ctn` trigger byte the finish motion's script sets), the
  stick is centred (`mAnlg.pow == 0`), **melee is held** (`mBtnOn & 1`: mashing keeps it held when the window arrives)
  and the weapon isn't mid-change (`mEnableShortId == mShortId`): `changeEffectType(1, 5)`, `finishEffectId(6, 1)`,
  `mIsWpChangeCancel = 1` (keeps the grip through setActionAtck), **`uPlayer::setActionAtck(this, 6 /* Million Stab */,
  -1 /* both halves */)`, then `moveAtckRevellionHyaku(this)` in the same tick**, return. Otherwise `mMotionFrameEnd[0]`
  -> `setActionFootwork(10.0, 1)`. `mIsAutoCombo` forces the chain (phase 4, `mIsEnableAtckForceCancel`).
- Every phase ends in the Stinger-jump check: `mActFlag[0] && checkStingerJump(mRotate.mTarget)` loads `mSJumpParam`
  from the `.plp` (mpData[5..7]) and `setAction(9)` + `moveActStingerJump`.

**Million Stab (`uPlayerDante::moveAtckRevellionHyaku` 0x7CDC50, atckId 6)**: phase 0 requests motion 0x208 (bank 2 =
`pl006_03.lmt`, block 8, the looping stab; start frame 9 when the previous motion was the Stinger finish 0x210, else 0),
loads the mash timers `mRendaTimer[0..3]` from `.plp` mpData[109..112] (`mRendaTblNo` 1, `mRendaLevel` 1), zeroes
velocity, gate on at once. Phase 1 waits for `mMotCont.free0` to fire the ground effect (list 2 index 0xB, id 4). Phase
2: `uPlayer::checkAtckRenda` keeps the loop alive while the mash holds up; when it fails (`mActFlag[0]`) and `free0 >= 2`
the move either chains (`mPlCmd[33].mTame` state 1 / 2 -> `setActionAtck(11)`, 3 + SM style + bit 16 -> `setActionAtck(16)`)
or requests the finish 0x209 with 10 interpolation frames (effect list 2 index 0xC) and ends on `mMotionFrameEnd[0]` with
`setActionFootwork(10.0, 1)`.

**The effect calls of the state functions (conventions, 2026-10-24):** `sDevil4Effect::setEffectConst` 0x480480 takes
the list in eax and the file index in edx, then five stack words (parent unit, group mask, material mask, unit line,
owner; `retn 14h`) and returns the effect; `uPlayer::getEfctMtrlFlg` 0x820060 (this@eax) is the material mask of the
surface under the player (a 110 cm ray); `uPlayer::cWeaponCtrl::getHeldWeapon` 0x7B1F90 (`&mWeaponCtrl` +0x1D88 @esi)
the held weapon unit for weapon-parented effects; `uPlayer::setEffect` 0x81FD60 (effect@eax, this@ecx, EFCT_TYPE, id,
bool, bool; callee pops) registers it in the 128-entry list +0x2A5C (skipped, and the effect told to end, when
`mEfctControlLevel` +0x305C < 0); `uPlayer::killEffectId` 0x81FAF0 (this@eax, id; `retn 4`) and `finishEffectId`
0x81FB70 (this@eax, id, bool) end a registered one. dmc4_hook: `devil4_sdk::effect_const / register_effect /
kill_effect / finish_effect / ground_material / held_weapon`.

**`uPlayer::setActionFootwork` 0x7AA2C0** (`__userpurge`: this@esi, float `hokan`, char `isMotSet`): the ground exit
of the attack moves: zeroes velocity / acceleration / `mMoveVel` / `mMoveAcc` / `mYoyakuAtckId`, `mOldAtckId = mAtckId`,
`mAtckId = 0`, `mRunMode` none; not posing -> attack counters zeroed, `isMotSet` -> requests the (battle) footwork motion
with `hokan` interpolation frames, `setAction(1)`; posing -> pose motions and `setAction(13)`. dmc4_hook MoveDef uses it
for `exit` on the ground (`set_action_footwork`).

**`uPlayer::setActionAtck` 0x7AAC80** (`__userpurge`: this@eax, atckId@ecx, `body` on the stack, callee pops; SE
`setActionAtck(int, BODY_ID)`): `mOldAtckId = mAtckId; mAtckId = id`; `body != 0` -> vtbl 103 `setActionUpperBdy(12)`
(which runs `initActionCancel`); always vtbl 102 `setActionLowerBdy(12)` (phase 0); by the row's attr (vtbl 152):
0 melee `++mAtckShortCnt` (capped 100), 1 gun `++mAtckLongCnt`; `++mJumpAtckCnt` (capped 50); `mActStat = (mActStat &
~0x14) | AST_ATCK`; `mIsCancelCehckEnable = 0`; unless `mIsWpChangeCancel` was set, the grip is switched to the short
or long weapon. 40 callers: `checkAtckSub` (the row match), the auto-combo changers, damage procs, and the moves that
chain (Hyaku, Stinger, HiTime, the Rolling series, Drive, Magma Drive, Dio Knife, Honeycomb, Pandora, Nero's grabs and
Combo B). So a custom state function may call it to hand off to another custom move and run that move's function at
once; dmc4_hook `MoveDef` does (`<next to="move:name">`, `set_action_atck`).

## Wall jump entry, jump counters, movement fields (2026-10-18/19)

Traced for the dmc4_hook wall run (`D:\dmc4_hook\src\mods\WallRun.cpp`, which ports both functions). DX9.

- **`uPlayer::checkWallJumpBegin` 0x804650** (`this`@esi, result@al; callers `uPlayer/Nero/Dante::checkAction`):
  returns 0 unless `mActStat & 2` (in a jump) and a jump input: either buffered in the C_JUMP cancel window
  (`mMotCncl[4].mStat == 2 && mMotCncl[4].mIsReserve`, +0x3174 / +0x3178) or pressed now while allowed
  (`mActLimit.bit & 8` +0x1550 and `mBtnTrg.bit & 4` +0x1410); then `mWallJumpCnt > 0` (+0x1E7F); then one
  `findIntersection` line at hip height from 80 cm behind to 80 cm ahead (`mPos + up * 10 -/+ fwd * 80`, rows 1 / 2 of
  `mWmat`), `sCollision::Param(127, 0x20000, 0, 0, 10)`, both sides, hitOut = `mGroundPoly`; a hit whose triangle
  has `surface_attr & 1` is refused. Success: `initJumpBegin(3)` (vtbl 109), `mJump.mode = JUMP_MODE_NORM_WALL_LO`
  (4), `setAction(0x18)` (vtbl 101), return 1.
- **The jump-cancel buffer (`mMotCncl[C_JUMP].mIsReserve` +0x3178), traced 2026-10-24.** `uPlayer::updateMotCancel`
  0x803320 runs at the top of every `uPlayer::main` tick (right after `updateCharTbl`, before the command check and
  the action checks): for each of the 8 `cMotCancel` windows (0x2C each: `mStat` +4, `mIsReserve` +8, then the
  `mBtnOn` / `mAnlg` snapshot, `mpParent`, `mpCheckFunc` +0x28) with `mStat != 0` and no reserve yet it calls the
  window's check function and stores the result; a window at `mStat` 0 has its reserve cleared. C_JUMP's check is
  `uPlayer::checkMotCnclJump` 0x803390 (`mBtnTrg & 4`, not in action 6, action 7 only above the `.plp` height),
  C_CHOUHATSU's `checkMotCnclChouhatsu` 0x803420 (`mBtnTrg & 8`); the attack windows have none (their reserve is
  `mYoyakuAtckId`). Readers of the C_JUMP reserve: Dante's ground jump `uPlayerDante::checkJumpBegin` 0x7B8570
  (**only** `mStat == 2 && mIsReserve`: no live-press path), `checkWJumpBegin` 0x803880 and `checkWallJumpBegin`
  0x804650 (the latch, or `mActLimit.bit & 8 && mBtnTrg & 4`), `checkEmJumpBegin` 0x804970 (a press, or the latch
  while `mActStat & AST_ATCK`), Nero's `checkJumpBegin` 0x7E4D39. The press itself has no other reader in the player
  code (`mBtnTrg & 4`: these four). Every window, reserve included, is zeroed by `uPlayer::initMotCancel` 0x8032B0
  from `uPlayer::updateMotion` 0x820F50 whenever `cMotionCtrl::update` 0x455040 sets a requested motion on controller
  0 or 1 (`updateMotion` runs late in the tick, after `moveAction`), and by `initActionCancel` 0x7AAF30 from
  `setActionUpperBdy`. So a latch never survives a motion change: a press buffered during a move only fires if the
  window reaches `mStat` 2 within the same motion. A hook that returns 0 from `checkWJumpBegin` to redirect a press
  (DanteAirDodge) should still clear the latch `updateMotCancel` made from it, else the jump checks take it on the
  next tick with no press for the hook to see.
  `uPlayer::checkAction` tries `checkEmJumpBegin`, then `checkWallJumpBegin`, then the air hike (vtbl 142); the enemy
  step is the only one that reads no window (gate + press + `mIsEmJumpEnable` + an `isEmJump` actor on move line 15 /
  16), so a custom move can offer it from frame 0 by calling 0x804970 itself while its gate is off, without opening
  C_JUMP (which also frees the air hike: DT Dante cancelled the dodge into one at once).
  **A press can be visible on two ticks.** With the game ticking faster than 60 Hz (the user's build: motion frames
  advance 0.6 per tick, so ~100 ticks/s) `mBtnTrg` carried the dodge's jump press on the tick after the dodge
  started, and `updateMotCancel` re-latched the C_JUMP reserve through the borrowed script's 0x30 window; the window
  opening to 2 at the cancel frame then started a jump with no new press. A press-started custom move should eat
  the trigger bit and that reserve until the button is released once (DanteAirDodge `eat_held_jump`).
- **`uPlayer::setActionLowerBdy` 0x7AA2A4** writes `mBdyAction[1].no = act` and `.phase = 0` on every action
  entry (+0x1500 / +0x1504); the state functions own the phase word from there (the game itself uses values up
  to 0x1E in it).
- **`uPlayer::initJumpBegin` 0x7AC9E0** (`JUMP_INIT_TYPE`): 0 / 1 / 4 / 5 / 8 / 9 / 11 reset `mWJumpCnt` = 0,
  `mWallJumpCnt` = `mpActDataTbl->wallJumpCnt`, `mWallHikeJumpCnt` = `->wallHikeCnt` (0 also clears the attack
  counters and `mPose.isHoldGun`); 2: `++mWJumpCnt`, `mWallJumpCnt` = 0; 3 (the wall jump): `--mWallJumpCnt`,
  `++mWJumpCnt`; 6: `--mWallHikeJumpCnt`; all clear `mJumpAtckCnt`. Counters: `mJumpAtckCnt` +0x1E7D, `mWJumpCnt`
  +0x1E7E (air jumps used), `mWallJumpCnt` +0x1E7F, `mWallHikeJumpCnt` +0x1E80; `mpActDataTbl` +0x1DD0 ->
  `kActionData { wJumpCnt, wallJumpCnt, wallHikeCnt }` (chars).
- **Movement fields** (IDB): `mMoveVel` +0x1E1C (horizontal speed of a jump, loaded by `setJumpRate` 0x7ACC70
  from the jump table; `calcSpeedXZ` 0x7ACAB0 turns it into XZ velocity along `mJump.moveAng` +0x16C0 each tick;
  the sdk calls it `inertia`), `mMoveAcc` +0x1E20 (its per-frame change), `mMoveAngle` +0x1E24 (stick yaw for
  movement), `mAddSpd` +0x1E30 (MtVector3) with `mIsAddSpeed` +0x1E40 (an additive speed the motion step adds:
  carried momentum, moving floors). `adjustJumpSpeed` 0x7ACCE0 (`this`@esi) applies the table's gravity /
  `mDownMaxSpd` (+0x2164, `mParamTbl[0].mpData[103]`).
- **`moveActWallJump` 0x827200** (`this`@eax, no stack args): phases 0-4 in `mBdyAction[1].phase`, see the IDB
  function comment; kick-off motions F 20 / 25, L 23 / 27, R 22 / 26, B 28 (after the turn 21), V 20 / 25 with
  attribute 5 (`A_NULL_TRANS_OFF | A_LOOP_OFF`); fall motions 4 / 5 / 9 attribute 1, interpolation 10, start 7;
  phase 3 re-requests the fall motion looped (0x15) from frame 51 when the `.ctn` byte `free0 >= 2`; the dust is
  `sDevil4Effect::setEffectStayDir(0, 0x18, ...)` at `mGroundPoly.hit_pos` along the wall normal with
  `cUtil::getEfctMtrlFlg(&mGroundPoly)`, registered with `uPlayer::setEffect(effect, this, 1, -1, 1, 1)`.
- **`cResource::release` 0x8DDA00** is `__usercall(sResource* this@eax, cResource* rsrc@edi)` (refcount at +0x44,
  destroyed at 0 through `sub_8DFC90`). dmc4_hook's `release_resource` wrapper got this wrong until 2026-10-19.
- **Collision filters** (sCollision::Param `filter`, from dmc4_hook RayTest): walls 0x20000, ground 0x80800,
  fall-stop (invisible walls that stop Stinger) 0x10000000, camera-stop 0x20000000. The game's wall checks use
  0x20000 only.

## Action limits and status: `mActLimit` / `mActStat` (2026-10-20)

Both are typed in the IDBs with the SE PDB's names (DX9 and SE agree). `uPlayer::setAction(act)` 0x7AA030 calls
`setActionUpperBdy` / `setActionLowerBdy` (`mBdyAction[n] = {act, phase 0}`), then `setActionStatus` 0x7ACD70, then
loads `mActLimit` from the action's table row; the move functions edit the bits from there as the action progresses.

- **`mActLimit` +0x1550 = `uPlayer::yActLimit { kActLimitBit bit; u32 raw }`**, "what may start from this action
  now". Bits (bit n = 1 << n): 0 `fall`, 1 `walk`, 2 `walkEnd`, 3 `jump`, 4 `pose`, 5 `poseEnd`, 6 `poseWalk`,
  7 `poseWalkEnd`, 8 `poseWalkLo`, 9 `poseWalkEndLo`, 10 `atck`, 11 `guard`, 12 `ik`, 13 `atckVl`, 14 `intr`,
  15 `pause`, 16-31 `dmy`. Readers found: `fall` -> `uPlayer::main` (`mPos.y -= mFallHeight * dt`, the ground
  snap), `checkFloor` 0x803D60, `updateCollisionCorrectScr` (the action follows the floor / may drop off an edge;
  every airborne start clears it with `and ~1`, attack recoveries set it with `or 1`); `walk` -> `checkRunBegin`;
  `jump` -> `checkWJumpBegin`, `checkWallJumpBegin`, `uPlayerDante::checkBlockActSet`; `pose` / `poseEnd` ->
  `checkPoseBegin` / `checkPoseEnd` (the gun-ready stance, `setPoseWeapon`); `poseWalkEndLo` -> `checkPoseRunEnd`
  (the `Lo` pair = lower-body pose walk while the upper body shoots: gun moves OR in 0x301 = fall | poseWalkLo |
  poseWalkEndLo); `atck` -> `checkAtck` 0x803B70 (no attack may start without it, except cancels through
  `checkAtckCancel`), `uPlayerNero::checkAfterAction` / `checkDevilTriggerAtck` / `checkODChargeTrg` /
  `checkEnemyBlockFinish`. No reader of `ik`, `atckVl`, `intr`, `pause`, `poseWalk`, `poseWalkEnd` turned up in
  0x400000-0x4A0000 / 0x7A0000-0x840000 / 0x8C0000-0x900000 (`ik` is presumably `cLegIkCtrl`, `intr` / `pause` the
  event / message side: Damage, Dead and Revive carry `intr | pause` and nothing else).
- **`mActStat` +0x1554 = `uPlayer::ACT_STAT`** (also `yActStat { kActStatBit }`): the category the action is in.
  `AST_NONE` 0, `AST_STAND` 1, `AST_JUMP` 2 (airborne: what every "in the air" test reads), `AST_ATCK` 4 (set by
  `checkAtckSub` when an attack starts, cleared by `setActionDamage` / `reverseMessage`), `AST_POSE` 8,
  `AST_GUARD` 0x10, `AST_RUN` 0x20, `AST_FLY` 0x40. `setActionStatus`: `mActStatOld = mActStat`; the table row's
  `actStatus` replaces it, but a row of 0 keeps the previous status minus `AST_GUARD` (transition actions inherit
  stand / jump).
- **The tables.** `uPlayer::mpActionTbl[2]` +0x155C: `[0]` = `uPlayer::actionTbl` 0xC776F0 for actions 0-34,
  `[1]` = the character's table for actions 35+ (`uPlayerNero::actionTbl` 0xC3F908, `uPlayerDante::actionTbl`
  0xC418A0; `uPlWpGilgamesh::setCnstJoint` swaps `[1]` to a Gilgamesh-specific one at +0x50 of its table).
  Row = `kActionTbl { yActLimit actLimit; yActStat actStatus }` (8 bytes). `mActionNo` +0x14F0.

  Base actions (`uPlayer::actionTbl`, names from `moveActionLower` 0x8215E0 / `moveActionUpper` 0x821880):

  | act | name | limit | status |
  |---|---|---|---|
  | 0 | (none) | fall walk jump ik | stand |
  | 1 | Footwork | fall walk jump pose atck guard ik | stand |
  | 2 | 180Turn | same as 1 | stand |
  | 3-5 | RunBegin / Run / RunEnd | fall jump pose atck guard ik | stand run |
  | 6 | JumpBegin | fall ik | stand |
  | 7 | Jump | jump guard | jump |
  | 8 | WJump (air hike) | jump atck guard | jump |
  | 9 | StingerJump | jump atck guard | jump |
  | 10 | Land | fall atck guard ik | stand |
  | 11 | Fall | jump atck guard | jump |
  | 12 | - | 0 | 0 (inherit) |
  | 13 | PoseL / PoseU | fall walk jump poseEnd atck guard ik | stand pose |
  | 14 | - | same | stand |
  | 15-16 | PoseRunBeginL / PoseRunL (+U) | fall jump poseEnd atck guard ik | stand pose run |
  | 17 | - | fall jump atck guard ik | stand run |
  | 18-19 | PoseJumpBegin, - | fall guard ik atckVl | stand pose |
  | 20 | Damage | intr pause | 0 (inherit) |
  | 21 | Dead | fall intr pause | stand |
  | 22 | Revive | intr pause | stand |
  | 23 | - | fall ik intr | stand |
  | 24 | **WallJump** | jump atck guard | jump |
  | 25 | EmJump | jump atck guard | jump |
  | 26 | Catapult | jump | jump |
  | 27 | HolyWater | fall ik intr | stand |
  | 28-29 | - | fall guard ik atckVl | stand pose |
  | 30 | - | jump guard | jump |
  | 31 | - | fall guard ik atckVl | stand pose |
  | 32 | - | fall guard ik atckVl | stand |
  | 33 | - | jump guard | jump |
  | 34 | - | fall guard ik atckVl | stand |

  Dante 35+ (`uPlayerDante::moveActionLower` 0x7C9670): 35 StyleChange (fall jump guard ik / stand), 36 TsDash
  (fall ik intr / stand), 37 TsAirDash (intr / jump), 38 TsAirTrick (intr / 0), 39 - (fall guard ik atckVl /
  stand pose), 40 TsAirEsc (intr / jump), 41 TsAirEnemyHike (intr / jump), 42 GilgameshRollingBegin (fall ik /
  stand), 43 RollingB / 44 RollingW (jump atck guard / jump), 45 RgBlock, 46 -, 47 RgJustBlock, 48 RgGuardCrush
  (fall ik intr / stand), 49 RgAirBlock, 50 -, 51 RgAirJustBlock, 52 RgAirGuardCrush (intr / jump), 53
  RgInvincible (fall ik intr / stand), 54 (fall ik intr / stand), 55-57 (0 / 0). Nero 35+ (`uPlayerNero::actionTbl`,
  9 rows; its dispatcher isn't a plain switch): 35-36 (fall guard ik atckVl / stand pose), 37-38 (fall walk jump
  poseEnd atck guard ik / stand pose, + run), 39 (jump atck guard ik / jump pose), 40 (0 / jump pose), 41 (fall /
  0), 42 (fall walk jump / stand), 43 (0 / atck pose).
- **For a custom action** (the wall run runs as action 24): the table gives `jump | atck | guard`, status `jump`;
  the state function may OR more in (`or [+1550], imm`) and the game's checks pick them up next tick. Writers
  that set a whole word: `setAction` (table), `setActionUpperBdy`, the gun / Pandora moves.

- **Unlocked-moves gate (2026-10-20).** `uPlayer::checkAtck` 0x803C67: `test [bitset + (atckId / 32) * 4 + 0x18], 1 << (atckId % 32)`
  on a per-player bitset (from vtbl slot 110's object) before the weapon check (vtbl 111 `(2, atckConditionWp)`),
  `checkAtackActionStatus` (`atckAs` 1 stand / 2 jump / 3 either / 0x40 fly, against `mActStat`) and the etc
  condition (`checkAtckEtc` -> vtbl 108 `checkAtckEtcSub(atckConditionEtc)`; 0 = none). A custom row with a new
  `atckId` fails the bitset test unless the DLL lets its id through (dmc4_hook `MoveTable` `detour0`).

- **Cancel verdict, settled 2026-10-21** (`checkAtck` 0x803B70 while `mActStat & AST_ATCK`): the candidate row needs
  `AI_CANCEL`; `checkAtckCancel` 0x7AC4A0 then wants every non-`or` window entry (`cmdNo`, `val` = CANCEL_NO) at
  `mStat` 2 or 1 (one `or` entry at 2 / 1 satisfies everything) and, if the row has `prev` entries (`cmdId`), one
  equal to the current `mAtckId`; `mStat` 1 also raises the "buffered" flag. `checkAtckSub` 0x7AC710 (vtbl 110;
  Nero's 0x7E5B00 calls it first) then checks the input (command bit, or the melee / gun press for attr 0 / 1, or
  the row being the reserved `mYoyakuAtckId` +0x1760), the weapon (vtbl 111), the style, `checkAtckEtc` (vtbl 108:
  mostly height-above-ground minimums from the `.plp`, e.g. etc 3 for the air combo), and **with the buffered
  flag reserves the row (`mYoyakuAtckId = id`, cleared by Footwork / Fall / Land / Pose / initActionCancel) instead
  of starting it; without it starts it now** (`setActionAtck`). So a `.ctn` byte 0x10 (`mStat` 2) = cancel now,
  0x30 (`mStat` 1) = take the input now, start when the move allows. `mActLimit.atck` only matters outside an
  attack (it bypasses the window test there) and for the first gate. Nero's melee rows: combo followers carry
  `prev` links (never reachable from a custom move), the air combo start (id 23) needs C_NORM0 or C_NORM1 and
  height, the gun rows C_GUN, the command moves C_COMMAND.

- **The cancel gate (2026-10-21).** `uPlayer::main` 0x7A7DC0 runs `checkBeforeAction` (vtbl 147: dash, DT, holy
  water, weapon change, provoke, `checkFloor`, Nero's `checkJumpBegin` (vtbl 150), then `checkAtck`) and
  `checkAction` (vtbl 148: run / pose / wall jump / air hike checks per action) **only while `mIsCancelCehckEnable`
  +0x1F50 is set** (sdk `fullHouseSomething1`). `setActionUpperBdy` sets it, `setActionAtck` 0x7AAC80 and
  `setActionDamage` clear it, and every vanilla attack / Dante style function writes it back to 1 at the frame its
  recovery begins (`moveAtckRevellionCombo1` 0x7CD9A3 ...). A custom attack-row move must do the same at its cancel
  frame, else no cancel of any kind (attack, jump, gun) is even evaluated, whatever the `.ctn` windows say. The
  `.ctn` windows then decide which rows pass (`checkAtckCancel`); the jump checks read C_JUMP's `mStat` / `mIsReserve`.

## Shells and code-defined hitboxes (2026-10-22)

How a shell (the game's word for a projectile / detached hitbox unit) carries an attack, from
`uEm019_ice::setup` 0x680B80 (Frost's ice shot) **H**:

1. `rAttackStatusData *atk = sResource::create(sDevil4Resource, &rAttackStatusData::DTI, "Collision\em019", 1)`:
   the `.atk` (cached by path; `+0x60 mNum`, `+0x64 cAttackStatus **` whose `+0xC` is the 0x58-byte `kAttackStatus`).
2. `uCollisionMgr::init_0(actor@eax, mgr@esi, rCollisionShape *col, rAttackStatusData *atk)` 0x50BDD0: the unit's own
   collision manager (`mMode = 1`, `mpReportActor = mpModel = actor`, addRefs the two resources, no `.dfd`). `col` may
   be 0 when the primitives come from code. (dmc4_hook `custom_utils::load_atk_col` is this call.)
3. `mAttackStatus = *atk->mppAttackStatus[6]->mpAttackStatus` (one entry copied into the unit).
4. `uCollisionMgr::setCollision(slot@eax = -1 (first free of 32), mgr, colGroup = -1, kCollPrim *prims, num = 1,
   uniqueId = -1 (sMediator::getCollisionUniqueID), createdFrom = -1)` 0x50C290 allocates the `cCollisionGroup`
   (336 B) and one `cCollision` (272 B) per primitive. With a `.col` group (`prims = 0`) it also calls
   `uCollisionMgr::setVsAttr(group, frd, mgr, kind, attrBits)` from the group record (`+0x14` kind, `+0x18..0x1B`
   atk / dmg / psh / grb, `+0x1C` ride, `+0x1D` friend); with code primitives the caller sets them.
   `uCollisionMgr::setCollision_1(colGroup@eax, uniqueId@edx, mgr, atkIndex)` 0x50CA60 is the `.col` + `.atk`
   form (`setCollisionIdx` in earlier notes): `setCollision` then the `kAttackStatus` copy into group `+0xA4`
   (KnockbackEdits hooks the copy at 0x50CAD7 / 0x50CA35).
5. Group fields the ice sets: `mAttackStatus` (`+0xA4`, 0x58 B, name[15] = 0), `mpAttackStatusSrc +0xFC`, `mKind +4 = 4`,
   `mAttr +8 = 1`, `mVsAttr +0xC = 0`, `cCollisionGroup::setAttr(group@eax, frd@cl, kind)` 0x509FE0 (ORs the vs
   bits per kind: 0 Pl 0x22222200 | frd 0x22, 1 Ps same, 2/4 Em/Es 0x22202022, 3/5 0x22020222, 6 Set 0x20222222,
   7 Stg 0x2222222; the `.col` path reads the manager's own tables instead: `mVsAttrPlAtk +0x2B0`, Ps `+0x2C4`, Em
   `+0x2D8`, Es `+0x2EC`, Em2 `+0x300`, Es2 `+0x314`, Set `+0x328`, Stg `+0x33C`, filled by the constructor),
   `mLife +0x14C = 240` frames, `mpRefMat +0x140 = &mWmat` (the group follows the unit's matrix), `mOffset +0x148 = 0`;
   `+0x144` is `mTimer`. Kinds (`setVsAttr`'s switch): 0 Pl, 1 Ps (player shell), 2 Em, 3 Em2, 4 Es (enemy shell),
   5 Es2, 6 Set, 7 Stg.
6. `cResource::release(atk)` (the manager keeps its own reference). Per tick the owner calls
   `uCollisionMgr::move` (vtbl +0x18, 0x50CC40: `updateWorldMatrix` + group life) or `updateWorldMatrix` 0x50D090
   from its postMain; the global passes (`sCollisionGame::checkAttackMain` 0x47BC30 ...) resolve the hits.

`kCollPrim` (0x40): type (0 sphere, 1 box, 2 cylinder, 3 capsule), bone0 / bone1 (-1 = the ref matrix), radius,
pos0, pos1, attr, id, shrink, dummy (-1). The ice: type 3, both points 0, radius 30.

**Knock direction** (`uActor::calcDamageVec` 0x4A9BD0, called from `uActor::damagePreMessage` 0x4A80D5 for the
victim): reads the attacking group's `mBlownAngleType` (`+0xF4` = `kAttackStatus +0x50`) and the attacker
(`group->mpCollisionMgr->mpModel`, `+0x98` then `+0xE4`): **0 BLOWN_ANGLE_TYPE_POS** = direction from the attacker's
position to the victim; **1 BLOWN_ANGLE_TYPE_ANG** = the attacker's facing (`uCoord::getAngle(attacker).y`, so its
mQuat). DX9 handles only those two (2-5 fall through to world +Z). The result goes to the victim's `mDamageVec`
(+0x12F0), `mDamageAngleYF / YB / YFB / YFBLR` and the front / back / left / right classes; the enemy blown states
(`uEm000Base::setDamageBlown` 0x54F9E0 ...) turn the enemy to that angle and play the blown motion, so a shell whose
mQuat is a yaw of the wanted direction with type ANG knocks in world space; type POS knocks away from the shell.

dmc4_hook: `GerbShell` (`mods/GerbShell.cpp`, a `CustomUnit`) does 1-6 with kind 1 (Ps) and a capsule along the jump;
`uShell` (0x1380) has no collision manager of its own (`+0x1370 mpSrcActor`), so a custom shell owns and destroys
its `uCollisionMgr` (dtor 0x50B480) itself. `uActor` size 0x1370: `mActorType +0xEA4`, `mVel +0xEC0`, `mAcc +0xED0`,
`mDamagePos +0x12E0`, `mDamageVec +0x12F0`.

**The hit hand-off** (`sCollisionGame::checkAttackObj` 0x47C300 -> `uActor::damagePreMessage` 0x4A7F30, victim@edi, attack
group, victim group) **H**: the victim de-duplicates by the attack group's `mUniqueID` (a 16-entry queue, unless
`mUseUniqueID` is off), flags both managers `mInDamageMessage`, calls the **attacker's** report actor's vtable slot 37
(+0x94, the shell's `onhit` in dmc4_hook's CustomUnit; slot 38 when the victim is actor type 6) and, unless the victim
is type 6 / the attack is id 13 / the victim's `mActorStatus` (+0xEA8) has 0x200 and the attack isn't a grab, the
attacker's slot 51 (+0xCC); then **copies `mDamageTypeI` over `mDamageType` and `mAttackLvI` over `mAttackLv`** in the
attack group's status (so a code-made attack must set the I fields), calls the victim's slot 51, `calcDamageVec`
(the knock direction above) and the victim's slot 36 (+0x90, the damage message). No check of the attacker's actor
type or owner: a code-defined shell with kind 1 / attr 1 / vs 0x22222200 reaches an enemy as soon as the capsule
overlaps its damage group. Frame order (`sDevil4Main::move` 0x8AEE80): `sCollisionGame` rebuilt (chains emptied),
every unit line ticked (each `uCollisionMgr::move` re-chains its groups), `sCollision::move`, `checkPushMain`,
`checkAttackMain`; so any unit line registers in time (Nero's shells use line 0x12). `uCollisionMgr::updateWorldMatrix`
takes the collision scale from `mpDstModel->mScale.x`, or a 1.0 constant when the manager has no model, and ends
with `cCollisionGroup::updateAABB` (the broad phase's boxes) and `mAABBHit = 0`.

**What makes an enemy react** (Nero's `Collision\pl000.atk`, 187 entries): the vanilla attacks leave `mDamageType` /
`mDamageTypeI` at 0 and put the reaction in **`mDamageTypeB`** (2 blown: Streak, Split_01; 3 blown 2: Dropkick; 4 upper
/ launch: High Roller, Roulette Spin; 5 ground: Split_00), gated by the levels against the victim's `kDefendStatus`
(`mMaxInterrupt[5]` / `mMaxBlown[5]`): `mAttackLvI` 2-3 and `mAttackLvB` 2-3 on those, `mAttackLv` 0 (overwritten by
LvI at the hit anyway). A code-made attack with levels 0 hits (damage, hit stop, style) but never knocks back. Blown
angle type: Streak / High Roller 0 (POS), Dropkick 1 (ANG).
