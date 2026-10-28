# DMC4 DX9 `.sbc` (SBC1 v18) — loader, BVH traversal and triangle attributes

Source: DX9 IDB (`DevilMayCry4_DX9.exe`, read-only session, nothing renamed or retyped), cross-checked against the 74
version-18 `.sbc` files on disk (mostly `arctool\*`; 664 groups, 134,835 triangles). Confidence: **H** = read directly
in code and confirmed by every file, **M** = read in code but a reader elsewhere can't be ruled out, **L** = inference.

## 1. Resource and loader

`rCollision` (DTI 0xB7C830, size 160 = `cResource` 96 + 64). Constructor 0x95F830, vtable 0xC05E70 (`load` 0x95F8D0,
`save` 0x95FA30, misspelt `rColliosion::save` in the IDB).

| rCollision | File | Field | Read by |
|---|---|---|---|
| +0x60 | 0x00 | magic `SBC1` | load (4 byte compares) |
| +0x64 | 0x04 | u16 version | load: `cmp word ptr [ebx+64h], 12h` 0x95F97A |
| +0x66 | 0x06 | u16 num_groups (= parts) | load, `Sbc::setPartsNum` via 0x942540, `activateParts` 0x943F30, `SetScrAttribute` 0x47B6D0, per-thread scratch 0x9466F0 |
| +0x68 | 0x08 | u16 num_groups_nodes | **no reader found** |
| +0x6A | 0x0A | u8 max_parts_nest_count | **no reader found** |
| +0x6B | 0x0B | u8 max_nest_count | **no reader found** |
| +0x6C | 0x0C | u32 num_boxes | load |
| +0x70 | 0x10 | u32 num_faces | load, `SetScrAttribute` (last group's triangle count) |
| +0x74 | 0x14 | u32 num_vertices | load |
| +0x78 / +0x84 | 0x18 / 0x24 | bbox min / max | `query_all_sbcs` 0x95E350 broad cull |
| +0x90..+0x9C | — | `mpNode`, `mpPartsInfo`, `mpTriangle`, `mpVertex` (heap pointers) | everything below |

- **Validation (H):** only the magic and `version == 18`. A bad magic or version makes load return 0 (0x95F940 / 0x95F98A).
  The counts aren't checked against the file size.
- **No pointers or offsets in the file (H).** The 0x30-byte header is read into +0x60. Then
  `boxes[num_boxes]` (80 B), `groups[num_groups]` (96 B), `triangles[num_faces]` (28 B) and `vertices[num_vertices]`
  (16 B) are **read sequentially from the stream** (`MtDataReader::read` 0x95F9CD / 0x95F9E4 / 0x95FA01 / 0x95FA14).
  Each goes into its own `ResourceAllocator` block aligned to 16 (helpers 0x95FC10 / 0x95FBC0 / 0x95FC60 / 0x95FCB0).
- **Alignment and order (H):** no padding in the file and no alignment requirement. The arrays must follow each other
  in exactly this order. `save` writes the same layout back.

## 2. The node array (`boxes`, `rCollision::Node`, 80 B) holds two kinds of tree

| Off | Field |
|---|---|
| 0x00 / 0x10 | child 0 AABB min / max (xyz + unused w) |
| 0x20 / 0x30 | child 1 AABB min / max |
| 0x40 | u16 flags |
| 0x42 / 0x44 | u16 child_index[0] / [1] |
| 0x46..0x4F | padding (zero in all files) |

### Flags

| Bits | Meaning | Confidence |
|---|---|---|
| 0x40 | child 0 is a leaf. Tested as `test dword_E16B78[i], node+0x40`; the table at 0xE16B78 is {0x40, 0x80}. Used in `checkAttr` 0x95F5E2, `enumSomeContacts` 0x95EDF0 and `bvh_recurse` 0x95EC46. | H |
| 0x80 | child 1 is a leaf | H |
| bits 0-2 | child 0's min < child 1's min on x / y / z | M (no reader; data only) |
| bits 3-5 | child 0's max > child 1's max on x / y / z | M (no reader; data only) |

- **Bits 0-5** hold for about 99.9 % of nodes; the exceptions are float ties. None of the traversal code reads them.
  Computing them costs nothing, so the exporter should.
- **The high byte** is 0 in every file.

### Child index

- **Not a leaf:** a node index **relative to the tree's base**. Index 0 means "no child": it's never pushed or recursed
  into (`else if (v17)` in `checkAttr` 0x95F67A, `enumSomeContacts` 0x95F01D, `bvh_recurse` 0x95EDC6). So the root (0)
  can never be a child, and an empty slot is written as non-leaf with index 0. **(H)**
- **A leaf is one item:** one triangle in a group tree, or one group (part) in the top tree. **(H)**

### Traversal

Traversal uses an explicit stack (`checkAttr`, `enumSomeContacts`) or recursion (`bvh_recurse`).

- Each child's AABB is tested against the query AABB before it's used (leaf) or pushed (inner).
- The stacks are growable arrays (`sub_95E050` reallocates).

### Top tree over the groups

- Nodes `boxes[0 .. num_groups_nodes-1]`, root = `boxes[0]`.
- Leaf index = **group index**.
- Traversal starts at node 0: `query_all_sbcs` passes 0 to `bvh_recurse`, and `enumSomeContacts` pushes 0 (0x95EE56).
- **The shipped game uses `enumSomeContacts` (H):** `sDevil4Main::sDevil4Main` sets `byte_E559BA` (debug property
  `mFlgNewTypeCollision`) to 1 at 0x8AE7AF.
  - `enumSomeContacts` takes a top node's **leaf bits and child indices from `boxes[k]`**, but its **child AABBs from
    `groups[k].vmin[c] / vmax[c]`** (`mpPartsInfo + 96*k + 0x2C / 0x44`, read at 0x95EE86 ...).
  - So group record *k* is the AABB half of top node *k*. **Both copies must agree.**
  - The legacy `bvh_recurse` reads the AABBs from `boxes[k]` instead.

### One BVH per group (triangles)

- Root = `boxes[group.start_boxes]`. Child indices are relative to `start_boxes`.
- **Leaf index = triangle index relative to `group.start_tris`.**
- In `checkAttr` 0x95F4C0:
  - node base = `mpNode + 80*NodeIndex` (0x95F4F8)
  - triangle base = `mpTriangle + 28*TriangleIndex` (0x95F50B)
  - vertex base = `mpVertex + 16*VertIndex` (0x95F504)
- **Triangle vertex indices are relative to `start_vertices`:** `getTriangle` 0x948660 uses `vertex_base + 16*idx`. (H)

### What every file has (verified on all 74)

| Rule | Value |
|---|---|
| num_groups_nodes | `num_groups - 1` (1 when there's a single group) |
| groups[0].start_boxes | num_groups_nodes |
| Nodes in a group's tree | `max(1, tris - 1)`, packed one group after another |
| groups[0].start_tris / start_vertices | 0, ascending, contiguous |
| Leaf indices | each tree's leaves are a permutation of its triangles; each top tree's leaves are a permutation of the groups |
| Vertices | each group's range is used densely |
| Single-group file | `boxes[0]` = child 0 empty (AABB zero, index 0, non-leaf) and child 1 leaf → group 0 (flags 0x80) |

## 3. Group record (`rCollision::SbcInfo` / PartsInfo, 96 B)

| Off | Assumed name | Meaning | Evidence |
|---|---|---|---|
| 0x00 | base | 0 in every file. No reader seen. | M |
| 0x04 | start_tris | first triangle | `checkAttr` 0x95F50B; `SetScrAttribute` 0x47B729 |
| 0x08 | start_boxes | root of this group's BVH | `checkAttr` 0x95F4F8 |
| 0x0C | start_vertices | vertex base for the triangle indices | `checkAttr` 0x95F504; `SetScrAttribute` 0x47B77E |
| 0x10 | group_id | **part ID for script switching.** `Sbc::activateParts(Id, on)` 0x943F30 sets `Parts.mActive` on every part whose ID matches. Callers include `sub_873D20` (17 calls), `sub_869F00` and `uEm030GroundParts::move`. -1 = never switched (608 of 664 groups); the other values are 0-7 and 66. Parts start active (Parts constructor 0x942750: `mActive=1`). | H (use), L (who sets which IDs) |
| 0x14 / 0x20 | bbox_this min / max | the part's AABB in **local** space. Used by the moving-part broad phase (`moving_part_aabb_test` 0x95E5E0 → `check_part_narrow` 0x95F0C0). In the files it equals the union of the group root's two child boxes. | H |
| 0x2C / 0x38 | vmin[0] / vmin[1] | top node *k*'s child 0 / 1 AABB min (see §2) | H |
| 0x44 / 0x50 | vmax[0] / vmax[1] | top node *k*'s child 0 / 1 AABB max | H |
| 0x5C | child_index[2] | the files hold top node *k*'s **leaf** child indices, with 0 for inner children. The traversals take child indices from `boxes[k]`, so no reader was seen. | M |

- **Groups with no top node.** `groups[num_groups-1]` in multi-group files, and group 0 in a single-group file, carry
  their own bbox twice with child indices (0, 0).
- **The single-group case is safe:** `enumSomeContacts` reads `groups[0].vmin/vmax` for top node 0, and child 0 is
  skipped anyway (index 0, not a leaf).
- **AABB relations in the files** (a few float-noise exceptions):
  - The header bbox is the union of the groups' `bbox_this`.
  - A top-tree leaf box equals that group's `bbox_this`; an inner box is the union of its subtree.
  - A group-tree box contains its triangle or subtree; 99 % of them match it exactly.

**Group order matters (H).** `SetScrAttribute` 0x47B6D0 counts group *k*'s triangles as
`groups[k+1].start_tris - groups[k].start_tris`, and the last group's as `num_faces - start_tris` (0x47B71B-0x47B743).
The groups must therefore be stored in ascending, contiguous `start_tris` order. Otherwise the unsigned difference
makes it run off the triangle array.

## 4. Header counts that are never read (question 4)

`num_groups_nodes`, `max_parts_nest_count` and `max_nest_count` have no reader in:

- the whole `sCollision` range 0x940000-0x960000, scanned for `word`/`byte` loads at +0x68 / +0x6A / +0x6B
- `SetScrAttribute` or any of its 20 callers
- `rCollision::load` / `save`, which only copy them as part of the 0x30-byte header

The traversal stacks are growable (`sub_95E050`) and per-thread (`sCollision+0x17C + 20*thread`), not sized from these
bytes.

- **Writing 0 doesn't break or overflow the DX9 runtime (M-H).**
- Write the real values anyway:
  - `num_groups_nodes` = `max(1, groups-1)`
  - `max_parts_nest_count` = depth of the top tree, counted in nodes
  - `max_nest_count` = deepest group tree, counted in nodes

  All 74 files match these, and SE or other tools may read them.

## 5. Triangle (28 B)

| Off | Assumed name | Real meaning | Evidence |
|---|---|---|---|
| 0x00 | vert[3] u16 | relative to the group's `start_vertices` | `getTriangle` 0x948660 (H) |
| 0x06 / 0x07 | unk_00 / unk_01 u8 | **no reader found.** Not a packed normal (tested). Common pairs (177,176), (127,63). | M (looks like tool data; 0 is safe as far as the code shows) |
| 0x08 | runtime_attr | **Collision channel mask, rebuilt at load** by `sCollisionGame::SetScrAttribute` (store at `mov [edi+8], eax` 0x47BA99). Tested in `checkAttr` 0x95F602-0x95F62A against the query's `callback_struct_t.group_filter` (+0x50, from `ScrCollisionBeforeFunc`): `q = filter & 0x3FFFFF00; if (attr < 0) q ^= 0x3FFFFF00; hit only if q & attr & 0x3FFFFF00`. So bit 31 inverts the test. The file value is 0x3FFFFF00 in every triangle (matches every query), which keeps SBCs that skip `SetScrAttribute` working. | H |
| 0x0C | type | **Ground material ID** (1..0x21). `cUtil::getEfctMtrlFlg` 0x45F780 maps it to the effect / footstep material bit: 1-8, 0x18, 0x1F-0x21 → 1; 9-0xC, 0x1E → 2; 0x10-0x11 → 4; 0x12-0x17 → 8; 0xD → 0x10; 0x19, 0x1A, 0x1D → 0x20; 0x1B → 0x40; 0xE-0xF → 0x80; anything else, 0 included → 0 (no effect). Seen in files: 0, 1, 2, 4, 5, 7, 9, 11-14, 16-18, 20, 24, 25, 27, 30. | H |
| 0x10 | special_attr | **Channels this face doesn't block, plus an override.** Read by `SetScrAttribute` (`mov ebx,[edi+10h]`). See below. | H |
| 0x14 | surface_attr | **Flags** (below) | H for 0x10 / 0x20 / 0x40 / 0x1000; L for the rest |
| 0x18 | unk_02 | 0 in every file; no reader seen | M |

### `SetScrAttribute` (0x47B6D0) computes `runtime_attr`

It runs on every stage SBC: `aRoom::setRoom` 0x40D53A calls it on `st%03d-a-00` before `registResource`. Enemy and
gimmick setups (`uEm018/019/021/030`, `uStageSetMoveFloor` ...) call it on their own SBCs. Every function that creates
an `rCollision` (via `rCollision::DTI` 0xEADCE0) calls it, except `sub_862BE0`, which goes through `sub_8629C0`, a caller.

```
n    = normalize((v1 - v0) x (v2 - v0))             // game space, Y up
mask = (surface & 0x20)                     ? 0x7F00      // forced floor
     : (surface & 0x10) || n.y <= sin(40deg) ? 0x7F0000    // forced wall / steep
     :                                         0x7F00      // floor   (40deg = qword_C0F640, 0x47B9EB)
if (special & 0x7F7F00) {                    // each floor bit 8..14 also clears its wall twin 16..22
    special |= (special & 0x7F00) << 8 ... ; // 0x100 -> 0x10100, ..., 0x4000 -> 0x404000
    mask &= special ^ 0x307F7F00;            // i.e. mask &= ~special
}
if (special & 0x30000000) mask = special & 0x30000000;   // override (0x10000000 / 0x20000000 in files)
tri.runtime_attr = mask;
if (arg2) surface |= 0x40;                   // runtime mark
```

- **Channels:** bits 8-14 are 7 "floor" channels and 16-22 their "wall" twins.
  - The common query filter is 0x10100 (channel 0, floor + wall: 20 call sites).
  - Others use single channels: 0x100, 0x200 (e.g. `uPlayerDanteBoss::isArea408BedRoof`), 0x800, 0x1000, 0xC00.
- **special_attr** bits 8-14 / 16-22 make the face **pass-through for those channels**: it's invisible to queries
  that only use them. The most common values are 0x4A00, 0x4000, 0x2B00, 0xA00 and 0x7500.
- **0x10000000 / 0x20000000** replace the mask outright, so the face only answers queries with those bits.
- **surface_attr:**
  - 0x10 forces wall, 0x20 forces floor, and 0x40 is set at runtime (when arg2 is set).
  - 0x1000 means "sheltered": `getEfctMtrlFlg` 0x45F7AE returns the wet material (0x10) when a floor-channel face
    (`attr & 0x7F00`) is hit in jungle rain, unless 0x1000 is set.
  - 0x400 is tested by `isArea408BedRoof` (0x7C62C9) through `LineResult.pTriangle+0x14`.
  - 0x1, 0x2 and 0x8 are in the files, but no reader was found for them.

## 6. Normal and winding (question 6)

- **No stored normal (H).** `getNormalFromTri` 0x8C3990 and `SetScrAttribute` compute `(v1 - v0) x (v2 - v0)`;
  `vertex.w` is never read, since `getTriangle` copies only x, y, z.
- **One-sided line casts (H).** `collNarrow_LineSeg` 0x955970 rejects a hit when `!both_sides && dot(p1 - p0, n) > 0`
  (0x955AFC). So a segment only hits the side **n points to**.
  - `cUtil::checkGround` (0x45E790) and most of the 138 casts pass `both_sides = 0`.
  - So floors must have **n.y > 0**, i.e. counter-clockwise seen from above in the right-handed game frame.
  - In the files, 38,097 triangles face up, 9,239 down and 87,499 sideways.
- **Floor or wall (H).** The same normal decides floor (`n.y > 0.643`) or wall in `SetScrAttribute`.
  - A reversed floor becomes a wall-channel face that downward rays pass through.
  - Contact typing in `getAdjustContactType` 0x948610 uses n.y as well: 1 above `mSlopeSin`, 2 above `mWallSin`,
    4 for a wall, 8 for a ceiling.
- **Blender winding (H, math).** Albam's mesh conversion `(x, -z, y)` is a proper rotation (det +1), so Blender's
  CCW face normal maps to the game's front face. Keep Blender normals pointing out of the walkable side.

## 7. Other things the exporter must get right

1. **Header bbox** must contain all geometry (H). `query_all_sbcs` skips an SBC whose bbox misses the query AABB grown
   by 1 unit, unless it has moving parts (0x95E506).
2. **Top-node AABBs in the group records** (§2): the shipped `enumSomeContacts` path reads only those.
3. **`bbox_this`** must contain the part (H). It's the moving-part broad phase in part-local space.
4. **Limits** (H unless noted):
   - Vertex indices are u16, relative to `start_vertices`: at most 65,536 vertices per group.
   - Leaf and child indices are u16, relative to the group: at most 65,535 nodes / 65,536 triangles per group.
   - The group count is u16.
   - The `start_*` fields are u32.
   - Nest bytes over 255 would truncate; they aren't read anyway (§4).
5. **Moving parts** (`Sbc.mMoveX/Y/ZNum`, `mMovingPartsArray`) are set up by gameplay code, not by the file (M). The
   file only supplies `bbox_this` and the group ID used by `activateParts`.
6. **Writing `runtime_attr` = 0x3FFFFF00** (as every file does) is correct. 0 would make faces of any SBC that skips
   `SetScrAttribute` collide with nothing.
7. **Gameplay attributes come from `type` / `special_attr` / `surface_attr`.** The game derives floor/wall from the
   geometry plus surface 0x10 / 0x20. These three fields are what to preserve or expose.

## Addresses

| Symbol | DX9 |
|---|---|
| `rCollision::load` / `save` / ctor / DTI | 0x95F8D0 / 0x95FA30 / 0x95F830 / 0xB7C830 (DTI object 0xEADCE0) |
| `sCollisionGame::SetScrAttribute` | 0x47B6D0 |
| `sCollision::registResource` / Sbc set resource / scratch | 0x946750 / 0x942540 / 0x9466F0 |
| `Sbc::setPartsNum` / `Sbc::activateParts` / Parts ctor | 0x9425A0 / 0x943F30 / 0x942750 |
| `query_all_sbcs` / `enumSomeContacts` / `bvh_recurse` / `checkAttr` | 0x95E350 / 0x95EDF0 / 0x95EBA0 / 0x95F4C0 |
| `check_moving_parts` / `moving_part_aabb_test` / `check_part_narrow` | 0x95F050 / 0x95E5E0 / 0x95F0C0 |
| leaf-bit table / new-traversal flag | 0xE16B78 {0x40, 0x80} / 0xE559BA (set to 1 at 0x8AE7AF) |
| `getTriangle` / `getNormalFromTri` / `getAdjustContactType` | 0x948660 / 0x8C3990 / 0x948610 |
| `collNarrow_LineSeg` backface test | 0x955AFC |
| `cUtil::getEfctMtrlFlg` | 0x45F780 |

## Albam (2026-10-10)

**Before:** the export used upstream Albam's generic BVH (`lib/bvh_construction.py` + the Kaitai `Sbc156` path in
`collision.py`). It was measured by exporting all 67 unique DX9 files through it, then querying every triangle's
centroid with a simulation of the traversal above. Only **128,049 of 134,423 triangles (95.3 %)** could be reached,
and only 26 of 67 files were complete.

- **Single-group files** (props, enemy collision): 24 of 31 had nothing reachable.
  - `boxes[0]` was the group's own root, not a top node with a leaf to group 0, and `start_boxes` was off by one.
  - In 10 files `start_boxes` pointed past the end of the node array.
- **Stages:** 26 of 36 were complete, but `st001-a-00` was 5 % reachable.
  - Top-tree leaves pointed at groups whose boxes they didn't contain.
  - `num_boxes` was one short in 41 files.
- **Every file also had:**
  - `runtime_attr` = 0 on every triangle. Harmless for stages, which `SetScrAttribute` rebuilds; fatal otherwise.
  - `group_id` = 0 on every group, so `activateParts(0, ...)` would switch them all.
  - Nest counts of 0 (harmless, see §4).
  - Node flag bits 0-5 of 0 (unread).
  - 12 bytes of zeros per triangle at the end of the file (the size was computed with 40-byte triangles).

**Now:** `engines/mtfw/sbc_bvh.py` (pure Python) writes every rule in §2-§3.
- **The trees:** median-split BVHs with exact child boxes, the top node copied into the group records, and the
  single-group top node as the game has it.
- **The values:**
  - `runtime_attr` 0x3FFFFF00;
  - group IDs kept, -1 for new meshes;
  - triangles reordered into leaf order;
  - the nest counts and flag bits as the files have them.
- **Results:**
  - All 67 files rebuild with every rule holding and the same triangles, attributes, group IDs and file size.
  - Every triangle is reachable by the point-query simulation, both in plain Python and through Blender import/export.
- **Not yet confirmed in the game.**
