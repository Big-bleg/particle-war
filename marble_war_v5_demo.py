#!/usr/bin/env python3
"""粒子领地大战 v5 · 约 10 秒演示片.

展示全部 v5 新需求（非完整 10 分钟对局）:
  左侧共享双层 Plinko（倍率金字塔 + 传送叠倍率 + 四道具）;
  左侧专用提示条; 右侧四角单管机枪、护盾数字、带数子弹实时衰减;
  中心 Boss、停转对 Boss、按伤害分 8 倍奖池到左侧球倍率.
  无等级 / 无加速冰冻 / 无解说语音 / 无白钉点 / 无右侧技能条幅.
  无阶段系统（无发育/扩张/混战/决战）；唯一事件标记「Boss 来袭」.
  左侧倍率碰撞: Pymunk (Segment 斜面 + Circle 球, e≈0.8); 右侧涂色仍为 numpy.
"""
from __future__ import annotations
import math, os, subprocess, wave, time, argparse
import numpy as np
import pymunk
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FPS, W, H = 30, 1920, 1080
G = 900                                  # battlefield size
MX, MY = W - G - 18, (H - G) // 2        # map origin
TIP_X0, TIP_W = 8, 168                   # left tip strip
PX0 = TIP_X0 + TIP_W + 10                # plinko left
PX1 = MX - 14                            # plinko right
PTOP, PBOT = 92, H - 28
PW = PX1 - PX0                           # plinko width
LAYER1_Y = PTOP + 34                     # spawn height (top center)
LEDGE_Y = PTOP + 430                     # ~45% height: multiplier ledge (upper half = bounce-back zones)
SLOT_H = 52                              # multiplier chute depth below ledge
ROW_Y = PBOT - 104                       # lower row top: teleport + items
ROW_H = 84
GRAVITY = 420.0                          # px/s^2 — followable (slower than prior 760)
VMAX = 300.0                             # px/s clamp — slow cap
BALL_R = 9                               # small so exact 1/mult widths fit (16× = 2r+5)
PAINT_COST = 0.012
PROT_R = G / 8.0                        # protected circle radius around each base (~1/8 map)
OPEN_AIM_F = int(2.4 * FPS)              # opening: all guns aim center + spray, then clockwise
                       # number lost per enemy pixel painted (real-time decay)
NMAX = 8000
SUB = 4
MULTS = [2, 4, 8, 8, 4, 2]                     # left-right SYMMETRIC ledge
POWERS = ["护盾", "大球", "散射", "激光"]
POW_COL = {
    "护盾": (120, 240, 255), "大球": (255, 120, 210),
    "散射": (255, 150, 90), "激光": (255, 90, 200),
}
TEAMS = [
    ("红队", (238, 64, 92)),
    ("蓝队", (52, 128, 255)),
    ("绿队", (40, 200, 120)),
    ("金队", (250, 182, 40)),
]
NEU, BOSS_C, VOID = (58, 60, 78), (46, 18, 66), (12, 6, 14)
DEMO_SEC = 10.0
DEMO_F = int(DEMO_SEC * FPS)             # 300


# ---------------------------------------------------------------- helpers
_fc = {}
def font(sz):
    sz = max(10, int(sz))
    if sz not in _fc:
        _fc[sz] = ImageFont.truetype(FONT, sz)
    return _fc[sz]


def ctext(d, cx, y, s, fn, fill, sw=2, sf=(0, 0, 0)):
    d.text((cx - d.textlength(s, font=fn) / 2, y), s, font=fn, fill=fill,
           stroke_width=sw, stroke_fill=sf)


def fmt_num(v):
    v = float(v)
    if v >= 1e9: return f"{v/1e9:.1f}B"
    if v >= 1e6: return f"{v/1e6:.1f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return str(int(max(0, round(v))))


def floor_pow2(x):
    """Down to nearest in {1,2,4,8,16}; 0 if x < 1."""
    for v in (16, 8, 4, 2, 1):
        if x >= v:
            return v
    return 0


def boss_reward_shares(dmg):
    """Assign multipliers from 8x pool by damage share; sum <= 8."""
    tot = float(sum(dmg))
    if tot <= 0:
        return [0] * len(dmg)
    raw = [(d / tot) * 8.0 for d in dmg]
    shares = [floor_pow2(r) for r in raw]
    # Prefer larger raw first when trimming
    order = sorted(range(len(shares)), key=lambda i: (-raw[i], i))
    while sum(shares) > 8:
        trimmed = False
        for i in order:
            if shares[i] > 0:
                # step down one power-of-two rung
                shares[i] = {16: 8, 8: 4, 4: 2, 2: 1, 1: 0}[shares[i]]
                trimmed = True
                if sum(shares) <= 8:
                    break
        if not trimmed:
            break
    return shares


def corner_bases(nt, g):
    """4 teams → corners; >4 → regular polygon vertices (bases on sides)."""
    m = 48.0
    if nt == 4:
        return np.array([
            [m, m], [g - m, m], [g - m, g - m], [m, g - m]
        ], dtype=np.float64)
    # polygon: place bases at vertices of regular n-gon inset
    cx = cy = g / 2.0
    r = g / 2.0 - m
    ang0 = -math.pi / 2  # top vertex first for odd n looks nicer; for even, rotate
    if nt % 2 == 0:
        ang0 += math.pi / nt
    pts = []
    for i in range(nt):
        a = ang0 + 2 * math.pi * i / nt
        pts.append([cx + r * math.cos(a), cy + r * math.sin(a)])
    return np.array(pts, dtype=np.float64)


def voronoi_grid(bases, g, rng):
    nt = len(bases)
    yy, xx = np.mgrid[0:g, 0:g].astype(np.float32)
    wx = xx + 12 * np.sin(yy / 41 + rng.uniform(0, 6))
    wy = yy + 12 * np.sin(xx / 47 + rng.uniform(0, 6))
    d = np.stack([(wx - b[0]) ** 2 + (wy - b[1]) ** 2 for b in bases])
    return d.argmin(0).astype(np.int8)


# ---------------------------------------------------------------- Plinko layout (shared)
class PlinkoLayout:
    """Vertical ladder board.

    Upper half: angled deflector bars (busy area) then the multiplier ledge.
      Between multiplier openings sit bounce ridges under 「倍率」: low, shallow ridges
      that kick a ball back UP toward the top. Bigger multiplier = narrower opening.
    Lower half: sparse deflectors + white pegs, then ONE row:
      4 items | TELE(~⅔ center) | 4 items (each powerup twice). Flat dividers only.
    All coords are plinko-local x (0..PW) and screen y.
    """

    def __init__(self):
        # widths ∝ 1/mult → relative 4:2:1:1:2:4 for [2,4,8,8,4,2]
        # use ~72% of board as openings (tight gaps); 8× still ≥ ball diameter + 5px
        rel = np.array([8.0 / m for m in MULTS])
        open_budget = PW * 0.72
        widths = open_budget * rel / rel.sum()
        w_floor = 2 * BALL_R + 5
        if widths.min() < w_floor:
            widths *= w_floor / widths.min()
            widths *= open_budget / widths.sum()
        gw = np.array([1.6, 1.0, 1.0, 1.15, 1.0, 1.0, 1.6])           # remaining ~28% as tight bounce ridges
        gw *= (PW - widths.sum()) / gw.sum()
        self.slots, self.zones = [], []
        x = 0.0
        for i, m in enumerate(MULTS):
            self.zones.append((x, x + gw[i]))
            x += gw[i]
            self.slots.append((m, x, x + widths[i]))
            x += widths[i]
        self.zones.append((x, PW))
        self.ridge_h = 7.0                                            # low bumps in the tight gaps
        # angled deflector bars in the upper half (plus separate white pegs)
        self.bars = []
        for yy, fr, sgn in ((225, (0.36, 0.64), 1), (315, (0.18, 0.50, 0.82), -1), (400, (0.30, 0.70), 1)):
            for k, f in enumerate(fr):
                s = sgn * (1 if k % 2 == 0 else -1)
                cx, L, a = f * PW, 74.0, math.radians(17) * s
                self.bars.append(((cx - L / 2 * math.cos(a), yy - L / 2 * math.sin(a)),
                                  (cx + L / 2 * math.cos(a), yy + L / 2 * math.sin(a))))
        # sparse lower deflectors
        self.low_bars = []
        for yy, f, s in ((650, 0.22, 1), (650, 0.78, -1), (735, 0.50, 1), (815, 0.16, -1), (815, 0.84, 1)):
            cx, L, a = f * PW, 84.0, math.radians(22) * s
            self.low_bars.append(((cx - L / 2 * math.cos(a), yy - L / 2 * math.sin(a)),
                                  (cx + L / 2 * math.cos(a), yy + L / 2 * math.sin(a))))
        # denser white-dot pegs (static Circles) in UPPER + LOWER regions
        self.pegs = []; self.peg_r = 5.0
        rngp = np.random.default_rng(42)
        for row, y in enumerate(range(int(LAYER1_Y + 50), int(LEDGE_Y - 50), 36)):
            n = 10 if row % 2 == 0 else 9
            for x in np.linspace(24, PW - 24, n):
                self.pegs.append((float(x + rngp.uniform(-5, 5)), float(y + rngp.uniform(-4, 4))))
        for row, y in enumerate(range(int(LEDGE_Y + SLOT_H + 36), int(ROW_Y - 28), 40)):
            n = 9 if row % 2 == 0 else 8
            for x in np.linspace(28, PW - 28, n):
                self.pegs.append((float(x + rngp.uniform(-5, 5)), float(y + rngp.uniform(-4, 4))))
        # bottom row: 4 small items | CENTER teleport (~2/3) | 4 small items
        # each of 护盾/大球/散射/激光 appears twice (L and R); flat dividers only
        tw = PW * (2.0 / 3.0)
        side = (PW - tw) / 2.0
        iw = side / 4.0
        self.tele = ((PW - tw) / 2.0, (PW + tw) / 2.0)
        left = [(POWERS[i], i * iw, (i + 1) * iw) for i in range(4)]
        right = [(POWERS[i], self.tele[1] + i * iw, self.tele[1] + (i + 1) * iw) for i in range(4)]
        self.items = left + right
        self.row_div = [iw, 2*iw, 3*iw, side,
                        self.tele[1], self.tele[1]+iw, self.tele[1]+2*iw, self.tele[1]+3*iw]

    def slot_at(self, x):
        for m, a, b in self.slots:
            if a <= x <= b:
                return m
        return None

    def cell_at(self, x):
        if self.tele[0] <= x < self.tele[1]:
            return "TELE"
        for name, a, b in self.items:
            if a <= x <= b:
                return name
        return None

    def target_x(self, key):
        if key is None:
            return None
        if key.startswith("M"):
            raw, side = key[1:], "L"
            if raw.endswith("R") or raw.endswith("L"):
                side, raw = raw[-1], raw[:-1]
            want = int(raw)
            matches = [(a + b) / 2 for m, a, b in self.slots if m == want]
            if not matches:
                return None
            return matches[-1] if side == "R" else matches[0]
        if key == "TELE":
            return (self.tele[0] + self.tele[1]) / 2
        for name, a, b in self.items:
            if name == key:
                return (a + b) / 2
        return None


# ---------------------------------------------------------------- Marbles + Pymunk Plinko
class Marble:
    __slots__ = ("t", "x", "y", "vx", "vy", "mult", "r", "alive", "state",
                 "hit_mult", "script_tag", "_force", "body", "shape", "age", "_still")

    def __init__(self, t, x, y, vx=0.0, vy=0.0, mult=1, tag=""):
        self.t = t
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = float(vx), float(vy)
        self.mult = int(mult)          # ONLY changes on multiplier slot / boss reward
        self.r = BALL_R
        self.alive = True
        self.state = "fall"             # fall | done  (marble lifecycle, NOT game stages)
        self.hit_mult = False
        self.script_tag = tag
        self.body = None
        self.shape = None
        self.age = 0


def build_plinko_space(layout: PlinkoLayout):
    """Pymunk space for the LEFT board only (y+ down = screen)."""
    space = pymunk.Space()
    space.gravity = (0, GRAVITY)
    space.damping = 0.80              # drag → followable fall/bounce
    st = space.static_body

    def seg(a, b, r=3.0, e=0.62, mu=0.45):
        s = pymunk.Segment(st, a, b, r)
        s.elasticity, s.friction = e, mu
        space.add(s)

    seg((2, PTOP), (2, PBOT), 4)                        # side walls
    seg((PW - 2, PTOP), (PW - 2, PBOT), 4)
    seg((2, PTOP + 6), (PW - 2, PTOP + 6), 3.0)        # soft ceiling for fountain arcs
    for a, b in layout.bars + layout.low_bars:         # angled deflectors
        seg(a, b, 4.0)
    for (px, py) in layout.pegs:
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = (px, py)
        sh = pymunk.Circle(body, layout.peg_r)
        sh.elasticity, sh.friction = 0.70, 0.40
        space.add(body, sh)
    h = layout.ridge_h
    n = len(layout.zones)
    for i, (a, b) in enumerate(layout.zones):          # bounce-back ridges (low)
        if i == 0:
            seg((a, LEDGE_Y - h * 1.5), (b, LEDGE_Y), 4.0, 0.62)
        elif i == n - 1:
            seg((a, LEDGE_Y), (b, LEDGE_Y - h * 1.5), 4.0, 0.62)
        else:
            mid = (a + b) / 2
            seg((a, LEDGE_Y), (mid, LEDGE_Y - h), 4.0, 0.62)
            seg((mid, LEDGE_Y - h), (b, LEDGE_Y), 4.0, 0.62)
    for _, a, b in layout.slots:                        # multiplier chute walls
        seg((a, LEDGE_Y), (a, LEDGE_Y + SLOT_H), 3.0)
        seg((b, LEDGE_Y), (b, LEDGE_Y + SLOT_H), 3.0)
    for x in layout.row_div:                            # bottom row: FLAT dividers only (no slopes)
        seg((x, ROW_Y), (x, ROW_Y + ROW_H), 2.5)
    seg((0, ROW_Y + ROW_H), (PW, ROW_Y + ROW_H), 4.0)  # floor
    return space


# ---------------------------------------------------------------- Projectiles (numbered, shrinking)
# Each live bullet carries value; painting enemy pixels decrements value & size.
# RIGHT battlefield stays numpy — not pymunk.


# ---------------------------------------------------------------- Demo Sim
class Demo:
    def __init__(self, seed=5, nt=4):
        assert nt >= 2
        self.nt = nt
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.f = 0
        self.maxf = DEMO_F
        self.layout = PlinkoLayout()
        self.space = build_plinko_space(self.layout)  # LEFT physics
        self.bases = corner_bases(nt, G)
        self.grid = np.full((G, G), self.nt, np.int8)   # FULLY NEUTRAL start (no pre-colored territories)
        # single barrel angle per team (radians), rotating outward until Boss
        self.ang = np.array([
            math.atan2(G / 2 - self.bases[t, 1], G / 2 - self.bases[t, 0])
            for t in range(nt)
        ], dtype=np.float64)
        self.spin = 0.042             # unified clockwise spin rad/frame after opening
        self.fire_cd = np.zeros(nt, int)
        self.fire_period = 2          # dense particle stream (~15 jets/s)
        self.fire_period_pow = 16     # power-up: one big numbered ball, slower
        # team state (NO levels)
        self.mult_bonus = np.ones(nt, int)   # from boss rewards, applied to marbles
        self.shield = np.zeros(nt, int)      # frames remaining
        self.shield_hp = np.zeros(nt, int)   # displayed number on shield (stacks additively)
        self.shield_pop = np.zeros(nt, int)  # pop animation timer on stack
        self.power = [None] * nt             # active power name
        self.power_t = np.zeros(nt, int)
        self.power_val = np.ones(nt, float)  # base effect value before marble mult
        self.ammo = np.full(nt, 800.0)
        # marbles
        self.marbles: list[Marble] = []
        # projectiles
        z = lambda dt=float: np.zeros(NMAX, dt)
        self.px = z(); self.py = z(); self.pvx = z(); self.pvy = z()
        self.ptm = z(np.int8); self.pval = z(); self.pbase = z()
        self.palive = z(bool); self.ppow = z(bool); self.pkind = z(np.int8)  # 0 normal 1 scatter 2 big 3 laser-dot
        self.pcur = 0
        # boss
        self.boss = None                 # dict or None
        self.boss_dmg = np.zeros(nt, np.float64)
        self.boss_floats = []            # [x,y,vy,life,dmg,team]
        self.boss_rewards = None         # list of mults after kill
        self.boss_dead_f = -1
        # tips / banners (left strip)
        self.tips = []                   # [text, color, life, maxlife]
        self.banner = None               # (text, color, life)
        self.events = []                 # per-frame event list for audio
        # paint fx buffer
        self.fx = np.zeros((G, G, 3), np.float32)
        self.share = np.zeros(nt)
        self._script_done = set()
        self._spawn_plan = self._build_spawn_plan()
        self.tip("开局集火中央 · 随后顺时针旋转", (200, 220, 255), 70)

    def _build_spawn_plan(self):
        """Scripted marble spawns so every mechanic appears in ~10s."""
        # (frame, team, mult, vx, tag, force_slot_or_None)
        # force targets: "M2","M4","M8","TELE","护盾","大球","散射","激光"
        # force = "UPPER|LOWER": upper multiplier target | lower cell target
        plan = [
            (0,   0, 1, -0.4, "red_tele",    "M2|TELE"),
            (4,   1, 1,  0.35, "blu_sh1",    "M4|护盾"),
            (8,   2, 1, -0.2, "grn_laser",   "M8|激光"),
            (12,  3, 1,  0.5, "gld_big",     "M2R|大球"),
            (28,  1, 1, -0.25, "blu_sh2",    "M2|护盾"),
            (40,  3, 1,  0.2, "gld_scatter", "M8R|散射"),
            (55,  1, 1,  0.3, "blu_sh3",     "M4R|护盾"),
            (250, 0, 1,  0.2, "post0", None),
            (254, 1, 1, -0.2, "post1", None),
            (258, 2, 1,  0.1, "post2", None),
            (262, 3, 1, -0.1, "post3", None),
        ]
        self.tele_next = {"red_tele": "M4|散射"}
        return plan

    def tip(self, text, col, life=55):
        self.tips.append([text, col, life, life])
        if len(self.tips) > 8:
            self.tips = self.tips[-8:]

    def _attach_body(self, m, vx, vy):
        """Create pymunk Circle for marble; positions in plinko-local X, screen Y."""
        mass = 1.0
        moment = pymunk.moment_for_circle(mass, 0, m.r)
        body = pymunk.Body(mass, moment)
        body.position = (m.x, m.y)
        # velocities are ~px/frame historically; convert to px/s
        body.velocity = (vx * FPS, vy * FPS)
        shape = pymunk.Circle(body, m.r)
        shape.elasticity = 0.72
        shape.friction = 0.50
        shape.collision_type = 2
        self.space.add(body, shape)
        m.body, m.shape = body, shape
        return m

    def _detach_body(self, m):
        if m.body is not None:
            try:
                if m.shape is not None:
                    self.space.remove(m.body, m.shape)
                else:
                    self.space.remove(m.body)
            except Exception:
                pass
            m.body = m.shape = None

    def spawn_marble(self, t, mult=1, vx=0.0, tag="", force=None):
        # TOP CENTER fountain launch: upward arc + small horizontal spread, then free-fall into pegs
        # (also used for teleport returns)
        cx = PW / 2 + self.rng.uniform(-10, 10)
        # start a bit below the ceiling so the upward kick has room to peak
        sy = LAYER1_Y + 55 + self.rng.uniform(-8, 8)
        # vx: launch bias + random spray; vy negative = UP (screen y+)
        launch_vx = vx * 0.35 + self.rng.uniform(-2.8, 2.8)
        launch_vy = self.rng.uniform(-5.2, -3.4)          # upward kick (px/frame)
        m = Marble(t, cx, sy, launch_vx, launch_vy, mult, tag)
        m._force = force
        self._attach_body(m, launch_vx, launch_vy)
        self.marbles.append(m)
        return m

    @staticmethod
    def _split_force(force):
        if not force:
            return None, None
        up, _, low = force.partition("|")
        return (up or None), (low or None)

    def _sync_from_body(self, m):
        if m.body is None:
            return
        m.x, m.y = float(m.body.position.x), float(m.body.position.y)
        m.vx, m.vy = float(m.body.velocity.x) / FPS, float(m.body.velocity.y) / FPS

    def _steer(self, m):
        """Demo-only weak sideways force + age rescue so 10s still shows every mechanic."""
        up, low = self._split_force(m._force)
        key = up if not m.hit_mult else low
        b = m.body
        if key:
            tx = self.layout.target_x(key)
            # let fountain arc play out before demo steering
            ok = (m.age > 28 and m.y > LAYER1_Y + 90) if not m.hit_mult else (m.y > LEDGE_Y + SLOT_H)
            if ok:
                fx = float(np.clip((tx - m.x) * 1.1, -120.0, 120.0))
                b.apply_force_at_local_point((fx, 0), (0, 0))
            # age rescue: drop INTO the target opening (once), not above the ledge
            if (not m.hit_mult) and m.age == 110:
                b.position = (tx, LEDGE_Y + SLOT_H * 0.45); b.velocity = (0, 40)
            elif m.hit_mult and m.age == 75 and m.y < ROW_Y:
                b.position = (tx, ROW_Y + ROW_H * 0.35); b.velocity = (0, 20)
        sp = math.hypot(*b.velocity)
        m._still = (getattr(m, "_still", 0) + 1) if sp < 10 else 0
        if m._still > 28:
            b.apply_impulse_at_local_point((self.rng.uniform(-80, 80), -70), (0, 0)); m._still = 0
        if sp > VMAX:
            b.velocity = (b.velocity[0] * VMAX / sp, b.velocity[1] * VMAX / sp)

    def tick_marbles(self, ev):
        for fr, t, mult, vx, tag, force in self._spawn_plan:
            if self.f == fr and tag not in self._script_done:
                mm = max(1, int(mult) * int(self.mult_bonus[t]))
                self.spawn_marble(t, mm, vx, tag, force)
                self._script_done.add(tag)

        for m in self.marbles:
            if m.alive and m.state == "fall" and m.body is not None:
                m.age += 1
                self._steer(m)

        dt = 1.0 / FPS
        for _ in range(4):
            self.space.step(dt / 4)

        L = self.layout
        for m in self.marbles:
            if not m.alive or m.state != "fall":
                continue
            self._sync_from_body(m)
            # multiplier: number changes ONLY when passing a multiplier opening (stacks on teleport base)
            if not m.hit_mult and m.y > LEDGE_Y + 6:
                sm = L.slot_at(m.x)
                if sm is not None:
                    before = m.mult
                    m.mult = int(before * sm)
                    m.hit_mult = True
                    m.age = 0
                    ev.append(("mult", m.t, sm))
                    txt = f"{TEAMS[m.t][0]} 命中 {sm}×" + (f" ({before}→{m.mult})" if before > 1 else "")
                    self.tip(txt, TEAMS[m.t][1], 50)
            # bottom row: teleport or item
            if m.y >= ROW_Y + 8:
                up, low = self._split_force(m._force)
                cell = low if (low and m.hit_mult) else L.cell_at(m.x)
                self._detach_body(m)
                m.alive = False; m.state = "done"
                if cell == "TELE":
                    nxt = self.tele_next.get(m.script_tag, "M2|大球")
                    self.spawn_marble(m.t, m.mult, self.rng.uniform(-0.4, 0.4),
                                      tag=m.script_tag + "_re", force=nxt)
                    ev.append(("tele", m.t, m.mult))
                    self.tip(f"{TEAMS[m.t][0]} 传送 · 带{m.mult}×回顶", TEAMS[m.t][1], 60)
                elif cell in POW_COL:
                    self.apply_power(m.t, cell, m.mult, ev)
                continue
            if m.y > PBOT:
                self._detach_body(m); m.alive = False; m.state = "done"

        self.marbles = [m for m in self.marbles if m.alive][-40:]

    def apply_power(self, t, name, mult, ev):
        # power effect value = marble mult × base (no upgrades)
        base = {"护盾": 12, "大球": 18, "散射": 10, "激光": 22}[name]
        val = int(base * max(1, mult))
        self.power[t] = name
        self.power_t[t] = int(4.5 * FPS)
        self.power_val[t] = float(val)
        if name == "护盾":
            before = int(self.shield_hp[t])
            self.shield[t] = max(int(self.shield[t]), int(8 * FPS))
            self.shield_hp[t] = before + val          # ADDITIVE stacking
            self.shield_pop[t] = 24
            self.tip(f"{TEAMS[t][0]} 护盾 {before}+{val}={before + val}", TEAMS[t][1], 70)
        ev.append(("skill", t, name))
        self.tip(f"{TEAMS[t][0]} 获得{name} {val}", TEAMS[t][1], 60)
        self.banner = (f"{TEAMS[t][0]} · {name} ×{mult}", TEAMS[t][1], 40)

    # ---- guns / projectiles ----
    def _alloc(self, n):
        ids = []
        i = self.pcur
        for _ in range(NMAX):
            if len(ids) >= n:
                break
            i = (i + 1) % NMAX
            if not self.palive[i]:
                ids.append(i)
        self.pcur = i
        return ids

    def fire_team(self, t, ev):
        if self.fire_cd[t] > 0:
            return
        bx, by = self.bases[t]
        ang = self.ang[t]
        name = self.power[t]
        # projectile number = left mult × powerup effect
        mult_vis = max(1, int(self.mult_bonus[t]))
        # use active power value if any, else small basic shot
        if name and self.power_t[t] > 0:
            base_num = float(self.power_val[t])
            kind = {"散射": 1, "大球": 2, "激光": 3, "护盾": 0}.get(name, 0)
        else:
            base_num = 40.0 * mult_vis   # normal shot: paints but shows no number
            kind = 0
        powered = bool(name and self.power_t[t] > 0)
        if powered:
            # ONE big numbered ball (number drains only on foreign color)
            self.fire_cd[t] = self.fire_period_pow
            speed = 2.6 if name == "大球" else 3.2
            energy = base_num; r0 = 40.0; n_shot = 1; spread = 0.0; kind = 2
        else:
            # dense jet of SMALL particles (reference look)
            self.fire_cd[t] = self.fire_period
            speed = 5.5; energy = 8.0; r0 = 30.0; n_shot = 10; spread = 0.10; kind = 0
        ids = self._alloc(n_shot)
        for k, i in enumerate(ids):
            a = ang + (k - (n_shot - 1) / 2) * (spread / max(1, n_shot - 1))
            jitter = 0.0 if powered else self.rng.uniform(-0.04, 0.04)
            a += jitter
            sp = speed * (1.0 if powered else self.rng.uniform(0.85, 1.15))
            self.px[i] = bx + math.cos(a) * r0
            self.py[i] = by + math.sin(a) * r0
            self.pvx[i] = math.cos(a) * sp
            self.pvy[i] = math.sin(a) * sp
            self.ptm[i] = t
            self.pval[i] = energy if powered else energy
            self.pbase[i] = self.pval[i]
            self.palive[i] = True
            self.pkind[i] = kind
            self.ppow[i] = powered
        if name == "激光" and powered:
            self._laser_beam(t, ang, base_num)
            ev.append(("laser", t))

    def _laser_beam(self, t, ang, num):
        bx, by = self.bases[t]
        ca, sa = math.cos(ang), math.sin(ang)
        wid = max(2, int(3 + num / 20))
        remaining = float(num)
        for k in range(40, 380):
            if remaining <= 0:
                break
            qx = int(bx + ca * k); qy = int(by + sa * k)
            if qx < 0 or qy < 0 or qx >= G or qy >= G:
                break
            for dy in range(-wid, wid + 1):
                for dx in range(-wid, wid + 1):
                    if dx * dx + dy * dy > wid * wid:
                        continue
                    x2, y2 = qx + dx, qy + dy
                    if x2 < 0 or y2 < 0 or x2 >= G or y2 >= G:
                        continue
                    o = self.grid[y2, x2]
                    if o == self.nt + 1:  # boss cell
                        dmg = min(4.0, remaining)
                        self.boss_dmg[t] += dmg
                        remaining -= dmg
                        self._float_boss(t, dmg)
                        continue
                    if o == self.nt:
                        self.grid[y2, x2] = t  # neutral free — no number decrease
                        self.fx[y2, x2] = np.maximum(self.fx[y2, x2],
                            np.array(TEAMS[t][1], np.float32) * 0.8)
                    elif o < self.nt and o != t:
                        if self.shield[o] > 0:
                            dxb = x2 - self.bases[o, 0]; dyb = y2 - self.bases[o, 1]
                            if dxb * dxb + dyb * dyb < 55 * 55:
                                self.shield_hp[o] = max(0, self.shield_hp[o] - 1)
                                remaining -= 0.5
                                continue
                        self.grid[y2, x2] = t
                        remaining -= PAINT_COST  # ONLY other-team paints decrease number
                        self.fx[y2, x2] = np.maximum(self.fx[y2, x2],
                            np.array(TEAMS[t][1], np.float32) * 0.8)

    def tick_projectiles(self):
        boss_on = self.boss is not None and self.boss["hp"] > 0
        for i in range(NMAX):
            if not self.palive[i]:
                continue
            t = int(self.ptm[i])
            val0 = self.pval[i]
            if val0 <= 0:
                self.palive[i] = False
                continue
            # radius scales with remaining number
            rad = (max(7.0, 9.0 + 11.0 * (val0 / max(1.0, self.pbase[i]))) if self.ppow[i] else 2.6)
            if self.pkind[i] == 2:  # big
                rad *= 1.6
            for _ in range(SUB):
                self.px[i] += self.pvx[i] / SUB
                self.py[i] += self.pvy[i] / SUB
                x, y = self.px[i], self.py[i]
                if x < 1 or x >= G - 1:
                    self.pvx[i] = -self.pvx[i]; self.px[i] = min(max(x, 1.0), G - 1.5); x = self.px[i]
                if y < 1 or y >= G - 1:
                    self.pvy[i] = -self.pvy[i]; self.py[i] = min(max(y, 1.0), G - 1.5); y = self.py[i]
                ix, iy = int(x), int(y)
                # paint disk, decrement number in real time
                r = int(rad)
                painted = 0
                for yy in range(max(0, iy - r), min(G, iy + r + 1)):
                    for xx in range(max(0, ix - r), min(G, ix + r + 1)):
                        if (xx - ix) ** 2 + (yy - iy) ** 2 > r * r:
                            continue
                        o = self.grid[yy, xx]
                        if o == self.nt + 1 and boss_on:
                            dmg = min(1.5, self.pval[i])
                            self.boss_dmg[t] += dmg
                            self.pval[i] -= dmg
                            self._float_boss(t, dmg)
                            painted += 1
                            continue
                        if o == self.nt:
                            # neutral: free claim unless inside another team's protected circle
                            blocked = False
                            for ob in range(self.nt):
                                if ob == t: continue
                                dxb = xx - self.bases[ob, 0]; dyb = yy - self.bases[ob, 1]
                                if dxb * dxb + dyb * dyb < PROT_R * PROT_R:
                                    blocked = True; break
                            if blocked:
                                continue
                            self.grid[yy, xx] = t
                            painted += 1
                        elif o < self.nt and o != t:
                            # OTHER team color: paint AND decrease number (skip protected base circle)
                            dxb = xx - self.bases[o, 0]; dyb = yy - self.bases[o, 1]
                            if dxb * dxb + dyb * dyb < PROT_R * PROT_R:
                                continue
                            if self.shield[o] > 0 and dxb * dxb + dyb * dyb < 55 * 55:
                                self.shield_hp[o] = max(0, int(self.shield_hp[o] - 1))
                                self.pval[i] -= 0.4
                                continue
                            self.grid[yy, xx] = t
                            self.pval[i] -= PAINT_COST
                            painted += 1
                            if self.pval[i] <= 0:
                                break
                    if self.pval[i] <= 0:
                        break
                if painted:
                    self.fx[iy, ix] = np.maximum(
                        self.fx[iy, ix], np.array(TEAMS[t][1], np.float32))
                # mild energy drain even on own color so shots end
                self.pval[i] -= 0.008
                if self.pval[i] <= 0:
                    self.palive[i] = False
                    break

    def _float_boss(self, t, dmg):
        if self.boss is None:
            return
        # throttle floats
        if self.rng.random() > 0.35 and dmg < 6:
            return
        bx, by = self.boss["x"], self.boss["y"]
        jump = 3.5 + min(22.0, float(dmg)) * 1.1   # bigger dmg → taller jump
        self.boss_floats.append([
            bx + self.rng.uniform(-30, 30),
            by - 20,
            -jump,
            28,
            float(dmg),
            t,
        ])

    # ---- boss ----
    def spawn_boss(self, ev):
        cx = cy = G / 2
        r = 70
        self.boss = {"x": cx, "y": cy, "r": r, "hp": 1600.0, "maxhp": 1600.0}
        # stamp boss cells
        for yy in range(int(cy - r), int(cy + r) + 1):
            for xx in range(int(cx - r), int(cx + r) + 1):
                if 0 <= xx < G and 0 <= yy < G and (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                    self.grid[yy, xx] = self.nt + 1
        self.boss_dmg[:] = 0
        ev.append(("boss",))
        self.tip("Boss 来袭 · 全员停转集火", (255, 120, 255), 70)
        self.banner = ("⚠ Boss 来袭", (255, 100, 255), 55)

    def tick_boss(self, ev):
        if self.boss is None:
            return
        b = self.boss
        if b["hp"] <= 0:
            return
        # damage already applied via projectiles; sync hp from dmg sum this frame approx
        # Use cumulative boss_dmg vs maxhp
        dealt = float(self.boss_dmg.sum())
        # Soften: we accumulate dmg; hp = max - dealt
        b["hp"] = max(0.0, b["maxhp"] - dealt)
        # update floats
        nf = []
        for ft in self.boss_floats:
            ft[1] += ft[2]; ft[2] += 0.35; ft[3] -= 1
            if ft[3] > 0:
                nf.append(ft)
        self.boss_floats = nf[-40:]
        if b["hp"] <= 0:
            self._kill_boss(ev)

    def _kill_boss(self, ev):
        shares = boss_reward_shares(self.boss_dmg.tolist())
        self.boss_rewards = shares
        for t, s in enumerate(shares):
            if s > 0:
                self.mult_bonus[t] = max(1, int(self.mult_bonus[t]) * int(s))
                # bump live marbles of that team
                for m in self.marbles:
                    if m.alive and m.t == t:
                        m.mult = max(1, int(m.mult) * int(s))
        # clear boss cells to neutral
        if self.boss:
            cx, cy, r = self.boss["x"], self.boss["y"], self.boss["r"]
            for yy in range(int(cy - r), int(cy + r) + 1):
                for xx in range(int(cx - r), int(cx + r) + 1):
                    if 0 <= xx < G and 0 <= yy < G and self.grid[yy, xx] == self.nt + 1:
                        self.grid[yy, xx] = self.nt  # neutral index = nt
        self.boss_dead_f = self.f
        self.boss = None
        ev.append(("bkill", shares))
        parts = " ".join(f"{TEAMS[t][0]}{s}×" for t, s in enumerate(shares) if s > 0)
        self.tip(f"Boss击破 · 奖池8×分配", (255, 220, 120), 80)
        self.banner = (f"奖池分配 {parts}", (255, 220, 120), 70)
        self.tip(f"倍率乘到左侧球上", (255, 240, 180), 70)

    def tick(self):
        ev = []
        # countdown timers
        self.shield = np.maximum(self.shield - 1, 0)
        self.shield_pop = np.maximum(self.shield_pop - 1, 0)
        self.power_t = np.maximum(self.power_t - 1, 0)
        self.fire_cd = np.maximum(self.fire_cd - 1, 0)
        for t in range(self.nt):
            if self.shield[t] <= 0:
                self.shield_hp[t] = 0
            if self.power_t[t] <= 0:
                self.power[t] = None

        # scripted world events
        if self.f == 165 and self.boss is None:
            self.spawn_boss(ev)
        # ensure boss dies by ~7.5s if still up: inject damage
        if self.boss and self.f == 245:
            # guarantee kill ~7.2s; damage share favors red/green for visible reward split
            need = max(0.0, self.boss["maxhp"] - float(self.boss_dmg.sum()) + 50)
            weights = np.array([0.35, 0.20, 0.28, 0.17], dtype=np.float64)[:self.nt]
            weights /= weights.sum()
            extra = weights * need
            self.boss_dmg += extra
            for ti, d in enumerate(extra):
                for _ in range(5):
                    self._float_boss(ti, max(8.0, d / 5))

        self.tick_marbles(ev)

        boss_on = self.boss is not None and self.boss["hp"] > 0
        # aim / spin: opening = all aim CENTER and spray; then clockwise full circle; Boss locks aim
        for t in range(self.nt):
            bx, by = self.bases[t]
            if boss_on:
                self.ang[t] = math.atan2(self.boss["y"] - by, self.boss["x"] - bx)
            elif self.f < OPEN_AIM_F:
                self.ang[t] = math.atan2(G / 2 - by, G / 2 - bx)   # opening clash at center
            else:
                if self.f == OPEN_AIM_F:
                    # seed clockwise from current center-aim angle
                    self.ang[t] = math.atan2(G / 2 - by, G / 2 - bx)
                self.ang[t] = (self.ang[t] + self.spin) % (2 * math.pi)
            if self.f >= 8:   # almost immediate dense spray
                self.fire_team(t, ev)

        self.tick_projectiles()
        self.tick_boss(ev)

        # fx decay
        self.fx *= 0.82
        # share
        flat = self.grid.ravel()
        for t in range(self.nt):
            self.share[t] = np.count_nonzero(flat == t) / float(G * G)

        # tip life
        for tip in self.tips:
            tip[2] -= 1
        self.tips = [t for t in self.tips if t[2] > 0]
        if self.banner:
            txt, col, life = self.banner
            life -= 1
            self.banner = (txt, col, life) if life > 0 else None

        self.events = ev
        self.f += 1
        return ev


# ---------------------------------------------------------------- audio (no voice)
def make_audio(path, frames_ev, nframes, sr=44100):
    n = int((nframes / FPS + 0.5) * sr)
    a = np.zeros(n, np.float32)
    rng = np.random.default_rng(11)

    def add(st, sig):
        s = int(st * sr)
        if s >= n:
            return
        e = min(n, s + len(sig))
        a[s:e] += sig[:e - s]

    def tone(fr, dur, vol, dec=30, sw=0.0):
        t = np.arange(int(dur * sr)) / sr
        f = fr * (1 + sw * t / max(dur, 1e-6))
        ph = 2 * np.pi * np.cumsum(f) / sr
        return (np.sin(ph) * np.exp(-dec * t) * vol).astype(np.float32)

    def noise(dur, vol, dec, smooth=1):
        x = rng.normal(0, 1, int(dur * sr))
        if smooth > 1:
            x = np.convolve(x, np.ones(smooth) / smooth, "same") * math.sqrt(smooth) * 0.6
        return (x * np.exp(-dec * np.arange(len(x)) / sr) * vol).astype(np.float32)

    # slow ambient pulse
    ts = 0.0
    while ts < nframes / FPS:
        add(ts, tone(90, 0.25, 0.10, 12, -0.4))
        add(ts + 0.35, noise(0.05, 0.02, 60))
        ts += 0.70

    for fi, ev in enumerate(frames_ev):
        ts = fi / FPS
        for e in ev:
            k = e[0]
            if k == "mult":
                add(ts, tone(480 + 40 * int(e[2]), 0.22, 0.14, 10, 0.6))
            elif k == "tele":
                add(ts, tone(660, 0.3, 0.12, 8, 1.0)); add(ts + 0.08, tone(880, 0.25, 0.1, 9))
            elif k == "skill":
                add(ts, tone(360, 0.28, 0.13, 8, 1.1)); add(ts + 0.07, tone(720, 0.2, 0.1, 9))
            elif k == "boss":
                for j in range(4):
                    add(ts + j * 0.18, tone(220 if j % 2 == 0 else 330, 0.2, 0.16, 6))
                add(ts, noise(0.6, 0.12, 5, 8))
            elif k == "bkill":
                add(ts, noise(0.9, 0.35, 4, 10))
                for j, fr in enumerate([523, 659, 784, 1047]):
                    add(ts + 0.1 + j * 0.1, tone(fr, 0.45, 0.18, 5))
            elif k == "laser":
                add(ts, tone(200, 0.5, 0.08, 3, 0.4))
    a = np.tanh(a * 1.05) * 0.9
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((a * 32000).astype(np.int16).tobytes())


# ---------------------------------------------------------------- rendering
def build_static_bg(layout: PlinkoLayout, nt):
    yy = np.arange(H)[:, None, None] / H
    arr = np.broadcast_to(
        np.concatenate([8 + 10 * yy, 10 + 4 * yy, 26 + 20 * yy], -1), (H, W, 3)
    ).astype(np.uint8)
    bg = Image.fromarray(np.ascontiguousarray(arr))
    d = ImageDraw.Draw(bg)

    # tip strip panel
    d.rounded_rectangle((TIP_X0, PTOP, TIP_X0 + TIP_W, PBOT), 12,
                        fill=(14, 18, 38), outline=(60, 90, 160), width=2)
    ctext(d, TIP_X0 + TIP_W / 2, PTOP + 10, "战况提示", font(22), (160, 200, 255), 2)

    # plinko outer
    d.rounded_rectangle((PX0, PTOP, PX1, PBOT), 14,
                        fill=(12, 15, 32), outline=(70, 200, 240), width=2)
    ctext(d, (PX0 + PX1) / 2, PTOP + 4, "共享弹珠台 · 全队顶中发球", font(20), (180, 230, 255), 2)

    MC = {1: (180, 190, 220), 2: (110, 220, 255), 4: (255, 210, 70), 8: (255, 140, 80), 16: (255, 80, 120)}
    X = lambda x: PX0 + x
    # upper half tint = bounce-back area
    d.rounded_rectangle((PX0 + 6, PTOP + 26, PX1 - 6, LEDGE_Y + SLOT_H + 4), 10, fill=(16, 20, 44))
    ctext(d, X(PW * 0.12), PTOP + 32, "倍率", font(18), (130, 170, 255), 1)
    # angled deflector bars
    for (a, b) in layout.bars + layout.low_bars:
        d.line([(X(a[0]), a[1]), (X(b[0]), b[1])], fill=(120, 150, 230), width=8)
        d.line([(X(a[0]), a[1]), (X(b[0]), b[1])], fill=(185, 205, 255), width=2)
    # white-dot pegs (upper + lower)
    pr = layout.peg_r
    for px, py in layout.pegs:
        d.ellipse((X(px) - pr, py - pr, X(px) + pr, py + pr), fill=(235, 238, 255), outline=(150, 165, 210))
    # bounce ridges between 「倍率」 openings
    h = layout.ridge_h; nz = len(layout.zones)
    for i, (a, b) in enumerate(layout.zones):
        if i == 0:
            poly = [(X(a), LEDGE_Y - h * 1.5), (X(b), LEDGE_Y), (X(a), LEDGE_Y)]
        elif i == nz - 1:
            poly = [(X(a), LEDGE_Y), (X(b), LEDGE_Y - h * 1.5), (X(b), LEDGE_Y)]
        else:
            poly = [(X(a), LEDGE_Y), (X((a + b) / 2), LEDGE_Y - h), (X(b), LEDGE_Y)]
        d.polygon(poly + [(poly[-1][0], LEDGE_Y + SLOT_H), (poly[0][0], LEDGE_Y + SLOT_H)], fill=(34, 40, 78))
        d.line(poly, fill=(150, 185, 255), width=4)
            # multiplier openings (bigger = narrower)
    for mult, a, b in layout.slots:
        col = MC[mult]
        d.rectangle((X(a), LEDGE_Y, X(b), LEDGE_Y + SLOT_H), fill=(26 + mult * 3, 26, 52))
        d.line([(X(a), LEDGE_Y - 4), (X(a), LEDGE_Y + SLOT_H)], fill=col, width=3)
        d.line([(X(b), LEDGE_Y - 4), (X(b), LEDGE_Y + SLOT_H)], fill=col, width=3)
        ctext(d, X((a + b) / 2), LEDGE_Y + 10, f"{mult}×", font({2: 24, 4: 20, 8: 14}.get(mult, 16)), col, 1 if mult >= 8 else 2)
    ctext(d, (PX0 + PX1) / 2, LEDGE_Y + SLOT_H + 10, "▼ 下层：四道具 | 传送(居中⅔) | 四道具", font(16), (120, 140, 190), 1)
    # bottom row: 4 small | CENTER teleport (~⅔) | 4 small
    ta, tb = layout.tele
    for name, a, b in layout.items:
        col = POW_COL[name]
        d.rounded_rectangle((X(a) + 1, ROW_Y, X(b) - 1, ROW_Y + ROW_H), 5,
                            fill=(32, 24, 56), outline=col, width=2)
        ctext(d, X((a + b) / 2), ROW_Y + 32, name, font(12), col, 1)
    d.rounded_rectangle((X(ta) + 4, ROW_Y, X(tb) - 4, ROW_Y + ROW_H), 8,
                        fill=(22, 30, 70), outline=(110, 150, 255), width=3)
    ctext(d, X((ta + tb) / 2), ROW_Y + 10, "传送", font(28), (150, 190, 255), 2)
    ctext(d, X((ta + tb) / 2), ROW_Y + 46, "居中 · 约占⅔ · 带倍率回顶", font(15), (130, 160, 230), 1)

    # map frame
    d.rectangle((MX - 5, MY - 5, MX + G + 4, MY + G + 4), outline=(70, 230, 255), width=2)

    # title bar
    d.rounded_rectangle((MX, 8, MX + G, MY - 12), 10, fill=(14, 18, 40), outline=(60, 120, 200), width=1)
    ctext(d, MX + G / 2, 14, "粒子领地大战 v5 · 机制演示", font(28), (200, 230, 255), 2)

    return bg


def render(out_path, preview_prefix, seed=5, nt=4):
    demo = Demo(seed=seed, nt=nt)
    layout = demo.layout
    names = [n for n, _ in TEAMS[:nt]]
    pal = np.array([c for _, c in TEAMS[:nt]] + [NEU, BOSS_C, VOID], np.uint8)
    bg = build_static_bg(layout, nt)
    bg_np = np.asarray(bg)
    gl = np.zeros((G, G), bool); gl[::40] = True; gl[:, ::40] = True

    tmp = out_path + ".video.mp4"
    wav = out_path + ".wav"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
        stdin=subprocess.PIPE,
    )
    frames_ev = []
    snap_at = {40: "00", 75: "01", 110: "02", 140: "03", 180: "04", 215: "05", 255: "06", 290: "07"}
    t0 = time.time()

    for fi in range(demo.maxf):
        ev = demo.tick()
        frames_ev.append(ev)

        frame = bg_np.copy()
        # map
        img = pal[np.clip(demo.grid, 0, len(pal) - 1)]
        fx = demo.fx
        img = np.clip(img.astype(np.float32) + fx, 0, 255).astype(np.uint8)
        # grid lines subtle
        img = img.copy()
        img[gl] = (img[gl].astype(np.int16) + 18).clip(0, 255).astype(np.uint8)
        frame[MY:MY + G, MX:MX + G] = img

        im = Image.fromarray(frame)
        d = ImageDraw.Draw(im)

        # ---- left tip strip content ----
        ty = PTOP + 48
        for text, col, life, ml in reversed(demo.tips[-6:]):
            alpha_life = life / max(1, ml)
            d.rounded_rectangle((TIP_X0 + 6, ty, TIP_X0 + TIP_W - 6, ty + 36), 6,
                                fill=(20, 24, 48), outline=col, width=1)
            # truncate text
            fn = font(15)
            s = text
            while d.textlength(s, font=fn) > TIP_W - 20 and len(s) > 2:
                s = s[:-2]
            ctext(d, TIP_X0 + TIP_W / 2, ty + 6, s, fn, col, 1)
            ty += 42

        # team legend under tips
        ly = PBOT - 10 - nt * 36
        for t in range(nt):
            c = TEAMS[t][1]
            d.ellipse((TIP_X0 + 12, ly + 4, TIP_X0 + 28, ly + 20), fill=c)
            d.text((TIP_X0 + 34, ly + 2), f"{names[t]} {demo.share[t]*100:.0f}%",
                   font=font(16), fill=c)
            if demo.mult_bonus[t] > 1:
                d.text((TIP_X0 + 34, ly + 16), f"球加成×{demo.mult_bonus[t]}",
                       font=font(13), fill=(255, 230, 140))
            ly += 36

        # ---- marbles on plinko ----
        for m in demo.marbles:
            if not m.alive:
                continue
            X, Y = PX0 + m.x, m.y
            c = TEAMS[m.t][1]
            d.ellipse((X - m.r, Y - m.r, X + m.r, Y + m.r), fill=c, outline=(255, 255, 255), width=2)
            # number = multiplier (does NOT drift while falling)
            ctext(d, X, Y - 8, str(int(m.mult)), font(12), (255, 255, 255), 2)

        # spawn marker top center
        cx = PX0 + PW / 2
        d.polygon([(cx - 12, LAYER1_Y - 8), (cx + 12, LAYER1_Y - 8), (cx, LAYER1_Y + 6)],
                  fill=(200, 220, 255))

        # ---- bases: ONE barrel each + protected circle (r ≈ map/8) ----
        for t in range(nt):
            bx, by = demo.bases[t]
            X, Y = MX + bx, MY + by
            c = TEAMS[t][1]
            # semi-transparent protected zone
            pr = PROT_R
            zone = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            zd = ImageDraw.Draw(zone)
            zd.ellipse((X - pr, Y - pr, X + pr, Y + pr), fill=(*c, 45), outline=(255, 255, 255, 90), width=2)
            im = Image.alpha_composite(im.convert("RGBA"), zone).convert("RGB")
            d = ImageDraw.Draw(im)
            # base disk
            br = 22
            d.ellipse((X - br, Y - br, X + br, Y + br), fill=c, outline=(255, 255, 255), width=2)
            # shield ring + NUMBER
            if demo.shield[t] > 0 and demo.shield_hp[t] > 0:
                sr = 38
                d.ellipse((X - sr, Y - sr, X + sr, Y + sr), outline=(120, 240, 255), width=3)
                pop = demo.shield_pop[t]
                fsz = 20 + pop
                ctext(d, X, Y - sr - 18 - pop, str(int(demo.shield_hp[t])), font(fsz), (120, 240, 255), 3)
            # single barrel tube
            ang = demo.ang[t]
            L = 36
            x2 = X + math.cos(ang) * L
            y2 = Y + math.sin(ang) * L
            d.line([(X, Y), (x2, y2)], fill=(240, 240, 255), width=6)
            d.ellipse((x2 - 5, y2 - 5, x2 + 5, y2 + 5), fill=(255, 255, 255))
            # NO level text — show power if any
            if demo.power[t] and demo.power_t[t] > 0:
                ctext(d, X, Y + br + 2, demo.power[t], font(14), POW_COL[demo.power[t]], 1)

        # ---- projectiles with numbers + size ----
        for i in range(NMAX):
            if not demo.palive[i]:
                continue
            t = int(demo.ptm[i])
            val = demo.pval[i]
            if val <= 0:
                continue
            X = MX + demo.px[i]; Y = MY + demo.py[i]
            frac = val / max(1e-3, demo.pbase[i])
            if demo.ppow[i]:
                rad = max(9.0, 11.0 + 12.0 * frac)
                if demo.pkind[i] == 2: rad *= 1.15
                c = TEAMS[t][1]
                d.ellipse((X - rad, Y - rad, X + rad, Y + rad), fill=c, outline=(255, 255, 255), width=2)
                num_s = str(int(max(1, round(val))))
                fs = 14 if rad < 10 else 18
                ctext(d, X, Y - fs * 0.55, num_s, font(fs), (255, 255, 255), 2)
            else:
                # dense small particle jet
                rad = 2.2
                c = TEAMS[t][1]
                d.ellipse((X - rad, Y - rad, X + rad, Y + rad), fill=c)

        # ---- boss ----
        if demo.boss is not None:
            b = demo.boss
            X, Y = MX + b["x"], MY + b["y"]
            r = b["r"]
            d.ellipse((X - r, Y - r, X + r, Y + r), fill=(70, 30, 100), outline=(255, 100, 255), width=3)
            # hp bar
            hw = 160
            hp_f = b["hp"] / b["maxhp"]
            d.rectangle((X - hw / 2, Y - r - 24, X + hw / 2, Y - r - 12), fill=(40, 20, 50))
            d.rectangle((X - hw / 2, Y - r - 24, X - hw / 2 + hw * hp_f, Y - r - 12), fill=(255, 80, 200))
            ctext(d, X, Y - 12, "BOSS", font(28), (255, 180, 255), 2)
            # floating damage numbers
            for ft in demo.boss_floats:
                fx, fy, _, life, dmg, tm = ft
                col = TEAMS[int(tm)][1]
                fs = 14 + min(28, int(dmg))
                ctext(d, MX + fx, MY + fy, f"-{int(max(1, dmg))}", font(fs), col, 2)

        # reward overlay after boss kill
        if demo.boss_rewards is not None and demo.boss_dead_f >= 0:
            age = demo.f - demo.boss_dead_f
            if age < 90:
                d.rounded_rectangle((MX + 80, MY + 80, MX + G - 80, MY + 220), 12,
                                    fill=(20, 16, 40, ) if False else (20, 16, 40),
                                    outline=(255, 220, 120), width=2)
                ctext(d, MX + G / 2, MY + 95, "Boss 击破 · 8×奖池按伤害分配", font(26), (255, 230, 140), 2)
                # shares
                xs = MX + G / 2 - (nt - 1) * 70
                for t, s in enumerate(demo.boss_rewards):
                    c = TEAMS[t][1]
                    ctext(d, xs + t * 140, MY + 140, f"{names[t]}", font(20), c, 2)
                    ctext(d, xs + t * 140, MY + 168, f"→ 球×{s}" if s else "→ 0",
                          font(24), (255, 240, 180) if s else (140, 140, 160), 2)

        # top banner (left-of-map / over map top)
        if demo.banner:
            txt, col, life = demo.banner
            d.rounded_rectangle((PX0 + 40, 48, PX1 - 40, 88), 10, fill=(16, 20, 44), outline=col, width=2)
            ctext(d, (PX0 + PX1) / 2, 55, txt, font(24), col, 2)

        # timer
        d.text((MX + 12, MY + 8), f"{fi / FPS:04.1f}s", font=font(20), fill=(200, 220, 255))

        # opening title cards
        if fi < 25:
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 140))
            od = ImageDraw.Draw(overlay)
            ctext(od, W / 2, H / 2 - 40, "粒子领地大战 v5", font(54), (200, 230, 255), 3)
            ctext(od, W / 2, H / 2 + 30, "机制演示 · 无阶段 · 慢节奏", font(28), (180, 200, 240), 2)
            im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            d = ImageDraw.Draw(im)

        rgb = np.asarray(im)
        proc.stdin.write(rgb.tobytes())

        if fi in snap_at:
            im.save(f"{preview_prefix}_{snap_at[fi]}.png")
            print(f"  preview {preview_prefix}_{snap_at[fi]}.png @ {fi / FPS:.1f}s", flush=True)

        if fi % 30 == 0:
            print(f"  frame {fi}/{demo.maxf} ({fi/FPS:.1f}s)  {(time.time()-t0):.1f}s elapsed", flush=True)

    proc.stdin.close()
    proc.wait()
    print("encoding audio…", flush=True)
    make_audio(wav, frames_ev, demo.maxf)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-i", wav,
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", out_path],
        check=True,
    )
    os.remove(tmp)
    os.remove(wav)
    # end preview
    Image.fromarray(rgb).save(f"{preview_prefix}_end.png")
    print(f"done → {out_path}", flush=True)
    return demo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/workspace/side-income/pixel-war/marble_v5_demo.mp4")
    ap.add_argument("--preview", default="/workspace/side-income/pixel-war/marble_v5_demo_preview")
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--teams", type=int, default=4)
    args = ap.parse_args()
    print(f"rendering v5 demo → {args.out}", flush=True)
    render(args.out, args.preview, seed=args.seed, nt=args.teams)


if __name__ == "__main__":
    main()
