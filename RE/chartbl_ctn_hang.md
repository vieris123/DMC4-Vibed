# DMC4 DX9 character tables (`.ctn`, rCharTbl): the infinite loop and how to fix it

Read-only RE of `DevilMayCry4_DX9.exe` (IDB on port 13337), 2026-10-17. Nothing in the IDB was changed.
Confidence: **H** = read directly from code/disasm, **M** = inferred from code plus file data, **L** = guess.
Files checked: `arctool\uPlayerNero-vanilla\chartbl\pl000.ctn`, `uPlayerNero-SE\chartbl\pl000.ctn` (an SE-era
copy, same layout), `uPlayerDante-vanilla` / `Anima\uPlayerDante` / `em_dante\chartbl\pl006.ctn` (identical), and
the LMTs next to them. Addresses are DX9 only.

`.ctn` is class **rCharTbl** (native extension `bin`, arc type `0x19DDF06A`). The `.plp` files in the same
`chartbl\` folders are **rPlParamTbl**, a different class. `cCharTblMgr` runs one small script per motion. The
script sets the player's contact / cancel bytes on given frames. **H**

## Summary

- `cCharTblMgr::update` loops until a script command ends the frame. On a byte that isn't a known opcode, the loop
  goes round again **without moving the cursor**, so the game hangs on that frame. **H**
- Neither lookup path checks anything: not the bank count, not the slot count, not a zero entry, not the buffer
  bounds. **H**
- A motion with no script sends the cursor onto bytes that aren't a script. In every case checked, an empty slot
  lands on an unknown opcode, which hangs. **H** (code) + **M** (file scan)
- In the vanilla files, empty `.ctn` slots match empty LMT blocks almost exactly. So the usual trigger is a mod
  **putting an animation into an empty LMT block** (or adding blocks past the table's end) without giving the
  `.ctn` a script for it. **M**
- Fixes: give every playable motion a script (data only), a 1-byte exe patch that turns the hang into "script ends",
  or a small code cave in `update` that rejects bad cursors. The cave is the complete fix. Details below.

## Functions

| Address | Name (IDB) | Role |
|---|---|---|
| 0x4659C0 | rCharTbl vtbl (load) | allocates `+0x50` bytes (16-aligned) at `+0x60`, reads the whole file there, sets `mpDataTop` `+0x64` = buffer + 4. No magic or size check. |
| 0x42BA50 | `cCharTblMgr::set` | picks the script for the current motion (normal motions) |
| 0x821005, 0x82107B | inside `uPlayer::updateMotion` | inlined copies of the lookup for grab motions (see "Two lookup paths") |
| 0x42B8E0 | `cCharTblMgr::update` | the script interpreter (the loop) |
| 0x42B960 | `cCharTblMgr::procCtWait` | opcode 0 |
| 0x42B9D0 | `cCharTblMgr::procCtContact` | opcode 1 |
| 0x7AB720 | `uPlayer::updateCharTbl` | calls `update` on both managers each frame |
| 0x7E7E90 | `uPlayerNero::setShortGrabMotionSet` | stores the grab-bank override |
| 0x7EB1xx | `uPlayerNero::setShortGrabEnemyReactionFunc` | picks the grab LMT and its `.ctn` bank |
| 0x7E7F30 | `uPlayerNero::setBusterMotionRsrc` | loads a grab LMT into **motion bank 15** |

`cCharTblMgr` (0x24 bytes, `MtObject`): +0x04 `mpRsrc` (rCharTbl), +0x08 `mpMtn` (`uModel::Motion`: +0x04 u16
`mMotionNo`, +0x08 `mState` (bit 0 tested as "motion ended"), +0x18 float `mFrame`), +0x0C `mpDataTop` (script start), +0x10
`mpDataCrnt` (cursor), +0x14 u8 `mIsDone`, +0x15 `mContactData[2]` (6 bytes each). The player holds two managers
back to back, at +0x1DD4 and +0x1DF8. **H**

## File layout

All offsets are u32. "top" = file + 4 (`mpDataTop`). **H** (code) + **M** (the -1 markers, from the files)

```
+0x00  ".CTN"                                      magic (the loader doesn't check it)
+0x04  u32 bank_offset[]   relative to top,  ended by 0xFFFFFFFF   (0 = no table for that bank)
...    per bank: u32 slot_offset[]  relative to that table's start, ended by 0xFFFFFFFF   (0 = no script)
...    scripts
```

The game never reads the `0xFFFFFFFF` markers: it doesn't know how many banks or slots there are.

Script commands (`update` 0x42B8E0):

| Op | Size | Meaning |
|---|---|---|
| `00 mode .. ..  f32 frame` | 8 | wait. mode 0: wait until `mFrame >= frame` (or until the motion ends, if frame < 0), then go on in the same tick. mode 1: same test, but then the script is done. Any other mode: never advances (the script stalls; no hang). The files use mode 0 only. |
| `01 idx b2 b3 b4 b5 b6 b7` | 8 | contact: each non-zero byte b2-b7 is written into `mContactData[idx].info[0..5]` |
| `02 idx .. ..` | 4 | clear `mContactData[idx]` (6 bytes) |
| `03 .. .. ..  u32 back` | 8 | cursor = cursor - back + 8, then **return** (a loop, one pass per tick) |
| `FF` | 1 | done (`mIsDone = 1`) |
| anything else | - | **hang** (see below) |

The vanilla scripts use only these opcodes, wait mode 0 and contact index 0 / 1 (static walk of every script in
the three files). **M**

## Which bank and slot a motion uses

`mMotionNo` = bank << 8 | slot. The LMT paths are hardcoded in the exe. **H**

| Motion | LMT | `.ctn` | Bank | Slot |
|---|---|---|---|---|
| Nero, normal | `motion\pl000\pl000_NN` (the exe loads 01, 02, 04, 06) | `chartbl\pl000` | NN - 1 = `(motNo >> 8) & 0xF` | `motNo & 0xFF` |
| Dante, normal | `motion\pl006\pl006_NN` (01 to 10) | `chartbl\pl006` | NN - 1 | `motNo & 0xFF` |
| Nero, Buster grab | `motion\pl000\<target>\pl000_<target>_00`, loaded into motion bank 15 | `chartbl\pl000` | 10 to 29 by target (below) | `motNo & 0xFF` |

Grab banks (`setShortGrabEnemyReactionFunc`, the value written to player +0xD628): em000 (enemy kinds 0, 1, 8, 9,
0x23) 10, em003 11, em005 12, em006 13, em010 14, em011 15, em012 16, em013 17, em015 18, em016 19, em017 20, em018 21,
em019 22, em021 23, em022 24, em023 25, em026 26, pl006 (Dante boss) 27, pl002 28, pl023 29. **H**. The slot counts
of banks 10, 12-17, 21, 23, 24, 27 and 29 equal the block counts of the matching grab LMTs. **M**

Checked against the vanilla files: each body LMT `_NN` has as many or fewer blocks than bank NN - 1 has slots
(Nero 167/167, 36/100, 96/96, 47/47; Dante 178/178, 74/74, 74/74, 80/86 ...). Nero's banks 2 and 6-9 are unset
(no `_03`, `_07` ... body LMT). **M**

### Two lookup paths

1. **Normal motions: `cCharTblMgr::set` 0x42BA50.**
   `table = top + bank_offset[(motNo >> 8) & 0xF]`, `script = table + slot_offset[motNo & 0xFF]`. Motion 0xFFFF
   clears both pointers and sets `mIsDone`. **H**
2. **Grab motions (motion bank 15): inlined in `uPlayer::updateMotion`.**
   `setShortGrabMotionSet` 0x7E7E90 sees `(motNo & 0xF00) == 0xF00` and stores, for both body halves, a flag
   (+0x2A3C / +0x2A48), the grab bank from +0xD628 (+0x2A40 / +0x2A4C) and `motNo & 0xFF` (+0x2A44 / +0x2A50).
   `updateMotion` then skips `set` and does the same arithmetic at 0x821005 (manager +0x1DF8) and 0x82107B
   (manager +0x1DD4), with the bank **unmasked**. That is how banks 16-29 are reached. **H**

Neither path checks anything.

## Why it hangs

The `update` loop (0x42B8F0 - 0x42B934):

```
42b8f0  mov   edx, [ecx+10h]       ; cursor
42b8f3  movzx eax, byte ptr [edx]  ; opcode
42b8f6  cmp   eax, 0FFh
42b8fb  jg    default              ; never taken (movzx of a byte)
42b8fd  jz    done                 ; 0x42B945: mIsDone = 1; pop ebx; ret
42b8ff  cmp   eax, 3
42b902  ja    default              ; <- unknown opcodes go here
42b904  jmp   [jumptable + eax*4]  ; 0 wait / 1 contact / 2 clear / 3 loop
...
42b932  default: test bl, bl       ; bl = 1 unless the last wait said "stop for this tick"
42b934        jnz  42b8f0          ; ...so: re-read the same byte, forever
```

`bl` starts at 1 and only a wait changes it, so after an unknown opcode nothing breaks the loop: it re-reads the same
byte forever and the game freezes. **H**

### What a missing script lands on (vanilla files, static walk)

| Case | Cursor lands on | Result |
|---|---|---|
| Slot entry 0 (empty slot) | the slot table itself: low byte of entry 0 (0xA0, 0x94, 0x84, 0xCC, 0x2C ...) | **hang**, every bank of all three files |
| Bank entry 0 (Nero banks 2, 6-9) | `top` itself, so the header is read as the slot table: a bank table or the header read as a script | **hang** for every slot tried |
| Slot == slot count (the `0xFFFFFFFF` marker) | table - 1 (the add wraps): the byte before the table | Nero / Dante bank 0: `FF`, so no script. Every other bank: a wait with a bogus mode, so it **stalls** (no hang). |
| Slot past the marker | script bytes read as an offset | anything: hang, a garbage script, or a read outside the buffer (a crash) |

### When the vanilla game would hit it

Empty `.ctn` slots line up with empty LMT blocks (block offset 0): **M**

| File | script + animation | script + empty block | no script + empty block | no script + animation |
|---|---|---|---|---|
| Dante `pl006_01`-`_10` (slots the LMT has) | 434 | 71 | 181 | **0** |
| Nero `pl000_01`, `_02`, `_04`, `_06` | 230 | 22 | 93 | **1** (bank 0 slot 15) |

So the game never plays a motion without a script. Nero's `pl000_01` block 15 is the one exception: if anything
plays it, the game hangs, so the vanilla game presumably never does. **L**

A mod that **fills an empty block** (Albam's Add Animation takes the first free slot, which is usually one of
these), or **adds blocks past the table's end**, or **adds a body LMT for an unset bank**, makes the game play a
motion the `.ctn` has no script for, and it hangs. That fits the reports of "nonexistent or non-default
animations" hanging.

## Related hazard: the contact index

Opcodes 1 and 2 index `mContactData[idx]` (6 bytes, 2 entries at +0x15) without a check. An index of 2 or more
writes past the 0x24-byte manager. On the manager at +0x1DD4, index 2 reaches the next manager's vtable pointer and
index 3 its `mpRsrc`. The vanilla files use 0 and 1 only. A garbage script (a slot past the marker) can
therefore corrupt `uPlayer` even when it doesn't hang. **H**

## Fixes

### 1. Data only: give every playable motion a script (no exe change)

Rule: **every (bank, slot) the game can play must point at a valid script.** For each LMT the character loads:

- The bank must have a table: a non-zero `bank_offset`, and for a new body LMT `_NN` a header long enough to reach
  bank NN - 1.
- The table needs at least as many slots as the LMT has blocks, then the `0xFFFFFFFF` marker.
- No slot entry may be 0. A slot with no cancel windows can point at a shared one-byte script `FF`. Pointing it at
  a copy of a similar vanilla move's script gives it that move's cancel windows.
- Scripts may use only opcodes 00-03 / FF, wait mode 0 (or 1), contact index 0 / 1, and an op 3 jump that lands on
  the start of a command in the same script.

Rebuilding the file is easiest. Moving a whole table is cheap too: append the new table at the end of the file and
change only its `bank_offset`. The game adds offsets with 32-bit wraparound, so a table at the end can point back at
the existing scripts with "negative" offsets (`script - table` mod 2^32). Adding a bank past the header's end shifts
everything after the header, so that case needs a full rebuild. The loader reads the whole file at whatever size it
is, so a larger file is fine. **H** (the arithmetic and the loader)

### 2. One-byte exe patch: unknown opcode = end of script

Send the `ja default` at 0x42B902 to the existing "done" exit at 0x42B945 (`mov byte [ecx+14h], 1; pop ebx;
retn`). The stack is the same there (ebx pushed at 0x42B8EC), and ecx is still `this`. **H**

```
VA 0x42B902, file offset 0x2AD02:   77 2E   ->   77 41       ; ja 0x42B932  ->  ja 0x42B945
```

Every lookup path ends in `update`, so this covers normal and grab motions. An uncovered motion then runs no
script past that point. Its contact bytes keep whatever was set before (zero for a motion with no script); I haven't checked what zeroed
contact data means for cancelling in practice. **L**

Limits: it doesn't stop a garbage cursor that happens to read as a valid opcode (a slot past the marker). That can
still write out of bounds (the contact index), stall, or read outside the buffer and crash.

### 3. Code cave in `update`: validate every command (the complete exe fix)

All three lookups (`set` and the two inlined copies) feed the same cursor into `update`, and every command is
read at the loop head 0x42B8F0. One hook there covers everything. The lookups themselves read only two dwords at
small indices (bank <= 29, slot <= 255) inside a heap buffer, so they don't need patching. The garbage they produce
is caught in `update`.

Hook: replace `42b8f0 mov edx,[ecx+10h] / 42b8f3 movzx eax,byte [edx]` (6 bytes) with a 5-byte `jmp cave` + `nop`.
Registers at that point: ecx = `cCharTblMgr`, ebx pushed (bl = keep-going flag), eax / edx free. **H** (sketch below
untested)

```
cave:
    mov   edx, [ecx+10h]          ; cursor (replaced instruction)
    push  esi
    mov   esi, [ecx+4]            ; mpRsrc
    mov   eax, [esi+60h]          ; buffer start
    cmp   edx, eax
    jb    bad
    add   eax, [esi+50h]          ; buffer end (the size the loader read)
    sub   eax, 8                  ; room for the longest command
    cmp   edx, eax
    ja    bad                     ; a command this close to the end is treated as "done"
    movzx eax, byte ptr [edx]
    cmp   al, 0FFh
    je    ok
    cmp   al, 3
    ja    bad                     ; unknown opcode
    je    ok                      ; op 3: the next tick re-checks the jump target here
    cmp   byte ptr [edx+1], 1     ; ops 0-2: wait mode / contact index must be 0 or 1
    ja    bad
ok:
    pop   esi
    movzx eax, byte ptr [edx]     ; replaced instruction
    jmp   42B8F6                  ; back to `cmp eax, 0FFh`
bad:
    pop   esi
    jmp   42B945                  ; mIsDone = 1; pop ebx; ret
```

Every rejected case ends the script the same way `FF` does. A false reject is therefore harmless: the motion just
gets no more contact changes. Treating wait modes other than 0 / 1 as "done" replaces a stall, which had the same
effect. Rejecting the last 8 bytes of the buffer catches only a final `FF`, which ends the script anyway.

### Recommendation

Do 1 for every mod that adds or fills animations: it is the only fix that gives new motions real cancel windows.
Ship 2 or 3 in the exe as a safety net, so a missed slot means "no cancel windows" instead of a frozen game. 3 also
stops the out-of-bounds contact writes and out-of-buffer reads that 2 leaves open.

## Open questions

- What zeroed contact data means for cancelling (which `info` byte drives which cancel). `uPlayer::updateContactInfoSub`
  (called from 0x7AB720) is where to look.
- Whether anything plays Nero `pl000_01` block 15 (animation, no script).
- The `.plp` (rPlParamTbl) files weren't examined.
