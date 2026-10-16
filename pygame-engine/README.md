# War4Balls: Python + moderngl edition

One codebase does two things:
- a real-time window you can watch or play,
- deterministic offline video export to a high-bitrate 1920×1080, 60 fps MP4 via ffmpeg.

It ports every rule from `web-game/js/game.js`.

## Install (Windows / macOS / Linux, Python 3.10+)

```
pip install -r requirements.txt
```

ffmpeg must be on PATH for export. On Windows: `winget install ffmpeg`, or download it from gyan.dev and add `bin/` to PATH.

Chinese labels need a CJK font. It is found automatically on:
- Windows: Microsoft YaHei
- macOS: PingFang
- Linux: Noto Sans CJK

Or drop any CJK font at `assets/font.ttf`.

## Run

```
python main.py                         # real-time window (auto-pilot, watch)
python main.py --seed 7 --player 2     # you are blue: keys 1-5 directly fire 散弹/机枪/护盾/大球/狙击
python main.py --export out.mp4 --seed 7 --duration 660          # full match, offline
python main.py --export late.mp4 --seed 7 --start 450 --duration 30   # simulate to 7:30, record 30 s
python main.py --shots 2,30,300 --seed 7 --outdir shots          # PNG frames (headless)
```

Real-time keys:
- `Space`: pause
- `+` / `-`: sim speed ×2 / ÷2
- `1`–`5`: directly fire the matching item for the selected player team (big-ball casts use the baseline value when no marble landed)
- `R`: new match (next seed)
- `F11`: fullscreen
- `Esc`: quit

Export options:
- `--crf` (default 12, lower = more bitrate) and `--preset` (default `slow`).
- `--samples` sets MSAA (default 4).
- `--glow` sets bloom strength (default 0.55).

The same seed always gives the same match, frame for frame. All randomness comes from one `numpy.random.Generator`, pymunk is stepped with a fixed timestep, and the numba kernels are deterministic.

Headless export needs an OpenGL 3.3 context. It uses moderngl's standalone context (GLX, or EGL as fallback). On a Linux server without a display, run it under `xvfb-run`. On a desktop it uses your GPU directly.

## Engine choices

| Part | Choice | Why |
|---|---|---|
| Rendering | **moderngl** (GLSL 330) | Same render code for window and offscreen FBO. Instanced SDF shapes give tens of thousands of crisp anti-aliased primitives per frame. The territory is a GLSL shader. MSAA plus a separate half-resolution bloom layer. |
| Window / input / fonts | **pygame-ce** | Robust Windows window and GL context, keyboard, and font rasterisation for the glyph atlas. Rejected: moderngl-window (another windowing layer with nothing extra we need) and arcade (its sprite/shape pipeline adds per-object overhead, and custom territory shaders plus an offscreen export are harder). |
| Left board physics | **pymunk** (Chipmunk2D) | Real rigid bodies:<br>• kinematic rotating hexagon peg clusters (contacts use true surface velocity)<br>• round-capped walls and dividers<br>• sensors for cups and item slots<br>• a `pre_solve` value gate |
| Bullets / territory | **numpy + numba** | Up to 9000 bullets: one JIT kernel moves them, paints cells, cancels opposing bullets and chips shields in a single pass. |

## Rules (ported)

- **Opening:** at 0.5 s each base fires a sniper toward the centre, painting a thick line. The rounds meet at about 2 s and burst into a radial paint spray. Turrets start after that.
- **Paint rule (strict, UnityDots-style):** each bullet sweeps every grid cell touched by its full tick path, including diagonal corner touches. It passes through its own colour, then converts only the first foreign or neutral cell and dies. Opposing bullets whose swept paths touch the same cell cancel symmetrically before paint is applied, independent of processing order. Bullets bounce off arena walls (2 bounces, 15% speed loss per bounce).
- **Turrets:** sweep continuously and snap-lock (9 rad/s) onto enemy big balls within half the map. Each locked base grinds a big ball for 80K/s after its 5 s arrival grace period.
- **Big balls:** brushes that paint while moving.
  - A landed marble produces a ball with at least 3M strength and otherwise twice the marble value. It travels at 72 px/s, slower than bullets, and has a 5 s turret grace period.
  - Enemy paint erodes value at 0.12/s. A shield contact trades the same amount from ball strength and shield HP, then the ball bounces. The ball remains in play for up to 30 reference seconds.
- **Items:**
  - 散弹: 240 normal-paint bullets in a symmetric 25° cone (±12.5° around the barrel), with a short golden fan flash and bright pellet tracers.
  - 机枪: a 5 reference-second stream (scaled with `--match`) at 12 rounds per 1/60 reference second, rendered with long gold-white tracers and a muzzle ring.
  - 护盾: +max(250K, 3% of current HP), capped at 16M, with a precise HUD update, floating amount, and a 2.8 s expanding cyan ring.
  - 大球: see the strength, speed, grace, erosion, and shield-trade rules above.
  - 狙击: a 1500 px/s piercing round aimed at an enemy base, with a bright cyan head and white core streak as it paints to the edge.
- **Item triggers:** each physical bottom slot maps directly to its displayed label: 散弹/机枪/护盾/大球/狙击. A landing fires that slot's effect immediately for that marble's team and consumes the marble; it does not add then spend an inventory charge. This is an intentional departure from the independent LOOP item ticker described in the Douyin ep6 notes. Keyboard keys 1–5 are direct casts for the selected player team.
- **Cast aiming:** offensive casts (散弹/机枪/大球/狙击) snap the team's barrel toward its nearest living enemy base before firing, then hold that heading briefly; the machine gun holds it for its full stream. This is a deliberate choice so a marble rewarded by an item slot produces an immediate battlefield effect instead of inheriting the turret's random sweep direction.
- **Base display:** top number is the shield (starts at 8.0M); bottom is the ammo pool (starts at 249,968). Ammo at 0 only idles the turret.
- **Elimination and result:** a base is alive exactly while its shield is above 0. The last living base wins. If all shields reach 0 in the same tick, the match is a draw. At the time limit, remaining bases are ranked by territory share, then remaining shield, then fixed team order (red, green, blue, orange).
- **Pacing:**
  - `--match 300` compresses reference-time schedules and firing rates to a five-minute match while leaving projectile and marble movement speeds unchanged.
  - The weakest alive base takes ramping damage after about 7:10, 8:40 and 10:10.
  - From 10:15, sudden death drains every non-leader, so there is a survivor by about 10:50.
  - A flood wave from the leader runs after 7:20.
- **Left board:**
  - The emitter releases small mixed-colour marbles (values 1–8).
  - A cup multiplies the value by its X and teleports the marble to the top centre.
  - The buffer strip lets marbles ≥262K through (with a sparkle trail); smaller ones are boosted back up.
  - An item slot triggers on sensor entry and consumes the marble. Slot counts emerge from marble paths; ref2's 5/17/11/14/6 counts at 6:25 are reference observations, not a forced probability table.
- **Fairness:**
  - Each team has its own marble cap, plus a rotating first pick for a free slot.
  - Bullet processing order is shuffled every tick.
  - Spin directions are random per team.

## Fixed bugs from the web build

1. **Marbles parked on item-divider tops:** dividers and cup walls now have round caps, plus a stuck detector. If a marble barely moves for 0.5 s it gets nudged, or, if it is resting on a cup mouth, it counts as landing in that cup.
2. **Laser line on every big ball:** removed. Lasers are drawn only for the sniper item.
3. **Bullets in puffs:** each turret now emits a constant bullet rate. Every bullet starts at a random point within the tick, so the stream is continuous. The angle spread is half the old one (triangular ±0.063 rad).
4. **Blurry picture:**
   - Everything renders at native 1920×1080 with 4× MSAA and analytic SDF edges.
   - Text uses pixel-aligned glyphs.
   - Bloom is only a subtle additive half-resolution layer; the frame itself is never blurred.
5. **Item marble bouncing back out:** item slots are sensors. Entering one triggers the item and removes the marble immediately.
6. **Item casts that looked inactive:** offensive casts now aim at a living enemy; shotgun pellets and machine-gun rounds have distinct high-contrast tracers; shields add a visible fraction of HP; and big balls have enough strength and protection to reach a shield. These are deliberate cast behavior and balance changes. The bullet kernel still applies the same strict first-foreign-cell rule and symmetric cancellation to every shotgun and machine-gun bullet.

## Tools

```
python tools/sim_batch.py 16 1      # 16 headless matches: winner distribution, eliminations, items at 6:25
python tools/board_check.py 1 400   # stuck marbles, gate-by-value, item trigger/consume
python tools/item_pipeline_check.py 1,7,42 180
python tools/mechanics_check.py 1,7,42,2001
python tools/compare.py shots 7 sheet.png 30:douyin_detail_t0030 200:douyin_detail_t0320
```

After a result is decided, simulation state freezes. `--shots` and `--export` therefore show the same final state for any requested time after game over.
