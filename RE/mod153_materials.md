# DMC4 DX9 materials (.mod v153): runtime spec and Albam audit (2026-10-06)

Sources:
- **IDA, read-only:**
  - `rModel` load 0xA543E6-0xA54581;
  - `uModel::setMaterials` 0x9E7410;
  - `cMaterial::buildRenderState` 0xA61D00 / `setDrawState` 0xA617D0 / `beginDraw` 0xA61A70;
  - `cMaterialStandard::beginDraw` 0xA62C30;
  - the render-state replay in `sRender::dispatchCommands` 0x8F470A-0x8F49AD.
- **The shader binary:** `arctool\shader\system\xfshader\XfMaterialStandard.bfx`, all 149 VS and 586 PS disassembled.
- **The corpus:** 2,625 materials in 667 DX9 v153 files, and 59 headless Blender round trips.
- Scratch: Claude scratchpad `matre\` (shader dumps, `valid_permutations.json`), `matcorpus\` (statistics, round trips).

## Technique and permutation key
- Every `cMaterialStandard` uses `tXfMaterialStandard`. `htechnique` is resolved at load and then ignored; the corpus
  always has 0x88367C19.
- Key = `skin + 7*lighting + 35*normalmap + 140*specular + 700*lightmap + 5600*multitexture`. It is recomputed at
  load into `pipeline` (the file value is ignored). The bfx permutation table at 0x56C has 39,200 entries
  (u16 ps, u16 vs; 0xFFFF = none); 1,659 have shaders.

| Function | Values (radix) |
|---|---|
| SKIN | NONE, 1WT, 2WT, 4WT, 8WT, 4WT_SHAPE, STREAM_OUT (7) |
| LIGHTING | NONE, 4SPOT, SH4SPOT, EMITSH4SPOT, THINSH4SPOT (5) |
| NORMALMAP | NONE, STANDARD, DETAIL, PARALLAX (4) |
| SPECULAR | NONE, STANDARD, MIRROR, POWMAP, RIM (5) |
| LIGHTMAP | NONE, STANDARD, SHADOW, BLEND, BLENDSHADOW, VCOLOR, HDRVCOLOR, TEXCOLOR (8): no DX9 shader for BLEND, BLENDSHADOW or TEXCOLOR |
| MULTITEXTURE | NONE, ALPHA, BASE, FREEZE, VOLUME, SPEC, BLUR (7): no DX9 shader for FREEZE |

## Record (160 bytes; the ksy bit order is correct)

**Word 0**

| Bits | Field | Meaning |
|---|---|---|
| 0 | fog_enable | Fog |
| 1 | zwrite | D3DRS_ZWRITEENABLE (attr 0x20 never writes) |
| 2-13 | attr | 0x10 SOLID, 0x08 NUKI, 0x20 OVERLAP, 0x40 TRANSPARENT, 0x01 velocity proxy; anything else is opaque |
| 14-21 | num | material ID `mMtrlID`: `cMaterialHandler` runtime overrides match it |
| 22-24 | envmap_bias | env-cube LOD: max(0, envMips + bias - 6), 0 = none; bits 25-26 unread |
| 27-29 | vtype | vertex declaration |
| 30 | uvscroll_enable | gates game-code UV offsets |
| 31 | ztest | unread (ZENABLE is always on) |

**Word 1:** skin bits 0-3, lighting 6-9, normalmap 10-13, specular 14-17, lightmap 18-21, multitexture 22-25.

**Factors and other fields**

| Field | Meaning |
|---|---|
| transparency | `gXfBlendFactor` = transparency * fade: scales alpha; doesn't enable blending |
| fresnel_factor | FresnelFactor, FresnelBias, SpecularPow, EnvMapPower |
| lightmap_factor.xyz | LightMapScale (* lightmap texture header range); also the EMIT / THIN colour |
| detail_factor | DetailPower, DetailWrap, -, AmbientOccBias |
| parallax_factor | x, y parallax scale; sign(z) = bitangent sign |
| transmit_factor | unread |
| blend_state | 0x02A20225 additive, 0x02A20265 rev-subtract, else alpha blend (attr 0x20 / 0x40 only) |
| alpha_ref | low byte = D3DRS_ALPHAREF |
| reserved2[1] (0x9C) | **GlossMap texture index** (POWMAP exponent, MULTITEXTURE_SPEC) |
| glossmap (0x38) | AmbientOccMap, sampled by no shader |

**attr → draw**
- **0x10:** opaque, alpha ignored.
- **0x08:** alpha test, alpha > alpha_ref.
- **0x20:** blended decal, depth bias, no z write.
- **0x40:** blended, plus alpha test, z write per flag.
- **All:** single-sided (CULL_CW); a runtime fade below 1 forces blending.

## Texture slots (1-based into the 64-byte path table; 0 = none)

| Field | Sampler | Role | UV |
|---|---|---|---|
| basemap | AlbedoMap | colour * header range.rgb; header range.w = 0 → alpha multiplies colour, opacity 1 | TEXCOORD0 |
| normalmap | NormalMap | DXT5nm (X = A, Y = G) | TEXCOORD1 (= TEXCOORD0 in files) |
| maskmap | MaskMap | specular colour / intensity | TEXCOORD1 |
| lightmap | LightMap | rgb * a * LightMapScale (ambient) | **TEXCOORD2** |
| shadowmap | ShadowMap | R masks specular only (LIGHTMAP_SHADOW) | TEXCOORD2 |
| additionalmap | AdditionalMap | depends on the functions: MULTITEXTURE_ALPHA alpha mask (TEXCOORD2); EMIT emissive mask; THIN transmission mask; PARALLAX height; BASE albedo blend; DETAIL detail normal when there's no heightmap | |
| envmap | EnvironmentMap | cube, rgb / max(a, 1/255) * EnvMapPower | |
| heightmap | DetailMap | detail normal (_NM) | TEXCOORD1 * DetailWrap |
| reserved2[1] | GlossMap | | |

LIGHTMAP_VCOLOR (44% of materials) uses the vertex colour instead of a lightmap.

## Shading
- Blinn-Phong over 4 spot lights plus 4 diffuse lights, plus SH ambient (SH4SPOT).
- Specular = (lights + env) * mask.rgb * (1 - fresnel) * T.w.
- Diffuse = (lights * T.w + ambient) * albedo.
- **T.w = tangent.w is a per-vertex direct-light occlusion term**, not handedness.

## Albam (engines/mtfw/material.py, texture.py)

**Fixed 2026-10-06:**
- **Symmetric slots.** Export writes shadowmap ← "Special Map", additionalmap ← "Alpha Mask AM",
  heightmap ↔ "Detail DNM" (import too).
- **Missing textures** import as `albam_missing` placeholders: the reference is kept and no file is written.
- **Unchanged textures** export their original bytes. Edited ones keep the original revision and cube data.
- **A8R8G8B8 basemaps** are supported.
- **`pipeline`** is computed on export, and **function values without a DX9 shader** raise `AlbamCheckFailure`.
- **`setup_dmc4_material`** (display):
  - blend from attr / alpha_ref;
  - single-sided;
  - the alpha mask only for MULTITEXTURE_ALPHA;
  - lightmap / shadow / mask on TEXCOORD2 (uv3 or uv_stream2);
  - lightmap * a * factor * range;
  - VCOLOR from the vertex colour;
  - basemap range.w = 0 handling.
  - Export follows links through those nodes.
- **Detail driver path** is per app.
- **Defaults for new materials** follow the corpus.

**Also fixed (second pass):**
- **New inputs on the shared "MT Framework shader" group** (`_extend_mtfw_shader`, also upgrades groups in older
  .blend files). Their defaults keep the old look for other games:
  - `Use Specular Color` + `Roughness`: mask = specular tint, roughness = sqrt(2 / (SpecularPow + 2)) from
    fresnel_factor[2]; SPECULAR_NONE = no specular.
  - `Flip Normal Green`: 0 when parallax_factor.z < 0.
  - `Emission DMC4`: EMITSH4SPOT = albedo * additional.r * lightmap_factor.
- **tangent.w (occlusion)** imports as the point attribute `mtfw_tangent_w` and exports from it; byte-identical
  on em021, pl000 and st000.
- **Export checks** (`AlbamCheckFailure`, all hold for every corpus material):
  - vtype must agree with the functions: skin 0 ↔ vtype 2/3; skin 1-3 ↔ 0/5; skin 4 ↔ 1; lightmap 1/2 → vtype 2;
    VCOLOR → 3/5;
  - no skinned vtype on a model without bones;
  - a mesh may use only one material;
  - non-DDS (generated) images get the DDS error, not a crash.

- **Environment cube** (`_env_cube_display`, 308 materials in 67 files): the cube imports as a vertical strip (+X -X +Y
  -Y +Z -Z from the top, D3D face orientation; verified by colour continuity across all face edges). The
  `ALBAM DMC4 Cube UV` node group maps Blender's reflection vector to it. The term is
  rgb / max(a, 1/255) * EnvMapPower * mask * (1 - sat(FresnelFactor * facing^5 + FresnelBias)), added to
  `Emission DMC4`. It's skipped for SPECULAR_NONE and MIRROR.

- **Lighting functions (2026-10-17, from the re-disassembled pixel shaders; `d3dcompiler_47` D3DDisassemble on the
  586 PS / 149 VS blobs, permutation table at 0x56C):**
  - LIGHTING_NONE (116 materials) reads no light: albedo x base-map scale x (lightmap or vertex colour x
    LightMapScale) x (1 + AmbientOccBias x (T.w - 1)) + fog. Display: group input `Unlit`.
  - THINSH4SPOT (14, em009): per light, a back-facing N.L adds `light x -N.L`, plus the SH ambient toward -N; that
    sum x AdditionalMap.r x LightMapScale joins the diffuse light before the albedo. Display: group input
    `Translucency` (a Translucent BSDF) = albedo x additional.r x lightmap_factor.
  - LIGHTMAP_SHADOW (224): ShadowMap.r (TEXCOORD2) x T.w multiplies the Fresnel-weighted specular only. Display:
    Specular MM x shadow.r (the shadow texture keeps its direct link to Special Map for export).
  - SPECULAR_POWMAP (11): the environment cube is gone; a GlossMap (s3) is sampled per light for the exponent. Every
    file's GlossMap index is 0, so the game binds nothing there. Display: no env cube.
  - SPECULAR_MIRROR (3) and MULTITEXTURE_BLUR (9) sample a ScreenMap (the scene behind, gXfScreenOfs / Scale):
    not displayed.
  - Additional maps on 25 materials whose functions don't read one (skin/lighting/normal/spec combos (0,0,1,1),
    (3,2,1,1), (3,0,1,1), (3,0,1,0), (4,2,1,1)): leftover references, no shader samples them.
  - Not in any DX9 file: PARALLAX, DETAIL normal map, MULTITEXTURE BASE / VOLUME / SPEC, SPECULAR_RIM, HDRVCOLOR.

**Not done:**
- MIRROR / BLUR screen sampling;
- the reserved2[1] GlossMap index (exported as 0; 0 in the whole corpus);
- export orders the texture list by the materials' image nodes, so a file whose list is in another order (e.g.
  `ee010_01.mod`: env 4, additional 5) comes back renumbered (same textures in every slot).

## Corrections to older notes
- `cMaterialStandard.md`: bit 27 is **zwrite** (not fog_enable); transmit_factor is unread (+0x70 is LightMapFactor).
- `texture_binding.md`: the checks are multitexture == BLUR (+0x55) and specular == MIRROR (+0x53).
