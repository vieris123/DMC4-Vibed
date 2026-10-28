# MoveDef design

Scoped 2026-10-17 from the DX9 exe (IDB on port 13337), the vanilla Nero / Dante files, dmc4_hook and Albam. The
dmc4_hook side is written as decisions and hook points; the mods themselves are the user's own.

## 1. Two facts that shape everything

- **Upper and lower body moves run at once.** Two motion controllers and two `cCharTblMgr` (uPlayer +0x1DD4 =
  `BDY_UPPER` 0, +0x1DF8 = `BDY_LOWER` 1; motion controller 1 drives the upper half, controller 0 the lower). While
  an upper motion plays, its contact / cancel data wins (`uPlayer::updateCharTbl` 0x7AB720). A move declares its
  half; `both` means two motion requests.
- **Everything an actor needs is loaded in its `setup`** (LMTs, `.ctn`, `.plp`, `Collision\pl000.*`, rMotionSe)
  **except effects, which are requested on the fly** from the move's state function.

## 2. What is already data-driven

| Piece | Where it lives | Consumer in the game | Tooling today |
|---|---|---|---|
| Motion | LMT block `(bank, slot)`: bank = `pl000_NN` -> NN - 1, slot = block index; `motion_no = bank << 8 \| slot`. Banks are the 16 `uModel::mpMotionListArr` slots (+0xA38) per model, filled in `setup` (Nero 0, 1, 3, 5; Dante 0-9; 15 = Nero's Buster bank, loaded at grab time); **10-14 are free on both characters** and can be filled at runtime with `uModel::setMotionList` 0xA26340 | `uPlayer::requestSetMotion` 0x821450 | Albam LMT import / export, Add Animation |
| Hitbox windows | LMT event table 1: bit k -> `events_params_01[k]` = row of `.rCollisionIdxData` (row k = `.col` group k; columns 0, shape group, `.atk` entry, pair id, first-of-pair) | `uCollisionMgr::move` 0x50CC40 (`mSeqTrgOn/Off` -> `setCollisionIdx` / `removeCollisionGroupBySeqNo`) | Albam: events as pose markers, `.col` import / export / new; `.idx` / `.atk` / `.dfd`: templates only |
| Attack properties | `.atk`: `kAttackStatus` 0x58 B verbatim (name[16], mAttackID, damage, levels, range, hit stop, damage types, hit mark, hit SE, style points, DT add, flags, blown angle, element) | copied into the `cCollisionGroup` on activation | dmc4_hook struct + KnockbackEdits UI |
| Sounds | LMT event table 2: bit k -> `events_params_02[k]` = rMotionSe (`.msse`, XFS v5) entry | motion sequence -> `sDevil4Sound::requestSe` 0xA47AA0 | dmc4xml `xfs.py` reads it |
| Cancel windows, stage triggers, camera / pad shake | `.ctn` script per (bank, slot): contact[0] = atck, free2, camVib, free1, free0, padVib; contact[1] bytes 0-5 = cancel category (low nibble, via `cancelNoTbl`) and open / close (high nibble 0x10 / 0x20 / 0x30) | `cCharTblMgr::update` 0x42B8E0 -> `updateContactInfoSub` 0x7AB770 -> `mMotCncl[8]` (= permission bytes +0x30C4 + 0x2C k) | none; a motion without a script hangs (`RE/chartbl_ctn_hang.md`) |
| Move table row | `kAtckDefTbl` 0x38 B; priority list, first matching row's `atckId` -> `moveID2` -> jump table -> hand-written state function | `checkAtck*`, dispatch 0x7CD1A1 (Dante) | dmc4_hook MoveTable |
| Effects | **code only**: `sDevil4Effect::setEffectConst(listNo, fileNo, parent, groupMask, materialMask, unitLine, owner)` 0x480480 + `uPlayer::setEffect` 0x81FD60; the 0x39 `.efl` path lists at 0xDEB8B8 (counts 0xDEB9A0) | the state function | Albam `.efl` editor; dmc4_hook `effect_generator(path, ...)` |
| Physics, speed, stage logic | the state function (velocity +0xEC0.., gravity +0xED4, `.plp` tunables) | the state function | per-move pokes |

So the gap is effects (and the stage logic / physics around them). Hitboxes, attack data, sounds and cancels are
file-driven already; they need tooling, not a runtime.

## 3. The split

**The XML is the source. Albam compiles what has a binary home; dmc4_hook runs the rest.** The game's consumers
are correct and fast and already handle upper / lower, hitstop and speed; a DLL re-implementation would duplicate
those rules.

| XML section | Materialised as | Applied by |
|---|---|---|
| identity + table row | `kAtckDefTbl` row | DLL at init / reload |
| stages (motion per stage, speed, start / interp, transitions) | nothing | DLL scripted routine |
| cancel windows, camera / pad shake, stage-trigger bytes | `.ctn` script | Albam compile; game reads |
| hitbox windows (`.col` group + `.atk` entry, frame range) | LMT event table 1 runs + `.idx` row | Albam compile; game reads |
| sounds via rMotionSe | LMT event table 2 runs + `.msse` entry | Albam compile; game reads |
| effects, direct `requestSe`, physics | nothing | DLL timeline runner / routine |

Albam also **extracts** a vanilla move into XML (LMT block events, `.ctn` script, `.idx` row) so modders start from
an existing move. Reference tables Albam needs: the effect list table, `cancelNoTbl`, the bank / slot rule.

## 4. File shape

One XML per move in a per-character folder under the loose-file root (`movedef\pl000\<name>.xml`), plus
`_character.xml` for shared declarations (reserved move-ID block, default LMT / `.ctn` / `Collision\` paths).
Motions are `bank:slot`. See `schema.md`; the sketch:

```xml
<move name="nero_rising_slash" character="pl000" id="0x82" body="lower" version="1">
  <table insert_before="0x0C" attr="2" level="3" command="0x152" weapon="4" style="-1" dt="1" air="1"/>
  <stages>
    <stage name="windup" motion="1:0x2A" speed="1.0" start="0" interp="3">
      <next on="contact" byte="free0" value="1" to="slash"/>
      <next on="motion_end" to="exit"/>
    </stage>
    <stage name="slash" motion="1:0x2B"><next on="motion_end" to="exit"/></stage>
  </stages>
  <timeline motion="1:0x2A">                       <!-- compiled: .ctn script + LMT events + .idx -->
    <cancel category="C_JUMP" kind="open" from="18" to="40"/>
    <trigger byte="free0" value="1" frame="14"/>
    <vibrate pad="3" cam="2" frame="12"/>
    <hitbox col_group="4" atk="17" from="10" to="16"/>
    <sound msse="0x3A" frame="9"/>
  </timeline>
  <timeline motion="1:0x2A" runtime="true">        <!-- applied by dmc4_hook -->
    <effect efl="effect\efl\com\ec000_05v0" joint="R_Hand" group="-1" material="-1" unitline="0x14" frame="10"/>
    <physics frame="0" vel="0,0,6.5" gravity="-0.8"/>
  </timeline>
</move>
```

**Shared moves and runtime LMT banks (2026-10-18).** A move both characters use (the wall run) lives in
`movedef\common\` with `character="pl000 pl006"` and brings its own LMT: `<lmt bank="14" path="motion\common\wallrun"
coat_pl000="..." coat_pl006="..."/>`. The DLL loads the file into bank 14 of the body model (and the coat files
into the coat model's bank 14) when the player is set up, and the move's motions are `14:slot`. One body LMT fits
both skeletons (all 75 body joint numbers are shared; only 153 / 154 are parented differently and limb lengths
differ by a few cm), the coats don't (39 vs 46 joints), hence a coat file per character. Banks 10-14 have no
`.ctn` scripts of their own (bank 14 is a Buster bank in `pl000.ctn` and absent in `pl006.ctn`), so such a move
borrows cancels with `<stage ctn="0:22">`: the DLL writes `mMotionSetCharTblParam` (see section 5) before the
motion request, and no `.ctn` compile is needed for it.

A tweak of a native move says `<routine native="0x7D6ED0"/>` instead of `<stages>`; timelines still apply. Finer
native tweaks (RisingSun-style `push imm` swaps) stay C++, except `<native_motion_override from= to= speed=
start=/>`, a filter in the `requestSetMotion` hook active while `moveID2` is this move. Entity summons stay in
code; a scripted move may name a registered native callback (`<native_call fn= frame=/>`).

## 5. Game side (dmc4_hook): decisions and hook points

- **Timeline runner (passive).** Instance per (player, body half, motion_no, start frame) opened from a
  `requestSetMotion` 0x821450 hook; evaluated once per tick after `updateCharTbl` 0x7AB720, reading `mMotionNo` /
  `mFrame` through both managers' `mpMtn` (+0x1DD4+8, +0x1DF8+8). Fire when `prev < frame <= cur` and the instance
  bit is clear (covers speed, interpolation, hitstop, start frames); loops clear only `repeat="loop"` events. State
  keyed by `uPlayer*`. Works on vanilla moves too. To check: body half at the call; tick order of `updateMotion`
  0x820F50 vs `updateCharTbl`.
- **Scripted routine.** One generic state function on a reserved ID block per character: ID-gate bypass at
  0x403C67 for the block, dispatch case (Dante 0x7CD1A1 exists; Nero's dispatch site is new RE work), transitions on
  motion end (`Motion.mState` bit 0) / contact byte (`mContactData[0]`) / frame / input, exit via the neutral
  transition.
- **Table builder.** Stable IDs in the reserved block + `insert_before="<vanilla atckId>"` anchors instead of front
  insertion; `row_for_id(character, id)` for the mods that index the table today.
  Rows carry the input and the string position: `<input command=>` -> `atckCommand` / `atckCommandNo` (a `CMD_ID` the
  game's `commandCheckSub` recognizes), `<follows move= window=>` -> `cancelId` entries (`cmdId` = the previous move,
  `cmdNo` = the `.ctn` window that must be open). Custom input sequences (new `CMD_ID`s) are phase 3: the DX9
  command table is a fixed 85 entries with three flag words.
- **Runtime motion banks.** `sResource::create(sDevil4Resource, &rMotionList::DTI 0xEAE348, path, 1)` (dmc4_hook
  `get_stuff_from_files`) -> `uModel::setMotionList(model, rsrc, bank)` 0xA26340 (thiscall; releases the old list,
  addRefs the new, flags every blend slot for re-bind) -> release the creating ref: the sequence of
  `uPlayerNero::setBusterMotionRsrc` 0x7E7F30, which fills bank 15 of body, coat (`mCoat` +0x52C0), stand (+0xCDF8)
  and the stand's sub-model at grab time. `setMotionList(model, 0, bank)` unloads. Shared moves use bank 14.
- **Cancel gate (settled 2026-10-21 with Gerb).** A scripted move entered through an attack row runs with
  `mIsCancelCehckEnable` +0x1F50 cleared (`setActionAtck` does that), and `uPlayer::main` evaluates no cancel at all
  (`checkBeforeAction` / `checkAction`: attacks, jumps, gun, pose) until the move sets it back, which the vanilla
  attack functions do at their recovery frame. The runner must set it at the move's first `<cancel>` frame; the
  `.ctn` windows (or a synthesised script handed to the `cCharTblMgr` cursors, D11) then pick the rows. Byte 0x10
  (`mStat` 2) starts the next attack at once, 0x30 (`mStat` 1) reserves it (`mYoyakuAtckId`).
- **`.ctn` for runtime banks: borrow a script.** `uPlayer::mMotionSetCharTblParam[2]` +0x2A3C (`{bool isEnable; u32
  bank; u32 idx}`, [0] upper, [1] lower +0x2A48): when set, `updateMotion` 0x820F50 points that half's
  `cCharTblMgr` at `.ctn` bank `bank` slot `idx` instead of deriving them from the motion number, then clears it
  (the Buster grabs' path, `setShortGrabMotionSet` 0x7E7E90). Written right before `requestSetMotion`; `<stage
  ctn="bank:slot">` names the vanilla script to borrow. A script synthesised from `<timeline>` (D11) can later be
  reached the same way once the DLL appends it to the rCharTbl buffer.
- **Effects by `.efl` path** through `effect_generator`; `list` / `index` optional for vanilla effects; preload
  referenced `.efl` on level load.
- **`.ctn` safety net** first: the one-byte patch at 0x42B902 (`77 2E` -> `77 41`: unknown opcode = script done);
  later the code cave in `RE/chartbl_ctn_hang.md`.
- **Hot reload.** Timelines and table-row fields in place. rCharTbl's buffer (+0x60 / +0x64, size +0x50) can be
  swapped between motions (only the `cCharTblMgr` cursors point into it, and they reset at every motion start), so
  cancels hot-reload too. `.idx` / `.atk` / `.col` are parsed into heap objects wired into `uCollisionMgr` at setup:
  level reload. The game's own `save` vtable slots (`RE/resource_loaders_writers.md`) can dump an in-memory table
  back to a file.

### 5b. What the hand-coded moves settled (2026-10-20 .. 24)

Gerb (Nero, two rows) and DanteAirDodge (Dante) are complete custom moves in C++ (`D:\dmc4_hook\src\mods\`),
tested in-game, and they share one recipe. The MoveDef runner is that recipe made data-driven; every item below
is a rule the runner must follow, with the code that proves it.

| Step | What the runner does | Settled by |
|---|---|---|
| Row | front-insert the `kAtckDefTbl` row with the command byte's "disabled" bit, flip it when the move is enabled (`apply_row`) | Gerb / Dodge `apply_row`, `MoveTable::updateKDATbl` |
| ID gate | the unlocked-moves bitset test in `checkAtck` (dmc4_hook `detour0` at 0x403C67) must let the id through **per id and per enabled mod**; a chain that returns early when one mod is off hides every later mod's id | the "dodge not triggering" bug (2026-10-22) |
| Dispatch | Nero `moveActAtckL` hook at 0x7F9CDB (ids >= 0x34 free), Dante 0x7CD1A1 (ids >= 0x6C); **never gated on another mod's enable** (with LuciAirThrow off a dodge row set its action but no state function ran: frozen, no inputs, until restart; fixed 2026-10-24) | `MoveTable::detour3 / detour4` |
| State | the game's own phase word `mBdyAction[1].phase` (+0x1504, zeroed by setAction) for the stage; everything else in a per-player table of **4 slots with least-recently-seen eviction**, keyed by `uPlayer*` (hooks run for every uPlayer incl. NPC / boss copies; a 2-slot "reset when full" table thrashed after a stage switch and froze Gerb in place) | Gerb / WallRun `state_for` |
| Motion | `load_motion_bank(player, path, bank)` into a free bank 10-14 **per player object**; **a bank is per mod, not per file**: the loader skips a bank that is non-empty, so a second LMT asked for the same bank silently plays the first file's blocks (Gerb's 6-block file in bank 12 gave Nero's Million Stab the forward jump at slot 0 and a no-data wedge at slot 8: T-pose, frames stuck, even the footwork wedged; 2026-10-24). The runner records the resource it loaded and refuses a bank holding another; banks are config values in the C++ mods (Gerb 13 by default, the user's 12), so an XML move should take 10 / 11 (a stage switch makes a new uPlayer; `ensure_bank` runs every frame for the local player and at move entry), `get_motion_bank != 0` = ready, else the neutral air transition | `ensure_bank`, `ready` |
| Request | `requestSetMotion_2` (whole body) with `A_NULL_TRANS_OFF`, interp 4, start 0, speed 1; the entry phase leaves velocity alone (zeroing it froze the player) | Gerb entry |
| `.ctn` | `borrow_ctn(player, bank, idx)` before the request (a runtime bank has no script), then on the **next** tick `install_ctn_script(player, bytes)` with a script built by `sdk/CtnScript.hpp` (`ctn::Script`: `wait / contact / clear / loop_to / end`, `open / close / reserve({CANCEL_NO})`, `open_all`), one static buffer per player slot. The game's interpreter runs it: no `.ctn` compile for custom moves, and the same call can override a **vanilla** motion's script at its start (phase 1 needs no compile either) | D11 first use, Gerb 2026-10-21 |
| Gate | `mIsCancelCehckEnable` +0x1F50 = 1 from the first open window on (setActionAtck clears it; nothing is evaluated while it is 0) | Gerb 2026-10-21 |
| Input | custom sequences are available now: `sdk/InputCommand.hpp` runs extra `kCmdHead`s after `executeCommandCheck` (hook 0x7A83B5) and sets free `mCmdFlag` bits **85-95** (11 of them); `input_commands::Command` builder (`condition / button / lever / active`), an optional per-tick predicate; so `<command>` moves out of phase 3 | Gerb (lock-on + back-forward + style), Dodge (lock-on + jump + a stick predicate) |
| Press hygiene | a press that starts a move can be visible for a second tick (the game ticks faster than the pad reports: 0.6 motion frames per tick on the user's build) and `updateMotCancel` latches it as the C_JUMP reserve; eat the trigger bit and the reserve until the button is released once (`eat_held_jump`) | Dodge 2026-10-24 (log: `J 1/1` one tick in) |
| Jump cancel | the enemy step is window-free: call `uPlayer::checkEmJumpBegin` 0x804970 from the move while the gate is off to offer it from frame 0; **do not** open C_JUMP early (it frees the air hike / wall jump as well) | Dodge 2026-10-24 |
| Physics | launch at a frame: velocity = dir x speed + up x rise, then gravity per tick with a fall cap, `mMoveVel` / `mJumpMoveAng` kept in step, `mAddSpd` cleared, optional AST_JUMP status; land when `vel.y <= 0 && mCollMgr->mLand` (+0x1C) -> `setActionLand` 0x7AA6A0; exit otherwise through `neutral_air_transition` | Gerb / Dodge airborne phase |
| Watchdog | a motion that never advances (bank taken, block missing or empty) must not soft-lock: leave the move and log the motion word the controller plays vs the one requested | Dodge 2026-10-24 |
| Effects | `devil4_sdk::effect_stay(list, index, quat, pos, owner)` (SetEffectStay 0x4805D0 + uPlayer::setEffect) and `play_player_se(player, id)` (requestSe 0xA47AA0 with the player's SE resource +0x1D60); orientation from the player's basis leaned by a tilt (`mt_basis_quat`) | take-off fx 2026-10-21 |
| Hitbox (code) | a `CustomUnit` shell with its own `uCollisionMgr`: `custom_utils::load_atk_col` (init_0 0x50BDD0), `kAttackStatus` copied from a `.atk` path + entry with overrides (damage types I/B, levels, blown angle type), one `kCollPrim` capsule, `add_prim_attack_group` (setCollision 0x50C290, kind 1 Ps, vs attr re-asserted each tick), follows the owner, knocks along a yaw (`mBlownAngleType` 1 ANG) or away from it (0 POS). No `.idx` / `.col` / LMT-event compile: a second hitbox route, runtime-only and hot-reloadable | GerbShell 2026-10-22/23 |

Consequences for the design: the Albam **compile** step is no longer on the critical path. `.ctn` scripts and the
cancel gate are synthesised at runtime; hitboxes can be shells; only the LMT itself (Albam already exports it) and,
later, new `.atk` entries need files. Albam's share moves to **authoring** the XML from the Blender action (frames
from the pose markers, joints by name, effects from the `.efl` editor) and to the `.atk` codec.

## 6. Compile rules (Albam / dmc4xml)

- **`.ctn`: full rebuild** by a new codec (`ctn.py`, written upstream in dmc4_xml, then `scripts/sync_dmc4xml.py`).
  Every (bank, slot) with a non-empty LMT block gets a script; undeclared ones a shared one-byte `FF`. Emit only
  opcodes 00-03 / FF, wait mode 0, contact index 0 / 1, in-script loop targets. Cancel kinds -> high nibble 0x10
  (open, mStat 2) / 0x20 (close) / 0x30 (open, mStat 1); categories -> `cancelNoTbl` byte positions.
- **LMT events:** a free slot bit per `<hitbox>` / `<sound>` (8 per table per block), the runs written as (value,
  duration) from frame 0, `events_params_01[k]` = `.idx` row, `events_params_02[k]` = `.msse` entry. Extraction
  reads the existing pose markers.
- **`.idx`** (text): append rows, row k = `.col` group k. **`.atk`**: `ATK\0`, u16 0, u16 count, then
  `kAttackStatus` x count verbatim (0x58 each); until the codec exists, `atk=` must name an existing entry. `.col`
  export exists. All written to `Collision\pl000.*` via Save to Game Folder.
- **Validation** (Albam, hard errors): block exists and is non-empty, frames inside the block, `.efl` / joint /
  `.col` group / `.atk` entry exist, every (bank, slot) covered in `.ctn`, ID unique and in range. DLL: schema
  version, ID range, duplicates, unknown attributes; never load a partial move; refuse with a log line.

## 7. Dependencies and risk

- **DLL parser: pugixml** (decided 2026-10-17, D12), vendored under `dependencies\` like minhook. The schema stays
  inside the plain XML subset (elements, attributes, comments) regardless.
- `.plp` tunables referenced, not edited.
- Open RE items: `re_todo.md`.

## 8. Phases (revised 2026-10-24)

The hand-coded moves are the reference: the runner is done when the two of them run from XML files with no
behaviour change, and the C++ mods can go.

| # | dmc4_hook | Albam | In-game check |
|---|---|---|---|
| A runner | `MoveDef` mod: loads `movedef\*.xml` (pugixml, scaffold `XmlMove.cpp`), a per-character **registry** (stable ids, ID-gate bypass and dispatch by table lookup instead of per-mod asm; `MoveTable` keeps the rows), the generic state function (stages: motion request + `.ctn` borrow + synthesised script + gate; `<launch>` physics; land / exit; watchdog; press hygiene; enemy step), runtime timeline (`<effect>` stay / generator, `<se>`, `<physics>`), `<command>` through `input_commands`, `<shell>` through a generic GerbShell, ImGui list + reload | - | `gerb.xml` and `dante_air_dodge.xml` behave like the C++ mods (six directions, vertical row, shell knock, dodge with its two-tick press rule), with the C++ mods disabled |
| B vanilla overlay | the passive side: a `requestSetMotion` hook opens a timeline instance for **vanilla** motions the XML names (`<routine native>` moves), fires `<effect>` / `<se>` by frame, and installs a synthesised script at motion start when `<timeline>` has cancels | - | Streak (`examples/streak.xml`) fires its effects from XML; a changed cancel frame takes effect after Reload, no `.ctn` edit |
| C authoring | `.atk` codec (dmc4_xml upstream, vendored) and `<attack>`; Save to Game Folder writes xml + lmt + atk | move panel on the LMT action: stages from blocks, frames from pose markers, hitboxes as shells or events, effects picked from Game Files; validation (block exists / non-empty, frames inside, joint names, ids unique and in range) | a move authored in Blender runs after Save to Game Folder + Reload |
| D breadth | `both` halves, `<native_motion_override>`, grab banks, co-op audit, DT model bank question (re_todo 18), the `.ctn` code cave | hitboxes through LMT events + `.idx` when wanted (the game's own path), `.msse` entries | LuciAirThrow or Payline re-expressed in XML |

Phase 0 (pugixml, scaffold, `.ctn` patch) is done; the old phase 1 / 2 split (compile first, then a new move) is
superseded: the new-move path is proven in C++ and comes first, the compile path is optional.
