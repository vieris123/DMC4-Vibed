# Mass-Patch Plan: Redirect mpPlayer Resolution → Dispatcher

**Status:** DESIGN ONLY — nothing patched yet. The dispatcher itself (signature, index
selection, per-player table) is TBD; this document defines *how* to redirect existing sites to it
once it exists.

> **Scope carve-out:** the **damage/collision cluster does NOT go through the dispatcher.** Those
> handlers already receive the damage message (attacker + defender are call args / message fields),
> so the correct player is the *message sender/participant*, resolved locally. See
> [§ Damage / Collision — excluded from dispatcher](#damage--collision--excluded-from-dispatcher).
> Subtract these from every dispatcher site count below.

## The problem we're patching

Every player-resolution site ultimately executes the idiom:

```asm
mov rX, [sMediator::mpInstance]   ; load singleton  (rX ∈ {eax,ecx,edx,ebx,esi,edi,ebp})
mov rY, [rX+24h]                  ; rY = mpPlayer    (or cmp [rX+24h],0 for a null-check)
```

Measured against the live DB (2026-10-14; operand-based scan, see
[Corrections](#corrections-2026-10-14)):

| Route | Sites | Funcs | Shape |
|-------|-------|-------|-------|
| Inline `[mpInstance]`→`[+24h]` | **1019** | 753 | 7 load-reg forms × 52 deref-insn forms; 635 adjacent, rest up to 40 insns apart |
| Accessor `getPlayerPos` (`0x493240`) | 59 | 35 | uniform `call` |
| Accessor `getPlayerMat` (`0x493350`) | 45 | 24 | uniform `call` |
| **Distinct player-touching funcs** | — | **771** | |

The inline reads are the hard part: **there is no single byte signature** to find-and-replace.
The load register varies (eax 545, ecx 224, edx 135, edi 42, ebx 37, esi 29, ebp 7). The deref
always uses the load register as its base, but it appears as 52 distinct instruction forms
(`mov`/`cmp` with different destinations, `cmp [reg+24h],0` null-checks, `cmp [reg+24h],reg`).
So a literal "NOP these N bytes and write a call" sweep across 1019 sites is not viable — each site
is a different instruction pair at a different length and distance.

## Key insight: patch the field, not the 1019 sites

All 1019 inline sites and both accessors funnel through **one** memory access: `[mpInstance + 0x24]`.
That offset is the choke point. Three mechanisms can intercept it, in increasing order of how much
code we touch:

### Option 1 — Repoint the two accessors only (104 sites, 2 patches) — *partial*

`getPlayerPos`/`getPlayerMat` both begin `mov ecx,[ecx+24h]`. Replace each function's prologue with
a `jmp dispatcher_pos` / `jmp dispatcher_mat`. **2 patches** cover **104 call sites / 59 functions**.

- ✅ Trivial, reversible, no call-site edits.
- ❌ Covers only the 9% of sites that use accessors. The 1019 inline reads are untouched.
- **Use as:** the first, safe slice — and a template for the dispatcher's pos/mat ABI.

### Option 2 — Trampoline the accessors + convert inline sites to accessor calls — *full, invasive*

For every inline site, overwrite the `mov rX,[mpInstance]; mov rY,[rX+24h]` pair with a
`call get_player_into_rY` thunk. **Rejected as the primary plan:**

- The two instructions are adjacent at only 635/1019 sites; the rest are up to 40 instructions
  apart, some across an in-function `jmp` — can't assume a contiguous patch window.
- Variable total length (8–13 bytes) per site; many are too short to hold a 5-byte `call` + the
  register-move semantics without a per-site trampoline.
- 1019 bespoke trampolines = enormous surface, high regression risk, hard to audit.
- Only justifiable for sites the dispatcher must treat specially (e.g. the Nero-grab handlers).

### Option 3 — **Recommended: relocate `mpPlayer` behind the dispatcher via the field load** 

Keep the existing idiom intact and make `[mpInstance+0x24]` *itself* resolve through the
dispatcher. Two ways to do that, pick per how much we control the singleton:

**3a — Hook the writer, keep field as a cache.** Only **one** site writes a live `mpPlayer`:
`uPlayer::registerWithMediator` (`0x7A91C0`) does `mpInstance->mpPlayer = this`. If the dispatcher
owns player selection, redirect that single write (and the teardown `mov [edx+24h],0` in the spawn
state machine) so `+0x24` always holds "the player the dispatcher currently considers active for
this context." Every inline read then transparently gets the dispatcher's choice **with zero
read-site patches**. 
- ✅ Smallest patch set (1 writer + 1 teardown).
- ❌ Only works if "active player" is a *global* notion per frame — it is **not** for true
  splitscreen (camera A wants player 0 while camera B wants player 1 in the same frame). Good
  enough for "swap which single player everything sees" but not concurrent multi-view.

**3b — Trap the field via a guard page / indirection slot.** Make `+0x24` a pointer the dispatcher
updates per-consumer, or relocate the singleton so `+0x24` lands on an intercepted address. Heavy;
only if 3a's global-active-player model is insufficient and we still want to avoid read-site edits.

## Damage / Collision — excluded from dispatcher

Damage handling is **sender-aware by construction**, so it needs no global player lookup and no
dispatcher. The dispatcher answers "who is *the* player right now" — the wrong question for damage,
where the answer is "the player *in this exchange*."

**Why the message already carries the sender:** `uDamage::calc` (`0x51BE10`) is
`calc(this, param_1 = attacker, param_2 = defender)` — both combatants are explicit arguments. It is
called from **~46 `damageMessage` handlers** (one per enemy class: `uEm000Base`…`uEm035`,
`uPlayer::damageMessage`), each of which receives the damage message and forwards the participants.
**39 of those 46 handlers never read `mpPlayer` at all** — they are already correct. Only the
handlers that reach back to the global to *identify the attacking player* (e.g. to pick a Nero-vs-
Dante reaction animation, or spawn a hit-effect on the attacker) need changing, and the fix is local:
read the attacker from the message/`param_1` instead of `mpInstance->mpPlayer`.

### The 15 damage/collision functions that read the player

| Function | Addr | Player read is… | Fix |
|----------|------|-----------------|-----|
| `uDamage::calc` | `0x51BE10` | `mDevilTrg` gauge + `vtbl[134]` buster on attacker | use `param_1` (attacker) |
| `uDamage::calcEmPlCorrect` | `0x51BAB0` | `mPlayerID` + Nero `vtbl[182-184]` correction | use damage-ctx participant |
| `uEnemy::damageMessage4` | `0x7345B0` | `mPlayerID` → reaction anim | sender from message |
| `uEnemy::damageMessage5` | `0x7346B0` | `mPlayerID` → reaction anim | sender from message |
| `uEm011::damageMessage` | `0x5CBF50` | reads player + calls `calc` | sender from message |
| `uEm012::damageMessage3` | `0x5D90B0` | hit-effect on player + `vtbl[88]` | sender from message |
| `uEm025::damageMessage` | `0x6E4390` | reads player + calls `calc` | sender from message |
| `uEm036::damageMessage7` | `0x726B00` | reads player | sender from message |
| `sub_6B5AE0` | `0x6B5AE0` | reads player + calls `calc` | sender from message (verify) |
| `sub_864AF0` | `0x864AF0` | reads player + calls `calc` (stage obj) | sender from message (verify) |
| `sub_8701F0` | `0x8701F0` | reads player + calls `calc` (stage obj) | sender from message (verify) |
| `sub_886A90` | `0x886A90` | reads player + calls `calc` (stage obj) | sender from message (verify) |
| `sub_891B40` | `0x891B40` | reads player + calls `calc` (stage obj) | sender from message (verify) |
| `uCollisionMgr::move` | `0x50CC40` | `getPlayerMat` for lock-on push dir | **review-aggro**: use collision owner's lock-on target |
| `uEnemy::damageMessage7` | `0x735FB0` | player pos + caches as aggro target | **review-aggro**: attacker vs nearest player |

**Two are not pure sender reads** (`uCollisionMgr::move`, `uEnemy::damageMessage7`, tagged
`[MP/damage][review-aggro]`): they read the player as a **lock-on / aggro target**, not as the
damage participant. Those resolve from the unit's existing lock-on target, still not the dispatcher —
but confirm per-unit before patching.

All 15 carry an inline `[MP/damage]…` comment in the IDB as of this session. Excluding this cluster,
the dispatcher's job shrinks to the camera/HUD/state/enemy-targeting sites.

## Recommended layered plan (build order)

1. **Accessors first (Option 1).** Patch `getPlayerPos`/`getPlayerMat` prologues to
   `jmp` the dispatcher's pos/mat entry. Defines the dispatcher ABI on the simplest 104 sites and is
   independently testable (camera + enemy-grab matrix math run through these).
2. **Writer redirect (Option 3a).** Redirect the single `mpPlayer` write in
   `registerWithMediator` + the teardown zero-write. This makes all 1019 inline reads follow the
   dispatcher's global active-player choice for free. Validates the "swap active player" path.
3. **Targeted inline conversions (Option 2, surgical).** ONLY for sites that must diverge from the
   global active player in the same frame — primarily the **per-player camera** sites (160 sites /
   101 fns, every camera-class function that reads the player — see below) and the **Nero-grab
   handlers** (16 sites / 10 fns) which need a *specific* index/downcast, not "active player."
   For these, convert the inline idiom to a `call dispatcher_get(index)` via per-site trampolines.

This means the **bulk** (924 uncategorized sites) is handled by 2+2 patches (steps 1–2); the
~111 context-sensitive functions (176 sites) need individual trampolines (step 3). The camera share
grew from 15 to 101 functions once the 2026-10-14 SE→DX9 camera pass named the camera classes
(`RE/cam_se_dx9_map.md`): only 15 were deep-dived, the rest are classified by owning class.

## Mechanism details for the jump-to-dispatcher

- **x86, 32-bit, imagebase 0x400000.** A near `jmp rel32` / `call rel32` is 5 bytes
  (E9/E8 + rel32). The dispatcher must live where rel32 from each patch site can reach it (the whole
  .text fits in ±2GB, so any code-cave or appended section works).
- **Site instruction widths (from `ea_len`):** the site instruction (the `mov reg,[mpInstance]`
  load) is **5 bytes** only for `mov eax,…` (545 inline sites — the short `A1` encoding) and
  **6 bytes** for every other register, `ecx` included (474 sites — `8B /r` + disp32). The 104
  accessor `call`s are 5 bytes. All ≥5, so a `jmp rel32` always fits; the 6-byte sites leave 1
  trailing byte to `nop`. The **deref** (`deref_len`) is 3 bytes for `mov reg,[reg+24h]` and
  `cmp [reg+24h],reg` (912 sites), 4 for the `cmp [reg+24h],0` null-checks (106), and 7 for the
  single teardown write `mov [edx+24h],0` (`0x44BDFA`). No `movss` derefs exist. A per-site
  trampoline that rewrites the *load* must preserve `load_dst` (the register the original `mov`
  targeted) so the following deref still finds the pointer in the expected register.
- **dmc4_hook mapping:** each site is a mid-function hook
  `install_hook_offset(ea - 0x400000, hook, &detour, &jmp_ret, ea_len)`; the detour must replay the
  overwritten load. No site window overlaps an existing dmc4_hook hook or patch (checked
  2026-10-14), but five **deref** instructions are already hooked by mods:
  `Coop.cpp` `0x419189` (cam player pos), `0x419857` (lock-on cam), `0x508D82` (Nero HUD),
  `0x506CE4` (Dante HUD, commented out), and `CharSwitcher.cpp` `0x7A91CC`
  (`registerWithMediator` write — the step-2 target). Coordinate with those before patching.
- **Accessor patch (step 1):** overwrite byte 0 of `getPlayerPos`/`getPlayerMat`. `getPlayerPos`
  starts at `0x493240` with `mov ecx,[ecx+24h]` (3 bytes) — write `E9 <rel32>` (5 bytes), which
  spills 2 bytes into `test ecx,ecx`; fine, we never return into it. Dispatcher replicates the
  null-guard + the `result@<eax>`/`this@<ecx>` __usercall ABI and the field reads (+0x30 pos / +0x60
  mat) for the chosen player, then `retn`.
- **Code cave:** prefer appending a new section (e.g. `.disp`) over scavenging alignment padding —
  1019-site coverage will need real space for the dispatcher + per-site trampolines. A new PE section
  avoids cave-size limits and keeps the patch auditable.
- **Index source for step 3 trampolines:** the dispatcher needs to know *which* player a site wants.
  Candidates already available at those sites: camera owner index (give each `cCameraPlayer`/
  `uDevilCamera` a `mPlayerIndex`), and for Nero-grab the existing `strcmp "uPlayerNero"` /
  `vtbl[134]` test becomes "ask dispatcher for the Nero-slot player, null if none." TBD with the
  dispatcher design.

## Reversibility / safety

- Save original bytes of every patched site to `RE/patch_backups/` (addr → original bytes) before
  any write, so the whole set can be rolled back.
- Steps are independent and each is testable in isolation (1 → accessors, 2 → active-player swap,
  3 → per-view divergence). Do not proceed to a later step until the prior one is verified in-game.
- `idb_save` after each step; keep the patch list in this file updated with applied/not-applied.

## Authoritative call-site list (per-instruction)

`RE/mpplayer_call_sites.json` holds **every call site by precise instruction address** — the machine
input for patching. Generated from the live DB by `RE/scripts/build_mpplayer_sites.py`; regenerate
after any DB change. Each inline entry (accessor entries omit `deref_len`/`deref_dst`):

```json
{ "ea": "0x4FEDA3",        // site address: the mpInstance load (inline) or the call (accessor)
  "deref_ea": "0x4FEDBD",  // the [load_dst+24h] deref instruction (inline only; null for accessor)
  "fn": "0x4FEDA0", "fn_name": "sub_4FEDA0",
  "kind": "inline",                     // inline | accessor:getPlayer{Pos,Mat}
  "load_insn": "mov eax, sMediator__mpInstance",
  "deref_insn": "mov esi, [eax+24h]",
  "ea_len": 5, "load_dst": "eax",       // bytes of the site insn = dmc4_hook next_instruction_offset
  "deref_len": 3, "deref_dst": "esi",
  "category": "uncategorized",          // camera-per-player | nero-grab | damage-message-derivable
                                        //   | damage-review-aggro | uncategorized
  "class": "uCockpit", "class_src": "vtable",  // owning class (by name or vtable membership); null if unresolved
  "this_reg": "ecx", "cc": "thiscall", "arg0": "this" }  // register holding `this`; 'stack' or null
```

Totals: **1123 sites** = 1019 inline + 104 accessor. Categorized: camera 160, damage-derivable 19,
nero-grab 16, damage-review-aggro 4; the remaining **924 are `uncategorized`** (bulk
enemy/state/HUD that the writer-redirect step covers without per-site edits). Category, class, and
`this_reg` are per **function**; a function may own several sites (e.g. `cCameraPlayer::main01` = 4
inline sites), all listed individually with their own `ea`. A deref can be shared by two loads on
different paths (e.g. `0x45736C` from `0x457344` and `0x4572C5`); each load is its own site. Regenerate
with `RE/scripts/build_mpplayer_sites.py` (via ida-pro-mcp `py_exec_file`) after any DB change —
addresses/prototypes are live. `arg0` for untyped functions comes from Hex-Rays and can flip between
`a1` and `null` across runs; ignore that diff.

**Owning class** (`class`/`class_src`): 595/771 functions resolved — 527 by `Class::method` name,
54 by single-vtable membership, 14 `vtable-multi` (function shared across several class vtables,
`|`-joined). The rest (176 functions, 257 sites) are `sub_` helpers not in a named vftable.

**`this` register** (`this_reg`/`cc`): resolved from each function's prototype, falling back to a
Hex-Rays decompile. **This is NOT uniformly ecx** — the distribution across the 1123 sites is
`ecx` 394, `eax` 248, `stack` 246, `esi` 130, `edi` 73, `edx` 13, `ebx` 3, `null` 16. A trampoline
that assumes `this` in `ecx` would corrupt the ~65% of sites where it isn't
(`__usercall`/`__stdcall`/`__userpurge` functions pass `this` in eax/esi/edi/edx or on the stack).
`stack` means `this` is a stack argument (`[esp+N]`), not a register — those need the offset read
from the frame, not a register copy. `cc` records the convention so the trampoline can pick the
right retrieval per site. The 16 `null` sites (15 functions, 5 of them in `uPlayerDanteBoss` /
`uPlayerDanteBossMeleeCancel`; argless prototypes such as `uPlayer *()` report `cc: "unknown"`) need manual typing before
patching.

## Corrections (2026-10-14)

The earlier inventory (1047 sites on 2026-07-09, 1048 on 2026-10-05) came from a **text** match on
`+24h` within 6 instructions of the load. Verified against the live DB, that produced:

- **16 non-player records**, now removed: `[esp+24h+var]` stack slots after an mpInstance
  load (or null-check) whose value never reaches `+24h` (`0x52ADA9`, `0x52ADB6`, `0x52ADC1`,
  `0x57007D`, `0x5AD521`, `0x6DC549`, `0x77E2EC`, `0x77E359`, `0x790C04`, `0x841598` — most just
  pass sMediator to one of its methods);
  `[vtbl+24h]` virtual calls on another object (`0x4043C9`, `0x408FEC`); `+24h` of the matrix
  returned by `getPlayerMat` (`0x50D048`); camera `+24h` writes after reading sMediator `+0xD0`
  (`0x73FA68`, `0x74BFD8`, `0x83F1F8`).
- **1 mis-paired record:** `0x44CE94` jumps over the deref it was paired with.
- **1 wrong deref:** `0x51BAC1` recorded `mov [esi+24h],0` (`0x51BACE`); the real deref is
  `mov edi,[eax+24h]` at `0x51BAD5`. This was the second "teardown write" — only one exists.
- **92 missed sites:** derefs more than 6 instructions after the load, reached through an
  in-function `jmp`, or in functions defined after the last run (e.g. `uDamage::calc` `0x51C0F4`,
  `cCameraPlayer::main` `0x417A24`, `sub_713530`).
- **Wrong encoding claim:** `mov ecx,[abs]` is 6 bytes (`8B 0D` + disp32), not 5; only `eax` has the
  5-byte `A1` form.

The generator now matches the deref by operand (base register must still hold the loaded pointer),
follows in-function jumps, and scans up to 40 instructions. Every one of the 1123 sites was checked
in IDA for instruction head, length, owning function, and unpatched bytes. The pre-fix file is kept
as `RE/mpplayer_call_sites.orig.json`.

## Site inventories (already enumerated this session)

- Inline reader functions (753) and 1019 sites: regenerated on demand by
  `RE/scripts/build_mpplayer_sites.py`.
- Accessor call sites: `getPlayerPos` 59, `getPlayerMat` 45.
- Camera sites needing step-3 treatment: **160 sites / 101 fns** (151 inline, 9 accessor), category
  `camera-per-player` = the 15 deep-dived fns (`[MP/camera]` comments, *Camera Subsystem* section of
  `player_instance_findings.md`) plus every function owned by a camera class:

  | Owner | Sites | Fns |
  |-------|------:|----:|
  | `uCameraBoss` + `uCameraBossDante`/`Em0xx` | 99 | 50 |
  | `cCameraPlayer` | 34 | 31 |
  | `cCameraRail` / `Em025` / `Em026` / `cCameraPan` | 18 | 12 |
  | `uBossCameraTest` | 4 | 4 |
  | `uCameraCtrl` | 4 | 3 |
  | `uDevilCamera` | 1 | 1 |

  `this` is in `ecx` at only 26 of the 160 (eax 43, esi 41, stack 31, edi 16) — the camera
  trampolines must read `this_reg` per site. Only the 15 deep-dived functions have been audited by
  hand; the other 86 are categorized by class and still need a per-function read before patching.
- Nero-grab handlers needing step-3 treatment: 10 fns — see *Enemy Grab-Interaction Tables* section.
- Cached-member writers (set once in `init()`): 14 classes — see *Cached mpPlayer Members*; these
  are a separate hazard (stale pointer) and are fixed at the writer, like step 2, not the readers.
