# uAdhesion: projected decals (2026-10-27)

Names and signatures from the SE PDB (port 13338), DX9 addresses from the DX9 IDB. H = read in code, M = inferred.

## What it is (H, SE)

A **decal unit**: textures projected onto the triangles of whatever collision they land on ("adhesion" = sticking to a
surface). One uAdhesion holds a list of `ADHESION_INFO` entries (`addAdhesionInfo`, `setAdhesionNumber`), each with:
- a texture set: `setAdhesionTexture(id, base, normal, specular)` (rTexture x3), `setAdhesionUVRect(id, uv0, uv1)`,
  `setAdhesionColor`, `setAdhesionNormal`, `setAdhesionSpecular`;
- prim-draw settings: `setAdhesionPrimMaterial` (64-bit material flags), `PrimIntensity`, `PrimVolume`, `PrimZofs`;
- a projection: `setAdhesionProjection(id, const MtMatrix& view_proj, const MtVector3& dir)`;
- the triangles it covers: `addAdhesionTriangle`, `addAdhesionOptimizedTriangle(id, const MtMatrix&, const MtVector3*
  tri, const MtVector3& dir, float)` (clips a collision triangle against the projection; returns false when it misses).

`draw` -> `drawTriangleProjection` renders the triangles with the **XfAdhesion** shader (DX9 strings:
`system\xfshader\XfAdhesion`, technique `tXfAdhesionPart`, sampler `AdhesionSampler`, constants `gXfAdhesionProj`,
`gXfAdhesionDir`, `gXfAdhesionColor`, `gXfAdhesionTangent`, `gXfAdhesionBinormal`, `gXfAdhesionUVRange`; set up in DX9
sub_AAF4B0): projective texturing with a tangent frame, so the decal is normal-mapped. `removeAllAdhesion` / `freeMemory`
clear it.

**uSynchroAdhesion** (derives from uAdhesion; ctor `(cUnit* owner, bool)`, `update(cUnit*)`, `moveAfter`,
`setTransparency(cEffectTransparency)`): the same, bound to a unit, so decals on a moving object follow it.

## Who makes them (H, SE)

The SE effect system: **cParticleGeneratorAdhesion** (a particle-generator type, created by `uEffect::createParticleManager`)
is the only caller of addAdhesionInfo / setAdhesionNumber / setAdhesionProjection / addAdhesionOptimizedTriangle, from its
`update`; `getSynchroAdhesion(cPolygon*)` makes a uSynchroAdhesion for a moving hit. Budget in sEffect:
`mAdhesionLimitMax` / count (`isCreateAdhesion`, `add/subtractAdhesionLimitCount`), `mAdhesionDivideMax`,
`getAdhesionCollisionFilter`. So in SE, effect particles leave marks (scorches, splats) where they hit.

## DX9: present but dormant (H for the code, M for "nothing uses it")

- The classes, their DTIs (uAdhesion::DTI 0xEAEA48, uSynchroAdhesion::DTI 0xEAEA68, getDTI 0xAAF2E0 / 0xAAF2F0), the
  vtable (0xC0B560, uSynchroAdhesion's follows at 0xC0B59C), the shader setup (sub_AAF4B0) and the draw code
  (0xAAF990 ... 0xAB1760, unnamed) are in the exe.
- **No code outside the class calls into it**: every function in 0xAAF2E0-0xAB1830 is reached only from its own vtables
  or from each other.
- No DX9 data file creates one: the DTI hashes (uAdhesion 0x595364DF, uSynchroAdhesion 0x4A20429B, dmc4xml classes.py)
  appear in no `.sdl` / `.pla` under arctool.
- DX9's effects are the older uEffectVFR / `.efl` 0x20070801 system, which has no adhesion generator; cParticleGeneratorAdhesion
  belongs to SE's rewritten effect system (SE `.efl` 0x20120306).

So DX9 carries the decal renderer without a user. A mod could still spawn one (DTI newInstance) and feed it entries to
get decals (bullet holes, blood, scorch marks); the DX9 setters would first have to be matched to the SE functions
(they are unnamed in the DX9 IDB).
