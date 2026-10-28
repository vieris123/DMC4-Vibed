# DMC4 DX9: resource loaders and the game's own writers (per class)

Read-only RE of `DevilMayCry4_DX9.exe` (IDB on port 13337), 2026-10-17, for the MoveDef project. The resource
hash table and `cResource` layout are in `sResource_findings.md`. Confidence **H** unless marked.

## Load path

`sResource::create(sResource *this, MtDTI *dti, const char *path, uint flags)` 0x8DF530: hash the path to a 64-bit
id; cache hit -> refcount++ and return the existing object; miss -> `create_file_load` 0x8DF980:
1. `dti->vtbl+4` allocates the `cResource` subclass; `mID` (+0x58) = hash; priority bits -> `mState`.
2. Full path = `<root>\<path>.<ext>` (`sResource::getFullPath` 0x8DF190: root = `mNativePath` when `mAttr & 0x10`,
   else `mResourcePath`; ext = the class's vtbl slot 6, e.g. `rCharTbl` -> "bin"). The user's dmc4_hook LoadOrder
   mod hooks around here to prefer loose files.
3. `MtFile` open (0x8BC7B0) wrapped in an `MtFileStream` (vftable 0xBFF338); `GetFileSize` -> `mSize` (+0x50).
4. **`vtbl slot 8 (+0x20) load(stream)`**. Success -> `mState |= 1`; failure -> `mState |= 0x10` and the object is
   destroyed. Then insert into the table (double-checked under the lock).

Stream vtable (MtFileStream 0xBFF338; MtMemoryStream 0xBFF448 has the same slots): +0x30 `read(buf, n)`, +0x3C
`write(buf, n)`, +0x44 `size()`. Loaders call `(*(*stream + 0x44))()` for the size and `(*(*stream + 0x30))(buf,
n)` to read.

## Resource class vtable (from rCharTbl's, 0xB9B2B0)

| Slot | Offset | Role |
|---|---|---|
| 0 | +0x00 | destructor |
| 4 | +0x10 | `getDTI` |
| 6 | +0x18 | extension string |
| 8 | +0x20 | **load(MtStream*)** |
| 9 | +0x24 | **save(MtStream*)** |

`save` serialises through `MtDataWriter` (ctor 0x8C6FE0: a buffered writer over the stream, flushing with stream
+0x3C). **Nothing in the release exe calls slot 9** (only the vtables reference those functions), so a hook can
call it itself with its own stream to write a resource it edited in memory.

## Per class

| Class (file) | load | save | What the writer settles |
|---|---|---|---|
| rCharTbl (`.ctn`) and rPlParamTbl (`.plp`) | 0x4659C0: `GlobalAllocator` buffer of `mSize` at +0x60, whole file read into it, `mpDataTop` (+0x64) = buffer + 4 | none (0x46D740 returns 0) | raw bytes. `.ctn` layout: `chartbl_ctn_hang.md` |
| rCollisionIdxData (`.rCollisionIdxData`) | 0x467260: text; `atol` of the first line = row count (`sub_4646A0` allocates), then per row 5 `atol`s into a 60-byte `cCollisionIdx` at +4, +8, +12, +20, +24 (`== 1` -> bool) | 0x4673E0: `"%d\r\n"` count, rows `"%d\t%d\t%d\t%d\t%d\t\r\n"` (fields +4, +8, +12, +20, +24), then `$End\r\n` | 5 integer columns, exactly as the files look |
| rAttackStatusData (`.atk`) | 0x464930: whole file into a `ResourceAllocator` buffer; header 8 bytes (`ATK\0`, u16, u16 count at +6); entries at +8, **0x58 each, used in place** (a 16-byte `cAttackStatus` object per entry points at it; name from the entry) | 0x464A90: `ATK\0`, u16 0, u16 count, then `memcpy` of 0x58 per entry | **the entry is the `kAttackStatus` struct verbatim** (dmc4_hook `uCollisionMgr.hpp`: `char mAsName[16]; int mAttackID; float mDamageValue; int mAttackLv, mAttackLvI, mAttackLvB, mRangeType, mHitStopTimer, mDamageType, mDamageTypeI, mDamageTypeB, mHitmarkAngle, mHitSE; float mStylishPoint, mStylishTimer, mDTAdd; int mAttackFlag, mBlownAngleType, mElementType`). The 010 template's 4 unknown bytes after the name are `mAttackID`. |
| rDefendStatusData (`.dfd`) | 0x4693D0: same pattern, 0x30 per entry (`cDefendStatus`) | 0x469530: `DFD\0`, u16 0, u16 count, 0x30 per entry | `kDefendStatus` verbatim |
| rCollisionShape (`.col`) | `rCollisionShape::load` 0x4684F0: `COL\0`, u16 version, u16 groups, 2 dwords; per group: shape count, kind (+20), flag bits 1/2/4/8/0x10/0x20 -> six bools (+24..+29), a dword; shapes 0x40 raw (`cCollPrim` points at them; version < 2 zeroes shape dword 14) | `rCollisionShape::save` 0x468780: `COL\0`, u16 2, u16 groups, -1, -1; per group: count, kind, flags, -1; shapes 0x40 raw | matches `dmc4xml/col.py` |
| rMotionList (`.lmt`) | `rMotionList::load` 0xA69F20: checks `LMT\0` + version 49, then relocates every block's offsets in place (block table at +8, per block +0x74 and +0xBC pointers, 32-byte track entries at +12) | `rMotionList::save` 0xA69FF0: a full writer (405 lines) | the game can write LMTs: a reference for Albam's export |
| rMotionSe (`.msse`) | 0x4781B0: `MtSerializer::deserializeBinary` (XFS) | 0xA6AA50: returns 1, writes nothing | XFS v5 (`dmc4xml/xfs.py`) |
| rEffectList (`.efl`) | `rEffectList::load` 0xA3B6F0: `EFL\0`, `0x20070801`, header fields (base fps +0x18, list num +0xC, generator type +0x10, move type +0x14, content size +0x8), content copied, `create_resource_infos` | `rEffectList::save` 0xA3B7E0: header + raw content | matches Albam's parser |

## What this enables

- **Exact codecs.** `.atk` / `.dfd` / `.col` / `.idx` can be written byte-exact from the struct layouts above; the
  game's writer is the oracle (dump a loaded table through slot 9 and diff).
- **In-game dump.** dmc4_hook can edit `kAttackStatus` entries in memory (KnockbackEdits already does) and call the
  resource's slot 9 with a file stream to save the `.atk`. An `MtFileStream` opened for writing is still to be
  located (ctor sites: `sResource::loaderHandler` 0x8DDA60, 0x8DD700, 0x8DDF80; `MtFile` 0x8BC7B0).
- **Hot swap.** `rCharTbl` and `rMotionList` keep the whole file in one self-contained buffer. For `.ctn` the only
  pointers into it are the `cCharTblMgr` cursors (`mpDataTop` / `mpDataCrnt`), reset at every motion start, so a
  hook can replace the buffer (+0x60, `mpDataTop` +0x64, `mSize` +0x50) between motions. `.idx` / `.atk` / `.dfd` /
  `.col` are parsed into heap objects that `uCollisionMgr::init` wires in at setup: replacing them means re-running
  that setup (level reload in practice).
- **Cache.** Re-calling `create` for a path already loaded returns the cached object; a reload must either swap
  the buffer in place or release every reference and evict the table entry first.
