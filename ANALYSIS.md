# War4Balls pygame-engine mechanic audit

**Scope:** static review of `pygame-engine/war4balls/{sim,board,kernels,config,render}.py`, its README/tools, and the supplied reference notes. No game/tests were run and no implementation files were changed. This is an internal logic review, not a claim that the simulation matches the unavailable original JavaScript source.

**Initial review status:** the statements above record the code as found before the task fixes. The execution checklist below records verification and supersedes any stale finding text.

## Findings

### Defects and material inconsistencies

1. **Opposing-bullet cancellation is unreachable in normal grid states — high.**

   `step_bullets()` only registers a bullet in the occupancy table inside `if ow == t` (it crossed a cell already owned by its team), then tries cancellation if that same cell was registered by a different team (`kernels.py:44-52`). In a single tick, the grid owner is one fixed team: two opposing bullets cannot both reach this registration branch for the same cell. If they meet in a neutral cell, the first paints and dies; the second then sees that paint as foreign, overwrites it, and dies (`kernels.py:53-62`). Thus the README rule “opposing bullets in the same cell cancel” is not implemented; paint outcome instead depends on shuffled processing order (`README.md:62`, `sim.py:348-354`).

2. **The “strict first foreign cell” rule is sampled at the endpoint, not traversed — medium/high.**

   Each bullet advances by its full per-tick displacement (`kernels.py:19-24`) and checks only the single grid cell containing its new endpoint (`kernels.py:38-44`). It never tests cells crossed between the prior and new positions. At the configured grid scale (`config.py:8-10`), normal bullets can move farther than one cell per 60 Hz tick, so a bullet can skip intervening neutral/enemy cells or a narrow shield boundary. That makes the documented first-cell paint rule an approximation, not a strict swept-path rule (`README.md:62`).

3. **Timeout can award a winner without a last survivor; zero survivors are not handled — high.**

   Shield-zero elimination is correctly centralized in `hit_base()` (`sim.py:109-117`). However, at `tp >= MATCH`, if more than one team remains, the code awards victory to the team with the largest painted share (`sim.py:410-416`), despite the stated “last survivor wins” rule (`README.md:74`) and the requested last-base condition. There is also no zero-alive branch: late wave selection calls `max(al, ...)` once `tp > 440` (`sim.py:291-297`), and timeout selection also calls `max(al, ...)` (`sim.py:413-416`). If all bases are eliminated before the match ends, a later tick can raise `ValueError` instead of ending as a draw/defined result.

4. **The implemented board and first item do not match the supplied War4Balls ep6 notes — high if ep6 is the target.**

   The ep6 notes describe six multiplier pockets `x8, x4, x2 | x2, x4, x8` and a separate five-item LOOP ticker (`refs/douyin_rwsx/NOTES.md:14-16,23-27`). This engine has eight multiplier sensors and eight multipliers (`config.py:32-35`; `board.py:69-71`), with a physical five-slot bar (`config.py:38-42`). More importantly, its first item is `散弹`/shotgun, while ep6’s first item is `风暴`/storm (`config.py:41-42`; rendered at `render.py:221-233`). `use()` maps item 0 to 90 shotgun bullets (`sim.py:151-168`); it has no storm item case. The later leader flood waves (`sim.py:290-305`) are automatic pacing events, not a storm-slot effect. This may be intentional because the README says the engine ports a different `web-game/js/game.js` and the local `ref2` notes describe an eight-cup MarblePi layout; the referenced JavaScript source is not present in the inspected tree (`README.md:7`). It should not be treated as ep6 fidelity without resolving which source/spec is authoritative.

5. **Big-ball strength is not tied to the marble that lands in the item slot — medium/high reference mismatch.**

   The board passes only `(team, item-index)` into `use()`; it does not pass the landing marble’s value (`board.py:225-237`). The big ball is instead assigned a random time-based power with exponent capped at 23, i.e. at most 8,388,608 (`sim.py:180-184`). The ep6 notes report a 7.8M sphere plus a +34M firepower label (`refs/douyin_rwsx/NOTES.md:26`); the separate 16:18 detail notes show later 347M/537M balls (`refs/douyin_detail_notes.md:183-187`). If a landed marble is intended to size the corresponding item effect, that linkage is absent. The engine’s internal rule is deterministic/random-by-time, but it does not reproduce those larger observed values.

6. **The shield item silently becomes a no-op at its cap — medium.**

   Shield use adds at most 20K doubled every 90 reference seconds, capped at 320K per use, while total HP is capped at 16M (`sim.py:172-179`). When HP is already 16M, `actual` is zero, yet `use()` still returns success and the board records/flashes the item as fired (`board.py:229-237`). That is mechanically consistent with “consume on landing” but can produce a counted item with no gameplay effect. If that is intended, the UI/event should distinguish a capped shield from a successful buff.

7. **Current direct-trigger flow makes inventory/keyboard item use mostly redundant; cap overflow can consume a stored charge — medium/edge case.**

   Every live item-slot landing first increments `items[team][it]`, then immediately calls `use(..., force=True)`, which spends one charge (`board.py:229-237`; `sim.py:90-92,137-149`). Under ordinary operation the count therefore returns to its prior value (normally zero), so the manual `1`–`5` controls and AI inventory chooser have nothing to use (`main.py:121`; `sim.py:239-248`). If a bag is already at its 99-charge cap, `give_item()` does not add a charge but `use()` still removes one; the landing consumes a previously stored charge (`sim.py:90-92,137-149`). This edge is unlikely in the current flow but follows directly from combining inventory with immediate firing. For the user’s immediate-fire spec, a direct effect call with no temporary inventory accounting is the cleanest model.

8. **Machine-gun duration disagrees with its own documentation — low/medium.**

   `use()` sets `mg[team] = 3.0` seconds (`sim.py:169-171`), but the README says 2.5 seconds (`README.md:69`). The emitted stream decrements the timer by `dt` (`sim.py:236-238`). Pick one duration and align the rule text.

9. **The 300-second preset does not compress every timer consistently — medium for that mode.**

   `Game` defines `k = match / MATCH` and says the 300-second preset compresses pacing timers (`sim.py:26-29`). Several pacing variables still use unscaled simulation seconds: power drift every 6 seconds (`sim.py:277-283`), machine-gun duration (`sim.py:169-170,236-238`), and big-ball lifetime (`sim.py:307-310,337-344`). Meanwhile board spawn cadence multiplies by `sim.k` (`board.py:196-199`) and reference-time decisions use `tp`. Thus the shortened match changes the relative lifetime/strength of balls and boosts versus spawn/pacing. This is a preset consistency issue, not a problem with fixed-step determinism.

10. **“Instant beam” is not instant in this implementation — low/reference mismatch.**

    The README calls the sniper item an instant beam (`README.md:72`), but `use()` spawns a moving projectile at 1500 px/s and paints its traversed segment each tick (`sim.py:185-189,359-384`). It takes a fraction of a second to cross the map. Either the rule text or the intended behavior should be clarified.

### Rules that look internally consistent

- **Cup multiply/teleport and value gate:** the cup sensor queues a cup landing; `_land_cup()` increments the cup count, awards ammo using the multiplier, multiplies the marble’s value, rebuilds it, and returns it to the top emitter (`board.py:157-160,274-288`; `sim.py:83-88`). The gate admits `v >= 262144` and boosts smaller marbles upward (`board.py:166-174`; `config.py:43`), matching the notes’ 131K-bounce/262K-pass observations (`refs/ref2_notes.md:34-38`).
- **Requested immediate item action:** on bottom-slot entry, the engine grants then force-uses the corresponding item for `m.team` in the same `Board.tick()`, flashes the matching slot, records the event, and consumes the marble (`board.py:162-164,211-238`). The `force=True` path bypasses the big-ball pacing gate (`sim.py:137-148`). This matches the user’s explicit spec; it intentionally differs from the ep6 observation below.
- **Big-ball shield exchange:** at contact the ball loses `0.81 * min(ball_value, shield)` and the shield takes the same amount before the late-game multiplier (`sim.py:319-333`). That is roughly 1:1 under ordinary pacing. During late-game ramp, shield damage is multiplied by `late_k` while ball value is not (`sim.py:94-107,330-332`), so it stops being 1:1 by design.
- **Base elimination:** `hit_base()` clamps HP to zero and marks the team dead at `hp <= 0`, then zeros ammo and removes the lock (`sim.py:109-117`). The last-survivor branch wins if exactly one team remains (`sim.py:410-414`). The timeout and all-dead holes above are the exceptions.
- **Seeded fixed-step run:** one `numpy.random.Generator` is seeded in `Game`, shared with `Board`, and used for game randomness (`sim.py:26-30`; `board.py:43-47`). Offline simulation and real-time updates call the fixed `DT` (`main.py:61-77,122-127`); bullet order is randomized from that same generator (`sim.py:347-354`). Same seed, same code/dependency versions, fixed `DT`, and same player inputs should reproduce the run. There is no input/event recording or replay file, so a seed alone cannot replay a manually controlled run; cross-version bit-for-bit determinism is not established.

### Determinism / export inconsistency

After `over` becomes true, `tick()` continues simulating and only returns after updating the world; the winner value stays fixed (`sim.py:193-195,398-416`). This is documented as deliberate animation. However, screenshot mode stops stepping once `game.over` is true (`main.py:59-63`), while video export keeps calling `tick()` for every output frame (`main.py:74-78`). For requested times after an early win, `--shots` and the matching timestamp in an export can therefore show different world states. This does not break fixed-seed replay before the result, but it weakens output consistency.

## Item-trigger discrepancy and recommendation

The ep6 notes say the six multiplier pockets and five item ticker are separate systems; the item ticker advances independently and slowly, with many pocket hits producing no item tick or visible effect (`refs/douyin_rwsx/NOTES.md:14-27`). The current board instead has five physical bottom item sensors, and each landing immediately fires the matching item for that marble’s team (`board.py:79-82,211-238`).

**Recommendation:** keep the immediate per-marble trigger because it is the explicit user spec. Treat this as a deliberate departure from the recorded ep6 behavior: keep multiplier pockets/counters independent from the five item slots, and avoid describing the implementation as a faithful reproduction of ep6’s independent LOOP ticker. If ep6 visual fidelity is also required, use its six-pocket layout and storm/machine-gun/shield/big-ball/sniper item names/effects, while preserving immediate team-specific firing as the chosen gameplay rule. Do not silently pair multiplier pockets with item slots.

## Open-source search and reference status

I searched the web for `War4Balls` source, `MarblePi` source, `球球领土战争` source, and four-color territory-war / marble-Plinko code. I found **no verifiable public source repository for the War4Balls or MarblePi creator implementation** in those searches. This is not proof that no such repository exists.

- Closest code result: [`snezhinka-gw/ball-war`](https://github.com/snezhinka-gw/ball-war). **Checked:** opened the GitHub repository page successfully on 2026-10-16; it is a public Unity territory-war prototype with four factions, bases, a territory grid, rotating turrets, and ball/base combat. It does not describe the Plinko multiplier/item-trigger system in this repo. The page’s root listing did not show a license, and I could not verify licensing; do not assume that public visibility means reuse is licensed.
- Supplied ep6 link: [`https://v.douyin.com/RWSxLzMRJEg/`](https://v.douyin.com/RWSxLzMRJEg/). **Checked:** attempted a direct open and an exact-shortcode search on 2026-10-16. The browser tool could not access the URL and search returned no result, so I cannot independently confirm its current reachability. `refs/douyin_rwsx/NOTES.md:3-4` records this short link and a final Douyin video URL, but the workspace currently contains only `NOTES.md`, not `war4balls_ep6.mp4`. The notes describe a clean 22:19 capture (`NOTES.md:10-12`), while the task context says the available mp4 is partial/corrupt; I could not inspect the video itself, so the written observations are the basis for the source comparison.
- The local [`refs/ref2_notes.md`](refs/ref2_notes.md) is a separate MarblePi recording, not the ep6 source: it documents eight cups and the shotgun/machine-gun/shield/big-ball/sniper slots (`ref2_notes.md:13-23`). That explains why some current code matches ref2 while diverging from the ep6 notes.

## Overall assessment

The board’s core multiply → teleport → threshold → item-slot pipeline is coherent. The initial code defects were opposing-bullet cancellation, unswept bullet paths, missing all-dead result handling, cap-hit shield success UI, inventory add/spend behavior, and unscaled pacing timers. The engine intentionally retains the ref2 physical item slots under the user's direct-trigger rule rather than adopting ep6's independent ticker.

## Execution checklist (2026-10-16)

- [x] **1. Bullet cancellation:** verified the old occupancy branch could not pair opponents on neutral paint; replaced it with a swept-cell occupancy prepass that marks opposing paths symmetrically before paint order is applied.
- [x] **2. Strict swept paint:** DDA supercover now visits all crossed cells, including diagonal corner touches, stops at the first tick-start foreign/neutral cell, and traces the reflected route after wall bounces. Shield contact uses the crossed cell's rectangle so a thin base edge cannot be skipped.
- [x] **3. Results:** the last live base wins; all-dead resolves to a draw; timeout ranks survivors by territory share, shield HP, then red/green/blue/orange order. Late-wave selection is guarded by result resolution.
- [x] **4. Ep6 ticker discrepancy:** verified as a reference mismatch, not an implementation defect under this task. Kept physical slot → same-label immediate team effect and documented the intentional departure in `pygame-engine/README.md`; no LOOP ticker was added.
- [x] **5. Big-ball strength:** slot land passes the landed marble value to the big ball. Its existing slow speed and near-1:1 shield trade remain.
- [x] **6. Shield cap:** verified capped use previously returned success; it now produces no use/shield event, count, floater, flash, or success FX. Stored manual charges remain untouched on failure.
- [x] **7. Inventory/controls:** slot land calls the item effect directly without a temporary grant/spend. `1`–`5` are direct player casts; inventory-backed `use()` still spends one stored charge when explicitly used.
- [x] **8. MG/sniper docs:** set shared config values to 3 reference seconds and 1500 px/s; README now describes the moving sniper projectile rather than an instant beam.
- [x] **9. 300-second pacing:** scaled reference-time firing cadence (including MG/late bonus rates), item cooldowns, MG duration, power drift, opening launch, marble spawn/emitter cadence, and big-ball lifetime by `match / 660`; spatial movement speeds and animation lifetimes stay physical/visual.
- [x] **10. Export consistency:** game state freezes after result, and procedural frame sparkle placement derives from seed/frame so direct shots match exported frames after game over.
- [x] **README item-mix claim:** verified `ITEM_MIX` is not read by gameplay; reworded the listed ref2 5/17/11/14/6 values as observed sample counts, not an enforced probability table.
- [x] **A. Headless tests:** `item_pipeline_check.py` passed for seeds 1, 7, 42, 1185, 2001 (180 s); `board_check.py` passed for seeds 1, 42, 1185 (240 s, `--match 300`); new `mechanics_check.py` passed for seeds 1, 7, 42, 1185, 2001.
- [x] **B. Story search/export/review:** 200 seeds (1–200) at `--match 300`; best qualified seed 6 (284 s, orange winner, nine lead changes, third at midpoint, all five items, 5 snipers/8 MG). Export validated as 1920×1080, 60 fps, 18,000 frames, 300 s; 789,736,140 bytes. Send copy: 80,515,780 bytes. Reviewed opening, MG, big ball, sniper, shield, shotgun, and late frames at native resolution; post-game shot/export frame average absolute RGB difference was 2.0.
- [ ] **C. Sync/package/commit/push:** final source sync, archive rebuild, and remote push still pending.
