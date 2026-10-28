# MoveDef: move definition files for DMC4 DX9

**Brief.** One editable XML per player move, holding everything the move needs: the LMT motion(s) to play, the
effects and when they fire, the hitbox groups and attack entries, cancel windows, sounds, camera / pad shake, and
the move-table row that triggers it. Albam (Blender) authors the file and compiles the parts that have a binary
home (`.ctn` cancel scripts, LMT event tables, `.idx` rows) into the files the game already reads; dmc4_hook loads
the file at runtime and runs the rest (effects on a frame timeline, the move's stage machine, the table row).
Entity summons stay in code. Scoped 2026-10-17. **Since then (2026-10-20 .. 24) two complete custom moves were
hand-coded in dmc4_hook (Gerb, DanteAirDodge) and the pieces they needed moved into its SDK; design.md section 5b
lists what they settled and section 8 the revised phases: the runner is a data-driven version of that recipe, the
Albam compile step is optional, and the acceptance test is parity with the two C++ moves (D16-D21).**

**v1 (2026-10-24).** The dmc4_hook runner (`mods/MoveDef.cpp`, `mods/XmlMove.cpp`, `sdk/MoveRegistry`) is at a
usable first version: files in `nativePC\movedef\` give a move its row, input command, motion bank, stage (slots by
stick direction, borrowed + synthesised `.ctn`, ballistics, landing / footwork exits, watchdogs, press hygiene, enemy
step), effects / sounds by frame, `<next>` transitions and hand-offs between files, `<follows>` string steps, shared
commands, and overlays on vanilla moves. Proven in-game by Nero's Million Stab out of Streak (`examples/nero_*.xml`);
the dodge parity file and the effects / hand-off details of the latest build are not yet reported. Known limits: one
stage per file (chain files), no `<shell>` hitbox yet, no synthesised script on vanilla motions, no `.ctn` compile.
What the hand-coded C++ moves settled is in `design.md` 5b; the C++ mods stay (D21).

**Status** (revised 2026-10-24; phases per design.md section 8)

| Phase | What | State |
|---|---|---|
| 0 | pugixml vendored, `XmlMove.cpp` parser scaffold, `.ctn` hang patch | done |
| A runner | `MoveDef` mod: registry (ids, gate bypass, dispatch), generic state function, synthesised `.ctn` scripts, `<launch>` physics, `<command>`, `<shell>`, runtime `<effect>` / `<se>`, panel + reload; **coverage check = `gerb.xml` and `dante_air_dodge.xml` behave like the C++ mods (which stay, D21)** | **in progress (2026-10-24)**: step 1 `sdk/MoveRegistry` built OK (Gerb / Dodge / LuciAirThrow register, the hand-written gate / dispatch chains are gone); step 2 **running in-game (2026-10-24: the Nero Million Stab chain works end to end; the dodge parity file not yet reported)**: `mods/XmlMove.*` (v0.2 parser) + `mods/MoveDef.*` (one stage, slots by stick, borrowed + synthesised `.ctn`, gate, `<launch>` + fx, land exit, watchdog, press hygiene, enemy step, `<command>` on a free bit with a ctx predicate, `<air_jump>`, air-hike hook on the base 0x803880, `MoveTable::add_row`), `<follows>` / `<window>` with names resolved across files and shared `<commands>` files (D22); `examples/dante_air_dodge.xml` is the parity file (id 0x6F). Next: `<shell>`, Gerb's second row, then the C++ mods go |
| B vanilla overlay | `<next>`s on vanilla moves **done and working in-game 2026-10-24** (Streak -> Nero's Million Stab on a held melee, janky but running) (`overlay="true"` files, ticked by the dispatch detours through `move_registry::vanilla_tick` before the game's function; `examples/nero_streak_hold.xml`); `<effect>` / `<se>` / `<kill_effect>` by frame on custom and vanilla motions written 2026-10-24 (untested; the stab example fires Dante's dust and burst); to do: the synthesised script on vanilla motions (Streak's cancels from `examples/streak.xml`) | - | Streak hands off to Nero's Million Stab on a held melee; later Streak's effects from XML |
| C authoring | Albam move panel (XML from the action and its pose markers), `.atk` codec upstream, Save to Game Folder of xml + lmt + atk | not started |
| D breadth | `both` halves, native motion overrides, grab banks, co-op audit, DT bank (re_todo 18), hitboxes via LMT events + `.idx`, `.msse` | not started |

## Index

### This folder

| File | What it holds |
|---|---|
| [design.md](design.md) | The design: what is already data-driven, the XML / compile / runtime split, game-side hook points, compile rules, risks, phases. |
| [schema.md](schema.md) | Element and attribute reference for the XML (draft v0.1). |
| [examples/streak.xml](examples/streak.xml) | Phase 1 file: an existing move with effects and cancels (block numbers still to fill in). |
| [examples/new_move.xml](examples/new_move.xml) | Phase 2 file: a new move with a table row and a scripted stage machine. |
| [examples/dante_air_dodge.xml](examples/dante_air_dodge.xml) | **The runner's parity file** (v0.2, loads today): DanteAirDodge as XML on id 0x6F; copy to `nativePC\movedef\`. |
| [examples/nero_streak_hold.xml](examples/nero_streak_hold.xml) | **The overlay example** (v0.2, untested): on vanilla Streak (id 28), melee held + stick centred once the finish's `free1` trigger is 2 hands off to Nero's Million Stab, Dante's own input for it. |
| [examples/nero_million_stab.xml](examples/nero_million_stab.xml), [nero_million_stab_finish.xml](examples/nero_million_stab_finish.xml) | **The chaining example** (v0.2, untested): Million Stab for Nero out of Streak. A melee row with `<follows move="28" window="C_NORM0">` (the string step), Dante's `pl006_03.lmt` blocks 8 / 9 in Nero's bank 12, the stab loop ending on `idle="18"` into a hand-off-only finisher (`<next to="move:...">`, the Stinger -> Million Stab way), footwork exit. |
| [decisions.md](decisions.md) | One entry per decision, with the reason, and the open ones. |
| [re_todo.md](re_todo.md) | Reverse-engineering items still open, as IDA tasks. |

### Reverse-engineering notes (in `..\RE\`)

| Note | Covers |
|---|---|
| [player_move_pipeline.md](../RE/player_move_pipeline.md) | How a player move runs: body halves, `updateCharTbl`, the contact bytes and `cancelNoTbl` (cancel windows), effect requests and the 0x39 effect-list table, `uCollisionMgr::move` (LMT event bits -> `.idx` -> `.col` + `.atk`), the state-function pattern, `requestSetMotion`, input commands and attack strings, **motion banks** (the 16 `mpMotionListArr` slots, which are free, runtime loading, the `mMotionSetCharTblParam` `.ctn` override, Nero / Dante joint compatibility). New 2026-10-17, extended 2026-10-18. |
| [resource_loaders_writers.md](../RE/resource_loaders_writers.md) | How each file is loaded (`sResource::create`, vtbl slot 8) and the game's own writers (vtbl slot 9, `MtDataWriter`) per class; exact `.atk` / `.dfd` / `.col` / `.idx` layouts; hot-swap rule. New 2026-10-17. |
| [effect_list_table.md](../RE/effect_list_table.md) | The 0x39 effect lists (`setEffectConst` listNo / fileNo -> `.efl` path), dumped in full. |
| [chartbl_ctn_hang.md](../RE/chartbl_ctn_hang.md) | The `.ctn` (rCharTbl) format, bank / slot rule (body LMT `_NN` -> bank NN - 1, Buster grabs 10-29), why a motion without a script hangs, and the data / exe fixes. |
| [sResource_findings.md](../RE/sResource_findings.md) | `sResource::create`, the resource hash table, `cResource` layout, creation flags. |
| [motion_runtime_findings.md](../RE/motion_runtime_findings.md) | LMT evaluation, `uModel::updateFrame` sequence events (`mpSeqInfo` -> `mSequence`), `A_STOP`. |
| [collision_findings.md](../RE/collision_findings.md), [collision_lineCast.md](../RE/collision_lineCast.md) | Collision runtime, `cCollisionGroup` kinds / `mVsAttr`. |
| [uEffectVFR_findings.md](../RE/uEffectVFR_findings.md), [efl_import_plan.md](../RE/efl_import_plan.md) §3.2 | Effect spawning, `setParamConst`, the GroupFlag / MaterialFlag spawn filter. |
| [nero_grab_findings.md](../RE/nero_grab_findings.md) | Buster grabs (`mvAtckSG*`), the grab motion sets. |
| [player_instance_findings.md](../RE/player_instance_findings.md), [pl_dx9_se_map.md](../RE/pl_dx9_se_map.md) | uPlayer fields and the DX9 <-> SE function map. |
| [ik_constraint_findings.md](../RE/ik_constraint_findings.md) | `getNumberFromMotSeq` (how code reads LMT event bits). |

### Code this touches

| Where | What |
|---|---|
| `D:\dmc4_hook\src\mods\MoveTable.cpp`, `misc\kAtckDefTbl.cpp` | the move table (`kAtckDefTbl`), ID gate 0x403C67, Dante dispatch 0x7CD1A1 |
| `D:\dmc4_hook\src\mods\LMTSlotFix.cpp` | `cCharTblMgr` / `rCharTbl` structs, the `.ctn` loop guard |
| `D:\dmc4_hook\src\mods\SelectiveCancels.cpp` | cancel permission bytes by motion + frame (`mMotCncl[k].mStat` at +0x30C4 + 0x2C k) |
| `D:\dmc4_hook\src\mods\LuciAirThrow.cpp`, `AerialStinger.cpp`, `Payline.cpp`, `RisingSun.cpp` | hand-coded new moves: what a move needed code for |
| `D:\dmc4_hook\src\misc\kActionTbl.hpp` | `kActLimitBit` / `ACT_STAT` / `kActionTbl` (per-action limit and status words), the three game tables' addresses, action numbers, vanilla copies (2026-10-20) |
| `D:\dmc4_hook\src\mods\MoveDef.cpp/.hpp`, `XmlMove.cpp/.hpp` | **the runner** (2026-10-24, untested): `XmlMove` parses a file into `xmlmove::File` (schema.md "Implemented"), `MoveDef` loads `nativePC\movedef\*.xml` in three passes (parse, shared commands, moves), adds rows (`MoveTable::add_row`), registers ids (`sdk/MoveRegistry`), runs `movedef::run_move` (the generic state function), hooks the base `uPlayer::checkWJumpBegin` for `<air_jump suppress_air_hike>`; panel on the debug page with Reload |
| `D:\dmc4_hook\src\sdk\MoveRegistry.cpp/.hpp` | the registry of custom move ids (D19): `register_move`, `id_allowed` (the ID-gate detour), `dispatch` (both dispatch detours) |
| `D:\dmc4_hook\src\mods\DanteAirDodge.cpp/.hpp` | Dante's sideways air dodge (2026-10-22/24): a custom input command with a predicate, the air-hike hook, press hygiene (`eat_held_jump`), the enemy step from frame 0, watchdogs, the panel's action log; the second reference move for the runner |
| `D:\dmc4_hook\src\mods\GerbShell.cpp/.hpp` | the code-defined hitbox shell (2026-10-22/23): `CustomUnit` + own `uCollisionMgr`, `.atk` entry with overrides, knock modes; the model for `<shell>` |
| `D:\dmc4_hook\src\sdk\CtnScript.hpp`, `InputCommand.hpp/.cpp`, `Custom.hpp`, `DebugDraw.hpp`, `MtMath.hpp` | the SDK pieces the runner is built from: in-memory `.ctn` scripts, extra input commands (bits 85-95), custom units / attack groups, depth-tested debug lines, quaternion helpers |
| `D:\dmc4_hook\src\mods\Gerb.cpp/.hpp` | Gerb (2026-10-20): a free six-direction jump as a Nero MoveTable move (row id 0x40, input = a selectable `ATTACK_DIRECTION_CMD`, dispatched by the new Nero hook in `MoveTable.cpp`), its cycles from `motion\pl000\gerb.lmt` in bank 13 (0 fwd, 1 down, 2 back, 3 L, 4 R, 5 up), the jump-out physics of WallRun on its own; **first custom move with working cancels (2026-10-21)**: in-memory `.ctn` script + the `mIsCancelCehckEnable` gate |
| `D:\dmc4_hook\src\mods\WallRun.cpp/.hpp` | the wall run (2026-10-18): a MoveTable state function over a tentative offset view of uPlayer (`wallrun::pl::*`), two-cast wall detection, hand-off to the game's wall jump, and a readable port of `moveActWallJump` 0x827200; the planned first user of a runtime LMT bank (D14) and the `.ctn` borrow (D15) |
| `D:\dmc4_hook\src\mods\KnockbackEdits.cpp`, `VisualizeHitbox.cpp`, `CustomProjectile.cpp`, `LoadOrder.cpp` | `kAttackStatus` editor, hitbox debug draw, the collision pipeline by hand, loose-file loading |
| `D:\dmc4_hook\src\sdk\Devil4.hpp`, `uCollisionMgr.hpp`, `uPlayer.hpp`, `uActor.hpp` | `effect_generator`, `indexed_anim_call`, `kAttackStatus`, `cCollisionGroup`, `Motion` |
| Albam `engines\mtfw\animation.py` | LMT import / export, event tables as pose markers (`DMC4EventGroup`, `events_params_01/02`) |
| Albam `engines\mtfw\col_shapes.py` | `.col` import / export / new, `active_groups` (ev1 bit k -> group `events_params_01[k]`) |
| Albam `albam_vendor\dmc4xml` (upstream: `E:\DMC mod stuffs\dmc4_xml`) | `xfs.py` (`.msse`), `col.py`, `xfsxml.py`; **`ctn.py` (done 2026-10-17, byte-exact on the 3 files; `tests/test_ctn.py --show bank:slot` reads a move's windows)**; `idx.py` / `atk.py` to come, upstream first |
| Albam `engines\mtfw\effect*.py`, `efl\` | the `.efl` editor; `effect_filter.py` mirrors the spawn masks |

### Data

| Path | What |
|---|---|
| `E:\DMC mod stuffs\arctool\uPlayerNero-vanilla\` | Nero: `chartbl\pl000.ctn` + `.plp`, `motion\pl000\pl000_01/02/04/06.lmt`, `Collision\pl000.col/.atk/.dfd/.rCollisionIdxData`, `sound\se\player\pl000\` (rMotionSe `pl000.0CA6AED4`), `effect\efl\com\` |
| `E:\DMC mod stuffs\arctool\uPlayerDante-vanilla\` | Dante: `chartbl\pl006.ctn`, `motion\pl006\pl006_01..10.lmt` |
| `E:\DMC mod stuffs\DMC4 templates\DMC4_atk.bt`, `DMC4_dfd.bt`, `DMC4_col.bt` | 010 templates (`.atk`: the 4 unknown bytes after the name are `mAttackID`) |
