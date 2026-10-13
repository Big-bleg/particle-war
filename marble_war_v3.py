#!/usr/bin/env python3
"""粒子领地大战 v3 —— 10 分钟长篇版, 横屏 1920x1080.

左侧: 2xN 网格的每队 Plinko 弹珠台 (队名/弹药/等级/武器/领地), 底部大量技能槽, 越强的技能槽越窄.
右侧: 960x960 领土地图. 炮台 Lv1-8, 四个阶段(发育/扩张/混战/决战) + 阶段标题卡,
周期性 围剿/陨石/Boss 波/清屏炸弹/冰冻, 决战期毒圈向中心收缩, 尽量打到一队统一.
种子筛选: 多进程 headless 全程模拟 + 戏剧性打分.
"""
import argparse, os, subprocess, wave, time, math, json, sys
from multiprocessing import Pool
import numpy as np
from numba import njit
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FPS, W, H, G = 30, 1920, 1080, 960
MX, MY = W - G - 14, 106
LX0, LX1, TOP, BOT, GAP, HH, SH = 12, MX - 16, 106, 1066, 10, 100, 66
SUB, NMAX, BR = 6, 60000, 34
TEAM_POOL = [("红队", (238, 64, 92)), ("蓝队", (52, 128, 255)), ("绿队", (40, 200, 120)), ("金队", (250, 182, 40)),
             ("紫队", (158, 90, 250)), ("青队", (24, 206, 226)), ("橙队", (255, 118, 36)), ("粉队", (250, 112, 196))]
NEU_C, BOSS_C, VOID_C = (58, 60, 78), (46, 18, 66), (12, 6, 14)
# skill: (width weight, tier 0=common 1=mid 2=rare, color)
SKILLS = {
    "x2": (3.0, 0, (200, 205, 230)), "x3": (2.4, 0, (110, 220, 255)), "散射": (2.2, 0, (255, 150, 90)),
    "机枪": (2.0, 0, (255, 200, 120)), "护盾": (1.9, 0, (120, 240, 255)), "修复": (1.8, 0, (120, 255, 170)),
    "x5": (1.35, 1, (255, 210, 70)), "升级": (1.3, 1, (110, 255, 150)), "大球": (1.2, 1, (255, 120, 210)),
    "狙击": (1.15, 1, (230, 230, 255)), "导弹": (1.1, 1, (255, 110, 80)), "激光": (1.05, 1, (255, 90, 200)),
    "冰冻": (.8, 2, (150, 220, 255)), "援军": (.8, 2, (180, 255, 120)), "x10": (.7, 2, (255, 240, 120)),
    "终极": (.62, 2, (255, 70, 70)),
}
COMMON = [k for k, v in SKILLS.items() if v[1] == 0]; MID = [k for k, v in SKILLS.items() if v[1] == 1]
RARE = [k for k, v in SKILLS.items() if v[1] == 2]
WEAP = ["散射", "机枪", "大球", "狙击"]
NEED = {1: 2, 2: 3, 3: 3, 4: 4, 5: 4, 6: 5, 7: 6}
MAXL = 8
PATTERN = {1: "单管", 2: "双管", 3: "散射", 4: "连射", 5: "激光", 6: "导弹", 7: "双激光", 8: "终极"}
BARRELS = {1: [0.0], 2: [-.12, .12], 3: [-.28, 0, .28], 4: [-.2, 0, .2], 5: [-.3, -.1, .1, .3],
           6: [-.36, -.18, 0, .18, .36], 7: [-.36, -.18, 0, .18, .36], 8: [-.45, -.3, -.15, 0, .15, .3, .45]}
PHASES = ["发育期", "扩张期", "混战期", "决战期"]
PH_T = [0.0, .17, .38, .70]          # phase start (fraction of duration)
PH_COL = [(120, 220, 255), (140, 255, 160), (255, 210, 90), (255, 80, 80)]
PS, PDY, PY0 = 28, 26, 22            # plinko peg spacing


# ---------------------------------------------------------------- numba kernels
@njit(cache=True)
def nb_seed(s):
    np.random.seed(s)


@njit(cache=True)
def step(grid, x, y, vx, vy, tm, en, bp, alive, conv, prot, bases, br2, nt, bosshit, hits, nh):
    g = grid.shape[0]; BOSS = nt + 1; VOID = nt + 2
    for i in range(x.shape[0]):
        if not alive[i]:
            continue
        t = tm[i]
        for s in range(SUB):
            for ax in range(2):
                nx = x[i] + (vx[i] if ax == 0 else 0.0)
                ny = y[i] + (vy[i] if ax == 1 else 0.0)
                if nx < 0 or nx >= g or ny < 0 or ny >= g:
                    if ax == 0: vx[i] = -vx[i]
                    else: vy[i] = -vy[i]
                    continue
                cx, cy = int(nx), int(ny)
                o = grid[cy, cx]
                if o != t:
                    bounce = False
                    if o == BOSS:
                        bosshit[t] += 1; en[i] -= 4.0; bounce = True
                    elif o == VOID:
                        en[i] -= 6.0; bounce = True
                    else:
                        blocked = False
                        if o < nt and prot[o] > 0:
                            dx = nx - bases[o, 0]; dy = ny - bases[o, 1]
                            if dx * dx + dy * dy < br2 * 2.25:
                                blocked = True
                        if blocked:
                            en[i] -= 3.0; bounce = True
                        else:
                            grid[cy, cx] = t; en[i] -= 1.0; conv[t] += 1
                            if nh[0] < hits.shape[0] and np.random.random() < 0.004:
                                hits[nh[0], 0] = nx; hits[nh[0], 1] = ny; hits[nh[0], 2] = t; nh[0] += 1
                            if np.random.random() < bp[i]:
                                bounce = True
                    if bounce:
                        if ax == 0: vx[i] = -vx[i]
                        else: vy[i] = -vy[i]
                        continue
                x[i] = nx; y[i] = ny
            en[i] -= 0.09
            if en[i] <= 0:
                alive[i] = False
                break


@njit(cache=True)
def fire(x, y, vx, vy, tm, en, bp, alive, t, n, bx, by, ang, spread, speed, energy, bounce, start, r0):
    m = x.shape[0]; made = 0; i = start
    for _ in range(m):
        if made >= n:
            break
        i = (i + 1) % m
        if alive[i]:
            continue
        a = ang + (np.random.random() - 0.5) * spread
        sp = speed * (0.8 + 0.4 * np.random.random())
        x[i] = bx + math.cos(a) * r0; y[i] = by + math.sin(a) * r0
        vx[i] = math.cos(a) * sp; vy[i] = math.sin(a) * sp
        tm[i] = t; en[i] = energy; bp[i] = bounce; alive[i] = True
        made += 1
    return i


@njit(cache=True)
def beam(grid, bx, by, ang, L, wid, t, prot, bases, br2, nt, conv):
    g = grid.shape[0]; ca = math.cos(ang); sa = math.sin(ang); BOSS = nt + 1; VOID = nt + 2
    end = L
    for k in range(40, int(L)):
        px = bx + ca * k; py = by + sa * k
        if px < 0 or px >= g or py < 0 or py >= g:
            return k
        stop = False
        for dy in range(-wid, wid + 1):
            for dx in range(-wid, wid + 1):
                if dx * dx + dy * dy > wid * wid:
                    continue
                qx = int(px) + dx; qy = int(py) + dy
                if qx < 0 or qy < 0 or qx >= g or qy >= g:
                    continue
                o = grid[qy, qx]
                if o == BOSS or o == VOID:
                    stop = True; continue
                if o != t:
                    if o < nt and prot[o] > 0:
                        ex = qx - bases[o, 0]; ey = qy - bases[o, 1]
                        if ex * ex + ey * ey < br2 * 2.25:
                            stop = True; continue
                    grid[qy, qx] = t; conv[t] += 1
        if stop:
            return k
    return end


@njit(cache=True)
def count(grid, n):
    c = np.zeros(n, np.int64)
    for v in grid.ravel():
        c[v] += 1
    return c


@njit(cache=True)
def disk_counts(grid, cx, cy, r, n):
    g = grid.shape[0]; c = np.zeros(n, np.int64)
    for yy in range(max(0, cy - r), min(g, cy + r + 1)):
        for xx in range(max(0, cx - r), min(g, cx + r + 1)):
            if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                c[grid[yy, xx]] += 1
    return c


@njit(cache=True)
def fade(grid, t, c, p):
    g = grid.shape[0]
    for yy in range(g):
        for xx in range(g):
            if grid[yy, xx] == t and np.random.random() < p:
                grid[yy, xx] = c


@njit(cache=True)
def crater(grid, cx, cy, r, val, bases, alive_t, br2, nt):
    g = grid.shape[0]
    for yy in range(max(0, cy - r), min(g, cy + r + 1)):
        for xx in range(max(0, cx - r), min(g, cx + r + 1)):
            d2 = (xx - cx) ** 2 + (yy - cy) ** 2
            if d2 > r * r:
                continue
            # ragged edge
            if d2 > (r * 0.8) ** 2 and np.random.random() < 0.5:
                continue
            o = grid[yy, xx]
            if o == nt + 1 or o == nt + 2:
                continue
            ok = True
            for b in range(nt):
                if alive_t[b]:
                    ex = xx - bases[b, 0]; ey = yy - bases[b, 1]
                    if ex * ex + ey * ey < br2 * 2.25:
                        ok = False; break
            if ok:
                grid[yy, xx] = val


@njit(cache=True)
def apply_ring(grid, cx, cy, r, void):
    g = grid.shape[0]; r2 = r * r
    for yy in range(g):
        dy2 = (yy - cy) ** 2
        if dy2 <= r2:
            hw = math.sqrt(r2 - dy2)
            x0 = int(cx - hw); x1 = int(cx + hw) + 1
            for xx in range(0, max(0, min(g, x0))):
                grid[yy, xx] = void
            for xx in range(max(0, x1), g):
                grid[yy, xx] = void
        else:
            for xx in range(g):
                grid[yy, xx] = void


@njit(cache=True)
def draw_parts(img, fx, x, y, tm, en, alive, core, edge, glow):
    g = img.shape[0]
    for ps in range(2):
        for i in range(x.shape[0]):
            if not alive[i]:
                continue
            cx = int(x[i]); cy = int(y[i]); t = tm[i]
            big = en[i] > 200
            r = 3 if big else 1
            if ps == 0:
                lo, hi = -r - 1, r + 1
                if not big:
                    lo, hi = -1, 1
                for dy in range(lo, hi + 1):
                    for dx in range(lo, hi + 1):
                        px = cx + dx; py = cy + dy
                        if 0 <= px < g and 0 <= py < g:
                            img[py, px, 0] = edge[t, 0]; img[py, px, 1] = edge[t, 1]; img[py, px, 2] = edge[t, 2]
                k = 3.0 if big else 1.0
                for c in range(3):
                    fx[cy, cx, c] += glow[t, c] * 0.55 * k
            else:
                lo, hi = -r, r
                for dy in range(lo, hi):
                    for dx in range(lo, hi):
                        px = cx + dx + 1; py = cy + dy + 1
                        if 0 <= px < g and 0 <= py < g:
                            img[py, px, 0] = core[t, 0]; img[py, px, 1] = core[t, 1]; img[py, px, 2] = core[t, 2]


@njit(cache=True)
def fx_disk(fx, cx, cy, r, cr, cg, cb):
    g = fx.shape[0]; ir = int(r) + 1
    for yy in range(max(0, int(cy) - ir), min(g, int(cy) + ir)):
        for xx in range(max(0, int(cx) - ir), min(g, int(cx) + ir)):
            d = math.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            if d < r:
                k = 1.0 - d / r
                fx[yy, xx, 0] += cr * k; fx[yy, xx, 1] += cg * k; fx[yy, xx, 2] += cb * k


@njit(cache=True)
def fx_points(fx, xs, ys, cols, k):
    g = fx.shape[0]
    for i in range(xs.shape[0]):
        cx = int(xs[i]); cy = int(ys[i])
        if 0 < cx < g - 1 and 0 < cy < g - 1:
            for c in range(3):
                v = cols[i, c] * k
                fx[cy, cx, c] += v
                fx[cy + 1, cx, c] += v * 0.5; fx[cy, cx + 1, c] += v * 0.5


@njit(cache=True)
def fx_line(fx, x0, y0, x1, y1, wid, cr, cg, cb):
    g = fx.shape[0]; L = int(math.hypot(x1 - x0, y1 - y0)) + 1
    for k in range(L):
        px = x0 + (x1 - x0) * k / L; py = y0 + (y1 - y0) * k / L
        for dy in range(-wid, wid + 1):
            for dx in range(-wid, wid + 1):
                qx = int(px) + dx; qy = int(py) + dy
                if 0 <= qx < g and 0 <= qy < g:
                    f = 1.0 - (abs(dx) + abs(dy)) / (2.0 * wid + 1)
                    fx[qy, qx, 0] += cr * f; fx[qy, qx, 1] += cg * f; fx[qy, qx, 2] += cb * f


def fmt(v):
    v = float(v)
    for u, d in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= d:
            return f"{v/d:.2f}{u}" if v / d < 10 else (f"{v/d:.1f}{u}" if v / d < 100 else f"{v/d:.0f}{u}")
    return str(int(v))


@njit(cache=True)
def paint_disk(grid, cx, cy, r, val, nt, p):
    g = grid.shape[0]
    for yy in range(max(0, cy - r), min(g, cy + r + 1)):
        for xx in range(max(0, cx - r), min(g, cx + r + 1)):
            if (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r:
                o = grid[yy, xx]
                if o != val and o != nt + 1 and o != nt + 2 and np.random.random() < p:
                    grid[yy, xx] = val


# ---------------------------------------------------------------- per-team plinko board
class Board:
    def __init__(self, t, bw, bh, nslots, rng):
        self.t, self.bw, self.bh, self.k, self.rng = t, bw, bh, nslots, rng
        self.ncol = int((bw - 16) / PS); self.mx = (bw - self.ncol * PS) / 2
        self.slot_y = bh - SH; self.nr = int((self.slot_y - 34 - PY0) / PDY) + 1
        self.ball = None; self.wait = int(rng.integers(5, 45)); self.last = None
        self.reshuffle()

    def reshuffle(self):
        rng, k = self.rng, self.k
        nr = max(2, min(len(RARE), k // 4)); nm = max(3, min(len(MID), k // 3)); nc = min(len(COMMON), k - nr - nm)
        nm = min(len(MID), k - nr - nc)
        mids = ["升级"] + list(rng.choice([m for m in MID if m != "升级"], nm - 1, replace=False))
        names = list(rng.choice(COMMON, nc, replace=False)) + mids + list(rng.choice(RARE, nr, replace=False))
        names = [str(n) for n in names]; rng.shuffle(names)
        # width inversely proportional to value, with a minimum so labels still fit
        # rare: 21-24px, mid: 29-33px, common: share the rest by weight (always the widest)
        wt = np.array([SKILLS[n][0] for n in names]); tier = np.array([SKILLS[n][1] for n in names]); tot = self.bw - 6
        wd = np.where(tier == 2, 14 + 12 * wt, np.where(tier == 1, 14 + 14 * wt, 0.0))
        com = tier == 0; wd[com] = (tot - wd[~com].sum()) * wt[com] / wt[com].sum()
        self.names = names; self.edges = 3 + np.concatenate([[0], np.cumsum(wd)])
        self.flash = np.zeros(len(names), int)

    def pegs(self):
        out = []
        for r in range(self.nr):
            py = PY0 + r * PDY
            if r % 2 == 0: out += [(self.mx + PS / 2 + j * PS, py) for j in range(self.ncol)]
            else: out += [(self.mx + j * PS, py) for j in range(1, self.ncol)]
        return out

    def tick(self, w):
        self.flash = np.maximum(self.flash - 1, 0)
        if self.ball is None:
            self.wait -= 1
            if self.wait <= 0:
                good = [i for i, s in enumerate(self.names) if SKILLS[s][1] >= 1]
                tg = int(self.rng.choice(good)) if self.rng.random() < 0.12 + 0.5 * w else -1
                self.ball = [self.bw / 2 + self.rng.uniform(-30, 30), 4.0, self.rng.uniform(-.8, .8), 0.0, tg, w]
            return []
        x, y, vx, vy, tg, wk = self.ball; rng = self.rng
        for _ in range(3):
            vy += 0.10
            if tg >= 0 and y > 110:
                cx = (self.edges[tg] + self.edges[tg + 1]) / 2
                vx += 0.012 * (0.6 + wk) * np.sign(cx - x)
            x += vx; y += vy
            if x < 9: x = 9; vx = abs(vx) * .5
            if x > self.bw - 9: x = self.bw - 9; vx = -abs(vx) * .5
            r = int(round((y - PY0) / PDY))
            if 0 <= r < self.nr:
                py = PY0 + r * PDY; off = self.mx + (PS / 2 if r % 2 == 0 else 0.0)
                j = int(round((x - off) / PS))
                if (r % 2 == 0 and 0 <= j < self.ncol) or (r % 2 == 1 and 1 <= j < self.ncol):
                    px = off + j * PS; dx, dy = x - px, y - py; d = math.hypot(dx, dy)
                    if d < 9.0:
                        nx, ny = (dx / d, dy / d) if d > 1e-3 else (0.0, -1.0)
                        x, y = px + nx * 9.0, py + ny * 9.0
                        vn = vx * nx + vy * ny
                        if vn < 0: vx -= 1.5 * vn * nx; vy -= 1.5 * vn * ny
                        vx += rng.normal(0, .5)
            sp = math.hypot(vx, vy)
            if sp > 3.4: vx *= 3.4 / sp; vy *= 3.4 / sp
        self.ball = [x, y, vx, vy, tg, wk]
        if y >= self.slot_y:
            s = int(np.clip(np.searchsorted(self.edges, x) - 1, 0, len(self.names) - 1))
            self.flash[s] = 26; self.last = [x, s, 20]; self.ball = None; self.wait = int(rng.integers(8, 22))
            return [(self.names[s], s)]
        return []


def layout(nt):
    cols = (nt + 1) // 2; cw = (LX1 - LX0 - (cols - 1) * GAP) / cols; ch = (BOT - TOP - GAP) / 2
    return [(LX0 + (t % cols) * (cw + GAP), TOP + (t // cols) * (ch + GAP), cw, ch) for t in range(nt)]


# ---------------------------------------------------------------- simulation
class Sim:
    def __init__(self, seed, nt=6, dur=600.0):
        self.nt = nt; self.dur = dur; self.maxf = int(dur * FPS); self.seed = seed
        rng = self.rng = np.random.default_rng(seed); nb_seed(seed)
        md = G * {4: .42, 5: .38, 6: .33, 7: .30, 8: .27}[nt]; sites = []; tries = 0
        while len(sites) < nt:
            a, r = rng.uniform(0, 2 * math.pi), G * .34 * math.sqrt(rng.uniform(.15, 1))
            p = (G / 2 + r * math.cos(a), G / 2 + r * math.sin(a)); tries += 1
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= md for q in sites): sites.append(p)
            if tries > 4000: sites, tries, md = [], 0, md * .95
        self.bases = np.array(sites, float)
        yy, xx = np.mgrid[0:G, 0:G].astype(np.float32)
        wx = xx + 18 * np.sin(yy / 47 + rng.uniform(0, 6)); wy = yy + 18 * np.sin(xx / 53 + rng.uniform(0, 6))
        d = np.stack([(wx - b[0]) ** 2 + (wy - b[1]) ** 2 for b in self.bases])
        self.grid = d.argmin(0).astype(np.int8); del d, wx, wy, yy, xx
        z = lambda dt=float: np.zeros(NMAX, dt)
        self.x, self.y, self.vx, self.vy, self.en, self.bp = z(), z(), z(), z(), z(), z()
        self.tm = z(np.int8); self.alive = z(bool); self.cur = 0
        self.ammo = np.full(nt, 1000.0); self.level = np.ones(nt, int); self.pts = np.zeros(nt, int)
        self.alive_t = np.ones(nt, bool); self.shield = np.zeros(nt, int); self.weap = np.full(nt, -1); self.wt = np.zeros(nt, int)
        self.frozen = np.zeros(nt, int); self.mis = np.zeros(nt, int); self.reinf = np.zeros(nt, int)
        self.ang = np.zeros(nt); self.phs = rng.uniform(0, 6.28, nt)
        self.tgt = np.full(nt, -1); self.tgt_t = np.zeros(nt, int)
        self.ult_cd = np.full(nt, 60); self.laser_t = np.zeros(nt, int); self.beam = [None] * nt
        self.cells = layout(nt); cw, ch = self.cells[0][2], self.cells[0][3]
        ns = int(np.clip(cw / 33, 6, 13))
        self.boards = {t: Board(t, cw, ch - HH, ns, np.random.default_rng(seed * 100 + t)) for t in range(nt)}
        S = self.sec
        self.siege_t, self.siege_left, self.siege_cd = -1, 0, S(20)
        self.next_meteor = S(rng.uniform(45, 60)); self.meteors = []
        self.boss = None; self.boss_fs = [S(150), S(300), S(445)]; self.boss_dmg = np.zeros(nt, np.int64); self.wave = 0
        self.bomb_fs = [S(rng.uniform(250, 265)), S(rng.uniform(390, 405))]
        self.ring_f = int(.78 * self.maxf); self.ring_end = int(.96 * self.maxf); self.ring = None; self.ring_c = None
        self.protect_f = S(105); self.sd_f = int(.9 * self.maxf)
        self.hits = np.zeros((600, 3)); self.nh = np.zeros(1, np.int64); self.fades = []
        self.f = 0; self.phase = 0; self.done = False; self.winner = -1
        self.lead, self.lead_changes, self.comebacks, self.elims = -1, 0, 0, []
        self.low_f = {}; self.cb_cd = np.zeros(nt, int); self.close_cd = 0; self.hist = []; self.elim_by = {}
        self.share = count(self.grid, nt + 3) / float(G * G); self.nskill = 0; self.lv8 = -1

    def sec(self, s):
        return int(s * self.maxf / 600.0)

    def add_up(self, t, k, ev):
        self.pts[t] += k
        while self.level[t] < MAXL and self.pts[t] >= NEED[self.level[t]]:
            self.pts[t] -= NEED[self.level[t]]; self.level[t] += 1; ev.append(("lvl", t, int(self.level[t])))
            if self.level[t] == MAXL:
                ev.append(("cap", f"{TEAM_POOL[t][0]}炮台满级 Lv.8！终极形态！", t))
                if self.lv8 < 0: self.lv8 = self.f
        if self.level[t] == MAXL and self.pts[t] > 0:
            self.pts[t] = 0; self.ult_cd[t] = min(self.ult_cd[t], 1)

    def strongest_enemy(self, t):
        o = [x for x in range(self.nt) if x != t and self.alive_t[x]]
        return max(o, key=lambda x: self.share[x]) if o else -1

    def skill(self, t, name, ev):
        self.nskill += 1; F = FPS
        if name[0] == "x":
            m = int(name[1:]); self.ammo[t] *= m
            if m == 10: self.add_up(t, 1, ev); ev.append(("cap", f"{TEAM_POOL[t][0]}命中 x10 大奖！", t))
        elif name == "升级": self.add_up(t, 1, ev)
        elif name in WEAP:
            self.weap[t] = WEAP.index(name); self.wt[t] = {0: 7, 1: 7, 2: 5, 3: 6}[self.weap[t]] * F
        elif name == "护盾": self.shield[t] = 10 * F
        elif name == "修复":
            paint_disk(self.grid, int(self.bases[t, 0]), int(self.bases[t, 1]), 80, t, self.nt, 1.0)
            self.shield[t] = max(self.shield[t], 3 * F)
        elif name == "激光": self.laser_t[t] = max(self.laser_t[t], 45)
        elif name == "导弹": self.mis[t] += 8
        elif name == "援军":
            self.reinf[t] = 4 * F; ev.append(("cap", f"{TEAM_POOL[t][0]}召唤援军！", t))
        elif name == "冰冻":
            o = self.strongest_enemy(t)
            if o >= 0:
                self.frozen[o] = 6 * F; ev.append(("freeze", t, o)); ev.append(("cap", f"{TEAM_POOL[t][0]}冰冻了{TEAM_POOL[o][0]}！", t))
        elif name == "终极":
            bx, by = self.bases[t]
            self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, 2200, bx, by,
                            0.0, 2 * math.pi, 1.1, 50.0, .3, self.cur, 36.0)
            self.laser_t[t] = max(self.laser_t[t], 40); ev.append(("ult", t))
            ev.append(("cap", f"{TEAM_POOL[t][0]}释放终极大招！", t))
        ev.append(("skill", t, name))

    def target(self, t):
        if self.siege_left > 0 and self.siege_t != t and self.alive_t[self.siege_t]:
            return self.siege_t
        if self.tgt_t[t] <= 0 or self.tgt[t] < 0 or not self.alive_t[self.tgt[t]]:
            cand = [o for o in range(self.nt) if o != t and self.alive_t[o]]
            if not cand: return -1
            cand.sort(key=lambda o: np.hypot(*(self.bases[o] - self.bases[t])))
            self.tgt[t] = cand[0] if len(cand) == 1 or self.rng.random() < .65 else cand[1]
            self.tgt_t[t] = int(self.rng.integers(120, 300))
        self.tgt_t[t] -= 1
        return int(self.tgt[t])

    def eliminate(self, t, c, ev):
        self.alive_t[t] = False; self.alive[self.alive & (self.tm == t)] = False
        self.fades.append([t, c, 45]); self.ammo[c] += self.ammo[t] * .5; self.ammo[t] = 0
        self.elims.append(self.f); self.elim_by[t] = c
        ev.append(("elim", t, c)); self.add_up(c, 2, ev)
        if self.f < self.sd_f:   # aftershock shield: every surviving base is safe for a while
            self.shield[self.alive_t] = np.maximum(self.shield[self.alive_t], self.sec(35))
        n = int(self.alive_t.sum())
        ev.append(("cap", f"{TEAM_POOL[t][0]}出局！" + (f"剩余{n}队" if n > 1 else ""), c))

    def tick(self):
        nt, f, rng, S = self.nt, self.f, self.rng, self.sec; ev = []; T = f / self.maxf
        ph = sum(T >= p for p in PH_T) - 1
        if ph != self.phase:
            self.phase = ph; ev.append(("phase", ph))
            for b in self.boards.values(): b.reshuffle()
            ev.append(("reshuffle",))
        sd = f >= self.sd_f
        if f == self.sd_f: ev.append(("sd",)); ev.append(("cap", "终局加速！基地防御失效", -1))
        al = self.alive_t; aidx = [int(t) for t in np.flatnonzero(al)]
        sh = self.share[:nt]; avg = sh[al].mean()
        weak = np.clip((avg - sh) / max(avg, 1e-6), 0, 1) * al
        for t in aidx:
            for lab, s in self.boards[t].tick(weak[t]): self.skill(t, lab, ev)
        # siege on the leader
        if self.siege_left > 0:
            self.siege_left -= 1
            if self.siege_left == 0 or not al[self.siege_t]:
                self.siege_left = 0; self.siege_cd = S(24); ev.append(("siege_end", self.siege_t))
        else:
            self.siege_cd -= 1
            if ph >= 1 and self.siege_cd <= 0 and len(aidx) >= 3 and f % 15 == 0:
                o = sorted(aidx, key=lambda t: -sh[t])
                if sh[o[0]] > max(.22, 1.3 * sh[o[1]]):
                    self.siege_t, self.siege_left = o[0], S(11); ev.append(("siege", o[0]))
                    ev.append(("cap", f"{TEAM_POOL[o[0]][0]}被围剿！", o[0]))
        # meteors
        if f >= self.next_meteor and T < .95:
            lead = max(aidx, key=lambda t: sh[t])
            if rng.random() < .6:
                ys, xs = np.nonzero(self.grid == lead)
                k = int(rng.integers(len(ys))) if len(ys) else 0
                mx, my = (int(xs[k]), int(ys[k])) if len(ys) else (G // 2, G // 2)
            else:
                mx, my = int(rng.integers(80, G - 80)), int(rng.integers(80, G - 80))
            r = int(rng.integers(45, 80)); self.meteors.append([mx, my, r, f + 24]); ev.append(("meteor", mx, my, r))
            self.next_meteor += S(rng.uniform(14, 24) if ph == 3 else rng.uniform(18, 30))
        for m in [m for m in self.meteors if m[3] == f]:
            crater(self.grid, m[0], m[1], m[2], nt, self.bases, self.alive_t, float(BR * BR), nt)
            ev.append(("impact", m[0], m[1], m[2])); self.meteors.remove(m)
        # boss waves
        if f in self.boss_fs and self.boss is None:
            self.wave += 1; best = None
            for _ in range(300):
                p = rng.uniform(G * .2, G * .8, 2); dd = np.hypot(*(self.bases[al] - p).T).min()
                if best is None or dd > best[0]: best = (dd, p)
            bx, by = int(best[1][0]), int(best[1][1]); yy, xx = np.ogrid[0:G, 0:G]
            self.grid[(xx - bx) ** 2 + (yy - by) ** 2 <= 42 * 42] = nt + 1; hp = 12000 * (1 + .6 * (self.wave - 1))
            self.boss = dict(x=bx, y=by, hp=hp, hp0=hp, f0=f); self.boss_dmg[:] = 0; ev.append(("boss", bx, by, self.wave))
            ev.append(("cap", f"第{self.wave}波 Boss 降临！击破者弹药x8 +2级", -1))
        if self.boss and (f - self.boss["f0"]) % 150 == 149:
            crater(self.grid, self.boss["x"], self.boss["y"], 100, nt, self.bases, self.alive_t, float(BR * BR), nt)
            ev.append(("bshock", self.boss["x"], self.boss["y"]))
        if self.boss and f - self.boss["f0"] > S(90):
            self.grid[self.grid == nt + 1] = nt; self.boss = None; ev.append(("bleave",)); ev.append(("cap", "Boss 撤退了…", -1))
        if f in self.bomb_fs:
            self.alive[:] = False; ev.append(("bomb",)); ev.append(("cap", "清屏炸弹！全场粒子清空", -1))
        if f >= self.ring_f:
            if self.ring_c is None:
                top = sorted(aidx, key=lambda t: -sh[t])[:2]
                if len(top) == 2:
                    a, b = self.bases[top[0]], self.bases[top[1]]; c = (a + b) / 2
                    self.ring_r1 = max(130.0, np.hypot(*(a - b)) / 2 + 75)
                else:
                    c = self.bases[top[0]]; self.ring_r1 = 130.0
                self.ring_c = c; ev.append(("ring",)); ev.append(("cap", "毒圈收缩！最终决战！", -1))
            fr = min(1.0, (f - self.ring_f) / max(1, self.ring_end - self.ring_f)); e = fr * fr * (3 - 2 * fr)
            cx = G / 2 + (self.ring_c[0] - G / 2) * e; cy = G / 2 + (self.ring_c[1] - G / 2) * e
            self.ring = (cx, cy, G * .72 + (self.ring_r1 - G * .72) * e)
            if f % 3 == 0: apply_ring(self.grid, cx, cy, self.ring[2], nt + 2)
        # fire
        I = (.4 + .6 * T) * (1.3 if sd else 1.0)
        for t in aidx:
            o = self.target(t)
            self.beam[t] = None
            if o < 0: continue
            bx, by = self.bases[t]; ox, oy = self.bases[o]
            ba = math.atan2(oy - by, ox - bx); self.ang[t] = ba + .55 * math.sin(f * .04 + self.phs[t])
            inc = 6 * (1 + 25 * sh[t]) * (1 + 2 * weak[t]) * 10 ** (f / FPS / 160 * 600 / self.dur)
            L = int(self.level[t]); self.ammo[t] = (self.ammo[t] + inc) * (1 - .012 - .0012 * L)
            if self.frozen[t] > 0: continue
            lg = max(.6, math.log10(self.ammo[t] + 10) - 1.6)
            n = 3.2 * lg * (1 + .9 * weak[t]) * I * (1.6 if L == 4 else 1.0) / math.sqrt(len(BARRELS[L]))
            energy, spread, speed, bounce = 30 + 4 * L, .10, 1.0, .45
            w = self.weap[t] if self.wt[t] > 0 else -1
            if w == 0: spread, n = 1.2, n * 2
            elif w == 1: n, spread = n * 3, .04
            elif w == 2: n, energy, bounce = max(.3, n / 10), 1500.0, 0.0
            elif w == 3: self.ang[t] = ba; n, spread, energy, bounce = n / 2, .02, 300.0, 0.0
            for off in BARRELS[L]:
                k = int(n + rng.random())
                if k: self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, k, bx, by,
                                     self.ang[t] + off, spread, speed, energy, bounce, self.cur, 36.0)
            if L >= 5 and self.laser_t[t] == 0 and (f + t * 23) % (110 if L < 7 else 70) == 0:
                self.laser_t[t] = 26; ev.append(("laser", t))
            if L >= 6 and f % 8 == 0:
                self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, 2, bx, by,
                                ba, .06, 1.2, 260.0, 0.0, self.cur, 36.0)
            if self.mis[t] > 0 and f % 4 == 0:
                self.mis[t] -= 1
                self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, 4, bx, by,
                                ba, .05, 1.3, 420.0, 0.0, self.cur, 36.0)
            if self.reinf[t] > 0:
                self.reinf[t] -= 1
                self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, int(n * 2) + 6, bx, by,
                                ba, .9, 1.0, 45.0, .3, self.cur, 36.0)
            if L == MAXL:
                self.ult_cd[t] -= 1
                if self.ult_cd[t] <= 0:
                    self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, 1500, bx, by,
                                    0.0, 2 * math.pi, 1.1, 45.0, .3, self.cur, 36.0)
                    self.ult_cd[t] = S(14); ev.append(("ult", t))
        self.wt -= 1; self.shield = np.maximum(self.shield - 1, 0); self.frozen = np.maximum(self.frozen - 1, 0)
        prot = ((self.shield > 0) | (f < self.protect_f)).astype(np.int64)
        conv = np.zeros(nt, np.int64)
        for t in aidx:
            if self.laser_t[t] > 0:
                self.laser_t[t] -= 1
                Lb = 330 + 25 * ph
                e = beam(self.grid, self.bases[t, 0], self.bases[t, 1], self.ang[t], Lb, 4 if self.level[t] < 7 else 6,
                         t, prot, self.bases, float(BR * BR), nt, conv)
                self.beam[t] = (self.bases[t, 0], self.bases[t, 1], self.bases[t, 0] + math.cos(self.ang[t]) * e,
                                self.bases[t, 1] + math.sin(self.ang[t]) * e)
        bosshit = np.zeros(nt, np.int64); self.nh[0] = 0
        step(self.grid, self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, conv, prot,
             self.bases, float(BR * BR), nt, bosshit, self.hits, self.nh)
        if self.boss:
            self.boss_dmg += bosshit; self.boss["hp"] -= int(bosshit.sum())
            if self.boss["hp"] <= 0:
                dm = self.boss_dmg * al; k = int(dm.argmax())
                self.grid[self.grid == nt + 1] = k; self.ammo[k] *= 8; self.boss = None
                ev.append(("bkill", k)); ev.append(("cap", f"{TEAM_POOL[k][0]}击破Boss！弹药x8", k)); self.add_up(k, 2, ev)
        # base self-repair (keeps eliminations spread out); none in sudden death
        regen = 0.0 if sd else .06 * (1 - T) ** 1.6
        if f >= self.protect_f and regen > 0:
            for t in aidx:
                paint_disk(self.grid, int(self.bases[t, 0]), int(self.bases[t, 1]), BR, t, nt, regen)
        # eliminations
        if f >= self.protect_f:
            thr = .55 if sd else (.45 if ph == 3 else .3)
            for t in aidx:
                if not self.alive_t[t] or self.alive_t.sum() <= 1: continue
                c = disk_counts(self.grid, int(self.bases[t, 0]), int(self.bases[t, 1]), BR, nt + 3)
                if c[t] / max(1, c.sum()) < thr or self.share[t] < .0015:
                    oth = [o for o in range(nt) if o != t and self.alive_t[o]]
                    conq = max(oth, key=lambda o: (c[o], self.share[o]))
                    self.eliminate(t, conq, ev)
        for fd in self.fades:
            if not self.alive_t[fd[1]] and fd[1] in self.elim_by: fd[1] = self.elim_by[fd[1]]
            fade(self.grid, fd[0], fd[1], 1.0 / max(fd[2], 1)); fd[2] -= 1
        self.fades = [fd for fd in self.fades if fd[2] > 0]
        self.share = count(self.grid, nt + 3) / float(G * G); sh = self.share[:nt]
        if f % 15 == 0:
            self.hist.append(sh.copy())
            al2 = [t for t in range(nt) if self.alive_t[t]]
            if al2:
                lead = max(al2, key=lambda t: sh[t]); low = min(al2, key=lambda t: sh[t])
                self.low_f[low] = f
                if lead != self.lead and self.lead >= 0 and self.alive_t[self.lead] and sh[lead] > sh[self.lead] + .005:
                    self.lead_changes += 1; ev.append(("lead", lead))
                    if f - self.low_f.get(lead, -10 ** 9) < S(45) and self.cb_cd[lead] <= f and len(al2) >= 2:
                        self.comebacks += 1; self.cb_cd[lead] = f + S(30)
                        ev.append(("cap", f"{TEAM_POOL[lead][0]}绝地反击！", lead)); ev.append(("comeback", lead))
                    else:
                        ev.append(("cap", f"{TEAM_POOL[lead][0]}反超，登顶第一！", lead))
                    self.lead = lead
                elif self.lead < 0 or not self.alive_t[self.lead]:
                    self.lead = lead
                if len(al2) == 2 and abs(sh[al2[0]] - sh[al2[1]]) < .05 and f >= self.close_cd:
                    self.close_cd = f + S(25); ev.append(("cap", "势均力敌，胜负难料！", -1))
        self.f += 1
        if self.alive_t.sum() <= 1 or self.f >= self.maxf:
            al2 = [t for t in range(nt) if self.alive_t[t]]
            self.winner = max(al2, key=lambda t: sh[t]); self.done = True; ev.append(("win", self.winner))
        return int(conv.sum()), ev


def run_headless(args):
    seed, nt, dur = args
    t0 = time.time(); s = Sim(seed, nt, dur)
    while not s.done: s.tick()
    sc, info = score(s); info["sim_s"] = round(time.time() - t0)
    return seed, (sc, info)


def score(s):
    hist = np.array(s.hist); dur = s.dur; el = [e / FPS for e in s.elims]; ne = len(el); k = dur / 600
    sc = min(s.lead_changes, 16) * 2 + min(s.comebacks, 5) * 4 + ne * 6
    natural = bool(s.alive_t.sum() == 1); end = s.f / FPS
    if s.lv8 >= 0 and s.lv8 < .5 * s.maxf: sc -= 10
    if el:
        if 120 * k <= el[0] <= 240 * k: sc += 12
        elif el[0] < 90 * k: sc -= 15
    if ne >= 2:
        g = np.diff([0] + el); sc += 12 * max(0, 1 - g.std() / g.mean())
        if np.diff(el).min() < 10 * k: sc -= 6
    if natural: sc += 25
    if natural and end > .88 * dur: sc += 15
    if natural and end < .8 * dur: sc -= 25
    duel = [t for t in range(len(s.hist[0]))]
    # two (or more) teams alive at the start of the last 2 minutes
    if ne == 0 or sum(1 for e in el if e < dur - 120 * k) <= s.nt - 2: sc += 8
    tail = hist[int(len(hist) * .75):]
    top2 = np.sort(tail, 1)[:, -2:]; closeness = float((top2[:, 1] - top2[:, 0]).min()) if len(tail) else 1
    if closeness < .05: sc += 8
    mid = hist[int(len(hist) * .45)]
    if mid.max() > .40: sc -= 15
    return float(sc), dict(lead_changes=s.lead_changes, comebacks=s.comebacks, elims=[round(e, 1) for e in el],
                           end=round(end, 1), natural=natural, winner=int(s.winner), close=round(closeness, 3),
                           mid_max=round(float(mid.max()), 3), skills=s.nskill, lv=[int(v) for v in s.level],
                           lv8=round(s.lv8 / FPS, 1) if s.lv8 >= 0 else None)


# ---------------------------------------------------------------- audio
def make_audio(path, frames_ev, nframes, sr=44100):
    n = int((nframes / FPS + 1) * sr); a = np.zeros(n, np.float32); rng = np.random.default_rng(7)

    def add(st, sig):
        s = int(st * sr)
        if s >= n: return
        e = min(n, s + len(sig)); a[s:e] += sig[:e - s]

    def tone(fr, dur, vol, dec=30, sw=0.0, wave_="sin"):
        t = np.arange(int(dur * sr)) / sr; f = fr * (1 + sw * t / dur); ph = 2 * np.pi * np.cumsum(f) / sr
        w = np.sin(ph) if wave_ == "sin" else (2 * ((ph / (2 * np.pi)) % 1) - 1) * .6
        return (w * np.exp(-dec * t) * vol).astype(np.float32)

    def noise(dur, vol, dec, smooth=1):
        x = rng.normal(0, 1, int(dur * sr))
        if smooth > 1: x = np.convolve(x, np.ones(smooth) / smooth, "same") * math.sqrt(smooth) * .6
        return (x * np.exp(-dec * np.arange(len(x)) / sr) * vol).astype(np.float32)

    # background beat: tempo / layers change per phase (发育 92bpm -> 扩张 108 -> 混战 124 -> 决战 140)
    BPM = [92, 108, 124, 140]; bass = [55, 55, 65.4, 49, 55, 73.4, 65.4, 49]; ts = 0.0; i = 0
    total = nframes / FPS
    while ts < total:
        ph = frames_ev[min(len(frames_ev) - 1, int(ts * FPS))][2]; beat = 60.0 / BPM[max(0, ph)]
        add(ts, tone(100 + 6 * ph, .22, .15 + .03 * ph, 14, -.6))
        add(ts + beat / 2, noise(.04, .018 + .008 * ph, 70))
        if ph >= 1 and i % 2 == 1: add(ts, noise(.12, .045, 25, 6))
        if ph >= 1 and i % 4 == 0: add(ts, tone(bass[(i // 4) % 8] * 2, beat * 1.8, .035, 2))
        if ph >= 2: add(ts, tone(bass[(i // 4) % 8], beat * .9, .06 + .02 * (ph - 2), 4, 0, "saw"))
        if ph >= 2 and i % 2 == 0: add(ts + beat / 4, noise(.03, .02, 90))
        if ph == 3 and i % 8 == 4: add(ts, tone(880, .12, .05, 10))
        ts += beat; i += 1
    last = -1
    for fi, (conv, ev, ph) in enumerate(frames_ev):
        ts = fi / FPS
        if conv > 0 and ts - last >= 1 / 14:
            add(ts, tone(rng.uniform(1100, 1900), .035, .03 + .05 * min(1, conv / 30000), 90)); last = ts
        for e in ev:
            k = e[0]
            if k == "mult": add(ts, tone(500 + 70 * e[2], .25, .16, 10, .7))
            elif k == "jack":
                for j, fr in enumerate([784, 988, 1175, 1568, 1976]): add(ts + j * .06, tone(fr, .3, .16, 8))
            elif k == "skill":
                tier = SKILLS[e[2]][1]
                if tier == 0: add(ts, tone(520, .14, .09, 14, .5))
                elif tier == 1: add(ts, tone(330, .3, .14, 8, 1.2)); add(ts + .07, tone(660, .22, .1, 9))
                else:
                    for j, fr in enumerate([784, 988, 1175, 1568]): add(ts + j * .06, tone(fr, .3, .15, 8))
            elif k == "freeze": add(ts, tone(2400, .6, .1, 4, -.5)); add(ts, noise(.5, .05, 6, 2))
            elif k == "lvl":
                for j, fr in enumerate([392, 523, 659, 784, 1047][:e[2] + 1]): add(ts + j * .07, tone(fr, .4, .18, 6))
                add(ts, noise(.4, .04, 8) * np.linspace(0, 1, int(.4 * sr), dtype=np.float32))
            elif k == "elim":
                add(ts, noise(1.4, .55, 3.5, 14)); add(ts, tone(70, 1.0, .5, 3, -.4)); add(ts + .03, tone(440, .6, .2, 5, -.6))
            elif k == "impact": add(ts, noise(.9, .45, 5, 10)); add(ts, tone(55, .7, .4, 5, -.3))
            elif k == "meteor": add(ts, (noise(.8, .08, 1, 3) * np.linspace(0, 1, int(.8 * sr), dtype=np.float32)))
            elif k == "ult": add(ts, tone(200, .5, .22, 1, 4.0)); add(ts + .45, noise(.8, .4, 5, 8)); add(ts + .45, tone(60, .6, .4, 5))
            elif k == "bomb": add(ts, noise(1.2, .5, 3, 4)); add(ts, tone(1600, .8, .2, 4, -.9))
            elif k == "laser": add(ts, tone(180, .8, .12, 2, .3, "saw"))
            elif k in ("siege", "ring", "boss", "sd"):
                for j in range(4): add(ts + j * .22, tone(880 if j % 2 == 0 else 660, .18, .15, 6))
            elif k == "bkill": add(ts, noise(1.0, .4, 4, 10)); add(ts + .1, tone(523, .5, .2, 5, .5))
            elif k == "phase": add(ts, tone(262, .6, .18, 3, 1.0))
            elif k == "win":
                for j, fr in enumerate([523, 659, 784, 1047]): add(ts + .3 + j * .13, tone(fr, .5, .22, 5))
                for fr in (523, 659, 784, 1047): add(ts + .9, tone(fr, 1.8, .14, 1.8))
    a = np.tanh(a * 1.1) * .92
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32000).astype(np.int16).tobytes())


# ---------------------------------------------------------------- rendering
_fc = {}
def font(sz):
    sz = max(10, int(sz))
    if sz not in _fc: _fc[sz] = ImageFont.truetype(FONT, sz)
    return _fc[sz]


def ctext(d, cx, y, s, fn, fill, sw=3, sf=(0, 0, 0)):
    d.text((cx - d.textlength(s, font=fn) / 2, y), s, font=fn, fill=fill, stroke_width=sw, stroke_fill=sf)


def rtext(d, rx, y, s, fn, fill, sw=2):
    d.text((rx - d.textlength(s, font=fn), y), s, font=fn, fill=fill, stroke_width=sw, stroke_fill=(0, 0, 0))


def slot_label(d, X0, X1, y0, y1, name, col):
    """Horizontal label if it fits, else stacked (two lines)."""
    wd = X1 - X0; cx = (X0 + X1) / 2
    for fs in (24, 22, 20):
        fn = font(fs)
        if d.textlength(name, font=fn) + 4 <= wd:
            ctext(d, cx, (y0 + y1) / 2 - fs * .62, name, fn, col, 2); return
    parts = ["x", name[1:]] if name[0] == "x" else list(name)
    fs = 20 if wd >= 26 else 18; fn = font(fs); lh = fs + 3; yy = (y0 + y1) / 2 - lh * len(parts) / 2 - 2
    for pt in parts:
        ctext(d, cx, yy, pt, fn, col, 2 if wd >= 26 else 1); yy += lh


def slot_rect(b, s, x0, y0):
    return (x0 + b.edges[s] + 1, y0 + b.slot_y + 6, x0 + b.edges[s + 1] - 1, y0 + b.bh - 6)


def build_bg(sim, pal):
    yy = np.arange(H)[:, None, None] / H
    arr = np.broadcast_to(np.concatenate([8 + 10 * yy, 10 + 4 * yy, 26 + 20 * yy], -1), (H, W, 3)).astype(np.uint8)
    bg = Image.fromarray(np.ascontiguousarray(arr)); d = ImageDraw.Draw(bg)
    d.rectangle((MX - 6, MY - 6, MX + G + 5, MY + G + 5), outline=(70, 230, 255), width=2)
    for t, (x0, y0, cw, ch) in enumerate(sim.cells):
        c = tuple(int(v) for v in pal[t]); dim = tuple(int(v * .5) for v in pal[t]); b = sim.boards[t]
        d.rounded_rectangle((x0, y0, x0 + cw, y0 + HH - 4), 10, fill=(18, 22, 46), outline=dim, width=2)
        d.rectangle((x0 + 3, y0 + 3, x0 + 9, y0 + HH - 8), fill=c)
        by = y0 + HH
        d.rounded_rectangle((x0, by, x0 + cw, y0 + ch), 10, fill=(13, 16, 34), outline=dim, width=2)
        for px, py in b.pegs():
            X, Y = x0 + px, by + py
            d.ellipse((X - 3, Y - 3, X + 3, Y + 3), fill=(150, 165, 215))
        for s, name in enumerate(b.names):
            col = SKILLS[name][2]; tier = SKILLS[name][1]
            fill = [(26, 30, 56), (44, 36, 70), (78, 40, 52)][tier]
            r = slot_rect(b, s, x0, by)
            d.rounded_rectangle(r, 4, fill=fill, outline=col, width=1 + tier)
            slot_label(d, r[0], r[2], r[1], r[3], name, col)
        for e in b.edges[1:-1]:
            d.line((x0 + e, by + b.slot_y - 22, x0 + e, by + b.slot_y + 6), fill=(110, 120, 170), width=2)
    return bg


class FX:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed + 999)
        self.fx = np.zeros((G, G, 3), np.float32)
        self.sp = np.zeros((0, 8), np.float32)
        self.rings, self.banners, self.caps, self.pops, self.cards = [], [], [], [], []
        self.shake = 0.0; self.flash = 0.0; self.slow = 0; self.cap = None

    def burst(self, x, y, n, col, spd=3.0, life=30):
        a = self.rng.uniform(0, 2 * np.pi, n); v = self.rng.exponential(spd, n)
        c = np.array(col, np.float32)[None].repeat(n, 0) * self.rng.uniform(.7, 1.3, (n, 1))
        s = np.column_stack([np.full(n, x), np.full(n, y), np.cos(a) * v, np.sin(a) * v,
                             self.rng.integers(life // 2, life, n), c]).astype(np.float32)
        self.sp = np.concatenate([self.sp, s])[-20000:]

    def update_sparks(self):
        s = self.sp
        if len(s):
            s[:, 0] += s[:, 2]; s[:, 1] += s[:, 3]; s[:, 2:4] *= .93; s[:, 4] -= 1
            self.sp = s[s[:, 4] > 0]
            k = np.clip(self.sp[:, 4:5] / 20, 0, 1)
            fx_points(self.fx, self.sp[:, 0], self.sp[:, 1], self.sp[:, 5:8] * k, 1.0)


def mmss(sec):
    return f"{int(sec) // 60:02d}:{int(sec) % 60:02d}"


PH_SUB = ["基地保护中 · 弹珠积累技能", "保护解除 · 抢地盘开始", "Boss 波次 · 清屏炸弹 · 围剿", "毒圈收缩 · 一决雌雄"]


def render(seed, nt, dur, episode, out, prefix, log=print):
    names = [n for n, _ in TEAM_POOL[:nt]]
    pal = np.array([c for _, c in TEAM_POOL[:nt]] + [NEU_C, BOSS_C, VOID_C], np.uint8)
    pf = pal.astype(np.float32)
    core = np.clip(pf * .35 + 255 * .65, 0, 255).astype(np.uint8)
    edge = np.clip(pf * .5, 0, 255).astype(np.uint8)
    glow = np.clip(pf * 1.15 + 30, 0, 255).astype(np.float32)
    sim = Sim(seed, nt, dur); fx = FX(seed); bg_np = np.asarray(build_bg(sim, pal))
    gl = np.zeros((G, G), bool); gl[::48, :] = True; gl[:, ::48] = True
    tmp = out + ".video.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                          "-maxrate", "4.2M", "-bufsize", "8.4M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
                         stdin=subprocess.PIPE)
    frames_ev = []; fi = 0; end_f = None; hold = 5 * FPS; elim_info = {}; keys = []
    snaps = {int(sim.maxf * k): i for i, k in enumerate((.02, .12, .2, .3, .4, .5, .6, .7, .8, .9))}
    fx.cards.append([f"粒子领地大战 · 第{episode}集", f"{nt}队混战 · 10分钟长篇", (120, 240, 255), 110, 110])
    T = lambda t: tuple(int(v) for v in pal[t])
    t0 = time.time(); cells = sim.cells; d0 = ImageDraw.Draw(Image.new('RGB', (4, 4)))
    while True:
        conv, ev = 0, []
        if end_f is None:
            if fx.slow <= 0 or fi % 2 == 0:
                conv, ev = sim.tick()
            if sim.done and any(e[0] == "win" for e in ev): end_f = fi
        frames_ev.append((conv, ev, sim.phase))
        for e in ev:
            k = e[0]
            if k in ("elim", "boss", "bkill", "phase", "bomb", "ring", "win", "ult", "freeze", "siege", "sd"): keys.append((fi, k))
            if k == "reshuffle":
                bg_np = np.asarray(build_bg(sim, pal))
            elif k == "lvl":
                t, L = e[1], e[2]; bx, by = sim.bases[t]
                fx.banners.append([f"{names[t]} 升级 Lv.{L} · {PATTERN[L]}！", T(t), 55, 55]); fx.rings.append([bx, by, 10, 26, T(t), 26])
                fx.burst(bx, by, 250, glow[t], 4, 30); fx.shake = max(fx.shake, 3 + L * .8); fx.flash = max(fx.flash, .1)
                if L == MAXL: keys.append((fi, "lv8"))
            elif k == "elim":
                t, c = e[1], e[2]; bx, by = sim.bases[t]; elim_info[t] = (c, sim.f)
                fx.banners.append([f"{names[t]} 基地被 {names[c]} 攻破！", T(c), 85, 85])
                fx.burst(bx, by, 1800, glow[t], 7, 60); fx.burst(bx, by, 600, (255, 255, 230), 5, 40)
                fx.rings.append([bx, by, 10, 40, (255, 255, 255), 40]); fx.rings.append([bx, by, 5, 50, T(c), 50])
                fx.shake = 16; fx.flash = max(fx.flash, .45); fx.slow = 40
            elif k == "ult":
                t = e[1]; bx, by = sim.bases[t]
                fx.flash = max(fx.flash, .5); fx.shake = max(fx.shake, 10); fx.rings.append([bx, by, 20, 34, T(t), 34])
                fx.banners.append([f"{names[t]} 终极大招！", T(t), 45, 45]); fx.burst(bx, by, 500, glow[t], 6, 40)
            elif k == "impact":
                _, x, y, r = e; fx.shake = max(fx.shake, 12); fx.flash = max(fx.flash, .16)
                fx.burst(x, y, 900, (255, 170, 70), 5, 45); fx.rings.append([x, y, r * .5, 30, (255, 200, 120), 30])
            elif k == "meteor": fx.banners.append(["陨石来袭！", (255, 170, 70), 45, 45])
            elif k == "bomb":
                fx.flash = .9; fx.shake = 10; fx.banners.append(["清屏炸弹！", (255, 255, 255), 60, 60])
                fx.rings.append([G / 2, G / 2, 20, 40, (255, 255, 255), 40])
            elif k == "siege":
                fx.banners.append([f"围剿 {names[e[1]]}！全员集火领先者", T(e[1]), 75, 75]); fx.shake = max(fx.shake, 6)
            elif k == "boss":
                fx.cards.append([f"第 {e[3]} 波 Boss 来袭", "击破者 弹药x8 · 升2级", (210, 120, 255), 80, 80])
                fx.rings.append([e[1], e[2], 10, 40, (210, 120, 255), 40])
            elif k == "bshock":
                fx.rings.append([e[1], e[2], 40, 30, (210, 120, 255), 30]); fx.shake = max(fx.shake, 5)
            elif k == "bkill":
                t = e[1]; fx.banners.append([f"{names[t]} 击破 Boss！", T(t), 70, 70])
                fx.flash = max(fx.flash, .4); fx.shake = 12; fx.slow = 24
            elif k == "freeze":
                t, o = e[1], e[2]; bx, by = sim.bases[o]; fx.banners.append([f"{names[t]} 冰冻 {names[o]} 6秒！", (150, 220, 255), 55, 55])
                fx.burst(bx, by, 400, (170, 230, 255), 4, 40); fx.rings.append([bx, by, 10, 30, (170, 230, 255), 30])
            elif k == "ring": fx.banners.append(["毒圈收缩 · 最终决战", (255, 80, 80), 70, 70])
            elif k == "sd": fx.cards.append(["终局加速", "基地防御失效 · 火力提升", (255, 90, 60), 80, 80])
            elif k == "phase":
                ph = e[1]; fx.cards.append([f"第{'一二三四'[ph]}阶段 · {PHASES[ph]}", PH_SUB[ph], PH_COL[ph], 95, 95])
            elif k == "cap":
                fx.caps.append(e[1]); fx.caps = fx.caps[-2:]
            elif k == "win":
                fx.slow = 0; fx.flash = .6; fx.shake = 12
            elif k == "skill":
                t, name = e[1], e[2]; b = sim.boards[t]; x0, y0 = cells[t][0], cells[t][1] + HH
                if b.last:
                    s = b.last[1]; cx = x0 + (b.edges[s] + b.edges[s + 1]) / 2
                    txt = ("+" + name) if name[0] == "x" else name + "!"
                    hw = d0.textlength(txt, font=font([22, 26, 32][SKILLS[name][1]] * 1.35)) / 2 + 4
                    cx = min(max(cx, cells[t][0] + hw), cells[t][0] + cells[t][2] - hw)
                    fx.pops.append([cx, y0 + b.slot_y - 30, txt, SKILLS[name][2], 45, SKILLS[name][1]])
                if SKILLS[name][1] == 2:
                    fx.banners.append([f"{names[t]} 命中稀有技能【{name}】！", SKILLS[name][2], 50, 50])
                bx, by = sim.bases[t]; fx.burst(bx, by, 60 + 80 * SKILLS[name][1], SKILLS[name][2], 3, 24)
        # ---- map layer
        fx.fx *= .72
        fx.update_sparks()
        if sim.nh[0]:
            h = sim.hits[:sim.nh[0]]
            for j in range(0, len(h), 3):
                fx.burst(h[j, 0], h[j, 1], 4, glow[int(h[j, 2])], 1.8, 10)
        for t in range(nt):
            if sim.alive_t[t]:
                L = sim.level[t]; fx_disk(fx.fx, sim.bases[t, 0], sim.bases[t, 1], BR + 10 + 6 * L,
                                          *(glow[t] * (.05 + .022 * L) * (1 + .3 * math.sin(fi * .2))))
                if sim.beam[t]:
                    x0, y0, x1, y1 = sim.beam[t]; fx_line(fx.fx, x0, y0, x1, y1, 5, *(glow[t] * .5))
        for m in sim.meteors:
            kk = (m[3] - sim.f) / 24; mx, my = m[0] + 300 * kk, m[1] - 500 * kk
            fx_disk(fx.fx, mx, my, 16, 255, 150, 60); fx.burst(mx, my, 6, (255, 140, 40), .8, 16)
        mp = pal[sim.grid]
        mp[gl] = (mp[gl] * .8 + 34).astype(np.uint8)
        gimg = Image.fromarray(np.clip(fx.fx, 0, 255).astype(np.uint8)).resize((G // 4, G // 4), Image.BOX)
        gimg = np.asarray(gimg.filter(ImageFilter.GaussianBlur(3)).resize((G, G), Image.BILINEAR), np.float32)
        mp = np.clip(mp.astype(np.float32) + fx.fx * .55 + gimg * 1.6, 0, 255).astype(np.uint8)
        draw_parts(mp, fx.fx, sim.x, sim.y, sim.tm, sim.en, sim.alive, core, edge, glow)
        if sim.ring:   # draw on the map layer only so the circle is clipped to the map
            mim = Image.fromarray(mp); md = ImageDraw.Draw(mim); cx, cy, r = sim.ring
            for wdt, col in ((9, (120, 20, 30)), (3, (255, 90, 90))):
                md.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=wdt)
            mp = np.asarray(mim)
        img = bg_np.copy(); img[MY:MY + G, MX:MX + G] = mp
        im = Image.fromarray(img); d = ImageDraw.Draw(im)
        ox, oy = MX, MY
        for t in range(nt):
            if sim.alive_t[t] and sim.beam[t]:
                x0, y0, x1, y1 = sim.beam[t]
                d.line((ox + x0, oy + y0, ox + x1, oy + y1), fill=T(t), width=10)
                d.line((ox + x0, oy + y0, ox + x1, oy + y1), fill=(255, 255, 255), width=3)
        if sim.boss:
            b = sim.boss; X, Y = ox + b["x"], oy + b["y"]; pr = 44 + 3 * math.sin(fi * .3)
            d.ellipse((X - pr, Y - pr, X + pr, Y + pr), outline=(210, 120, 255), width=4)
            ctext(d, X, Y - 18, "BOSS", font(24), (235, 200, 255))
            hp = max(0, b["hp"] / b["hp0"]); d.rectangle((X - 40, Y + 50, X + 40, Y + 58), fill=(30, 10, 40))
            d.rectangle((X - 40, Y + 50, X - 40 + 80 * hp, Y + 58), fill=(210, 120, 255))
        for rg in fx.rings:
            x, y, r0, life, col, l0 = rg; kk = 1 - life / l0; r = r0 + kk * (150 if l0 >= 40 else 90)
            d.ellipse((ox + x - r, oy + y - r, ox + x + r, oy + y + r), outline=col, width=max(1, int(8 * (1 - kk))))
            rg[3] -= 1
        fx.rings = [r for r in fx.rings if r[3] > 0]
        for t in range(nt):
            bx, by = ox + sim.bases[t, 0], oy + sim.bases[t, 1]
            if not sim.alive_t[t]:
                d.ellipse((bx - 22, by - 22, bx + 22, by + 22), fill=(30, 30, 36), outline=(80, 80, 90), width=3)
                d.line((bx - 12, by - 12, bx + 12, by + 12), fill=(150, 150, 160), width=4)
                d.line((bx - 12, by + 12, bx + 12, by - 12), fill=(150, 150, 160), width=4)
                continue
            L = int(sim.level[t]); c = T(t); R = 22 + 2 * L; a = sim.ang[t]
            if sim.f < sim.protect_f or sim.shield[t] > 0:
                w_ = 2 if sim.f < sim.protect_f and sim.shield[t] == 0 else 5
                d.ellipse((bx - BR * 1.5, by - BR * 1.5, bx + BR * 1.5, by + BR * 1.5), outline=(140, 235, 255), width=w_)
            if L >= 3:
                ar = R + 12 + 2 * L
                for j in range(6):
                    st = fi * 6 + j * 60
                    d.arc((bx - ar, by - ar, bx + ar, by + ar), st, st + 32, fill=c, width=3 if L < 6 else 5)
            blen = R + 16 + 3 * L
            for off in BARRELS[L]:
                aa = a + off
                d.line((bx, by, bx + math.cos(aa) * blen, by + math.sin(aa) * blen), fill=(20, 20, 30), width=12 if L < 6 else 14)
                d.line((bx, by, bx + math.cos(aa) * (blen - 2), by + math.sin(aa) * (blen - 2)), fill=c, width=7 if L < 6 else 9)
            fz = sim.frozen[t] > 0
            d.ellipse((bx - R, by - R, bx + R, by + R), fill=(170, 220, 255) if fz else c, outline=(255, 255, 255), width=3)
            ctext(d, bx, by - 15, f"Lv{L}", font(20), (255, 255, 255) if not fz else (20, 60, 120), 2 if not fz else 0)
            if fz: ctext(d, bx, by + R + 4, "冰冻", font(20), (170, 230, 255))
            if sim.siege_left > 0 and sim.siege_t == t:
                d.ellipse((bx - R - 26, by - R - 26, bx + R + 26, by + R + 26), outline=(255, 60, 60), width=3)
                ctext(d, bx, by + R + 6, "被围剿", font(20), (255, 90, 90))
        for m in sim.meteors:
            X, Y, r = ox + m[0], oy + m[1], m[2]
            d.ellipse((X - r, Y - r, X + r, Y + r), outline=(255, 160, 60), width=2)
        # ---- boards
        for t, (x0, y0, cw, ch) in enumerate(cells):
            b = sim.boards[t]; c = T(t); sc = min(1.0, cw / 299); by0 = y0 + HH
            for s in np.flatnonzero(b.flash):
                kk = b.flash[s] / 26; r = slot_rect(b, s, x0, by0); name = b.names[s]; col = SKILLS[name][2]
                fill = tuple(int(30 * (1 - kk) + col[i] * kk * .8) for i in range(3))
                d.rounded_rectangle((r[0] - 2, r[1] - 2 - 6 * kk, r[2] + 2, r[3] + 2), 4, fill=fill, outline=(255, 255, 255), width=2)
                slot_label(d, r[0], r[2], r[1], r[3], name, (255, 255, 255) if kk > .5 else col)
            if b.ball is not None and sim.alive_t[t]:
                X, Y = x0 + b.ball[0], by0 + b.ball[1]
                d.ellipse((X - 13, Y - 13, X + 13, Y + 13), fill=tuple(int(v * .4) for v in c))
                d.ellipse((X - 9, Y - 9, X + 9, Y + 9), fill=c, outline=(255, 255, 255), width=2)
                lab = fmt(sim.ammo[t]); fn = font(18); tw = d.textlength(lab, font=fn)
                lx = min(max(X - tw / 2, x0 + 4), x0 + cw - tw - 4)
                d.text((lx, Y - 34 if b.ball[1] > 40 else Y + 12), lab, font=fn, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
            if b.last and b.last[2] > 0:
                X = x0 + b.last[0]; Y = by0 + b.slot_y + 2; b.last[2] -= 1
                d.ellipse((X - 6, Y - 6, X + 6, Y + 6), fill=c, outline=(255, 255, 255), width=2)
            # header
            hx = x0 + 16; L = int(sim.level[t])
            d.text((hx, y0 + 4), names[t], font=font(28 * sc), fill=c, stroke_width=3, stroke_fill=(0, 0, 0))
            rtext(d, x0 + cw - 10, y0 + 8, f"Lv.{L} {PATTERN[L]}", font(22 * sc), (255, 235, 140))
            d.text((hx, y0 + 38), fmt(sim.ammo[t]), font=font(30 * sc), fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
            rtext(d, x0 + cw - 10, y0 + 44, f"领地 {sim.share[t]*100:.1f}%", font(21 * sc), (230, 235, 255))
            pw = min(14.0, (cw * .45) / MAXL)
            for j in range(MAXL):
                X0 = hx + j * pw; tc = (255, 220, 90) if j < 5 else (255, 120, 90)
                d.rectangle((X0, y0 + 80, X0 + pw - 3, y0 + 88), fill=tc if j < L else (50, 54, 80))
            if sim.frozen[t] > 0: wt, wc = f"冰冻 {math.ceil(sim.frozen[t]/FPS)}s", (150, 220, 255)
            elif sim.shield[t] > 0 and sim.f >= sim.protect_f: wt, wc = f"护盾 {math.ceil(sim.shield[t]/FPS)}s", (120, 240, 255)
            elif sim.wt[t] > 0 and sim.weap[t] >= 0: wt, wc = f"{WEAP[sim.weap[t]]} {math.ceil(sim.wt[t]/FPS)}s", (255, 140, 220)
            elif sim.reinf[t] > 0: wt, wc = "援军出击", (180, 255, 120)
            elif sim.mis[t] > 0: wt, wc = f"导弹 x{sim.mis[t]}", (255, 110, 80)
            else: wt, wc = "武器 —", (120, 125, 160)
            rtext(d, x0 + cw - 10, y0 + 72, wt, font(19 * sc), wc)
            if not sim.alive_t[t]:
                ov = Image.new("RGBA", (int(cw), int(ch)), (5, 5, 10, 180))
                im.paste(ov, (int(x0), int(y0)), ov); d = ImageDraw.Draw(im)
                ctext(d, x0 + cw / 2, y0 + ch / 2 - 50, "已淘汰", font(40 * sc), (200, 200, 210), 3)
                if t in elim_info:
                    ctext(d, x0 + cw / 2, y0 + ch / 2 + 5, f"被{names[elim_info[t][0]]}攻破", font(24 * sc), T(elim_info[t][0]), 2)
                    ctext(d, x0 + cw / 2, y0 + ch / 2 + 40, mmss(elim_info[t][1] / FPS), font(22 * sc), (180, 180, 190), 2)
        for pp in fx.pops:
            x, y, txt, col, life, tier = pp
            a = min(1.0, life / 18); cc = tuple(int(v * a + 13 * (1 - a)) for v in col)
            sc_ = 1.0 + max(0, (life - 38) * .05)
            ctext(d, x, y - (45 - life) * 1.6, txt, font([22, 26, 32][tier] * sc_), cc, 3, tuple(int(v * a) for v in (0, 0, 0))); pp[4] -= 1
        fx.pops = [pp for pp in fx.pops if pp[4] > 0]
        # ---- top bar
        d.text((22, 18), "粒子领地大战", font=font(44), fill=(120, 240, 255), stroke_width=3, stroke_fill=(20, 40, 90))
        tx = 22 + d.textlength("粒子领地大战", font=font(44)) + 14
        d.rounded_rectangle((tx, 28, tx + 96, 66), 10, fill=(255, 80, 150))
        ctext(d, tx + 48, 30, f"第{episode}集", font(24), (255, 255, 255), 0)
        ph = sim.phase; px = tx + 120
        d.text((px, 22), PHASES[ph], font=font(36), fill=PH_COL[ph], stroke_width=3, stroke_fill=(0, 0, 0))
        d.text((px + 130, 30), f"{mmss(sim.f / FPS)} / {mmss(dur)}", font=font(28), fill=(230, 235, 255))
        tl0, tl1 = px, MX - 30
        d.rectangle((tl0, 76, tl1, 82), fill=(40, 44, 70))
        d.rectangle((tl0, 76, tl0 + (tl1 - tl0) * min(1, sim.f / sim.maxf), 82), fill=PH_COL[ph])
        for pt in PH_T[1:]:
            X = tl0 + (tl1 - tl0) * pt; d.rectangle((X - 1, 72, X + 1, 86), fill=(220, 220, 240))
        x = MX; byb = 34
        for t in sorted(range(nt), key=lambda t: -sim.share[t]):
            wd = G * sim.share[t]
            if wd < 1: continue
            d.rectangle((x, byb, x + wd, byb + 36), fill=T(t))
            if wd > 70: ctext(d, x + wd / 2, byb + 4, f"{sim.share[t]*100:.0f}%", font(22), (255, 255, 255), 2)
            x += wd
        d.rectangle((MX, byb, MX + G, byb + 36), outline=(200, 220, 255), width=2)
        d.text((MX, byb - 28), "领地占比", font=font(20), fill=(150, 160, 200))
        rtext(d, MX + G, byb - 28, f"存活 {int(sim.alive_t.sum())}/{nt} 队", font(20), (200, 210, 240), 0)
        # ---- banners, title cards, captions
        yb = MY + 60
        for bn in [bn for bn in fx.banners if bn[2] > 0][-2:]:
            txt, col, life, l0 = bn; age = l0 - life; scl = 1.0 + max(0, .3 - age * .05)
            fn = font(46 * scl); tw = d.textlength(txt, font=fn)
            if tw > G - 80: fn = font(46 * scl * (G - 80) / tw); tw = d.textlength(txt, font=fn)
            d.rounded_rectangle((MX + (G - tw) / 2 - 26, yb - 10, MX + (G + tw) / 2 + 26, yb + fn.size + 22), 18,
                                fill=(10, 12, 28), outline=col, width=4)
            d.text((MX + (G - tw) / 2, yb), txt, font=fn, fill=col, stroke_width=3, stroke_fill=(0, 0, 0))
            yb += 92
        for bn in fx.banners: bn[2] -= 1
        fx.banners = [bn for bn in fx.banners if bn[2] > 0][-6:]
        if fx.cards:
            title, sub, col, life, l0 = fx.cards[0]; age = l0 - life
            a = min(1.0, age / 8, life / 10); cy = MY + G / 2 - 90
            ov = Image.new("RGBA", (G, 190), (6, 8, 20, int(215 * a)))
            im.paste(ov, (MX, int(cy)), ov); d = ImageDraw.Draw(im)
            cc = tuple(int(v * a + 6 * (1 - a)) for v in col)
            d.rectangle((MX, cy, MX + G, cy + 4), fill=cc); d.rectangle((MX, cy + 186, MX + G, cy + 190), fill=cc)
            ctext(d, MX + G / 2 + (1 - a) * 60, cy + 22, title, font(76), cc, 4)
            ctext(d, MX + G / 2 - (1 - a) * 60, cy + 122, sub, font(34), tuple(int(v * a) for v in (230, 235, 255)), 2)
            fx.cards[0][3] -= 1
            if fx.cards[0][3] <= 0: fx.cards.pop(0)
        if fx.cap is None and fx.caps: fx.cap = [fx.caps.pop(0), 66]
        if fx.cap:
            txt = "解说｜" + fx.cap[0]; fn = font(34); tw = d.textlength(txt, font=fn); yc = MY + G - 80
            d.rounded_rectangle((MX + (G - tw) / 2 - 22, yc - 8, MX + (G + tw) / 2 + 22, yc + 50), 12, fill=(0, 0, 0))
            d.text((MX + (G - tw) / 2, yc), txt, font=fn, fill=(255, 240, 150))
            fx.cap[1] -= 1
            if fx.cap[1] <= 0: fx.cap = None
        # ---- ending
        if end_f is not None:
            k = fi - end_f; w = sim.winner
            if k > 20:
                ov = Image.new("RGBA", (W, H), (0, 0, 0, min(175, (k - 20) * 10)))
                im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"); d = ImageDraw.Draw(im)
            if k > 26:
                el = sorted(elim_info.items(), key=lambda kv: kv[1][1])
                how = "一统全图！" if sim.alive_t.sum() == 1 else "按领地判定获胜"
                lines = [("冠军 · " + how, font(46), (255, 230, 120)), (names[w], font(120), T(w)),
                         (f"占领 {sim.share[w]*100:.1f}% 领地 · 炮台 Lv.{sim.level[w]} · 用时 {mmss(sim.f / FPS)}", font(38), (255, 255, 255)),
                         ("淘汰顺序：" + "  ".join(f"{names[t]} {mmss(v[1] / FPS)}" for t, v in el), font(28), (210, 215, 240)),
                         (f"领先易主 {sim.lead_changes} 次 · 绝地反击 {sim.comebacks} 次 · 技能触发 {sim.nskill} 次", font(30), (210, 215, 240)),
                         ("你押中了吗？评论区见 · 下集更多队伍！", font(32), (210, 215, 240))]
                y = 200
                for txt, fn, col in lines:
                    ctext(d, W / 2, y, txt, fn, col, 5); y += fn.size + 30
            if k % 3 == 0 and k < 100:
                for _ in range(3):
                    fx.burst(fx.rng.uniform(100, G - 100), fx.rng.uniform(100, G - 100), 120,
                             glow[w] if fx.rng.random() < .6 else (255, 240, 160), 4, 40)
        frame = np.asarray(im)
        if fx.flash > .01:
            frame = (frame * (1 - fx.flash) + 255 * fx.flash).astype(np.uint8); fx.flash *= .8
        if fx.shake > .5:
            dx, dy = (fx.rng.uniform(-1, 1, 2) * fx.shake).astype(int)
            frame = np.roll(frame, (dy, dx), (0, 1)); fx.shake *= .85
        fx.slow -= 1
        frame = np.ascontiguousarray(frame)
        if prefix and end_f is None and sim.f - 1 in snaps and fi not in getattr(render, "_saved", set()):
            Image.fromarray(frame).save(f"{prefix}_{snaps.pop(sim.f - 1):02d}_{mmss(fi / FPS).replace(':', 'm')}s.png")
        p.stdin.write(frame.tobytes()); fi += 1
        if fi % 600 == 0:
            el_ = time.time() - t0; est = el_ / fi * (sim.maxf * 1.02 + hold)
            log(f"frame {fi} (sim {mmss(sim.f / FPS)}) {fi / el_:.1f} fps, elapsed {el_/60:.1f} min, ETA ~{max(0, est - el_)/60:.1f} min")
        if end_f is not None and fi - end_f >= hold:
            if prefix: Image.fromarray(frame).save(f"{prefix}_end.png")
            break
    p.stdin.close(); p.wait()
    log("encoding audio / muxing")
    wav = out + ".wav"; make_audio(wav, frames_ev, fi)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "128k", "-shortest", "-movflags", "+faststart", out], check=True)
    os.remove(tmp); os.remove(wav)
    return fi, sim, keys, end_f


def make_trailer(src, keys, end_f, total_f, out, maxlen=60.0):
    """~60s highlight cut: opening + key moments (eliminations / boss / ultimate ...) + ending."""
    pri = {"elim": 0, "win": 0, "bkill": 1, "ring": 2, "boss": 2, "sd": 3, "lv8": 3, "bomb": 3, "ult": 4, "freeze": 5, "siege": 5, "phase": 6}
    segs = [(0.0, 5.0), (end_f / FPS - 3, total_f / FPS)]
    for f, k in sorted(keys, key=lambda x: (pri.get(x[1], 9), x[0])):
        a, b = f / FPS - 1.5, f / FPS + (4.5 if k in ("elim", "bkill") else 3.0)
        cand = sorted(segs + [(a, b)]); merged = []
        for s in cand:
            if merged and s[0] <= merged[-1][1] + .5: merged[-1] = (merged[-1][0], max(merged[-1][1], s[1]))
            else: merged.append(s)
        if sum(e - s for s, e in merged) > maxlen: continue
        segs = merged
    segs = sorted(segs); n = len(segs)
    fc = "".join(f"[0:v]trim={s:.2f}:{e:.2f},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={s:.2f}:{e:.2f},asetpts=PTS-STARTPTS[a{i}];"
                 for i, (s, e) in enumerate(segs))
    fc += "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-maxrate", "5M", "-bufsize", "10M",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out], check=True)
    return segs


def main():
    ap = argparse.ArgumentParser(description="粒子领地大战 v3 (10 分钟长篇)")
    ap.add_argument("--teams", type=int, default=6); ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--seed-start", type=int, default=0); ap.add_argument("--seed", type=int)
    ap.add_argument("--duration", type=float, default=600.0); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=min(8, os.cpu_count()))
    ap.add_argument("--screen-only", action="store_true", help="只筛选种子, 不渲染")
    ap.add_argument("--no-trailer", action="store_true")
    ap.add_argument("--out", default="marble_v3_sample.mp4"); ap.add_argument("--preview", default="marble_v3_preview")
    ap.add_argument("--trailer", default="marble_v3_trailer.mp4")
    a = ap.parse_args(); nt = max(4, min(8, a.teams)); seed = a.seed
    log = lambda m: print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
    if seed is None:
        t0 = time.time(); res = []
        with Pool(a.jobs) as pool:
            for s, (sc, info) in pool.imap_unordered(run_headless, [(s, nt, a.duration) for s in range(a.seed_start, a.seed_start + a.seeds)]):
                log(f"seed {s:3d} score {sc:6.1f} {info}"); res.append((sc, s, info))
        best = max(res); seed = best[1]
        log(f"chosen seed {seed} score {best[0]:.1f} {best[2]} (screening {time.time()-t0:.0f}s)")
        if a.screen_only: return
    t0 = time.time(); fi, sim, keys, end_f = render(seed, nt, a.duration, a.episode, a.out, a.preview, log)
    sc, info = score(sim)
    log(f"rendered {fi} frames ({fi/FPS:.1f}s) in {(time.time()-t0)/60:.1f} min; seed {seed} winner {TEAM_POOL[sim.winner][0]} score {sc:.1f} {info}")
    if not a.no_trailer:
        segs = make_trailer(a.out, keys, end_f, fi, a.trailer)
        log(f"trailer {a.trailer}: {len(segs)} segments, {sum(e - s for s, e in segs):.1f}s")


if __name__ == "__main__":
    main()
