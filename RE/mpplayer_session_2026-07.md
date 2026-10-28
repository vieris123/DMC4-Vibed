# mpPlayer Reference Audit — Session Summary (2026-06-28 → 07-09)

Working session on the project goal: **decouple `sMediator`'s per-player members to enable
multiplayer.** This doc is the index/changelog for the artifacts produced; the detail lives in the
linked files.

## What was done

1. **Re-inventoried every `sMediator::mpPlayer` (mpInstance+0x24) reference** against the live DB and
   corrected the stale figures in the prior report.
2. **Deep-dived the camera cluster** (15 functions) — all per-player, 3 Nero-exclusive hazards.
3. **Mapped the enemy grab-interaction tables** → 10 Nero-exclusive `uPlayerNero`-downcast handlers
   (4 table-dispatched, 6 direct-call), plus the 48-slot `uEm000Base` grab-callback table.
4. **Separated the damage/collision cluster** (15 functions) as **not needing the dispatcher** —
   those handlers already receive the attacker/defender in the damage message.
5. **Designed the mass-patch strategy** (jump-to-dispatcher) — not executed, design only.
6. **Emitted an authoritative per-call-site JSON** with, for each site: precise address,
   owning function+class, the register holding `this` (and CC), category, kind, and instruction
   lengths / destination registers for patching. (1047 sites at the time; see the 2026-10-14
   correction below — the current figure is 1123.)

> **Correction (2026-10-14).** The July inventory matched `+24h` as disassembly text within 6
> instructions of the load. Re-verified against the live DB, it included 16 non-player records
> (stack slots, `[vtbl+24h]` calls, a `getPlayerMat` result), one mis-paired load, and one wrong deref
> (`0x51BAC1`), and it missed 92 real sites. Its "5-byte `mov eax/ecx`" claim was also wrong — only
> `mov eax` is 5 bytes. The generator now matches by operand; figures below are the corrected ones.
> Details: *Corrections (2026-10-14)* in [mpplayer_dispatcher_patch_plan.md](mpplayer_dispatcher_patch_plan.md).

## Key numbers (live DB, corrected 2026-10-14)

| Metric | Value |
|--------|-------|
| Raw xrefs to `sMediator::mpInstance` | 2721 (2026-07-09 count; not re-measured) |
| Player-resolution call sites | **1123** (1019 inline + 104 accessor) — was reported as 1047 |
| Distinct player-touching functions | 771 (753 inline) — was 724 (707) |
| `getPlayerPos` / `getPlayerMat` call sites | 59 / 45 (unchanged) |
| Categorized: camera / damage-derivable / nero-grab / damage-review-aggro | 160 / 19 / 16 / 4 — was 19 / 17 / 14 / 5 (camera now = every camera-class function, after the 2026-10-14 SE→DX9 camera pass) |
| `this` register: ecx / eax / stack / esi / edi / edx / ebx / untyped | 394 / 248 / 246 / 130 / 73 / 13 / 3 / 16 |
| Site instr width: 5-byte (`mov eax` + calls) / 6-byte (other regs, incl. `ecx`) | 649 / 474 (no 7-byte sites) |

## Corrections to the prior report

- "685+ functions / 731 sites" was stale → **707 functions / 942 sites** at the same 6-insn window
  (more code defined since). Now regenerable, not a frozen number. *(2026-10-14: the 6-insn text
  scan itself was flawed; the operand-based count is 753 functions / 1019 inline sites.)*
- Several per-class site counts had folded in indirect + cached reads; corrected to strict
  direct-deref counts (e.g. `sGameState` 75→12, `uEm000Base` 28→14, `cCameraPlayer` 17→14).
- `getPlayerPos`/`getPlayerMat` **site** counts stable (±1); **caller** counts differed only due to
  a stricter counting method.

## Findings that change the refactor

- **`this` is NOT uniformly `ecx`.** ~65% of sites pass `this` in eax/esi/edi/edx or on the stack
  (`__usercall`/`__stdcall`/`__userpurge`). Any trampoline assuming `ecx` corrupts them.
- **Damage is sender-aware by construction.** `uDamage::calc(this, attacker, defender)` takes both
  combatants as args; **39 of ~46 `damageMessage` handlers never read `mpPlayer` at all.** The 15
  that do only reach back to *identify the attacker* — fix locally from the message, no dispatcher.
- **`mPlayerID` 0 = Dante, 1 = Nero** (confirmed via `moveRightStickAxisY` save-slot selection).
- **Nero-grab handlers resolve `uPlayerNero*` by runtime `strcmp(getDTI()->name,"uPlayerNero")`**,
  not a cached pointer — 10 handlers, all needing index+downcast with a Dante null-guard in MP.
- The 5 stage-hazard damage callers are `uStageSetBreak/ItemBox/GodHand/Switch` — they deal damage
  *to* the player (player is defender), consistent with the message-derivable model.

## Artifacts (all under `RE/`)

| File | Contents |
|------|----------|
| [player_instance_findings.md](player_instance_findings.md) | Master report: consumer surface, camera deep-dive, grab tables, accessors, cached members, struct layout |
| [mpplayer_dispatcher_patch_plan.md](mpplayer_dispatcher_patch_plan.md) | Mass-patch strategy (design only); damage/collision carve-out; JSON schema; mechanism/widths |
| [mpplayer_call_sites.json](mpplayer_call_sites.json) | **Authoritative** per-call-site table (1123 sites, regenerated 2026-10-14) — the machine input for patching; pre-correction copy in `mpplayer_call_sites.orig.json` |
| [scripts/build_mpplayer_sites.py](scripts/build_mpplayer_sites.py) | Regenerates the JSON from the live DB (via ida-pro-mcp `py_exec_file`) |
| [scripts/README.md](scripts/README.md) | How to run / regenerate, expected baseline, gotchas |

## IDB annotations added this session

Inline comments (prefix → tag): camera 14 sites `[MP/camera]`, Nero-grab 10 handlers
`[MP/grab][Nero]`, damage/collision 15 sites `[MP/damage]` (with `[message-derivable]` /
`[review-aggro]` sub-tags). IDB saved.

## Open items / next steps

- **Decide the dispatcher's player-selection model** — global "active player" (cheap; step-2
  writer-redirect covers ~924 uncategorized sites for free) vs. true concurrent multi-view (requires
  per-site index trampolines for the camera + grab clusters).
- **16 untyped sites** (`this_reg: null`, 15 functions) need manual typing before they can be trampolined.
- **246 stack-passed-`this` sites**: capture the exact `[esp+N]` offset per site if step-3
  trampolines end up covering any of them (not yet extracted).
- Audit remaining `damage-review-aggro` pair per-unit (attacker vs nearest/lock-on target).
