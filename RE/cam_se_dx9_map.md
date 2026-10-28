# Camera SE → DX9 mapping (2026-10-14)

Every camera method in the SE (leaked-PDB) build mapped onto the DX9 IDB. Names and `SE:` comments
are applied in DX9; the full per-method record is `RE/cam_map/cam_se_dx9_map.json`
(per-group sources `RE/cam_map/A.json`…`H.json`, worker brief `RE/cam_map/BRIEF.md`,
merge/check script `RE/scripts/cam_merge.py`).

## Scope

- **Camera classes** — any SE class whose qualified name contains `cam` (case-insensitive): 102 class
  qualifiers incl. `::MyDTI`, 1038 methods. Beyond the `*Camera*` classes this picks up the camera
  data classes (`cCamAreaConnect`, `cCamAreaData`, `cCamDataHeader`, `cCamPanData`, `cCamRailData`,
  `cCamRailDataCmn`), `uEfctCam`, `uModelCam`, `uEm027::uCamCtrl`, `rCameraList::CAMERA_INFO`.
- **Group H** — 97 methods whose *method* name contains `cam` on non-camera classes (`sMediator`,
  `uDevil4Model`, `cDraw`, `sVibration`, `uEm*`, `uGUI_Lbry*`, …).
- Compiler-generated `_dynamic_initializer_for_*` / `_dynamic_atexit_destructor_for_*` stubs excluded.

## Results

**1135 SE methods**: 613 high, 12 medium, 510 none. Of the 510 unmatched, **319 are per-class
allocator boilerplate** (`usage`, `operator new`, `operator delete`) that DX9 doesn't have — it
allocates through the global allocator. Excluding those, **625 / 816 = 77 %** of real methods map.
The other 191 are SE-only content, functions DX9 inlined, or functions SE never calls (the DX9
linker dropped them).

DX9 actions: **435 renamed**, **20 replaced** (old name kept as `was: …`), **111 confirmed**
(existing name already right — SE comment added), **21 commented** (ICF folds / medium).
All 566 rename/replace/confirm rows were re-checked against the live IDB after the pass: every
name matches the JSON, every one is a function start, every one carries an `SE:` comment.

| Grp | SE class | SE methods | high | med | none | DX9 DTI | DX9 vtable |
|-----|----------|-----:|-----:|----:|-----:|---------|-----------|
| A | cCameraBase | 15 | 4 | | 11 | 0xE56C28 | 0xB97FBC |
| A | cCameraNormalInitParam | 12 | 5 | | 7 | 0xE56C68 | 0xB98080 |
| A | cCamDataHeader | 11 | 4 | | 7 | 0xE56C48 | 0xB98064 |
| A | **cCameraPlayer** | 67 | 49 | | 18 | 0xE56C88 | 0xB9869C |
| B | cCamAreaConnect / cCamAreaData | 11 / 12 | 4 / 5 | | 7 / 7 | 0xE56D48 / 0xE56DE8 | 0xB98A78 / 0xB98A94 |
| B | cCamPanData / cCamRailData / cCamRailDataCmn | 11 / 12 / 11 | 4 / 5 / 4 | | 7 / 7 / 7 | 0xE56DA8 / 0xE56D88 / 0xE56DC8 | 0xB98ACC / 0xB98B04 / 0xB98AE8 |
| B | cCameraRailBase | 21 | 12 | | 9 | 0xE56E08 | 0xB98B20 |
| B | cCameraRail / Em025 / Em026 | 21 / 20 / 23 | 13 / 12 / 15 | | 8 / 8 / 8 | 0xE56CC8 / 0xE56D68 / 0xE56CA8 | 0xB98BA0 / 0xB98BE0 / 0xB98C20 |
| B | cCameraPan / cCameraNormal / cCameraRect3D | 23 / 12 / 12 | 14 / 4 / 5 | | 9 / 8 / 7 | 0xE56CE8 / 0xE56D08 / 0xE56D28 | 0xB98B60 / 0xB98C60 / 0xB98AB0 |
| C | **uCameraBoss** | 71 | 45 | | 26 | 0xE58338 | 0xBC5FAC |
| C | uCameraBossDante / Em018 | 22 / 40 | 14 / 27 | | 8 / 13 | 0xE58358 / 0xE58378 | 0xBC6178 / 0xBC628C |
| D | uCameraBossEm019 / 021 / 022 / 023 | 41 / 37 / 25 / 28 | 29 / 26 / 15 / 15 | | 12 / 11 / 10 / 13 | 0xE58398 / 0xE583B8 / 0xE583D8 / 0xE583F8 | 0xBC63A0 / 0xBC66B4 / 0xBC6720 / 0xBC67B0 |
| E | uCameraBossEm025 / 026 / 029 / 030 | 24 / 21 / 32 / 34 | 13 / 11 / 20 / 25 | | 11 / 10 / 12 / 9 | 0xE58418 / 0xE58438 / 0xE58458 / 0xE58478 | 0xBC6944 / 0xBC69B8 / 0xBC6A80 / 0xBC6B70 |
| E | uCameraCtrl | 30 | 19 | | 11 | 0xE58498 | 0xBC6C20 |
| F | sCamera / sCamera::Viewport | 16 / 7 | 12 / 5 | 0 / 1 | 4 / 1 | 0xEAD580 / 0xEAD560 | 0xC006C4 / 0xC006E4 |
| F | uCamera / **uDevilCamera** / uIdCamera | 9 / 29 / 18 | 3 / 14 / 9 | 2 / 2 / 1 | 4 / 13 / 8 | 0xEADF28 / 0xE58878 / 0xE599A8 | 0xBC8C34 / 0xBC8C70 / 0xBDBDD0 |
| F | rDevilCamera / rCameraList | 23 / 7 | 10 / 5 | 2 / 0 | 11 / 2 | 0xE57678 / 0xEAEA08 | 0xB9B7E8 / 0xC0B3E0 |
| F | uFreeCamera / uMotionCamera / uMotionCameraBoss | 11 / 12 / 11 | 7 / 9 / 3 | 1 / 0 / 1 | 3 / 3 / 7 | 0xEAD8E0 / 0xEAE5C8 / 0xE5B9B0 | 0xC0444C / 0xC09ABC / 0xBF5DCC |
| F | uEfctCam / uModelCam | 21 / 21 | 7 / 8 | 2 / 0 | 12 / 13 | 0xE588F8 / 0xE59F48 | 0xBC9348 / 0xBE0CC8 |
| G | uGameOverCamera / uItemGetCamera / uPowerUpCamera | 12 / 13 / 12 | 4 / 5 / 4 | | 8 / 8 / 8 | 0xE59888 / 0xE599C8 / 0xE5ADF0 | 0xBDA148 / 0xBDBE24 / 0xBEB31C |
| G | uScreenBreakCamera / uUseItemCamera | 12 / 12 | 4 / 4 | | 8 / 8 | 0xE5B1F0 / 0xE5BED0 | 0xBEE01C / 0xBF900C |
| G | uLbryCamera / uLbryEnemyCamera / uLbryItemCamera | 11 / 16 / 14 | 4 / 9 / 7 | | 7 / 7 / 7 | 0xE59A48 / 0xE59AC8 / 0xE59AA8 | 0xBDCEB0 / 0xBDCF00 / 0xBDCF50 |
| G | uBossCameraTest / uEm027::uCamCtrl | 20 / 14 | 10 / 4 | | 10 / 10 | 0xE5C450 / 0xE593B8 | 0xBFE0E0 / 0xBD6760 |
| H | cam-named methods on other classes | 97 | 48 | | 49 | — | — |

**Not in DX9:** `rCameraList::CAMERA_INFO` (DX9 has `rCameraListXml` / `rCameraListXml::CameraInfo`
instead) and `uGUI_LbryBase::uLbryCamera` (SE-only; DX9 DTI 0xE59A48 is SE `uLbryCamera` — it is the
parent of the Enemy/Item library cameras and has the setZoom/isZoom slots the GUI variant lacks).
H-group SE-only: all 24 `uGUI_Lbry*` methods, `uPlayerSE`, `sCollision` anti-trembling pair,
`sMediator::setMiniGameCameraInfo`.

## Class hierarchy (DX9, from DTI registrations)

```
cUnit ─ uCamera ─┬─ uDevilCamera ─┬─ uCameraBoss ─┬─ uCameraBossDante
                 │                │               └─ uCameraBossEm018/019/021/022/023/025/026/029/030
                 │                ├─ uCameraCtrl
                 │                ├─ uBossCameraTest
                 │                └─ uIdCamera ─┬─ uGameOverCamera, uItemGetCamera, uPowerUpCamera,
                 │                              │  uScreenBreakCamera, uUseItemCamera
                 │                              └─ uLbryCamera ─┬─ uLbryEnemyCamera
                 │                                              └─ uLbryItemCamera
                 ├─ uFreeCamera
                 └─ uMotionCamera ─ uMotionCameraBoss
MtObject ─ cCameraBase ─┬─ cCameraPlayer
                        └─ cCameraRailBase ─┬─ cCameraRail, cCameraRailEm025, cCameraRailEm026
                                            └─ cCameraPan, cCameraNormal
cSystem ─ sCamera        uDevil4Model ─ uModelCam, uEm027::uCamCtrl        uDevil4Effect ─ uEfctCam
```

`uCamera` and `uDevilCamera` are abstract in DX9 (generic abstract-DTI vtable 0xB8E3B0, no
`MyDTI::newInstance`).

## Vtable slot shifts (SE → DX9)

- **uCamera / uDevilCamera / uIdCamera / uCameraBoss\* / uCameraCtrl / Lbry cameras** (same map):
  SE 0–5 → 0–5 (dtor, createUI, isEnable, createProperty, getDTI, setup); SE 8 `move` → 6;
  SE 9 → 7; SE 11 `sync` → 8; SE 12 `draw` → 9; SE 18, 19 → 10, 11; SE 21 `kill` → 12;
  SE 24/25 `getViewMat`/`getProjMat` → 13/14. SE 10 `moveAfter`, 13–17, 20, 22, 23 have no DX9
  slot. DX9 has 15 slots against SE's 26. Lbry: SE 26/27 (setZoom/isZoom) → 15/16.
- **cCameraBase family** (cCameraPlayer, rail/pan/normal, camera data): **no shift** — same slot
  numbers in both builds.
- cResource (rDevilCamera, rCameraList): SE 10–12 → 8–10, SE 14 `clear` → 11.

## Structural notes

- `uDevilCamera::move_tick*` / `move_tick_mode0..6` and `uDevilCamera::resolveMovement` were
  earlier-session placeholders inside the uCameraBoss code. They are the per-class
  `uCameraBoss{Dante,Em018…Em030}::commonProccess` functions and `uCameraBoss::checkHit` — all
  replaced (`was:` kept in the comments).
- `uCameraBoss::sync` has no body in DX9: slot 8 is the shared thunk 0x749630 (`j_uDevilCamera::sync`,
  now named `uIdCamera::sync`, ICF comment lists both).
- Empty `move` overrides of every uCameraBoss subclass and uCameraCtrl fold into `nullsub_2`
  (0x507330); left unnamed.
- Shared deleting destructors left unnamed: 0x455B10 (92 vtables, cCamera\* family), 0x49B290
  (~36 vtables, uIdCamera family + uBossCameraTest), 0x539290 (uEfct\*).
- ICF folds named for the region owner with `ICF-folded:` comments: rail `calcFov`/`calcRoll`/
  `calcZoomRate`/`calcLockOn`/`calcTargetLockOn*` (cCameraRail ↔ Em025 ↔ Em026),
  `uGameOverCamera::setup` = `uScreenBreakCamera::setup`, `uPowerUpCamera::setup` = Lbry-item /
  use-item setup, `cCameraPlayer::throwEm012` = `throwEm012Ex`, `uCameraBoss::checkAngleYinFan`
  (0x4C7A10) = `cCameraPlayer::checkAngleYinFan`.
- Functions defined from bare `loc_` code: ~60 (deleting dtors, `MyDTI::newInstance` stubs, a few
  ctors). Functions split: 0x4CD910 (Em018 newInstance / ctor 0x4CD930), 0x8B07B0
  (uBossCameraTest newInstance / ctor 0x8B07D0).
- Vtable labels fixed: the GameOver/PowerUp/ScreenBreak/UseItem camera vtables carried the owning
  UI unit's label (`uGameOver::vftable` …) — now `<Camera>::vftable`, so those units' own vtables
  are currently unlabelled. `0xBDCF00` was `uLbryItemCamera::vftable`, is `uLbryEnemyCamera`.
  0xB98C58 `MtDTI_vtbl42_` → `cCameraRailEm026::MyDTI::vftable`. ~50 `MyDTI::vftable` labels added.
- 0x428360 carried a false FLIRT library name (`Concurrency::…::GetIScheduler`); it is
  `cCameraRailBase::getBoxNum`.

## Multiplayer implications

- **Camera code reads the single player pointer far more than the "camera cluster" suggests.**
  With camera functions now named, the regenerated `RE/mpplayer_call_sites.json` shows
  **160 mpPlayer sites in 101 camera-class functions**. Before this pass only 19 of those sites
  (the 15 deep-dived functions) were in the `camera-per-player` category; the other 141 sites /
  86 functions — cCameraPlayer boss-camera setup, air-throw modes and Electrigger, every
  uCameraBoss\* class (50 fns), rail cameras, uBossCameraTest — were `uncategorized`, i.e. left to
  the writer-redirect step, which only works under a single global "active player".
  **Fixed:** `build_mpplayer_sites.py` now puts every camera-class function in `camera-per-player`
  (160 sites); the patch plan's step 3 is updated accordingly.
- `sMediator::mpCamera` (+0xD0, SE +0x140, ~99 reader functions) is a single camera slot — per-player
  state. `mpCameraBoss` (+0xD4, SE +0x144, ~42 readers) is per encounter but feeds each view. Both
  accessor pairs are inlined in DX9 (no function to hook). 0x4C39E0 (uCameraBoss vtable) writes the
  same value into both slots.
- Player-specific branches found: `cCameraPlayer::getPosGrabedEnemy` (Nero only),
  `uEm022::setBusterCameraEnd` (`mPlayerID == 1`), `cEventScript::killBossCamera` (gated on mpPlayer).

## Follow-ups (outside this pass, not changed)

- **0x44A910 `sGameState::player_spawn_state` is misnamed** — two workers independently matched it
  to SE `cEventScript::executeCode` (it calls `cEventScript::killBossCamera`). The mpPlayer docs
  cite that name.
- 0x404CA0 `uFreeCamera::newInstance` is a free-camera spawn helper; the real `MyDTI::newInstance`
  is 0x9197A0.
- `sVibration::req_simple` / `req_at_pos` / `req_with_parent` / `alloc_slot` / `rec_*` (commented as a
  "particle_pool") are SE's vibration code (`reqVib` ×3, `openVibControl`, `VibControl::start`,
  `updateFadeParam` 0x90A1B0).
- `uCameraCtrl::check_box` (0x4F7C50) = SE class-less static `check_box` (0x68BE40).
- The DTI globals keep old labels (`stru_E56xxx`, `mParent__0`).
- Not saved: run `idb_save` when you're happy with the pass.
