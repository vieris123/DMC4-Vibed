# Nero's charge shot: why it launches enemies that are down (DX9)

Traced in IDA on 2026-10-27 (DX9 IDB). Scarecrows (`uEm000Base`) were followed end to end. Function comments were
added in the IDB; the IDB isn't saved.

**Short answer:**
- The check isn't "on the ground" (`AS_GROUND` 0x1). It's **`AS_DOWN` (0x4): the enemy is lying knocked down**.
- It lives in each enemy's `blownMessage`, and only runs once the shot has filled the enemy's **blown gauge**.
- A down enemy gets the High Time launch (action 93). A standing or airborne enemy is blown back (action 91).

## 1. The shot

- `uPlayerNero::moveAtckBlueRoseChargeShot` 0x801750: phase 3 calls `uPlNeroShl001::create(level)`, with
  level 0 / 1 / 2 for charge actions 45 / 46 / 47.
- `uPlNeroShl001::setup` 0x82C870:
  - Loads `Collision\wp000` (`.atk` + `.col`).
  - Puts collision group 2 / 3 / 4 (by level) on the shell.
  - Line-casts from Nero (+150 cm) to the shell's start point. If that hits a wall, `setWallHit` is called.
- `uPlNeroShl001::hitMessage` 0x82D820 (vtbl +0x94, called by `uActor::damagePreMessage` 0x4A7F30 before the
  target handles the hit) picks a distance band from Nero to the hit point:
  - 0 = near.
  - 1 = beyond Nero param +0x190.
  - 2 = beyond Nero param +0x194.
- It then copies `.atk` entry `[2, 9, 12 | 3, 10, 13 | 4, 11, 14][level × 3 + band]` into the group's
  `mAttackStatus` (+0xA4, `rAttackStatusData::get` 0x5099E0).

The charge entries in `wp000.atk` (vanilla), Short / Midd / Long:

| Level | mAttackID | Damage | mAttackLvI / LvB | mDamageType / I / B |
|---|---|---|---|---|
| Lv1 | 7 | 200 / 150 / 100 | 2 / 2 | 0 / 0 / 2 BLOWN |
| Lv2 | 8 | 300 / 250 / 200 | 3 / 3 | 0 / 0 / 3 BLOWN2 |
| Lv3 | 9 | 400 / 350 / 300 | 4 / 4 | 0 / 0 / 3 BLOWN2 |

Normal shots have mAttackID 0, LvI 1, LvB 0 and type B 2.

## 2. Picking the reaction: `uDamage::calc` 0x51BE10

The enemy's `damageMessage` (Scarecrow 0x557D50) calls `calcPlEmCorrect` and then `calc`. `calc` works with two
gauges of 5 levels each from the enemy's defend status (`.dfd`): `mBlown[5]` / `mMaxBlown[5]` and
`mInterrupt[5]` / `mMaxInterrupt[5]`. It checks them in this order:

1. **Blown gauge.** n = `mAttackLvB` (+ `mLvCorrect`, capped at 4). For each level k ≤ n with
   `mMaxBlown[k] ≥ 1`: `mBlown[k] += mPointCorrect + 1`.
   - If one reaches its max: the group's `mDamageType = mDamageTypeB` and `mAttackLv = n`.
   - Then, unless `mState` & 4, it calls **`blownMessage`** (vtbl +0xC8).
2. **Interrupt gauge**, the same with `mAttackLvI` → `mDamageTypeI`. It calls `interruptMessage` (+0xC4) unless
   `mState` & 2.
3. Neither gauge full: `injureMessage` (+0xC0), unless `mState` & 1.

`damagePreMessage` resets `mDamageType` to `mDamageTypeI` before this, so a blown verdict is the only way to get
type B.

## 3. Scarecrow `blownMessage` 0x558180

- Clears `mChargeShotHit`, `mEmBlown2Hit` and `mEmLeanHit`, and the AI's think flags.
- `t = kAttackStatus::getEmDamageType(group+0xA4)` (0x463E40). It reads `mDamageType` (+0x2C) and maps the player
  types 9 / 10 / 12 / 13 to 0 / 1 / 2 / 4.
- What happens next:

| Condition | Result |
|---|---|
| t == 4 (UPPER) | `setAction(93)` |
| t == 5 (GROUND) | `setAction(99)` (beat down) |
| t == 3 | also sets `mEmBlown2Hit` |
| t == 8 | also sets `mEmLeanHit` |
| **mAttackID 7 / 8 / 9 (charge shot)** | `checkSetPushShl`, `mChargeShotHit = 1`, then **`mActorStatus & AS_DOWN` → `setAction(93)`, else `setAction(91)`** |
| Any other attack | `setAction(91)` |

- In every case it sets `mDamage.mResetBlownReq`.

What the actions are (`uEm000Base::setAction` 0x541110):
- **Action 91 = `setDamageBlown`** 0x54F9E0: motion 53, routine 92, keeps the yaw.
- **Action 93 = `setDamageHighTime`** 0x5503A0: motion 57, routine 94, velocity cleared.
  - `damageHighTime` 0x5503F0 launches the enemy straight up.
  - The table at 0xDCC210 gives height 450 cm and time 35.5 frames for em000 / 001 / 003, plus a 0.2 term added
    once it starts falling. The launch speed is `2h / t` and the acceleration `-2h / t²`, i.e. it peaks 450 cm up
    after 35.5 frames.
  - It then falls; once it lands past frame 31 of the motion, it plays motion 58, then goes down (action 103).
- This is the same reaction a damage-type-4 (UPPER) attack such as High Roller gives. A charge shot gets it only
  when the enemy is down.
- `interruptMessage` (0x558090, for comparison) picks by status too: `AS_AIR` → 95, `AS_DOWN` → 97, otherwise
  87 / 89 / 101.

## Other enemies

A pattern scan of every `*::blownMessage` for a load of `mAttackID` followed by compares with 7, 8 and 9 finds the
charge-shot branch in:
- em000Base, em005, em008_009Base, em010, em013, em015, em016, em017, em023, em029, em030 and EmSample.
- Of these, em000Base, em008_009Base, em010, em017, em029 and em030 also test `mActorStatus & 4`.

Only Scarecrows were read in full.

## Changing it (dmc4_hook)

- **To launch standing enemies as well:** patch the `test byte ptr [esi+0EA8h], 4` / `jnz` at 0x55825A / 0x558276
  in the Scarecrow handler (and the matching spot in each listed class).
- **To make a charge shot launch without the down check:** give its `.atk` entry `mDamageTypeB` = 4 (UPPER). The
  t == 4 branch comes first, so every class that maps 4 to High Time launches it.
- **To reach the blown verdict sooner:** that depends on the enemy's `.dfd` `mMaxBlown` and the entry's
  `mAttackLvB`.
