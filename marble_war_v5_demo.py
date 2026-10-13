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
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
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
ROW_Y = PBOT - 78                        # lower row top: teleport + items
ROW_H = 56                       # compressed item/tele slot height
GRAVITY = 420.0                          # px/s^2 — followable (slower than prior 760)
VMAX = 300.0                             # px/s clamp — slow cap
BALL_R = 9                               # small so exact 1/mult widths fit (16× = 2r+5)
PAINT_COST = 0.012
PROT_R = (G / 8.0) * (2.0 / 3.0)         # protect radius = prior × 2/3 (was G/8)
BIG_V_REF = 18.0                        # reference numeric value for 「1×」visual size
BIG_D0 = G / 18.0                       # diameter at val≈BIG_V_REF (reasonable large ball)
BIG_D_MIN = G / 40.0                    # floor diameter for tiny numbers
BIG_D_MAX = G / 12.0                    # hard CAP diameter (~PROT_R scale; never 1/5 map)
POP_IN_F = 10                           # frames to ease-in power-up / ball visual scale
OPEN_AIM_F = int(2.4 * FPS)              # opening: all guns aim center + spray, then clockwise
                       # number lost per enemy pixel painted (real-time decay)
NMAX = 8000
SUB = 1
MULTS = [2, 4, 8, 8, 4, 2]                     # restored: 2×4×8×|8×4×2× continuous ledge
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


class V_TITLE:
    t = "粒子领地大战 v5 · 机制演示"
    sub = "机制演示 · 无阶段 · 慢节奏"


# ---------------------------------------------------------------- helpers
_fc = {}
_fc_reg = {}
def font(sz):
    sz = max(10, int(sz))
    if sz not in _fc:
        _fc[sz] = ImageFont.truetype(FONT, sz)
    return _fc[sz]

def font_reg(sz):
    """Regular weight — right-map HUD (ammo/score/HP/Boss/floats)."""
    sz = max(10, int(sz))
    if sz not in _fc_reg:
        _fc_reg[sz] = ImageFont.truetype(FONT_REG, sz)
    return _fc_reg[sz]


def ctext(d, cx, y, s, fn, fill, sw=2, sf=(0, 0, 0)):
    d.text((cx - d.textlength(s, font=fn) / 2, y), s, font=fn, fill=fill,
           stroke_width=sw, stroke_fill=sf)



def big_ball_radius(val, pop=1.0):
    """Continuous size from numeric value: soft sqrt, hard diameter CAP at BIG_D_MAX.

    diameter = clamp(BIG_D0 * sqrt(val / BIG_V_REF), BIG_D_MIN, BIG_D_MAX)
    No discrete tiers — only smooth growth with the number, then visual pop-in.
    """
    v = max(0.25, float(val))
    d = BIG_D0 * math.sqrt(v / BIG_V_REF)
    d = min(BIG_D_MAX, max(BIG_D_MIN, d))
    return 0.5 * d * float(pop)


def fmt_abbr(v):
    """Marble/ammo label: 2, 64, 4K, 1M …"""
    v = abs(float(v))
    if v >= 1e6:
        x = v / 1e6
        s = f"{x:.0f}M" if x >= 10 or abs(x - round(x)) < 0.05 else f"{x:.1f}M"
        return s.replace(".0M", "M")
    if v >= 1e3:
        x = v / 1e3
        s = f"{x:.0f}K" if abs(x - round(x)) < 0.05 else f"{x:.1f}K"
        return s.replace(".0K", "K")
    return str(int(round(v)))


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
    """4 teams → corners; >4 → regular polygon. Inset so PROT circle stays on-map."""
    m = float(PROT_R) + 10.0   # base center ≥ PROT_R+10 from every edge
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

    Mid ledge: continuous 2×4×8×|8×4×2× (widths ∝ 1/mult). NO mid-ledge teleport.
    Lower: regular white pegs (NO slopes), then bottom row:
      4 items | TELE(~⅔ center) | 4 items. Flat dividers only. Fountain spawn top-center.
    All coords are plinko-local x (0..PW) and screen y.
    """

    def __init__(self):
        # Restored ledge: continuous 2×4×8×|8×4×2× (NO mid-ledge tele); widths ∝ 1/mult
        mults = list(MULTS)  # [2,4,8,8,4,2]
        gap = 4.0
        rel = np.array([1.0 / m for m in mults], float)
        open_w = PW - gap * (len(mults) - 1)
        ws = open_w * rel / rel.sum()
        wmin = 2 * BALL_R + 4
        if ws.min() < wmin:
            ws *= wmin / ws.min(); ws *= open_w / ws.sum()
        self.slots, x = [], 0.0
        for m, w in zip(mults, ws):
            self.slots.append((m, x, x + w)); x += w + gap
        # Bottom row: 4 items | TELE(~⅔ center) | 4 items — flat dividers, no slopes
        tele_w = PW * (2.0 / 3.0)
        side_w = (PW - tele_w) / 2.0
        self.tele = (side_w, side_w + tele_w)
        iw = side_w / 4.0
        left_items = [(POWERS[i], i * iw, (i + 1) * iw) for i in range(4)]
        right_items = [(POWERS[i], side_w + tele_w + i * iw, side_w + tele_w + (i + 1) * iw) for i in range(4)]
        self.items = left_items + right_items
        self.row_div = [iw * i for i in range(1, 4)] + [side_w, side_w + tele_w] + [side_w + tele_w + iw * i for i in range(1, 4)]
        self.zones = []
        self.ridge_h = 0.0
        self.bars = []
        self.low_bars = []
        # Upper 4 rows + lower 4 rows; dense staggered (tight x-spacing, mid-gap fillers)
        self.peg_r = 7.5
        self.pegs = []
        def add_row(y, stagger):
            """Full-width staggered row with tight spacing + mid-gap filler pegs."""
            margin = 42.0
            sp = 48.0  # tight left-right spacing (was ~wide)
            xs = []
            x = margin + (sp * 0.5 if stagger else 0.0)
            while x <= PW - margin:
                xs.append(x)
                x += sp
            # insert extra peg into each middle gap → denser pattern
            filled = []
            for i, x in enumerate(xs):
                filled.append(x)
                if i + 1 < len(xs):
                    filled.append(0.5 * (xs[i] + xs[i + 1]))
            for x in filled:
                if 36 <= x <= PW - 36:
                    self.pegs.append((float(x), float(y)))
        # upper zone (spawn → ledge): 4 rows
        uy0 = LAYER1_Y + 85
        ugap = 42.0
        for r in range(4):
            add_row(uy0 + r * ugap, stagger=(r % 2 == 1))
        # lower zone (below 倍率 → items): 4 rows
        ly0 = LEDGE_Y + SLOT_H + 45
        lgap = 40.0
        for r in range(4):
            add_row(ly0 + r * lgap, stagger=(r % 2 == 1))


    def slot_at(self, x):
        for m, a, b in self.slots:
            if a <= x <= b:
                return m
        return None

    def cell_at(self, x):
        for name, a, b in self.items:
            if a <= x <= b:
                return name
        return None

    def tele_at(self, x):
        return self.tele[0] <= x < self.tele[1]

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
                 "hit_mult", "script_tag", "_force", "body", "shape", "age", "_still", "_ledge_done")

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
        self._ledge_done = False


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
    # NO slanted bars — pegs only + flat stepped ledge (holes for mult + center tele)
    for (px, py) in layout.pegs:
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = (px, py)
        sh = pymunk.Circle(body, layout.peg_r)
        sh.elasticity, sh.friction = 0.70, 0.40
        space.add(body, sh)
    opens = sorted([(a, b) for _, a, b in layout.slots])  # tele is bottom row, not mid-ledge hole
    cursor = 0.0
    for a, b in opens:
        if a - cursor > 2:
            seg((cursor, LEDGE_Y), (a, LEDGE_Y), 6.0)
        # vertical dividers at hole edges
        seg((a, LEDGE_Y - 2), (a, LEDGE_Y + SLOT_H), 3.0)
        seg((b, LEDGE_Y - 2), (b, LEDGE_Y + SLOT_H), 3.0)
        cursor = b
    if PW - cursor > 2:
        seg((cursor, LEDGE_Y), (PW, LEDGE_Y), 6.0)
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
        self.slot_hits = np.zeros(len(self.layout.slots), int)
        self.space = build_plinko_space(self.layout)  # LEFT physics
        self.bases = corner_bases(nt, G)
        self.grid = np.full((G, G), self.nt, np.int8)   # start neutral, then seed a solid blob at each base
        for ti in range(nt):
            bx, by = self.bases[ti]
            rr = int(PROT_R * 0.98)
            for yy in range(max(0, int(by) - rr), min(G, int(by) + rr + 1)):
                for xx in range(max(0, int(bx) - rr), min(G, int(bx) + rr + 1)):
                    if (xx - bx) ** 2 + (yy - by) ** 2 <= rr * rr:
                        self.grid[yy, xx] = ti
        # single barrel angle per team (radians), rotating outward until Boss
        self.ang = np.array([
            math.atan2(G / 2 - self.bases[t, 1], G / 2 - self.bases[t, 0])
            for t in range(nt)
        ], dtype=np.float64)
        self.spin = 0.042             # unified clockwise spin rad/frame after opening
        self.fire_cd = np.zeros(nt, int)
        self.fire_period = 3          # sparse slow white dots (not a machine-gun cloud)
        self.fire_period_pow = 16     # power-up: one big numbered ball, slower
        # team state (NO levels)
        self.mult_bonus = np.ones(nt, int)   # from boss rewards, applied to marbles
        self.shield = np.zeros(nt, int)      # frames remaining
        self.shield_hp = np.zeros(nt, int)   # shield pool (absorbs body damage first)
        self.hp = np.full(nt, 1000.0)         # team body HP; death when <= 0
        self.max_hp = np.full(nt, 1000.0)
        self.alive_t = np.ones(nt, bool)
        self.ammo_disp = np.full(nt, 5_000_000.0)  # cosmetic ammo readout on base
        self.shield_pop = np.zeros(nt, int)  # pop animation timer on stack
        self.power = [None] * nt             # active power name
        self.power_t = np.zeros(nt, int)
        self.power_val = np.ones(nt, float)  # base effect value before marble mult
        self.big_pending = np.zeros(nt, bool)  # 大球: one-shot huge ball waiting to fire
        self.big_energy = np.zeros(nt, float)
        self.ammo = np.full(nt, 800.0)
        # marbles
        self.marbles: list[Marble] = []
        # projectiles
        z = lambda dt=float: np.zeros(NMAX, dt)
        self.px = z(); self.py = z(); self.pvx = z(); self.pvy = z()
        self.ptm = z(np.int8); self.pval = z(); self.pbase = z()
        self.palive = z(bool); self.ppow = z(bool); self.pkind = z(np.int8)  # 0 normal 1 scatter 2 big 3 laser-dot
        self.pcur = 0
        self.phit = np.full(NMAX, -1, np.int8)  # base already damaged by this shot
        self.pscale = np.ones(NMAX, np.float32)   # visual pop-in scale 0→1
        self.page = np.zeros(NMAX, np.int16)      # frames since spawn (for ease-in)
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
        self.boss_f = 165          # Boss 来袭 frame
        self.boss_force_f = 245    # demo-only guaranteed kill (-1 = natural)
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
                b.position = (tx, LEDGE_Y + SLOT_H * 0.35); b.velocity = (0, 50)
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
            # mid ledge: multiplier slots only (no tele here)
            if (not getattr(m, "_ledge_done", False)) and m.y > LEDGE_Y + 6:
                sm = L.slot_at(m.x)
                if sm is not None and not m.hit_mult:
                    for si, (mm, a, b) in enumerate(L.slots):
                        if mm == sm and a <= m.x <= b:
                            self.slot_hits[si] += 1; break
                    m.mult = int(m.mult * sm)
                    m.hit_mult = True
                    m.age = 0
                    m._ledge_done = True
                    ev.append(("mult", m.t, sm))
                    self.tip(f"{TEAMS[m.t][0]} 命中 {sm}×", TEAMS[m.t][1], 50)
                elif m.y > LEDGE_Y + SLOT_H:
                    m._ledge_done = True
            # bottom row: TELE(~⅔) or item slot
            if m.y >= ROW_Y + 8:
                if L.tele_at(m.x):
                    stacked = m.mult
                    self._detach_body(m); m.alive = False; m.state = "done"
                    nxt = self.tele_next.get(m.script_tag, "M4|散射")
                    _up, low = self._split_force(m._force)
                    force = nxt if (_up == "TELE" or m.script_tag in self.tele_next) else (f"M2|{low}" if low else nxt)
                    self.spawn_marble(m.t, stacked, self.rng.uniform(-0.5, 0.5),
                                      tag=m.script_tag + "_re", force=force)
                    ev.append(("tele", m.t, stacked))
                    self.tip(f"{TEAMS[m.t][0]} 传送 · 带{stacked}×回顶", TEAMS[m.t][1], 60)
                    continue
                _up, low = self._split_force(m._force)
                cell = low if (low in POW_COL) else L.cell_at(m.x)
                self._detach_body(m); m.alive = False; m.state = "done"
                if cell in POW_COL:
                    self.apply_power(m.t, cell, m.mult, ev)
                continue
            if m.y > PBOT:
                self._detach_body(m); m.alive = False; m.state = "done"

        self.marbles = [m for m in self.marbles if m.alive][-40:]

    def apply_power(self, t, name, mult, ev):
        # power effect value = marble mult × base (no upgrades)
        base = {"护盾": 12, "大球": 18, "散射": 10, "激光": 22}[name]
        val = int(base * max(1, mult))
        if name == "大球":
            # ONE cast = ONE very large slow ball (no spray / no multi-fire)
            self.big_pending[t] = True
            self.big_energy[t] = float(val)
            self.power[t] = None
            self.power_t[t] = 0
            self.power_val[t] = float(val)
        else:
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


    def apply_base_damage(self, victim, amount, attacker, ev):
        """Shield absorbs first; leftover hits HP. Insufficient shield/HP => team dies."""
        if not self.alive_t[victim] or amount <= 0:
            return
        amt = float(amount)
        sh = float(self.shield_hp[victim])
        if sh > 0:
            take = min(sh, amt)
            self.shield_hp[victim] = int(max(0, sh - take))
            amt -= take
            if self.shield_hp[victim] <= 0:
                self.shield[victim] = 0
        if amt > 0:
            self.hp[victim] -= amt
            if self.hp[victim] <= 0:
                self.hp[victim] = 0
                self._kill_team(victim, attacker, ev)

    def _kill_team(self, victim, killer, ev):
        if not self.alive_t[victim]:
            return
        self.alive_t[victim] = False
        self.palive[self.palive & (self.ptm == victim)] = False
        self.tip(f"{TEAMS[victim][0]} 被击破！", TEAMS[killer][1], 70)
        self.banner = (f"{TEAMS[victim][0]} 阵亡", (255, 120, 120), 50)
        ev.append(("elim", victim, killer))
        # fade territory toward killer
        self.grid[self.grid == victim] = killer

    def threat_target(self, t):
        """Highest-threat enemy projectile currently INSIDE trigger range.

        Trigger ranges (only then do we break free rotation):
          • normal white dots: dist < PROT_R * 2
          • item projectiles (大球 / 散射 / 激光 numbered): dist < G / 2  (~half map)
        Score = power × proximity × approach. None → keep free clockwise spin.
        """
        if not self.alive_t[t]:
            return None
        bx, by = self.bases[t]
        best, best_sc = None, 0.0
        R_NORMAL = PROT_R * 2.0
        R_ITEM = G * 0.5
        for i in range(NMAX):
            if not self.palive[i]:
                continue
            src = int(self.ptm[i])
            if src == t or not self.alive_t[src]:
                continue
            px, py = float(self.px[i]), float(self.py[i])
            dx, dy = bx - px, by - py
            dist = math.hypot(dx, dy) + 1e-3
            is_item = bool(self.ppow[i]) or int(self.pkind[i]) in (1, 2, 3)
            if is_item:
                if dist > R_ITEM:
                    continue
            else:
                if dist > R_NORMAL:
                    continue
            vx, vy = float(self.pvx[i]), float(self.pvy[i])
            spd = math.hypot(vx, vy) + 1e-6
            approach = (vx * dx + vy * dy) / (spd * dist)
            if approach < 0.10:
                continue
            power = float(self.pval[i]) if self.ppow[i] else 3.0
            if self.pkind[i] == 2:
                power *= 4.0
            elif is_item:
                power *= 1.8
            sc = power * (200.0 / dist) * max(0.25, approach)
            if dist < PROT_R * 1.4:
                sc *= 2.5
            if sc > best_sc:
                best_sc, best = sc, (px, py, dist, power)
        return best

    def fire_team(self, t, ev):
        if not self.alive_t[t]:
            return
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
        # 大球: exactly one huge slow numbered ball per cast
        if self.big_pending[t]:
            self.big_pending[t] = False
            self.fire_cd[t] = self.fire_period  # don't block normal jets long
            ids = self._alloc(1)
            for i in ids:
                self.px[i] = bx + math.cos(ang) * 44.0
                self.py[i] = by + math.sin(ang) * 44.0
                sp = 3.2  # slow but crosses map in ~5s (demo window)
                self.pvx[i] = math.cos(ang) * sp
                self.pvy[i] = math.sin(ang) * sp
                self.ptm[i] = t
                self.pval[i] = float(self.big_energy[t])
                self.pbase[i] = float(self.big_energy[t])
                self.palive[i] = True
                self.pkind[i] = 2
                self.ppow[i] = True
                self.phit[i] = -1
                self.pscale[i] = 0.0
                self.page[i] = 0
            return

        powered = bool(name and self.power_t[t] > 0 and name != "大球")
        if powered:
            # other power-ups: one numbered ball at a time (not a spray)
            self.fire_cd[t] = self.fire_period_pow
            speed = 3.4
            energy = base_num; r0 = 38.0; n_shot = 1; spread = 0.0; kind = 1  # medium numbered ball (only 大球 is huge)
        else:
            # normal: slower + denser small-particle jet
            self.fire_cd[t] = self.fire_period
            speed = 3.6; energy = 10.0; r0 = 28.0; n_shot = 12; spread = 0.42; kind = 0  # density ×4; visible travel
        ids = self._alloc(n_shot)
        for k, i in enumerate(ids):
            a = ang + (k - (n_shot - 1) / 2) * (spread / max(1, n_shot - 1))
            jitter = 0.0 if powered else self.rng.uniform(-0.04, 0.04)
            a += jitter
            sp = speed * (1.0 if powered else self.rng.uniform(0.88, 1.12))
            ca, sa = math.cos(a), math.sin(a)
            # spawn at barrel; pixel-by-pixel push grows the front from own territory
            self.px[i] = bx + ca * r0
            self.py[i] = by + sa * r0
            self.pvx[i] = ca * sp
            self.pvy[i] = sa * sp
            self.ptm[i] = t
            self.pval[i] = energy
            self.pbase[i] = energy
            self.palive[i] = True
            self.pkind[i] = kind
            self.ppow[i] = powered
            self.phit[i] = -1
            self.pscale[i] = 0.0 if powered else 1.0
            self.page[i] = 0
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
                        # protect circle: laser deals base damage (shield then HP)
                        hit_b = -1
                        for ob in range(self.nt):
                            if ob == t or not self.alive_t[ob]:
                                continue
                            dxb = x2 - self.bases[ob, 0]; dyb = y2 - self.bases[ob, 1]
                            if dxb * dxb + dyb * dyb < PROT_R * PROT_R:
                                hit_b = ob; break
                        if hit_b >= 0:
                            dmg = min(8.0, remaining)
                            self.apply_base_damage(hit_b, dmg, t, [])
                            remaining -= dmg
                            continue
                        self.grid[y2, x2] = t
                        remaining = 0  # laser stops at first enemy frontier pixel (sharp border)
                        self.fx[y2, x2] = np.maximum(self.fx[y2, x2],
                            np.array(TEAMS[t][1], np.float32) * 0.8)

    def tick_projectiles(self, ev=None):
        """Pixel-by-pixel frontier push + bullet-vs-bullet cancel.

        Each bullet advances ≤1 cell at a time along its velocity. Own-color cells
        are traversed; the first neutral or enemy cell is painted and the bullet
        stops (consumed). A later bullet that arrives on already-own paint continues
        one cell further — the front advances only where fire keeps coming.
        """
        if ev is None:
            ev = []
        boss_on = self.boss is not None and self.boss["hp"] > 0
        nt = self.nt
        CELL = 6

        # ---- 0) smooth visual pop-in for powered projectiles (ease-out cubic) ----
        powered_alive = self.palive & self.ppow
        if powered_alive.any():
            idx = np.nonzero(powered_alive)[0]
            self.page[idx] = np.minimum(self.page[idx] + 1, POP_IN_F)
            # ease-out cubic: 1 - (1-u)^3
            u = self.page[idx].astype(np.float32) / float(POP_IN_F)
            self.pscale[idx] = 1.0 - (1.0 - u) ** 3

        # ---- 1) pixel-step move + paint ----
        for i in range(NMAX):
            if not self.palive[i]:
                continue
            t = int(self.ptm[i])
            if not self.alive_t[t] or self.pval[i] <= 0:
                self.palive[i] = False
                continue
            kind = int(self.pkind[i])
            vx, vy = float(self.pvx[i]), float(self.pvy[i])
            spd = math.hypot(vx, vy)
            if spd < 1e-6:
                self.palive[i] = False
                continue
            # pixel steps this frame — enough that motion is visible (~speed cells)
            n_steps = max(1, min(6, int(math.ceil(spd))))
            ux, uy = vx / spd, vy / spd
            if kind == 2:
                n_steps = min(7, n_steps + 1)

            for _ in range(n_steps):
                if not self.palive[i]:
                    break
                ox, oy = float(self.px[i]), float(self.py[i])
                # advance exactly 1 pixel along heading
                nx = ox + ux
                ny = oy + uy
                # wall bounce
                if nx < 1 or nx >= G - 1:
                    self.pvx[i] = -self.pvx[i]; ux = -ux
                    nx = min(max(nx, 1.0), G - 1.5)
                if ny < 1 or ny >= G - 1:
                    self.pvy[i] = -self.pvy[i]; uy = -uy
                    ny = min(max(ny, 1.0), G - 1.5)
                self.px[i], self.py[i] = nx, ny
                ix, iy = int(nx), int(ny)
                if not (0 <= ix < G and 0 <= iy < G):
                    self.palive[i] = False
                    break

                # base protect hit
                hit_base = -1
                for ob in range(nt):
                    if ob == t or not self.alive_t[ob]:
                        continue
                    bx, by = float(self.bases[ob, 0]), float(self.bases[ob, 1])
                    if (nx - bx) ** 2 + (ny - by) ** 2 < PROT_R * PROT_R:
                        hit_base = ob
                        break
                if hit_base >= 0:
                    dmg = float(self.pval[i]) if self.ppow[i] else 3.5
                    self.apply_base_damage(hit_base, dmg, t, ev)
                    self.palive[i] = False
                    self.pval[i] = 0
                    break

                o = int(self.grid[iy, ix])
                # boss cell
                if boss_on and o == nt + 1:
                    dmg = min(1.5, float(self.pval[i]))
                    self.boss_dmg[t] += dmg
                    self.pval[i] -= dmg
                    self._float_boss(t, dmg)
                    if self.pval[i] <= 0:
                        self.palive[i] = False
                    break

                # own color → keep pushing (later bullets extend the front)
                if o == t:
                    self.pval[i] -= 0.004 if kind == 0 else 0.008
                    if self.pval[i] <= 0:
                        self.palive[i] = False
                    continue

                # during Boss: skip neutral spokes — fly until boss/cancel
                if boss_on and o == nt:
                    self.pval[i] -= 0.02
                    if self.pval[i] <= 0:
                        self.palive[i] = False
                    continue

                # blank or enemy → paint a small footprint, then consume (visible dots)
                if o == nt or (o < nt and o != t):
                    pr = 2 if kind == 0 else (3 if kind == 2 else 2)
                    for dy in range(-pr, pr + 1):
                        for dx in range(-pr, pr + 1):
                            if dx * dx + dy * dy > pr * pr:
                                continue
                            x2, y2 = ix + dx, iy + dy
                            if not (0 <= x2 < G and 0 <= y2 < G):
                                continue
                            oo = int(self.grid[y2, x2])
                            if oo == nt or (oo < nt and oo != t):
                                self.grid[y2, x2] = t
                    self.fx[iy, ix] = np.maximum(
                        self.fx[iy, ix], np.array(TEAMS[t][1], np.float32))
                    self.palive[i] = False
                    self.pval[i] = 0
                    break

                self.pval[i] -= 0.01
                if self.pval[i] <= 0:
                    self.palive[i] = False
                    break

        # ---- 2) bullet-vs-bullet cancellation (after move) ----
        buckets = {}
        alive_idx = [int(i) for i in np.nonzero(self.palive)[0]]
        for i in alive_idx:
            cx = int(self.px[i]) // CELL
            cy = int(self.py[i]) // CELL
            buckets.setdefault((cx, cy), []).append(i)
        killed = set()

        def _rad(i):
            if self.pkind[i] == 2:
                return max(8.0, big_ball_radius(self.pval[i], 1.0) * 0.9)
            if self.ppow[i]:
                return 10.0
            return 6.5

        def _w(i):
            p = float(self.pval[i])
            if self.pkind[i] == 2:
                return p * 4.0
            if self.ppow[i]:
                return p * 2.0
            return p

        for (cx, cy), ids in buckets.items():
            neigh = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neigh.extend(buckets.get((cx + dx, cy + dy), ()))
            if len(neigh) < 2:
                continue
            for a in ids:
                if a in killed or not self.palive[a]:
                    continue
                ta = int(self.ptm[a])
                ax, ay = float(self.px[a]), float(self.py[a])
                ra = _rad(a)
                for b in neigh:
                    if b <= a or b in killed or not self.palive[b]:
                        continue
                    tb = int(self.ptm[b])
                    if ta == tb:
                        continue
                    bx, by = float(self.px[b]), float(self.py[b])
                    rb = _rad(b)
                    dx, dy = ax - bx, ay - by
                    lim = ra + rb
                    if dx * dx + dy * dy > lim * lim:
                        continue
                    wa, wb = _w(a), _w(b)
                    if wa >= wb:
                        self.palive[b] = False; self.pval[b] = 0; killed.add(b)
                        self.pval[a] = float(self.pval[a]) * max(0.0, 1.0 - wb / max(wa, 1e-6))
                        if self.pval[a] <= 0.4:
                            self.palive[a] = False; self.pval[a] = 0; killed.add(a); break
                    else:
                        self.palive[a] = False; self.pval[a] = 0; killed.add(a)
                        self.pval[b] = float(self.pval[b]) * max(0.0, 1.0 - wa / max(wb, 1e-6))
                        if self.pval[b] <= 0.4:
                            self.palive[b] = False; self.pval[b] = 0; killed.add(b)
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
        self.ammo_disp *= 1.0008  # cosmetic climb
        self.shield_pop = np.maximum(self.shield_pop - 1, 0)
        self.power_t = np.maximum(self.power_t - 1, 0)
        self.fire_cd = np.maximum(self.fire_cd - 1, 0)
        for t in range(self.nt):
            if self.shield[t] <= 0:
                self.shield_hp[t] = 0
            if self.power_t[t] <= 0:
                self.power[t] = None

        # scripted world events
        if self.f == self.boss_f and self.boss is None:
            self.spawn_boss(ev)
        # ensure boss dies by ~7.5s if still up: inject damage
        if self.boss and self.f == self.boss_force_f:
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
        # aim: open center → free clockwise spin; lock ONLY on in-range threats;
        # Boss lock unless an in-range threat (threat_target already range-gated)
        for t in range(self.nt):
            if not self.alive_t[t]:
                continue
            bx, by = self.bases[t]
            threat = self.threat_target(t)
            if threat is not None:
                tx, ty, _dist, _pw = threat
                self.ang[t] = math.atan2(ty - by, tx - bx)   # in-range threat overrides Boss
            elif boss_on:
                self.ang[t] = math.atan2(self.boss["y"] - by, self.boss["x"] - bx)
            elif self.f < OPEN_AIM_F:
                self.ang[t] = math.atan2(G / 2 - by, G / 2 - bx)
            else:
                if self.f == OPEN_AIM_F:
                    self.ang[t] = math.atan2(G / 2 - by, G / 2 - bx)
                self.ang[t] = (self.ang[t] + self.spin) % (2 * math.pi)
            if self.f >= 8:
                self.fire_team(t, ev)

        self.tick_projectiles(ev)
        self.tick_boss(ev)

        # fx decay
        self.fx *= 0.55
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
    # large regular white pegs (no slopes)
    pr = layout.peg_r
    for px, py in layout.pegs:
        d.ellipse((X(px) - pr, py - pr, X(px) + pr, py + pr), fill=(245, 248, 255), outline=(200, 210, 230))
    # flat stepped ledge deck — continuous 2/4/8/8/4/2
    d.rectangle((PX0, LEDGE_Y - 3, PX1, LEDGE_Y + 3), fill=(70, 80, 110))
    for si, (mult, a, b) in enumerate(layout.slots):
        col = MC.get(mult, (200, 200, 220))
        d.rectangle((X(a) + 1, LEDGE_Y, X(b) - 1, LEDGE_Y + SLOT_H), fill=(40, 44, 70), outline=col, width=2)
        ctext(d, X((a + b) / 2), LEDGE_Y + 14, f"x{mult}", font(16 if mult < 8 else 13), col, 1)
    # bottom: 4 items | TELE(~⅔ ↑ arrows) | 4 items
    ta, tb = layout.tele
    d.rectangle((X(ta), ROW_Y, X(tb), ROW_Y + ROW_H), fill=(18, 22, 40))
    n_ar = max(7, int((tb - ta) / 28))
    for i in range(n_ar):
        cx = X(ta + (i + 0.5) * (tb - ta) / n_ar)
        cy = ROW_Y + ROW_H / 2 + 6
        d.polygon([(cx, cy - 10), (cx - 6, cy + 6), (cx + 6, cy + 6)], fill=(230, 235, 255))
    ctext(d, X((ta + tb) / 2), ROW_Y + 2, "传送", font(20), (210, 225, 255), 2)
    for name, a, b in layout.items:
        col = POW_COL[name]
        d.rounded_rectangle((X(a) + 1, ROW_Y, X(b) - 1, ROW_Y + ROW_H), 5,
                            fill=(32, 24, 56), outline=col, width=2)
        ctext(d, X((a + b) / 2), ROW_Y + 18, name, font(12), col, 1)

    # map frame
    d.rectangle((MX - 3, MY - 3, MX + G + 2, MY + G + 2), outline=(70, 230, 255), width=1)

    # title bar
    d.rounded_rectangle((MX, 8, MX + G, MY - 12), 10, fill=(14, 18, 40), outline=(60, 120, 200), width=1)
    ctext(d, MX + G / 2, 14, getattr(V_TITLE, "t", "粒子领地大战 v5 · 机制演示"), font_reg(28), (200, 230, 255), 1)

    return bg


def render(out_path, preview_prefix, seed=5, nt=4, demo=None, crf=20, snap_at=None,
           post_draw=None, log_every=30):
    demo = demo if demo is not None else Demo(seed=seed, nt=nt)
    layout = demo.layout
    names = [n for n, _ in TEAMS[:nt]]
    pal = np.array([c for _, c in TEAMS[:nt]] + [NEU, BOSS_C, VOID], np.uint8)
    bg = build_static_bg(layout, nt)
    bg_np = np.asarray(bg)
    gl = np.zeros((G, G), bool); gl[::48] = True; gl[:, ::48] = True

    tmp = out_path + ".video.mp4"
    wav = out_path + ".wav"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
        stdin=subprocess.PIPE,
    )
    frames_ev = []
    snap_at = snap_at if snap_at is not None else {40: "00", 75: "01", 110: "02", 140: "03", 180: "04", 215: "05", 255: "06", 290: "07"}
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
        img[gl] = (img[gl].astype(np.int16) + 8).clip(0, 255).astype(np.uint8)
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

        # ---- live hit counts above 倍率 slots ----
        for si, (mult, a, b) in enumerate(layout.slots):
            ctext(d, PX0 + (a + b) / 2, LEDGE_Y - 22, str(int(demo.slot_hits[si])), font(14), (220, 225, 240), 1)
        # ---- marbles on plinko ----
        for m in demo.marbles:
            if not m.alive:
                continue
            X, Y = PX0 + m.x, m.y
            c = TEAMS[m.t][1]
            d.ellipse((X - m.r, Y - m.r, X + m.r, Y + m.r), fill=c, outline=(255, 255, 255), width=2)
            # number = multiplier (does NOT drift while falling)
            ctext(d, X, Y - 8, fmt_abbr(m.mult), font(11), (255, 255, 255), 2)

        # spawn marker top center
        cx = PX0 + PW / 2
        d.polygon([(cx - 12, LAYER1_Y - 8), (cx + 12, LAYER1_Y - 8), (cx, LAYER1_Y + 6)],
                  fill=(200, 220, 255))

        # ---- bases: translucent circle, ammo top / score bottom / rotating barrel ----
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for t in range(nt):
            if not demo.alive_t[t]:
                continue
            bx, by = demo.bases[t]
            X, Y = MX + bx, MY + by
            c = TEAMS[t][1]
            pr = PROT_R
            # shield pop-in: ease ring opacity/scale when shield stacks
            pop_t = int(demo.shield_pop[t])
            if demo.shield_hp[t] > 0:
                u = 1.0 - (pop_t / 24.0) if pop_t > 0 else 1.0
                ease = 1.0 - (1.0 - min(1.0, u)) ** 3
                ring_a = int(90 + 80 * ease)
                fill_a = int(40 + 30 * ease)
                pr_draw = pr * (0.85 + 0.15 * ease)
            else:
                ring_a, fill_a, pr_draw = 70, 35, pr
            od.ellipse((X - pr_draw, Y - pr_draw, X + pr_draw, Y + pr_draw),
                       fill=(255, 255, 255, fill_a), outline=(255, 255, 255, ring_a), width=1)

            # ammo (top) + score (bottom)
            # (text drawn after composite for crisp glyphs)
        im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
        d = ImageDraw.Draw(im)
        for t in range(nt):
            if not demo.alive_t[t]:
                continue
            bx, by = demo.bases[t]
            X, Y = MX + bx, MY + by
            ctext(d, X, Y - PROT_R * 0.55, fmt_abbr(demo.ammo_disp[t]), font_reg(22), (20, 20, 30), 1)
            score = int(demo.share[t] * G * G)
            ctext(d, X, Y + PROT_R * 0.35, f"{score:,}", font_reg(14), (30, 30, 40), 1)
            # shield number if any
            if demo.shield_hp[t] > 0:
                ctext(d, X + PROT_R * 0.55, Y - 10, f"盾{int(demo.shield_hp[t])}", font_reg(14), (80, 200, 255), 1)
            # HP bar under base
            hw = PROT_R * 1.1
            hf = max(0.0, demo.hp[t] / demo.max_hp[t])
            d.rectangle((X - hw / 2, Y + PROT_R * 0.62, X + hw / 2, Y + PROT_R * 0.62 + 6), fill=(40, 40, 50))
            d.rectangle((X - hw / 2, Y + PROT_R * 0.62, X - hw / 2 + hw * hf, Y + PROT_R * 0.62 + 6), fill=TEAMS[t][1])

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
            if demo.ppow[i] and demo.pkind[i] == 2:
                # 大球: continuous size from absolute number (soft √), CAP at BIG_D_MAX; pop-in ease
                pop = float(demo.pscale[i])
                rad = big_ball_radius(val, pop)
                c = TEAMS[t][1]
                fill = tuple(int(180 + v * 0.25) for v in c)
                d.ellipse((X - rad, Y - rad, X + rad, Y + rad), fill=fill, outline=(255, 255, 255), width=2)
                fs = max(11, int(10 + rad * 0.55))
                ctext(d, X, Y - fs * 0.55, fmt_abbr(val), font_reg(fs), (30, 30, 40), 1)
            elif demo.ppow[i]:
                pop = float(getattr(demo, "pscale", np.ones(NMAX))[i])
                rad = max(6.0, (8.0 + 7.0 * frac) * pop)
                c = TEAMS[t][1]
                d.ellipse((X - rad, Y - rad, X + rad, Y + rad), fill=c, outline=(255, 255, 255), width=2)
                fs = max(11, int(12 + 6 * frac * pop))
                ctext(d, X, Y - fs * 0.55, fmt_abbr(val), font_reg(fs), (255, 255, 255), 1)
            else:
                # visible white dots (~2.8px radius ≈ 5–6px diameter)
                rad = 2.8
                d.ellipse((X - rad, Y - rad, X + rad, Y + rad), fill=(255, 255, 255),
                          outline=(230, 235, 245))

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
            ctext(d, X, Y - 12, "BOSS", font_reg(28), (255, 180, 255), 1)
            # floating damage numbers
            for ft in demo.boss_floats:
                fx, fy, _, life, dmg, tm = ft
                col = TEAMS[int(tm)][1]
                fs = 14 + min(28, int(dmg))
                ctext(d, MX + fx, MY + fy, f"-{int(max(1, dmg))}", font_reg(fs), col, 1)

        # reward overlay after boss kill
        if demo.boss_rewards is not None and demo.boss_dead_f >= 0:
            age = demo.f - demo.boss_dead_f
            if age < 90:
                d.rounded_rectangle((MX + 80, MY + 80, MX + G - 80, MY + 220), 12,
                                    fill=(20, 16, 40, ) if False else (20, 16, 40),
                                    outline=(255, 220, 120), width=2)
                ctext(d, MX + G / 2, MY + 95, "Boss 击破 · 8×奖池按伤害分配", font_reg(26), (255, 230, 140), 1)
                # shares
                xs = MX + G / 2 - (nt - 1) * 70
                for t, s in enumerate(demo.boss_rewards):
                    c = TEAMS[t][1]
                    ctext(d, xs + t * 140, MY + 140, f"{names[t]}", font_reg(20), c, 1)
                    ctext(d, xs + t * 140, MY + 168, f"→ 球×{s}" if s else "→ 0",
                          font_reg(24), (255, 240, 180) if s else (140, 140, 160), 1)

        # top banner (left-of-map / over map top)
        if demo.banner:
            txt, col, life = demo.banner
            d.rounded_rectangle((PX0 + 40, 48, PX1 - 40, 88), 10, fill=(16, 20, 44), outline=col, width=2)
            ctext(d, (PX0 + PX1) / 2, 55, txt, font(24), col, 2)

        # timer
        d.text((MX + 12, MY + 8), f"{fi / FPS:04.1f}s", font=font_reg(20), fill=(200, 220, 255))

        # opening title cards
        if fi < 25:
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 140))
            od = ImageDraw.Draw(overlay)
            ctext(od, W / 2, H / 2 - 40, "粒子领地大战 v5", font(54), (200, 230, 255), 3)
            ctext(od, W / 2, H / 2 + 30, V_TITLE.sub, font(28), (180, 200, 240), 2)
            im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
            d = ImageDraw.Draw(im)

        if post_draw is not None:
            im = post_draw(demo, im, fi) or im
        rgb = np.asarray(im)
        proc.stdin.write(rgb.tobytes())

        if fi in snap_at:
            im.save(f"{preview_prefix}_{snap_at[fi]}.png")
            print(f"  preview {preview_prefix}_{snap_at[fi]}.png @ {fi / FPS:.1f}s", flush=True)

        if fi % log_every == 0:
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
