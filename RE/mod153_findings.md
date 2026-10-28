# DMC4 DX9 `.mod` v153: loading, drawing and culling (2026-10-06)

Read-only IDA sweep of `DevilMayCry4_DX9.exe` plus a corpus audit of every DX9 v153 `.mod` under `arctool` and
`Dante Cyber porting` (667 unique files, 12,588 meshes). Scripts: Claude scratchpad `modre\`, `modaudit\`, `mod\`.

## Draw call

`transDefault` (0x9F1B10-0x9F21CC), replayed by `sRender::dispatchCommands` opcode 3 @0x8F574E:

`DrawIndexedPrimitive(D3DPT_TRIANGLESTRIP, BaseVertexIndex = face_offset, MinIndex = min_index,
NumVertices = last.max_index - first.min_index + 1, StartIndex = face_position, PrimCount = num_indices - 2)`

- Stream 0 = VB + `vertex_offset`, stride `vertex_stride`; stream 1 = VB2 + `vertex_offset_2`, stride `vertex_stride_2`.
- Vertex i of the index buffer: `offset_vertex_buffer + vertex_offset + (face_offset + i) * vertex_stride` (stream 1 alike).
- `face_offset` is non-zero only in stage models past 65,535 vertices (341 meshes, 7 files), where `min_index` /
  `vertex_position_2` restart at 0.

## Mesh record (52 bytes)

| Off | ksy | Meaning |
|---|---|---|
| 0x00 | idx_group | parts number (`mPartsDisp` bit) |
| 0x02 | idx_material | material |
| 0x04 | disp | 0 = never drawn |
| 0x05 | level_of_detail | **bitmask** 1 near (<= middist), 2 mid (<= lowdist), 4 far; the shadow pass uses 4; 255 = all |
| 0x06 | alpha_priority | sort key += 2 * value (0x9F1E50) |
| 0x07 | vertex_format | **weights per vertex** (0 rigid; vtype 0: 1-4, vtype 1: 5-8, vtype 5: 1); not read when drawing |
| 0x08/09 | vertex_stride / _2 | stream strides (0 = no stream 1) |
| 0x0A | connective | runtime batching flags (bit 0 cleared at load when ranges don't chain; merge if (b & 0x8B) == 0x8B); 0 is safe |
| 0x0B | flags | bit 0 shape (morph), bit 7 sort; bits 1-6 untraced |
| 0x0C/0x10 | num_vertices / vertex_position_2 | not read when drawing; may include unused leading vertices |
| 0x0E | max_index | NumVertices |
| 0x14/0x18 | vertex_offset / _2 | stream byte offsets |
| 0x1C | face_position | StartIndex |
| 0x20 | num_indices | strip length |
| 0x24 | face_offset | BaseVertexIndex |
| 0x28/0x29 | vdeclbase / vdecl | overwritten at load from the material's vtype |
| 0x2A | min_index | MinIndex |
| 0x2C | num_weight_bounds | bounds of this mesh (consecutive records) |
| 0x2D | idx_bone_palette | envelope (u32 count + u8 joints[32]) |
| 0x2E | rcn_base | not read |
| 0x30 | boundary | overwritten with a runtime pointer at load |

## Vertex declarations (from material vtype, rModel load 0xA54459)

| vtype | decl base/draw | stream 0 (32 B) | stream 1 |
|---|---|---|---|
| 0 | 5/0 | SHORT4N pos, UBYTE4 idx, UBYTE4N w, N, T, uv0 h2, uv1 h2 (0xFFFFFFFF filler) | - |
| 1 | 7/2 | pos, idx x8, w x8, N, uv0 | TEXCOORD1 h2 (0 in files), TANGENT, stride 8 (always) |
| 2 | 6/1 | FLOAT3 pos, N, T, uv0, uv1, uv2 | TEXCOORD3 h2 stride 4, optional (zeros) |
| 3 | 6/8, 9 if func_multitexture == 1 | FLOAT3, N, T, uv0, uv1, D3DCOLOR | decl 9: TEXCOORD2 h2 stride 4 (tiled values) |
| 4 | 10/11 shape | pos, idx, w, N, UBYTE4 TEXCOORD, h2, h2 | TANGENT |
| 5 | 5/12 | as vtype 0 but +28 = D3DCOLOR | - |

## Header

- `num_vertices` / `num_faces` / `num_edges` = rModel `mVertexNum` / `mIndexNum` / **`mPolygonNum`** (triangle count:
  non-degenerate strip triangles). Game files end 2 bytes before `offset_index_buffer + 2 * num_faces`
  (num_faces = index count + 1).
- Header `bbox` = the dequantisation range for SHORT4N positions; header `bsphere` = the initial / jointless bound.
- `middist` / `lowdist` = LOD thresholds; `light_group` -> `uModel::mLightGroup`.
- Bones: JOINT_INFO byte 0 mNo (anim number), 1 parent, 2 mirror; +8 `mLength`; `parent_space_matrices` = `mLmat`,
  `inverse_bind_matrices` = `mImat` = inverse of the Lmat chain (row vectors: world_j = L_j . world_parent) in every
  file checked.

## Culling

- `uModel::frustumCullAndLOD` @0x9EDBB0: skipped when `mVFCullLevel` (+0x288, default 3) is 0; sphere vs 6 planes,
  then world AABB.
- `uModel::updateBoundary` @0x9E7DC0: **skinned models ignore the header bounds**. For every displayed mesh, each
  weight bound gives `c_world = (bsphere.xyz, 1) . Joint[bone_id].mWmat`, radius `bsphere.w`; the union box gives the
  model sphere. Jointless models use the header sphere / bbox.
- `uModel::cullPrimitivesAgainstFrustum` @0x9EDDD0: per mesh, culled only when all its bounds are outside; a mesh
  with no bounds is culled whenever the model straddles the frustum. OBB test: `oabb` rows 0-2 axes, row 3 centre
  (joint space), `oabb_dimension.xyz` half-extents.
- **Weight bound record (144 B): joint-local, cm, Y-up**: the box of `p . inverse_bind[j]` over the mesh's vertices
  weighted to joint j (verified on every bound of em021, em021_01, pl000). `bbox_min/max` and `unk` are not read.
- Radius 0 "fixes" culling because the model test can then only return -1 or 63, and 63 skips per-mesh tests.
  Jointless models with `bone_id = 255` make the per-mesh test read `mpJoint[255]` out of bounds.

## attr == 1 materials: velocity-stretch proxies

`uModel::setMaterials` @0x9E7B49 maps attr 1 to cMaterial mode 0x10, which every visible pass skips. Only render
mode 0x20 (IDB name `transDissolve` @0x9ECF30, really the motion-blur velocity pass, constant
`gXfVelocityStretchEnable`) draws them, twice (stretch 0 / 1), for jointed models within distance. The meshes are
zero-area "fins" (vertex pairs at the same position with different normals) that the shader opens along the motion
vector. 1,543 such meshes in the corpus, all 100% degenerate.

## Albam fixes made (engines/mtfw/mesh.py, structs/mod_153.py + mod-153.ksy)

- Parser: `face_offset` as base vertex (indices at `face_position * 2`; vertices and stream 1 at
  `(face_offset + min_index) * stride`, `max_index - min_index + 1` of them).
- Import: attr 1 meshes hidden, `mtfw_edge_mesh = True`; vtype 5's +28 imported as vertex colour; trailing all-filler
  UV layers dropped; stream 1 TEXCOORD (vdecl 9) as `uv_stream2`; LOD import filter as a bitmask; the file's weight
  count kept as `mesh.data["mtfw_weight_count"]`.
- Export: `vertex_format` = weight count (max of the stored and live counts); vertex runs keyed on (layout, stream-1
  stride) and split before 65,536 vertices; stream 1 for vtype 1 (TEXCOORD1 = 0), vdecl 1 (zeros), vdecl 9 /
  vtype 3 + multitexture (TEXCOORD2); vtype 4-8 vertex classes; vtype 5 colour; 0xFFFF filler for unused UV slots;
  `offset_bones_data` / `offset_vertex_buffer_2` = 0 when empty; `num_edges` = triangle count; **weight bounds in joint
  space**; **inverse bind matrices from the Lmat chain** (the old code flipped diagonal signs, wrong for rotated
  joints: 34 of em021_01's 37 joints). Untouched rigs keep their source matrices bit for bit.

## Joint table (checked 2026-10-16)

- rModel's loader (vtable slot, 0xA53F50) reads JOINT_INFO (24 B x n), Lmat and Imat (64 B x n each), the joint table
  (256 B at rModel+0x120) and the envelopes raw; nothing is derived there.
- `uModel::setModel` 0x9E6D70 reads per joint: byte 0 `mNo` (the joint number LMT tracks use), byte 1
  `mParentIndex` (255 = root), byte 2 `mSymmetryIndex` (a bone **index**; 255 = left alone by mirrored motions:
  updateMotionParam 0x9FA1E0 skips calcSymmetry when it's -1), +8 `mLength`, +12 `mOffset` (vec3, also the initial
  `mTrans`); `mWmat` starts as the Lmat and `mQuat` is extracted from it. **Byte 3 (Albam `idx_mapping`) and +4
  (Albam `length`) aren't read.**
- Corpus (5,377 joints, 286 DX9 models): `mOffset` = the Lmat translation and `mLength` = |mOffset| in every joint;
  mirror 255 on 1,577, self on 1,188, another joint on 2,612; joint numbers unique per model (one ware model has a
  joint numbered 255, not in its table); byte 3 is 0 on Nero's coat and scattered on bodies (63, 62, 191, 190, 68,
  197...); +4 matches no child distance.
- `setupMotionParam` maps a track's joint number through the joint table (255 = no such joint).

## Open

- How the game's own jointless stage / sky models avoid the `mpJoint[255]` read (cull level 0 or 1 presumably).
- Mesh flag bits 1-6.
- Albam's import falls back to `bone_map` for a palette index >= count; the game reads past the palette.

## Skinning constants (checked 2026-10-06)

- Envelope = bone palette `{u32 count; u8 joints[32]}`; the count sizes the constant allocation (4 joints per
  192-byte bit) and bounds the bake loop. Albam reads and writes it as the palette length, zero-padded.
- Per palette slot the game uploads 3 rows of `Imat[j] . Joint[j].mWmat` (uploadSkinningConstants 0x9F7B60), so
  the inverse bind matrices must be the inverse of the bind chain: Albam's export now guarantees that.
- Position dequantisation: `s / 32767 * (bbox_max - bbox_min) + bbox_min` from the header box (rModel+0x100/+0x110),
  as Albam imports and exports. The skinned path's `gXfStreamOutQuantPos*` constants quantise GPU stream-out from
  the runtime box and don't involve the file.
