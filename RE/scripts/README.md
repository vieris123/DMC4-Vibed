# RE/scripts

IDAPython analysis scripts for the DevilMayCry4_DX9 multiplayer / `sMediator` decoupling work.
Run them **inside the live IDA session** through the ida-pro-mcp `py_exec_file` tool — they use a
shared-globals scope. Do **not** paste them into `py_eval`: that tool splits globals/locals and
nested-function name lookups fail.

| Script | Purpose | Output |
|--------|---------|--------|
| `uem_features.py` | Dump per-function matching features (strings, callees, constants, vtable slots) for a class family from either IDB; config `features_cfg.json` in the scratchpad (`prefix`, `tag`, optional DX9 `span`). Used for the SE→DX9 name passes. | `se_<tag>_features.json`, `dx9_<tag>_features.json` |
| `uem_merge.py` / `pl_merge.py` | Merge the per-group SE→DX9 mapping JSONs and check coverage and duplicate claims. Plain Python (`python RE/scripts/...`), not IDA. | `RE/uem_map/uem_se_dx9_map.json`, `RE/pl_map/pl_dx9_se_map.json` |
| `cam_merge.py` | Merge the per-group camera SE→DX9 JSONs (`RE/cam_map/A–H.json`, SE-first) and check SE coverage, duplicate claims, ICF multi-claims and hex address fields. Plain Python: `python RE/scripts/cam_merge.py <se_cam_features.json>`. | `RE/cam_map/cam_se_dx9_map.json` |
| `efl_corpus_stats.py` | EFL corpus stats for `RE/efl_import_plan.md` (M0.3): versions per folder, DX9 container checks, per-slot type histograms, inferred block lengths vs minimum sizes, path-field folders. Plain Python (`python RE/scripts/efl_corpus_stats.py "E:\DMC mod stuffs"`), not IDA. | stdout; optional `--json` |
| `build_mpplayer_sites.py` | Enumerate every `sMediator::mpPlayer` (mpInstance+0x24) reference — inline reads + `getPlayerPos`/`getPlayerMat` call sites — and enrich each with owning class, `this`-register/CC, category, and instruction lengths. | `RE/mpplayer_call_sites.json` |

## Regenerating the call-site inventory

```
py_exec_file  RE/scripts/build_mpplayer_sites.py
```

Regenerate after **any** database change that defines, renames, or retypes functions — the JSON is
keyed to live instruction addresses and function prototypes and goes stale otherwise. The script is
idempotent and overwrites the JSON in place.

Expected output (baseline, DB as of 2026-10-14, operand-based scan): **1123 sites** = 1019 inline + 104 accessor;
categories camera 160 / damage-derivable 19 / nero-grab 16 / damage-review-aggro 4 / uncategorized 924
(camera = the hardcoded `CAMERA` set + any function whose name qualifier or vtable class contains "cam");
`this_reg` = ecx 394, eax 249, stack 245, esi 130, edi 73, edx 13, ebx 3, null 16;
`ea_len` 5-byte 649 / 6-byte 474. Sites with no owning class: 257.
Earlier baselines (1047 on 2026-07-09, 1048 on 2026-10-05) came from the old text-match scan and are
**not comparable**: they included 16 non-player records and one wrong deref, and missed 92 real sites —
see *Corrections (2026-10-14)* in `RE/mpplayer_dispatcher_patch_plan.md`.

If the counts drift, that's real signal (new functions defined, or a category function was
re-typed) — reconcile against `RE/mpplayer_dispatcher_patch_plan.md` before trusting the delta.

## Notes / gotchas baked into the script

- `func_type_data_t` exposes the calling convention via `.get_cc()` in IDA 9.3 and
  `.get_explicit_cc()` in IDA 9.2 — neither has a `.cc` attribute. The script handles both.
- The deref is matched by **operand**: a `[reg+24h]` whose base register still holds the loaded
  mpInstance pointer, followed through in-function `jmp`s, up to `SCAN_WINDOW` (40) instructions.
  Never go back to matching `+24h` in disassembly text — it hits `[esp+24h+var]` stack slots and
  `[vtbl+24h]` calls.
- Output goes to `RE/mpplayer_call_sites.json` next to the open `.i64` (path derived from
  `idc.get_idb_path()`), so the script works on any machine with the standard layout.
- `arg0` for untyped functions comes from Hex-Rays and can flip between `a1` and `null` between
  runs; ignore that diff.
- `this` is **not** uniformly `ecx` — ~65% of sites pass it in eax/esi/edi/edx or on the stack.
  Resolved from the prototype, falling back to a Hex-Rays decompile for untyped functions.
- FP-return functions misreport arg0 as a `st0`/`xmm0` return slot; the script skips to the first
  GP-register (or stack) argument.
- The category EA sets (`CAMERA`, `NERO_GRAB`, `DAMAGE`, `DAMAGE_REVIEW`) are hardcoded from this
  session's analysis. Extend them there if new per-player/damage/grab handlers are identified.
  `camera-per-player` additionally includes every function owned by a camera class
  (`is_camera_class`: name qualifier or vtable class contains "cam"), which relies on the names from
  the SE→DX9 camera pass — renaming camera functions back to `sub_` would drop them from the category.
