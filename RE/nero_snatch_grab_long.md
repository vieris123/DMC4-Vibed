# Nero's Snatch ("grab long"): how the enemy is held and pulled (DX9)

Traced in IDA on 2026-10-24, DX9 IDB. Scarecrows (`uEm000Base`, em000 / 001 / 003) are followed end to end.
The other enemies are covered only by what their `grabLongMessage` returns. Renamed in the IDB on 2026-10-24
(the IDB isn't saved yet): `uEnemy::moveGrabLong` (was sub_7355F0), `uEm000Base::grabBlownEndCallback` (was
sub_55E630) and `uEnemy::setGrabFailEffect` (was sub_734E10).

## Player side: hand -> hit

1. `uPlWpRightHand::moveActSnatch` 0x83BF00.
   - Phase 0 measures `Distance`: the chest joint to the lock-on target, or `getRightHandGrabDistance`.
   - At phase 0xC, custom message 20 / param 0 from the motion sets `clsn.mMvType = MV_TYPE_LONG_GRAB`
     (`MV_TYPE_LONG_GRAB_D` when Devil Trigger is on, phase 0x3C).
   - Phases 0x14 / 0x15: the hand moves out by `mSpeed = (Distance - 360) * 0.2` per frame
     (`mSnatchFrontOfs`).
2. `uCollisionCtrl::moveLongGrab` 0x83D770.
   - Phase 0: `setLongGrabCollision` puts the hand collision (group kind **5**) on the right-hand joint.
   - Phase 1: a line cast from the chest joint to the hand. If it hits the stage, `mGrabHitInfo` = type 1
     (the snatch fails against the wall).
3. When the hand touches an actor, `uCollisionCtrl::grabHitMessage` 0x83DFE0 runs two more stage line casts:
   chest -> hit point, and chest -> the target's position. If either is blocked, nothing happens. Otherwise it
   calls `grabHitMessageNormal` 0x83E260, or `grabHitMessageDevil` in DT.
4. `grabHitMessageNormal`, for `mActorType` (+0xEA4) 3 (enemies):
   - It calls the target's `uEnemy::grabMessage` (vtbl +0xDC).
   - Unless the result is 6, it gives **hit stop to both the enemy and Nero**: `hitStopMessage` (vtbl +0xCC)
     -> `setHitStop(group+0xCC)`. Result 6 becomes reaction 5 with no hit stop.
   - Result 3 also makes the enemy the auto-snatch target (`setAutoSnatchHitTarget`).
   - It stores `cGrabHitInfo{type 3 = HIT_LG_GRAB, reaction = result, pos, actor}` on Nero (+0xCCB0) and calls
     `setGrabHit`.
5. Back in `moveActSnatch`, message 20 / param 3 reads `reaction`:
   - `GR_PULL_FAIL` / `GR_PULL_FAIL_L`: phase 40.
   - `GR_PULL_ENEMY`: phase 30, or 60 in DT.
   - `GR_PULL_PLAYER`: phase 50 (Nero flies to the enemy).
   - `GR_PULL_RETURN`: phase 30.

`uEnemy::GRAB_REACTION`: 0 DEFAULT, 1 PULL_FAIL, 2 PULL_FAIL_L, 3 PULL_ENEMY, 4 PULL_PLAYER, 5 PULL_RETURN,
6 PULL_RETURN_NO_HITSTOP, 7 / 8 GRAB_FAIL(_L), 9-18 GRAB_SHORT_0..9, 19 GRAB_HITSTOP.

## Enemy side: `uEnemy::grabMessage` 0x734EE0

- Collision group kind (+0xB4):
  - 5 (Snatch) -> `grabLongMessage` (vtbl +0x160).
  - 6 (Buster) -> `grabShortMessage` (+0x15C), only when Nero's right hand holds this enemy (+0x2720).
- On 3 or 4 (and +0x14F0 == 0) it spawns effect `setEffectConst(1, 0xC)`, the Snatch hit flash. Then come
  vtbl +0x114 (a nullsub for em000) and `uActor::setGrabHitSE(result)`.

### Scarecrow: `uEm000Base::grabLongMessage` 0x5586D0

| Enemy state | What happens | Returns |
|---|---|---|
| Action 135 / 136 (guarding) | `setAction(135)`, `setGrabFailEffect` | 1 FAIL |
| (+0x5238) set, (+0x1500) == 2 and (+0x3FC) & 0x4000000 | nothing | 1 FAIL |
| Otherwise | `+0x18DC = 0x11111111`, `setAction(119)` | 3 PULL_ENEMY |

### Action 119: `setGrabBlown` 0x552B40 + `grabBlownNormal` 0x552CF0

`uEm000Base::setAction` 0x541110 runs the action's set function (vtbl +0x3B8). Like every damage action, it
clears `mThinkMgr.mbCheck[9]`, which cuts the AI off. **The enemy is held by its own routine.** Nothing in the
grab writes a "stunned" flag or timer.

`setGrabBlown` (skipped if the enemy is already `AS_GRAB`):
- `mActorStatus = AS_GRAB | AS_AIR`.
- `mGrabStartPos` = its current position.
- `mGrabEndPos` = the right hand's `mRetPos` (+0x33E0). `uPlWpRightHand::setSnatchReturnPos` 0x83C750 sets it
  to Nero's position plus an offset from Nero's parameter table (floats 139-141 of the table at Nero+0x1EA8),
  rotated by Nero's Y angle. **It's a fixed point in front of Nero, not the moving hand.**
- The enemy turns to face Nero (`moveAngleYNoRate`) and plays motion 150.
- Routine 121, or 125 when the elevation angle toward Nero is below -70 deg (`Em000_001_GrabFarAngle_Tbl` =
  70 / -70).

`grabBlownNormal` (the routine for 121 / 125) sets `mCollMgr.mWeightType = 1` **every frame** (the constructor
default is 5; the enemy's own value is saved at +0x19F0). What the weight type does wasn't traced: it isn't
read inside `uCollisionMgr`, so it's probably actor-vs-actor push priority. The routine runs in phases:

| Phase | Frames | What it does |
|---|---|---|
| 0 | 1 | `mCollMgr.mFall = 1`. `mTimer0 = T` (T = 10 frames for em000 / 001 / 003, table 0xDCC2D0). `uEnemy::initGrabLong`. Sets `mRoutineEndCallback = grabBlownEndCallback` (restores the weight type if something else interrupts the action). |
| 1 | 7 | **Hangs in place**: nothing moves it (no velocity step, no `addGravity`), status still `AS_GRAB`. Together with the hit stop above, this is the freeze you see before the pull. |
| 2 | T | Status `AS_DAMAGE | AS_AIR` (+0xEA8 = 10). `uEnemy::moveGrabLong` steps the pull. When `mTimer0` reaches 0: `mVel` x / z = 0, and y too unless routine 125. The weight type is restored. |
| 3 | until it lands | Falls (`addGravity`) until `mCollMgr.mLand` with `mVel.y <= 0`. Then velocity 0 and motion 151. |
| 4 | until the motion ends | `AS_DAMAGE | AS_DOWN`, `mAlignLand`. When the motion ends: `setAction(103)` = `setDownLoop(60)`, i.e. **60 more frames on the ground**, then `setWakeUp`. |

**The pull's motion** (`initGrabLong` 0x735400 + `moveGrabLong` 0x7355F0):
- Scarecrow gravity is `mGravity` = (0, -0.5, 0) cm/frame² (`Em000_001_Gravity_Tbl`).
- `d = mGrabEndPos - mGrabStartPos + (0, 0.25 T², 0)`. The extra 0.25 T² cancels the drop from gravity over T
  frames.
- Start velocity `mVel = 2d / T`, constant acceleration `mGrabLongGravity` (+0x14E0) `= -2d / T²`.
- Each frame: `pos += vel·dt + ½(a + g)·dt²`, then `vel += (a + g)·dt`.
- The enemy therefore lands exactly on `mRetPos` after T frames. Its pull velocity is 0 by then (only gravity's
  -0.5 T is left, and phase 2's end zeroes that too), so it stops dead in front of Nero and then drops.

**In total**, a Scarecrow is out of action for:
- hit stop,
- 7 frames hanging,
- 10 frames being pulled,
- the fall and the land motion,
- 60 frames down, then the wake-up.

The AI is off the whole time, because these are all damage actions.

## Other enemies' `grabLongMessage` results

The first check in most handlers returns 0 when a flag is set (+0x1590 / +0x158C / +0x1594: dead or not
grabbable).

| Class | Result |
|---|---|
| uEm005 / 006 | 0, or 4 PULL_PLAYER |
| uEm008_009Base (Mephisto / Faust) | Cloaked: cloak damage, stun counter, returns **6** (the cloak comes off, no hit stop, nothing pulled). Uncloaked and airborne: `setAction(61)`, returns 3. Some states return 1. |
| uEm010 (Frost) | `setAction(28)`, returns 3 |
| uEm010Ice | 4 |
| uEm011 | `setGrabBlown`, returns 3. Returns 6 / 1 in some states (one of them is an armour check). |
| uEm012 | 4 when (+0x2424) == 1 and (+0x243C) is set, else 2 FAIL_L + fail effect |
| uEm013 | `setGrabLong`, returns 3. Busy: 0. +0x148E set: 1. |
| uEm015 | `setGrabFar`, returns 3; or `setDmgRangeNokezori`, returns 4 |
| uEm016 | always `setGrabFar`, returns 3 |
| uEm017 | `setGrabSnatch`, returns 3 |
| uEm018 | 4, or 0 |
| uEm019_00 (frog) | Dodges (`set_em019_avoid`, returns 0) unless it's in a vulnerable state; then `set_em019_grabbed_far`, returns 3 |
| uEm021 parts / Shell | 4 |
| uEm022 | 4 when shielded, else `setAtkShield`, returns 3 |
| uEm023 | 4, or a fail effect |

Not traced: what the weight type 1 does, the Devil Trigger path (`grabHitMessageDevil`, `MV_TYPE_LONG_GRAB_D`),
and the hit-stop length (`cCollisionGroup` +0xCC of the hand group, from `uCollisionCtrl::mLgAttackStatus`
0xE13BC0).
