# MoveDef XML schema, draft v0.1 (2026-10-17)

Not implemented. The subset of XML used: elements, attributes, comments. No entities, mixed content or namespaces,
so a small reader can parse it. Numbers accept decimal or `0x` hex. Frames are **motion frames of the referenced
block** at 60 fps (what `Motion.mFrame` counts), as floats.

## `<move>` (root)

| Attribute | Meaning |
|---|---|
| `name` | file-unique name (also the default log label) |
| `character` | `pl000` (Nero) / `pl006` (Dante), or both space-separated (`"pl000 pl006"`, a shared move in `movedef\common\`): picks the LMT bank mapping, `.ctn`, `Collision\` files |
| `id` | `atckId`: an existing one (the move is a tweak / overlay) or one from the character's reserved block in `_character.xml` |
| `body` | `lower` (default) / `upper` / `both` |
| `version` | schema version, `1` |

Children, each at most once unless noted: `<lmt>`, `<table>`, `<routine>` or `<stages>`, `<timeline>` (several).

## `<lmt bank= path= [coat_pl000= coat_pl006=]/>` (a motion bank loaded at runtime)

`<lmt bank="14" path="motion\common\wallrun" coat_pl000="motion\common\wallrun_pl000_03" coat_pl006="motion\common\wallrun_pl006_03"/>`

The DLL loads `path` into `bank` of the body model and the matching `coat_*` file into the coat model's `bank`
(`uModel::setMotionList`, see `design.md` section 5), after the character's `setup`. `bank` must be one of the free
banks **10-14** (the setup banks are Nero 0 / 1 / 3 / 5, Dante 0-9; 15 is Nero's Buster bank); the DLL refuses
others. Motions of the move are then `bank:slot`. Albam checks that the file exists and that every referenced slot
is a non-empty block. One body LMT serves both characters (shared body joint numbers); coats need one file each.

## `<table>` (the `kAtckDefTbl` row: input, string position, conditions; applied by the DLL)

The game picks a move by walking the character's row list in order (`uPlayer::checkAtck`): a row matches when its
input is present, its conditions hold, and, while an attack is playing, its cancel entries pass. The real row layout
(SE PDB) and the walk are in `RE/player_move_pipeline.md`, "Input commands and attack strings".

```xml
<table attr="command" insert_before="0x0C" start="true" cancel="true" repeat="false"
       weapon="RedQueen" style="-1" etc="0" air="ground">
  <input command="CMD_LOCK_FLEVER_SHORT"/>        <!-- how it is triggered -->
  <follows move="0x1C" window="C_NORM0"/>         <!-- string step: after move 0x1C, once its C_NORM0 window is open -->
  <window category="C_ALL" or="true"/>            <!-- standalone cancel window -->
</table>
```

| Attribute | Row field | Values |
|---|---|---|
| `attr` | `atckAttr` | `melee` (0 SHORT: the melee button), `gun` (1 LONG), `command` (2: needs `<input>`), `proper` (4) |
| `insert_before` | position | the vanilla `atckId` this row goes before (earlier rows win) |
| `start` / `cancel` / `repeat` | `atckInfo` bits 1 / 2 / 4 | may start from neutral / may be entered by cancelling an attack / may chain into itself |
| `weapon` | `atckConditionWp` | -1 any, or `uPlWeapon::ID` number or name (RedQueen 0 ... Rebellion 4, Gilgamesh 5, Lucifer 6, Coyote 7, Pandora 8, EbonyIvory 9) |
| `style` | `atckConditionStyle` | -1 any, 0 SM, 1 GS, 2 TS, 3 RG, 4 DS |
| `etc` | `atckConditionEtc` | extra condition (`checkAtckEtc`; DT states) |
| `air` | `atckAs` | `ground` 1, `air` 2, `both` 3, `fly` 0x40 |

Children:

| Element | Compiles to |
|---|---|
| `<input command="CMD_..."/>` | `atckCommand` 1 + `atckCommandNo` = the `CMD_ID` (SE enum name or number; DX9 has ids 0x00-0x54). Omitted = the plain button of `attr`. |
| `<input mash="N"/>` | `atckCommand` 2 + the mash table index |
| `<follows move= window= [or="true"]/>` | two `cancelId` entries: `cmdId` = the previous `atckId` (string link) and `cmdNo` = the `CANCEL_NO` window that must be open (`or` sets `cmdOr`) |
| `<window category= [or="true"]/>` | one `cmdNo` entry (a window with no particular predecessor) |

Limits: five `cancelId` entries in total (each `<follows>` uses two unless its `window` is omitted); the DLL refuses
more. `window` names are the `CANCEL_NO` categories the `.ctn` scripts open (`<cancel>` on the predecessor's
timeline). Omitted `<table>` = the move only overlays an existing row (`id` must be vanilla).

**Custom input sequences** (`<command>` in `_character.xml`: steps of `btn` / `lever` / `charge` / `mash` with
timers, like `uPlayer::commandTbl`) are phase 3: DX9 runs a fixed 85-entry table and three flag words, so new
`CMD_ID`s need the DLL to extend the table and the flag storage.

## `<routine native="0xADDR"/>`

Use a native state function. Mutually exclusive with `<stages>`.

## `<stages>` / `<stage>` / `<next>` (the scripted routine)

`<stage name= motion="bank:slot" speed="1.0" start="0" interp="3" loop="false" spawn="none|mirror" ctn="bank:slot">` requests that motion on entry
(`ctn=` borrows that vanilla `.ctn` script's cancels / triggers for this motion through `mMotionSetCharTblParam`; required for
motions in a runtime bank, where no `.ctn` script exists, optional elsewhere)
(`spawn="mirror"` = also send it to the Devil Bringer unit the way `setRedQueenMotion` does; Nero only)
(`requestSetMotion`: motion_no, attr word, speed, start frame, interpolation frames). Children `<next on= to=>`
are checked each tick in order:

| `on` | Extra attributes | Fires when |
|---|---|---|
| `motion_end` | | `Motion.mState` bit 0 |
| `contact` | `byte` (`free0` / `free1` / `free2`), `value` | that contact byte equals `value` (set by the `.ctn` `<trigger>`) |
| `frame` | `frame` | `mFrame >= frame` |
| `input` | `button`, `held="true"` | the button is pressed / held |
| `always` | | immediately |

`to="exit"` leaves through the neutral transition. `<physics frame="0" .../>` and `<native_call fn= frame=/>`
may sit inside a stage as entry actions (frame 0) or on the runtime timeline.

## `<timeline motion="bank:slot">` (compiled by Albam)

Several per move, one per motion block the move uses. Children:

| Element | Attributes | Compiles to |
|---|---|---|
| `<cancel>` | `category` (`C_NORM0` / `C_NORM1` / `C_NORM2` / `C_COMMAND` / `C_JUMP` / `C_CHOUHATSU` / `C_GUN` / `C_ALL`), `kind` (`open` = 0x10: the next attack starts at once (`mStat` 2); `buffer` = 0x30: the input is taken and the attack reserved until the move allows it (`mStat` 1, `mYoyakuAtckId`); `close` = 0x20), `from`, `to` (optional: close at `to`). The first `<cancel>` of an attack-row move also sets the cancel gate `mIsCancelCehckEnable` (design.md section 5) | `.ctn` wait + contact[1] byte: byte 0 C_NORM0 (nibble 1 / 2 = C_NORM1 / 2), 1 C_COMMAND, 2 C_JUMP, 3 C_CHOUHATSU, 4 C_GUN, 5 C_ALL (the vanilla files use nibble 0 only) |
| `<trigger>` | `byte` (`free0` / `free1` / `free2`), `value`, `frame` | `.ctn` contact[0] byte |
| `<vibrate>` | `pad` (1-based id, 0xFF stop, 0xFE hold), `cam` (`uDevilCamera::vibReq` id + 1), `frame` | `.ctn` contact[0] padVib / camVib |
| `<hitbox>` | `col_group`, `atk` (entry index or `mAsName`), `from`, `to`, `pair` (optional) | `.idx` row (0, group, atk, pair, first) + one slot bit of LMT event table 1 on `[from, to)` |
| `<sound>` | `msse` (rMotionSe entry), `frame`, `to` (optional) | one slot bit of LMT event table 2 |
| `<attack>` | `name`, and any `kAttackStatus` field | a new `.atk` entry (phase 3) |

Limits: 8 slot bits per table per block (the `events_params` arrays); Albam refuses more. Runs start at frame 0
and cover the block (`_serialize_events`).

## `<timeline motion="bank:slot" runtime="true">` (applied by dmc4_hook)

| Element | Attributes |
|---|---|
| `<effect>` | `efl` (game path, no extension) or `list` + `index` (the 0x39-list table, `RE/effect_list_table.md`), `joint` (name, MT joint number, or `weapon` = the held weapon; omitted = the actor), `group` / `material` (spawn masks: -1 default, `material="ground"` = `uPlayer::getEfctMtrlFlg()`), `unitline` (0x14 default), `type` / `id` (`uPlayer::setEffect` registration; `id` lets a later `<finish id=>` end it), `frame`, `repeat` (`once` default / `loop`), `stationary="true"`, `if` (a named runtime condition registered in dmc4_hook, e.g. `exceed>=1`) |
| `<se>` | `id`, `frame` (direct `requestSe`) |
| `<physics>` | `frame`, `vel="x,y,z"`, `gravity`, `inertia`, `weight` (each optional) |
| `<native_call>` | `fn` (a name registered in dmc4_hook code), `frame` |
| `<native_motion_override>` | `from`, `to` (motion numbers), `speed`, `start` |

Firing rule: `prev_frame < frame <= cur_frame` once per motion instance; `repeat="loop"` re-arms when the frame
wraps within the same motion.

## `_character.xml`

`<character id="pl000" ctn="chartbl\pl000" collision="Collision\pl000" lmt="motion\pl000\pl000_%02d">` with
`<ids from="0x80" to="0xBF"/>` (the reserved `atckId` block), `<banks setup="0,1,3,5" free="10-14" grab="15"/>` (Dante:
`setup="0-9"`, no grab bank) so a move's `<lmt bank=>` can be validated, and `<bank n="1" lmt="..."/>` overrides if needed.

## v0.2 additions (2026-10-24, from the hand-coded moves; see design.md 5b)

Runtime-side elements that have no compiled counterpart. Attribute defaults are the values Gerb / DanteAirDodge
settled on.

### `<lmt>` per player object, `<stage>` extras
`<lmt bank="13" path="motion\pl000\gerb"/>` is loaded for **every** uPlayer object that enters the move (a stage switch
makes a new one); the move refuses to start (neutral air transition) until the bank reads back non-empty. `<stage>` gains
`ctn="bank:slot"` (already in v0.1: the borrowed vanilla script), `attr="null_trans_off"` (the request's attribute word),
`land="exit"` (leave by `setActionLand` when `vel.y <= 0` and the collision manager reports ground) and `status="jump"`
(set AST_JUMP, clear AST_STAND, so the air rules apply).

### `<launch frame= speed= rise= gravity= max_fall= face="true|false" direction="stick|facing|fixed" side_angle= />`
Inside a `<stage>`: at `frame` of the stage's motion, velocity = direction x `speed` + up x `rise`; then `gravity` per
tick, capped at `-max_fall`. `direction`: `stick` = the stick relative to the lock-on facing, quantised to
forward / back / left / right by `side_angle` (Gerb), with `slots="fwd,down,back,left,right,up"` on the `<stage>`
naming the LMT slot per direction; `facing`; or `fixed="x,y,z"`. `face="true"` turns the player toward the direction.
Also keeps `mMoveVel` / `mJumpMoveAng` in step and clears the additive speed (runner rule).

### `<effect>` extras
`stay="true"` = `SetEffectStay` (list + index, the air hike's effect: Nero 1 / 0x28, Dante 2 / 0x14) at the player's
position with the player's basis leaned `tilt` degrees toward the launch direction (`roll="180"` turns it upside down,
the dive). `<se id="40"/>` plays through the player's SE resource. Both default to the launch frame when inside `<launch>`.

### `<command name= condition="lockon|dash|laser|none" active="1">` (D17)
Children in order: `<btn id="melee|gun|jump|lockon|style|0x.." mode="trg|rel|on" timer="0"/>`, `<lever dir="centred|forward|back|any"
mode="target45|target70|screen" timer="15"/>`. Compiles to an `input_commands::Command`; the runner assigns a free
`mCmdFlag` bit (85-95) and `<input command="name"/>` on the row refers to it. Optional `predicate="stick_sideways"`
names a runner-side check evaluated each tick (the dodge's left / right test); the list of predicates is code.

### `<shell>` (D18), inside a `<stage>` or `<launch>`
```xml
<shell atk="Collision\pl000" entry="14" kind="1" vsattr="0" unitline="0x12"
       shape="capsule" radius="60" length="120" height="80" life="90"
       knock="direction|away|facing" knock_up="4" knock_down="5"
       damage_type="-1" type_b="-1" level_i="-1" level_b="-1" blown_angle="-1" end_on_hit="false"/>
```
One capsule from the player's position + `height` along the launch direction, `kAttackStatus` from `atk` entry `entry`
with any listed override (-1 = keep), kind / vs-attr per `cCollisionGroup::setAttr`'s table, alive while the stage is
airborne or for `life` ticks, following the owner. `knock`: `direction` = `mBlownAngleType` 1 with the shell's yaw on the
launch direction, `facing` = 1 with the player's yaw, `away` = 0 (from the player). `knock_up` / `knock_down` = the type-B
reaction for a vertical launch (upper / ground).

### Runner defaults that need an attribute only to turn off (D20)
`<press eat="true"/>` (eat the starting button's trigger and the C_JUMP reserve until released), `<enemy_step from="0"/>`
(call `checkEmJumpBegin` while the gate is off), `<watchdog ticks="60"/>`, `<cancel_gate frame=>` (defaults to the first
`<cancel>` frame).

### `<routine native="0x..">` with runtime `<timeline>` (phase B)
Unchanged from v0.1; the runner opens the timeline instance at the motion request and installs a synthesised script
when the compiled-style `<timeline>` has cancels, so the `.ctn` compile is optional for vanilla moves too (D16).

## Implemented by dmc4_hook `MoveDef` (2026-10-24; `mods/XmlMove.cpp` parses, `mods/MoveDef.cpp` runs)

The runner reads `nativePC\movedef\*.xml` at start-up. What it understands today, with the defaults it applies; anything
else in a file is ignored with a log line.

```xml
<move name="dante_air_dodge" character="pl006" id="0x6F" version="2">
  <table attr="command" level="7" start="true" cancel="false" repeat="false" weapon="-1" style="-1" etc="0" air="air">
    <input command="dodge"/>                     <!-- a <command> name (this file or a shared one), a CMD_ID number, or omitted -->
    <follows move="other_move" window="C_ALL" or="false"/>   <!-- string step: after that move (name or vanilla id) -->
    <window category="C_ALL" or="true"/>         <!-- a window that must be open; default when neither: C_NORM0, or C_ALL -->
  </table>
  <command name="dodge" condition="lockon" predicate="stick_sideways" active="1">   <!-- the move's own: bit 85-95 -->
    <btn id="jump" mode="trg" timer="0"/>  <lever dir="back" mode="target45" timer="15"/>
  </command>
  <lmt bank="12" path="motion\pl006\airdodge"/>
  <stage name="dodge" ctn="0:5" attr="null_trans_off" interp="4" start="0" speed="1" status="jump" land="exit"
         cancel_frame="10" enemy_step="true" eat_press="jump" watchdog="60" motion="12:0">
    <slot dir="right" block="1"/>  <slot dir="left" block="0"/>          <!-- blocks of <lmt bank>; without slots: motion= -->
    <cancel frame="26" kind="buffer" categories="C_NORM0 C_JUMP"/>      <!-- instead of / besides cancel_frame -->
    <launch frame="0" direction="stick" speed="20" rise="8" gravity="-1.1" max_fall="30" side_angle="50" face="false">
      <effect list="2" index="0x14" tilt="45" roll="0"/>  <se id="40"/>
    </launch>
    <air_jump cost="1" required="true" suppress_air_hike="true" per_air="0"/>
  </stage>
</move>
```

- **Banks**: pick one no other mod uses on that character (the C++ mods' banks are config values: Gerb 13 by default, the
  dodge 12 on Dante, the wall run 14); the runner refuses a bank that already holds another LMT and says so in the log,
  since the loader would otherwise play that file's blocks under your slot numbers (the T-pose of 2026-10-24).
- **Ids**: Nero >= 0x34, Dante >= 0x6C, unique across the loaded files; the row goes to the front of the character's table
  (`MoveTable::add_row`), the id into `sdk/MoveRegistry`. One `<stage>` per move for now (the first is run).
- **`<table>`**: `attr` melee 0 / gun 1 / command 2 / proper 4; `start` / `cancel` / `repeat` = `atckInfo` bits 1 / 2 / 4
  (defaults 1, 0, 0: the hand-coded rows' word); `air` ground 1 / air 2 / both 3 / fly 0x40; `cancel_words="w0,w1,w2,w3,w4"`
  overrides the five `cancelId` words; else `<follows>` / `<window>` are encoded as `yCancelInfo` words (`cmdId` word with the
  previous id, `cmdNo` word with the window; `or` sets `cmdOr`; five words at most, a `<follows>` with a window takes two);
  else the default `{1, 0, 0, 0, 0x07000005}`.
- **Chaining between files (D22)**: `<follows move="name">` is resolved to that file's id when the folder loads (every file is
  parsed first, so order doesn't matter); a number is a vanilla `atckId`. The predecessor opens the window with its own
  `<cancel>` / `cancel_frame`, the game's `checkAtck` does the rest. Shared commands: a `<commands character="pl006">` file
  (or a move file's second and later `<command>`s) defines commands any move of that character can name in `<input>`;
  they are always on while the mod is, and their only predicate is `stick_sideways` with the command's own `side_angle`.
- **`<command>`**: `condition` none / lockon / dash / laser; `predicate` `stick_sideways` (a move's own command also enforces
  its `<air_jump>` budget); steps `<btn id= mode=trg|rel|on timer=>` (ids melee / gun / jump / lockon / style or a number) and
  `<lever dir=centred|forward|back|any mode=target45|target70|screen timer=>`. One free `mCmdFlag` bit each, 11 in the game.
- **`<stage>`**: `ctn` borrowed vanilla script (bank:slot), `attr` null_trans_off (1) or a number, `interp` / `start` / `speed`
  the request's, `status="jump"` sets AST_JUMP at the launch, `land="exit"` leaves by `setActionLand` on ground contact
  (`none` keeps the move), `cancel_frame` opens every window at that frame (the gate opens with the first window),
  `enemy_step` calls `checkEmJumpBegin` while the gate is off, `eat_press` eats that button's trigger (and the C_JUMP
  reserve for jump) until released once after entry, `watchdog` ticks without motion progress before a bail-out.
- **`<slot dir= block=>`**: the direction (`forward` / `back` / `left` / `right` / `up` / `down`) picked from the stick
  relative to the facing (`side_angle` splits sideways from along), among the slots the stage has; no stick = forward.
- **`<launch>`**: at `frame`, velocity = direction x `speed` + up x `rise`; `gravity` per tick to `-max_fall`; `face` turns
  the player; `<effect list= index= tilt= roll=>` is `SetEffectStay` with the player's basis leaned toward the launch
  (`roll` about forward, 180 = upside down); `<se id=>` through the player's SE resource.
- **`<air_jump>`**: `cost` added to `mWJumpCnt` at entry, `required` refuses the start with no air jump left,
  `suppress_air_hike` makes the base `uPlayer::checkWJumpBegin` return 0 for this move's press, `per_air` caps starts
  between landings.
- **Reload** (panel button) re-reads the loaded moves' files: stages, slots, cancels, launch, command steps, shared command
  steps. The row's words, a new file, a new command or a changed character need a restart.
- **`<trigger byte="free0" value="2" frame="20"/>`** (in a `<stage>`): a contact byte of set 0 in the synthesised script
  (atck / free2 / camVib / free1 / free0 / padVib), the way vanilla scripts arm their own stages; read back by `<next byte=>`.
- **`<next to="exit|move:name" .../>`** (in a `<stage>`, checked in order every tick after entry): fires when every condition
  given holds: `on="motion_end"` (`mMotionFrameEnd[0]`), `on="landing"`, `on="always"`, `frame="N"`, `byte="free0" value="2"`
  (the trigger byte), `button="melee" held="true"` (held, else pressed this tick), `stick="neutral"`. `exit` leaves through
  the neutral transition; a move name (same character, loaded) hands off the Stinger way: `setActionAtck(id, both halves)`
  and that move's entry in the same tick. Million Stab after Stinger in these terms: the Stinger file's finish stage has
  `<trigger byte="free0" value="2" frame="N"/>` and `<next byte="free0" value="2" button="melee" held="true" stick="neutral"
  to="move:million_stab"/>`.
- **Mash and stationary moves** (2026-10-24, the Million Stab example): `<next button="melee" idle="18" .../>` fires when that
  button has not been pressed for `idle` ticks (the runner counts melee / gun / jump / style presses per player; the
  starting press counts); `<stage stop="true">` zeroes velocity and acceleration at entry; a move **without `<table>`** is
  hand-off only (no row, no input of its own, reached by another move's `<next to=>`; it keeps its id for the dispatch);
  `to="exit"` and the watchdogs leave through `setActionFootwork(10, 1)` on the ground and the neutral air transition in the air.
  `land="exit"` only applies to ballistic (`<launch>`) stages.
- **Overlays on vanilla moves** (2026-10-24, phase B's first piece): `<move ... id="28" overlay="true">` (or with a
  `<routine native/>` child) names a VANILLA atckId (`ids="28 29"` for a move with several rows: Nero's Streak runs as 28
  or 29); it gets no row, bank or registry entry. Its stage's `<next>`s are
  evaluated every tick the vanilla move runs, before the game's own state function (the dispatch detours call
  `move_registry::vanilla_tick`), on the stage's `motion=` only when given. A hand-off (`to="move:name"`) runs the
  other move's entry in that tick and skips the vanilla function for it, as the Stinger does for Million Stab. `exit`
  works too. Example: `examples/nero_streak_hold.xml` (melee held + stick centred + `free1 == 2` in Streak's finish ->
  Nero's Million Stab).
- **The runtime timeline** (2026-10-24): `<effect frame= list= index= | efl= joint="self|weapon" group="-1" material="-1|ground"
  unitline="0x14" type="0" id="-1" repeat="once|loop"/>`, `<se frame= id=/>`, `<kill_effect frame= id=/>`, `<finish_effect frame=
  id=/>` inside a `<stage>`: fired once per entry when the motion frame passes `frame` (prev < frame <= cur; the first tick
  after the request fires everything at or before the start frame; `repeat="loop"` re-arms when a looping block wraps). An
  effect by `list` / `index` is `sDevil4Effect::setEffectConst` on the player or the held weapon unit with the masks
  (`material="ground"` = the surface under the player), by `efl` the path spawner; both are registered on the player
  (`uPlayer::setEffect` type / id) so a later `<kill_effect>` / `<finish_effect>` can end them by id. Works on overlays
  too (by the vanilla motion's frame; the fired set resets when the motion changes). Example: the Million Stab dust (list 2
  index 0xB, id 4) in the loop, killed by the finisher, which fires the burst (0xC).
- Not yet: more than one stage per file (chain files instead), `<shell>`, the synthesised script on vanilla motions, the `.ctn`
  compile.
