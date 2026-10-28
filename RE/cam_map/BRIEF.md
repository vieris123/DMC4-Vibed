# Camera SE → DX9 mapping — worker brief

Goal: map every **SE (leaked-PDB) camera method** in your group to its **DX9** counterpart, apply
confirmed names in DX9, and record the full mapping (including non-matches) as JSON.
"Camera" = any class whose qualified name contains `cam` (case-insensitive: `cCamera*`, `cCam*Data`,
`uCameraBoss*`, `uEfctCam`, `uModelCam`, `uEm027::uCamCtrl`, …), plus group **H**: methods whose
*method* name contains `cam` on non-camera classes (`sMediator::getCamera…`, `uDevil4Model::…Camera…`).

## HARD RULES

1. **IDA access.**
   - DX9 = the `ida-pro-mcp` tools (port 13337). Never call `select_instance`.
   - SE = read-only spot checks with `python S\idacall.py 13338 <script.py>` (Bash). The script runs
     via `py_exec_file` in the SE IDB. Write it under `S\<GROUP>\`; never write to the SE database.
   - **Every IDA call must finish in < 15 s** (hard kill at 60 s). Eight workers share each IDA
     process and requests are serialised. Bulk matching is **offline** in local Python against the
     JSON dumps; use IDA only for spot verification (`decompile`, `disasm`, small `py_eval`) and for
     applying names/comments in batches of ≤ 150.
2. **Only rename DX9 functions whose SE match belongs to a class in your group** (group H: the SE
   method's own class). Inherited/shared code (`uActor::*`, `uCoord::*`, `MtObject::*`, another
   group's class) — record it, don't rename it.
3. **Never overwrite existing comments.** Many camera functions already carry analysis comments
   (`[MP/camera] …`, `SE: …` from the uEm/uPl passes). Prepend yours.
4. Do not call `idb_save`. Never hand-convert number bases for reporting — use Python or `int_convert`.

## Inputs (read-only)

`S = C:\Users\fapro\AppData\Local\Temp\claude\e--DMC-mod-stuffs-Vibed\d2e3163c-289d-4d14-9e62-1d932ca40c12\scratchpad\cam`

| File | Content |
|------|---------|
| `S\groups.json` | group → SE class list (A–G). Group H = every SE func whose class does not contain `cam`. |
| `S\se_cam_features.json` | SE: `vtables` (**all** 3534 classes), `funcs` = the 1135 in-scope camera methods |
| `S\dx9_all_features.json` | DX9: `vtables` (all labelled), `funcs` = **every** DX9 function (~19.4k) |
| `S\dx9_cam_anchors.json` | DX9 per class: DTI, name string, registration (size, parent DTI), getDTI stub, vtable(s) |

`feat = {name, sig, cmt, size, nbb, ninsn, strs, callees[[ea,name]], callers[ea], gl[named globals], imms, flts, vt[[cls,slot]]}`.
`sig` = long demangled signature (SE: the full PDB signature). `cmt` = existing function comment.
Callee/global **names** compare across sides when the DX9 helper is already named (`sMediator::*`,
`MtMath`, `cUtil::*`, `uEnemy::*`, the `uEm*`/`uPl*` methods named by earlier passes, …).
Also read `CLAUDE.md`, `RE/uem_se_dx9_map.md`, `RE/pl_dx9_se_map.md`, and the *Camera Subsystem*
section of `RE/player_instance_findings.md`.

## Known structure / lessons from the uEm and uPl passes

- **SE is a newer engine with longer base vtables.** Absolute slot numbers don't line up; the SE→DX9
  slot shift is constant per base-class segment (uEm: SE 21→DX9 12 `kill`, 53→30 `main`, 54→31
  `updatePtr`; uPl was piecewise). Derive it from anchor slots (dtor, getDTI, createProperty, setup,
  kill, move) and align **class-owned overrides by relative order**.
- **Existing DX9 vtable labels can be wrong** (the old labeller put `Class::vftable` on nested/embedded
  vtables). Verify from the ctor's `mov [reg], offset vtbl` or the getDTI stub `B8 <DTI> C3`;
  `dx9_cam_anchors.json` already lists the stub-derived vtable(s) per class — trust that over labels.
- **SE-only content**: Vergil/Lady/Trish, Library (`uGUI_Lbry*`) additions, newer engine helpers.
  Unmatched is a valid outcome. Inlining differs between builds.
- **MSVC keeps per-TU order**: DX9 class code is contiguous per class and tends to follow SE order.
  Use TU-order fill between anchored matches.
- **ICF folding**: one DX9 body can match several SE methods. Name it for the class that owns the
  address region; comment `ICF-folded: one DX9 body for N SE methods: …`.
- **Action/state tables** (camera modes are often dispatched through static function-pointer tables,
  e.g. `cCameraPlayer` modes, `uCameraBoss*` states): match by table index + constants, verify by decompile.
- **Destructors** are often undefined `loc_` code at vtable slot 0 — define with `ida_funcs.add_func`,
  name with the SE mangled name (`??_G…`/`??1…`) since IDA turns `~` into `_`.
- `MyDTI::newInstance` / `MyDTI::~MyDTI` (SE `X::MyDTI::*`) exist in DX9 too — match them via the
  DTI vtable next to the class vtable.

## Suggested pipeline

1. **Class anchors** from `dx9_cam_anchors.json`: DTI, vtable, ctor, dtor, getDTI, createProperty
   (property-name strings are near-unique), setup.
2. **Vtable alignment** per class (DP/LCS over owned-override sequences; score size/nbb, named
   callees, strings, floats).
3. **String anchors** (Jaccard on unique string sets), **callgraph propagation** to fixpoint
   (callee and caller lists, in order), **TU-order fill** between anchors.
4. **Verify**: decompile a sample of every evidence type — every order-fill/propagation-only match and
   every match with size ratio outside 0.5–2.0. Demote anything that doesn't hold.

## Confidence & actions

- `high` — ≥ 2 independent signals agree, no competing candidate (or decompile-verified) → rename.
- `medium` — one signal, or two candidates → comment only: `SE candidate: <sig> @ <SE ea> (medium: <evidence>)`.
- `none` — no DX9 counterpart (SE-only) → no DX9 action.

Applying (short `py_eval`, wrap in `def main(): ...; main()`):
- `high`: `ida_name.set_name(ea, "Class::method", ida_name.SN_NOWARN | ida_name.SN_NOCHECK)` (strip
  the arg list; overload collision → `_2`, `_3`…) and repeatable function comment
  `SE: <full signature> @ <SE ea>` prepended to any existing comment.
- Existing non-auto DX9 name:
  - equals the SE name → comment only, `action: "confirmed"`;
  - lowercase_underscore placeholder or clearly wrong → replace, start the comment with `was: <old>`,
    `action: "replaced_existing"`;
  - looks like a deliberate real name that disagrees → don't rename, `action: "conflict"`, explain in notes.
- Label missing/incorrect vtables of your classes `Class::vftable` (and `Class::MyDTI::vftable`).

## Output

Write `E:\DMC mod stuffs\Vibed\RE\cam_map\<GROUP>.json`:

```json
{
  "group": "C",
  "classes": {
    "uCameraBoss": {
      "se":  {"vtable": "0x...", "nslots": 0, "nfuncs": 0},
      "dx9": {"dti": "0x...", "vtable": "0x...", "ctor": "0x...", "size": "0x...", "parent": "...",
              "nslots": 0, "code_range": ["0x...", "0x..."]},
      "slot_shift": "SE n -> DX9 n-k (k=..) / piecewise: ...",
      "vtable_label_fixed": false
    }
  },
  "methods": [
    {"se_ea": "0x...", "se_name": "uCameraBoss::move(void)", "dx9_ea": "0x...", "old_dx9_name": "sub_...",
     "new_dx9_name": "uCameraBoss::move", "confidence": "high|medium|none",
     "evidence": ["vtable","callees","strings","consts","order","propagation","decompile","table"],
     "action": "renamed|replaced_existing|confirmed|commented|conflict|none", "notes": ""}
  ],
  "dx9_only": [{"dx9_ea": "0x...", "name": "...", "notes": "in class region, no SE counterpart"}],
  "notes": "free-form: class not in DX9, layout surprises, ICF folds, wrong labels fixed"
}
```

**Every SE function of your group must appear in `methods`** (`dx9_ea: null` if unmatched).
All addresses are hex strings (`"0x..."`) or `null` — no prose in address fields.
Helper scripts go in `S\<GROUP>\`, not in the repo. Finish with a short summary: counts per
confidence/action, classes not present in DX9, anything the coordinator must reconcile.
