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
python main.py --seed 7 --player 2     # you are blue: keys 1-5 fire 散弹/机枪/护盾/大球/狙击
python main.py --export out.mp4 --seed 7 --duration 660          # full match, offline
python main.py --export late.mp4 --seed 7 --start 450 --duration 30   # simulate to 7:30, record 30 s
python main.py --shots 2,30,300 --seed 7 --outdir shots          # PNG frames (headless)
```

Real-time keys:
- `Space`: pause
- `+` / `-`: sim speed ×2 / ÷2
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
- **Paint rule (strict, UnityDots-style):** a bullet flying over its own colour keeps going. On the first foreign or neutral cell it converts exactly that cell and dies. Opposing bullets in the same cell cancel. Bullets bounce off arena walls (2 bounces, 15% speed loss).
- **Turrets:** sweep continuously and snap-lock (9 rad/s) onto enemy big balls within half the map. Locked streams grind the ball (−550K/s per base).
- **Big balls:** brushes that paint while moving.
  - They lose value over enemy paint (×e^−0.95 per second) and keep flying after their base dies.
  - Against a shield the trade is roughly 1:1: both lose 0.81 × min(ball, shield), and the ball bounces off.
- **Items:**
  - 散弹: 90 normal bullets in a symmetric 25° cone (±12.5° around the barrel), same rules as the stream.
  - 机枪: 2.5 s straight stream.
  - 护盾: +HP with a floating "+20K"-style number.
  - 大球: big ball.
  - 狙击: instant beam painting a solid line to the edge.
- **Base display:** top number is the shield (starts at 8.0M); bottom is the ammo pool (starts at 249,968). Ammo at 0 only idles the turret.
- **Elimination:** at shield 0 the base explodes and its turret is removed. Last survivor wins.
- **Pacing:**
  - The weakest alive base takes ramping damage after about 7:10, 8:40 and 10:10.
  - From 10:15, sudden death drains every non-leader, so there is a survivor by about 10:50.
  - A flood wave from the leader runs after 7:20.
- **Left board:**
  - The emitter releases small mixed-colour marbles (values 1–8).
  - A cup multiplies the value by its X and teleports the marble to the top centre.
  - The buffer strip lets marbles ≥262K through (with a sparkle trail); smaller ones are boosted back up.
  - An item slot triggers on sensor entry and consumes the marble. Item mix follows ref2 (5/17/11/14/6).
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

## Tools

```
python tools/sim_batch.py 16 1      # 16 headless matches: winner distribution, eliminations, items at 6:25
python tools/board_check.py 1 400   # stuck marbles, gate-by-value, item trigger/consume
python tools/compare.py shots 7 sheet.png 30:douyin_detail_t0030 200:douyin_detail_t0320
```
