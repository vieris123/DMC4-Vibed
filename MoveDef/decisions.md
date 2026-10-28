# MoveDef decisions

One entry per decision; date, the choice, the reason. Open ones at the end.

## D1 (2026-10-17): the XML is the source; Albam compiles what has a binary home; the DLL runs the rest
Cancel windows, hitbox windows and sounds are already read from files by `cCharTblMgr`, `uCollisionMgr::move` and
the LMT sequence events, which also carry the upper / lower precedence, hitstop and speed rules. Compiling into
those files reuses that; a DLL runtime for them would duplicate it. Effects, physics and stage logic have no binary
home, so they are runtime.

## D2: one XML per move, per-character folder, `_character.xml` for shared declarations
The stated goal is one file per move. Per-character files make sharing a single move painful. The DLL globs a
folder.

## D3: timeline runner hooks `requestSetMotion` 0x821450 (instance open) and `updateCharTbl` 0x7AB720 (tick)
Game-tick rate, per player, pauses with the game, and `updateCharTbl` already reads exactly the upper / lower
motion pair. Fire-once per instance by a bitset; `prev < frame <= cur` handles speed, interpolation, hitstop and
start frames.

## D4: one generic scripted routine on a reserved `atckId` block per character
Extends the existing Dante dispatch pattern (0x7CD1A1); Nero's dispatch site is to be found. Native routines stay
usable through `<routine native>` with the timelines overlaid.

## D5: stable move IDs + `insert_before` anchors instead of front insertion in the table
Front insertion shifts every index other mods computed and the ImGui "Create" path can leave the table pointer
dangling after a reallocation. Stable IDs with `row_for_id()` remove the arithmetic.

## D6: effects referenced by `.efl` path (list + index optional)
`effect_generator` already spawns by path, and Albam-made `.efl` files have no entry in the exe's 0x39-list table.

## D7: `.ctn` compiled by a full rebuild with the hang-safety rule; exe patch 0x42B902 shipped first
Every (bank, slot) with a non-empty LMT block gets a script; undeclared ones share a one-byte `FF`. The patch turns
an unknown opcode into "script done" so a missed slot can't freeze the game while the tooling matures.

## D8: entity summons stay in code
Projectiles and other spawned actors are too varied for a schema; a scripted move may call a native callback
registered in dmc4_hook (`<native_call>`).

## D9: `.plp` (rPlParamTbl) referenced, not edited
Loosely defined per-character tunables; out of scope.

## D10: phase 1 target = Streak (Nero, lower body)
Few stages, an effect on hit, and Payline already touches its code so the frames are known.

## D11 (2026-10-17, the user's): tag custom-reader motions in `Motion.mReserved`
`uModel::Motion` +0x06 is a u16 the game never reads or writes (`RE/player_move_pipeline.md`), right after
`mMotionNo` and per blend slot, so it survives interpolation and works for both body halves. The hook sets it at
`requestSetMotion` time and a `cCharTblMgr::set` hook (plus the two inlined grab lookups) reads it through `mpMtn`:
non-zero = this motion's contact script comes from MoveDef, not the `.ctn`. The DLL can then point `mpDataTop` /
`mpDataCrnt` at a script it synthesised in memory from the XML `<timeline>` and let the game's own interpreter run
cancels, triggers and vibration (no `.ctn` compile needed for custom moves; hot reload for free). The value can carry
the move id (16 bits) rather than a bool. Open: whether the `.ctn` compile stays for shipping (files are
self-contained without the DLL) or becomes optional.
**First use 2026-10-20** (dmc4_hook `Gerb.cpp`): no `set` hook was needed. The move lets `updateMotion` install the
borrowed script on the request tick, then on the next tick points both `cCharTblMgr` cursors (`mpDataTop` /
`mpDataCrnt` +0xC / +0x10, `mIsDone` +0x14) at a static in-memory script (`wait(frame)`, `contact(1, 10 10 10 10 10 10)`,
`FF`), and the game's interpreter opens the windows. Poking `mMotCncl[k].mStat` directly from the move function
did not work (the game rebuilds them from the contact data).

## D12 (2026-10-17, the user's): DLL parser = pugixml
Decided after weighing "no new dependency": pugixml, vendored under `dependencies\` like minhook (one `.cpp`, two
headers, MIT). The schema still stays inside the plain subset (elements, attributes, comments; no entities, mixed
content or namespaces), so the files don't depend on parser features.

## D13 (2026-10-18, the user's): moves carry their input and their place in a string
The move table row already encodes both (`RE/player_move_pipeline.md`): the input as `atckAttr` + an optional
`CMD_ID` recognized by `commandCheckSub`, the string as `cancelId` entries naming the previous move and the cancel
window that must be open. `<table>` exposes exactly those (`attr`, `<input>`, `<follows move= window=>`,
`<window>`), so the DLL writes rows the game's own `checkAtck` walks: no second input system. New input sequences
(custom `CMD_ID`s) wait for phase 3, because the DX9 command table and flag words are fixed-size.

## D14 (2026-10-18): a move shared by both characters brings its own LMT into bank 14 at runtime
`uModel::mpMotionListArr` has 16 slots; setup fills Nero 0 / 1 / 3 / 5 and Dante 0-9, Nero's Buster grabs load into 15
on the fly (`setBusterMotionRsrc`), so 10-14 are free on both. Loading with the game's own `setMotionList` after
setup reuses the refcounted resource path and needs no exe change. One body LMT fits both skeletons (shared joint
numbers, small length differences), so a shared move is authored once; coats differ and get a file per character.
First user: the hand-coded wall run (`D:\dmc4_hook\src\mods\WallRun.cpp`), before the XML runner exists.

## D15 (2026-10-18): motions in a runtime bank borrow a vanilla `.ctn` script through `mMotionSetCharTblParam`
A runtime bank has no `.ctn` scripts (bank 14 is a Buster bank in `pl000.ctn`, absent in `pl006.ctn`: the hang).
The game already has a per-request override for exactly this (the grabs): `mMotionSetCharTblParam[half] = {1,
bank, idx}` before `requestSetMotion`, consumed and cleared by `updateMotion`. `<stage ctn="bank:slot">` exposes it.
This also gives D11's synthesised scripts a way in without touching `cCharTblMgr::set`. The `.ctn` compile stays
for moves on setup banks.

## D16 (2026-10-24): custom moves need no `.ctn` compile; scripts are synthesised at runtime
D11's mechanism (point the `cCharTblMgr` cursors at an in-memory script on the tick after the request) is now the
SDK's `install_ctn_script` + `ctn::Script` builder, used by Gerb and DanteAirDodge. The runner builds a move's
script from `<timeline>` (`<cancel>`, `<trigger>`, `<vibrate>`) and installs it; the same call overrides a
vanilla motion's script at its start, so phase 1 (Streak) needs no compile either. Albam's `ctn.py` stays for
shipping edits to vanilla moves without the DLL.

## D17 (2026-10-24): custom input sequences now, through the SDK command runner (bits 85-95)
D13 deferred new `CMD_ID`s to phase 3 because the DX9 table is fixed. `sdk/InputCommand` sidesteps the table: extra
heads run after `executeCommandCheck` and set the 11 free `mCmdFlag` bits. `<command>` in the move (or
`_character.xml`) compiles to an `input_commands::Command`; a row's `<input command=>` may name it. Limit: 11 custom
commands per game, shared by every mod (the SDK hands out the bits).

## D18 (2026-10-24): hitboxes have a runtime route: `<shell>`
GerbShell showed a code-defined capsule with a `kAttackStatus` taken from a `.atk` path + entry (with overrides)
hits and knocks enemies with no `.idx` / `.col` / LMT-event edits. `<shell>` is that unit, data-driven: shape,
offset, life, kind, the `.atk` source and the reaction overrides, knock mode. The LMT-event route stays for moves
that want the game's own hitbox files (phase D). New `.atk` entries need the codec (phase C).

## D19 (2026-10-24): the ID gate and the dispatch are registry lookups, never per-mod asm
Two bugs came from hand-written chains in `MoveTable`: a bypass chain that returned early when one mod was off hid
later ids (dodge not triggering), and Dante's dispatch gated on LuciAirThrow froze players with it off. The runner
registers (character, id, enabled flag, state function) once; `detour0` tests a bitset of live ids and the dispatch
detours look the id up. Existing mods migrate to the same calls.

## D20 (2026-10-24): press hygiene and the jump cancel are runner rules
A press can outlive its tick (pad cadence vs game ticks) and `updateMotCancel` latches it as the C_JUMP reserve, so
a move started by a press eats that button's trigger bit and the reserve until the button is released once. The
jump cancel from frame 0 is the enemy step (`checkEmJumpBegin`, window-free), called by the move while its gate is
off; C_JUMP is never opened early (air hike / wall jump would follow). Both are defaults, with attributes to turn
them off.

## D21 (2026-10-24, amended the same day): parity with Gerb and DanteAirDodge measures the runner's coverage
`gerb.xml` and `dante_air_dodge.xml` behaving like the C++ moves shows the XML can express what the hand-coded moves
needed. **The C++ mods stay** (the user's call: some things can simply remain code); parity is a nice-to-have, not a
removal plan. Any new rule learnt while porting goes into section 5b of the design.

## D22 (2026-10-24): moves chain through the game's own string mechanism, by name across files
A move that follows another is a row whose `cancelId` names the previous `atckId` and the window it must have open
(`yCancelInfo`, D13), so `<follows move="name" window=>` is the whole feature: the runner parses every file in the
folder first and resolves names to ids (a number is a vanilla id), the predecessor opens the window from its own
`<cancel>`, and `checkAtck` starts the follower on its input. No runner-side transition, no new input system. Shared
`<command>`s live in `<commands character=>` files (or as a move file's extra `<command>`s) and are named from any move's
`<input>`. A direct hand-off (`<next to="move:name">`, with or without input) is the Stinger -> Million Stab
way (the user's pointer, 2026-10-24): `setActionAtck(this, id, both halves)` then the new move's state function in the
same tick (`RE/player_move_pipeline.md`, Hand-off between moves). Conditions mirror the Stinger's: a `.ctn` trigger
byte (`<trigger>` in the predecessor's script), a held button (mashing), a centred stick, a frame, the motion end, the
landing.

## D23 (2026-10-24): overlays on vanilla moves ride the dispatch detours
A vanilla move's state function can't be edited, but every tick of it passes through MoveTable's dispatch detours
(Nero 0x7F9CDB, Dante 0x7CD1A1) before the game's jump table. They now call `move_registry::vanilla_tick(character,
id, player)` first; MoveDef's overlays (`overlay="true"`, a vanilla id) evaluate their `<next>`s there, and a hand-off
makes the detour return without running the vanilla function for that tick (its phase word already belongs to the new
move). This is phase B's hook point instead of a `requestSetMotion` hook: same tick position as the vanilla moves'
own chain checks (after `updateCharTbl`, inside `moveAction`), per player, no extra state. The `<effect>` / `<se>`
timeline on vanilla motions will use the same tick. First use: Dante's Stinger -> Million Stab input (melee held)
on Nero's Streak, after the press-in-window row alone did not match a hold.

## Open

- **`.ctn` hot-swap vs level reload** as the default dev loop for cancels (the buffer swap is possible, see
  `RE/resource_loaders_writers.md`; decide once the runner exists).
- **Where `<attack>` (new `.atk` entries) lands**: phase C, after the codec; until then `<shell atk= entry=>` names an
  existing entry of an existing `.atk` (Gerb's default: `Collision\pl000` entry 14, the Dropkick).
- **Who writes the runner**: the recent mods (Gerb, GerbShell, DanteAirDodge, the SDK pieces) were written by Claude
  and built / tested by the user; the runner can go the same way, or stay the user's, as the project note said.
- **DT model**: whether Dante's Devil Trigger model needs the runtime bank loaded too (re_todo 18); the dodge worked
  in DT on the user's build, which suggests the body model is shared, but it is unverified.
