#!/usr/bin/env python3
"""粒子领地大战 v2 —— 横屏 1920x1080 游戏视频生成器.

中间: 960x960 领土地图 (Voronoi 初始分区, 基地位于 Voronoi 站点).
两侧: 每队一条独立弹珠竖道 (迷你 Plinko), 底部槽位 x2/x3/x5/升级/武器, 偶尔出现 x10 大奖.
炮台 Lv1-5: 单发 -> 散射 -> 连射 -> 激光 -> 导弹+终极炮.
戏剧性: 弱者加成(橡皮筋)、围剿领先者、陨石、清屏炸弹、中立Boss、决战毒圈; 种子筛选打分.
"""
import argparse, os, subprocess, wave, time, math
from multiprocessing import Pool
import numpy as np
from numba import njit
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FPS, W, H, G = 30, 1920, 1080, 960
MX, MY = (W - G) // 2, 104
LANE_TOP, BOARD_TOP, BOARD_BOT = 104, 330, 1064
SUB, NMAX, BR = 6, 60000, 34
TEAM_POOL = [("红队", (238, 64, 92)), ("蓝队", (52, 128, 255)), ("绿队", (40, 200, 120)), ("金队", (250, 182, 40)),
             ("紫队", (158, 90, 250)), ("青队", (24, 206, 226)), ("橙队", (255, 118, 36)), ("粉队", (250, 112, 196))]
NEU_C, BOSS_C, VOID_C = (58, 60, 78), (46, 18, 66), (12, 6, 14)
SLOTS = ["x2", "升级", "x5", "武器", "x3"]
SLOT_COL = {"x2": (200, 205, 230), "x3": (110, 220, 255), "x5": (255, 210, 70), "升级": (110, 255, 150),
            "武器": (255, 120, 210), "x10": (255, 240, 120)}
WEAP = ["霰弹", "机枪", "护盾", "大球", "狙击"]
NEED = {1: 1, 2: 2, 3: 2, 4: 3}
PATTERN = {1: "单发", 2: "散射", 3: "连射", 4: "激光", 5: "导弹"}
BARRELS = {1: [0.0], 2: [-.28, 0, .28], 3: [-.2, 0, .2], 4: [-.3, -.1, .1, .3], 5: [-.36, -.18, 0, .18, .36]}
PHASES = ["发育期", "混战期", "决战期"]
NR, PY0, PDY, SLOT_Y = 18, 34, 34, 660   # lane pegs (lane-local coordinates)


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


# ---------------------------------------------------------------- per-team plinko lane
class Lane:
    NS = 5

    def __init__(self, t, lw, rng):
        self.t, self.lw, self.sw, self.rng = t, lw, lw / self.NS, rng
        self.slots = list(SLOTS); self.jp = -1; self.jpt = 0
        self.ball = None; self.wait = int(rng.integers(5, 45))
        self.flash = np.zeros(self.NS, int); self.last = None

    def pegs(self):
        out = []
        for r in range(NR):
            py = PY0 + r * PDY
            if r % 2 == 0: out += [(self.sw / 2 + j * self.sw, py) for j in range(self.NS)]
            else: out += [(j * self.sw, py) for j in range(1, self.NS)]
        return out

    def label(self, s):
        return "x10" if s == self.jp else self.slots[s]

    def tick(self, w):
        self.flash = np.maximum(self.flash - 1, 0)
        if self.jpt > 0:
            self.jpt -= 1
            if self.jpt == 0: self.jp = -1
        if self.ball is None:
            self.wait -= 1
            if self.wait <= 0:
                good = [i for i, s in enumerate(self.slots) if s in ("x5", "升级")] + ([self.jp] if self.jp >= 0 else [])
                tg = int(self.rng.choice(good)) if self.rng.random() < 0.2 + 0.6 * w else -1
                self.ball = [self.lw / 2 + self.rng.uniform(-10, 10), 4.0, self.rng.uniform(-.6, .6), 0.0, tg, w]
            return []
        x, y, vx, vy, tg, wk = self.ball; sw, rng = self.sw, self.rng
        for _ in range(3):
            vy += 0.11
            if tg >= 0 and y > 150:
                vx += 0.01 * (0.6 + wk) * np.sign((tg + 0.5) * sw - x)
            x += vx; y += vy
            if x < 7: x = 7; vx = abs(vx) * .5
            if x > self.lw - 7: x = self.lw - 7; vx = -abs(vx) * .5
            r = int(round((y - PY0) / PDY))
            if 0 <= r < NR:
                py = PY0 + r * PDY; off = sw / 2 if r % 2 == 0 else 0.0
                j = int(round((x - off) / sw))
                if (r % 2 == 0 and 0 <= j < self.NS) or (r % 2 == 1 and 1 <= j < self.NS):
                    px = off + j * sw; dx, dy = x - px, y - py; d = math.hypot(dx, dy)
                    if d < 9.5:
                        nx, ny = (dx / d, dy / d) if d > 1e-3 else (0.0, -1.0)
                        x, y = px + nx * 9.5, py + ny * 9.5
                        vn = vx * nx + vy * ny
                        if vn < 0: vx -= 1.5 * vn * nx; vy -= 1.5 * vn * ny
                        vx += rng.normal(0, .45)
            sp = math.hypot(vx, vy)
            if sp > 3.6: vx *= 3.6 / sp; vy *= 3.6 / sp
        self.ball = [x, y, vx, vy, tg, wk]
        if y >= SLOT_Y:
            s = min(self.NS - 1, max(0, int(x / sw))); lab = self.label(s)
            self.flash[s] = 24; self.last = [x, s, 18]; self.ball = None; self.wait = 10
            if lab == "x10": self.jp = -1; self.jpt = 0
            return [lab]
        return []


# ---------------------------------------------------------------- simulation
class Sim:
    def __init__(self, seed, nt=6, dur=72.0):
        self.nt = nt; self.maxf = int(dur * FPS); self.seed = seed
        rng = self.rng = np.random.default_rng(seed); nb_seed(seed)
        md = G * {4: .42, 5: .38, 6: .33, 7: .30, 8: .27}[nt]; sites = []; tries = 0
        while len(sites) < nt:
            a, r = rng.uniform(0, 2 * math.pi), G * .34 * math.sqrt(rng.uniform(.15, 1))
            p = (G / 2 + r * math.cos(a), G / 2 + r * math.sin(a)); tries += 1
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= md for q in sites): sites.append(p)
            if tries > 4000: sites, tries, md = [], 0, md * .95
        self.bases = np.array(sites, float)
        yy, xx = np.mgrid[0:G, 0:G].astype(np.float32)
        # warped voronoi for organic borders
        wx = xx + 18 * np.sin(yy / 47 + rng.uniform(0, 6)); wy = yy + 18 * np.sin(xx / 53 + rng.uniform(0, 6))
        d = np.stack([(wx - b[0]) ** 2 + (wy - b[1]) ** 2 for b in self.bases])
        self.grid = d.argmin(0).astype(np.int8)
        z = lambda dt=float: np.zeros(NMAX, dt)
        self.x, self.y, self.vx, self.vy, self.en, self.bp = z(), z(), z(), z(), z(), z()
        self.tm = z(np.int8); self.alive = z(bool); self.cur = 0
        self.ammo = np.full(nt, 1000.0); self.level = np.ones(nt, int); self.pts = np.zeros(nt, int)
        self.alive_t = np.ones(nt, bool); self.shield = np.zeros(nt, int); self.weap = np.full(nt, -1); self.wt = np.zeros(nt, int)
        self.ang = np.zeros(nt); self.phs = rng.uniform(0, 6.28, nt)
        self.tgt = np.full(nt, -1); self.tgt_t = np.zeros(nt, int)
        self.ult_cd = np.full(nt, 60); self.laser_t = np.zeros(nt, int); self.beam = [None] * nt
        # lanes: bases on the left half -> left lanes
        order = list(np.argsort(self.bases[:, 0])); nl = nt // 2
        left, right = order[:nl], order[nl:]; k = max(len(left), len(right))
        self.lw = (460 - (k - 1) * 10) / k; self.lane_x = {}
        for i, t in enumerate(left): self.lane_x[int(t)] = 10 + i * (self.lw + 10)
        for i, t in enumerate(right): self.lane_x[int(t)] = MX + G + 10 + i * (self.lw + 10)
        self.lanes = {t: Lane(t, self.lw, np.random.default_rng(seed * 100 + t)) for t in range(nt)}
        self.siege_t, self.siege_left, self.siege_cd = -1, 0, 0
        self.next_meteor = int(rng.uniform(11, 15) * FPS); self.meteors = []
        self.boss = None; self.boss_f = int(.3 * self.maxf); self.boss_dmg = np.zeros(nt, np.int64)
        self.bomb_f = int(rng.uniform(.5, .58) * self.maxf); self.ring_f = int(.68 * self.maxf); self.ring = None
        self.next_jp = int(rng.uniform(4, 7) * FPS); self.protect_f = int(.17 * self.maxf)
        self.hits = np.zeros((600, 3)); self.nh = np.zeros(1, np.int64); self.fades = []
        self.f = 0; self.phase = 0; self.done = False; self.winner = -1
        self.lead, self.lead_changes, self.comebacks, self.elims = -1, 0, 0, []
        self.low_f = {}; self.cb_cd = np.zeros(nt, int); self.close_cd = 0; self.hist = []; self.elim_by = {}
        self.share = count(self.grid, nt + 3) / float(G * G)

    def add_up(self, t, k, ev):
        self.pts[t] += k
        while self.level[t] < 5 and self.pts[t] >= NEED[self.level[t]]:
            self.pts[t] -= NEED[self.level[t]]; self.level[t] += 1; ev.append(("lvl", t, int(self.level[t])))
            if self.level[t] == 5: ev.append(("cap", f"{TEAM_POOL[t][0]}炮台满级！终极炮充能！", t))
        if self.level[t] == 5 and self.pts[t] > 0:
            self.pts[t] = 0; self.ult_cd[t] = min(self.ult_cd[t], 1)

    def slot(self, t, lab, ev):
        if lab[0] == "x":
            m = int(lab[1:]); self.ammo[t] *= m; ev.append(("mult", t, m))
            if m == 10: self.add_up(t, 1, ev); ev.append(("jack", t))
        elif lab == "升级":
            ev.append(("upg", t)); self.add_up(t, 1, ev)
        else:
            w = int(self.rng.integers(5))
            if WEAP[w] == "护盾": self.shield[t] = 6 * FPS
            else: self.weap[t] = w; self.wt[t] = 5 * FPS
            ev.append(("weap", t, w))

    def target(self, t):
        if self.siege_left > 0 and self.siege_t != t and self.alive_t[self.siege_t]:
            return self.siege_t
        if self.tgt_t[t] <= 0 or self.tgt[t] < 0 or not self.alive_t[self.tgt[t]]:
            cand = [o for o in range(self.nt) if o != t and self.alive_t[o]]
            if not cand: return -1
            cand.sort(key=lambda o: np.hypot(*(self.bases[o] - self.bases[t])))
            self.tgt[t] = cand[0] if len(cand) == 1 or self.rng.random() < .65 else cand[1]
            self.tgt_t[t] = int(self.rng.integers(90, 200))
        self.tgt_t[t] -= 1
        return int(self.tgt[t])

    def eliminate(self, t, c, ev):
        self.alive_t[t] = False; self.alive[self.alive & (self.tm == t)] = False
        self.fades.append([t, c, 36]); self.ammo[c] += self.ammo[t] * .5; self.ammo[t] = 0
        self.elims.append(self.f); self.elim_by[t] = c
        ev.append(("elim", t, c)); self.add_up(c, 2, ev)
        n = int(self.alive_t.sum())
        ev.append(("cap", f"{TEAM_POOL[t][0]}出局！" + (f"剩余{n}队" if n > 1 else "") , c))

    def tick(self):
        nt, f, rng = self.nt, self.f, self.rng; ev = []; T = f / self.maxf
        ph = 0 if T < .25 else (1 if T < .68 else 2)
        if ph != self.phase: self.phase = ph; ev.append(("phase", ph))
        al = self.alive_t; aidx = [int(t) for t in np.flatnonzero(al)]
        sh = self.share[:nt]; avg = sh[al].mean()
        weak = np.clip((avg - sh) / max(avg, 1e-6), 0, 1) * al
        for t in aidx:
            for lab in self.lanes[t].tick(weak[t]): self.slot(t, lab, ev)
        if f >= self.next_jp:
            p = (0.3 + weak[aidx]); p /= p.sum(); t = int(rng.choice(aidx, p=p)); ln = self.lanes[t]
            ln.jp = int(rng.integers(5)); ln.jpt = 6 * FPS; ev.append(("jpon", t))
            self.next_jp += int(rng.uniform(5, 9) * FPS)
        # siege on the leader
        if self.siege_left > 0:
            self.siege_left -= 1
            if self.siege_left == 0 or not al[self.siege_t]:
                self.siege_left = 0; self.siege_cd = 9 * FPS; ev.append(("siege_end", self.siege_t))
        else:
            self.siege_cd -= 1
            if ph >= 1 and self.siege_cd <= 0 and len(aidx) >= 3 and f % 15 == 0:
                o = sorted(aidx, key=lambda t: -sh[t])
                if sh[o[0]] > max(.26, 1.4 * sh[o[1]]):
                    self.siege_t, self.siege_left = o[0], 8 * FPS; ev.append(("siege", o[0]))
                    ev.append(("cap", f"{TEAM_POOL[o[0]][0]}被围剿！", o[0]))
        # meteors
        if f >= self.next_meteor and T < .93:
            lead = max(aidx, key=lambda t: sh[t])
            if rng.random() < .6:
                ys, xs = np.nonzero(self.grid == lead)
                k = int(rng.integers(len(ys))) if len(ys) else 0
                mx, my = (int(xs[k]), int(ys[k])) if len(ys) else (G // 2, G // 2)
            else:
                mx, my = int(rng.integers(80, G - 80)), int(rng.integers(80, G - 80))
            r = int(rng.integers(45, 75)); self.meteors.append([mx, my, r, f + 24]); ev.append(("meteor", mx, my, r))
            self.next_meteor += int(rng.uniform(8, 12) * FPS)
        for m in [m for m in self.meteors if m[3] == f]:
            crater(self.grid, m[0], m[1], m[2], nt, self.bases, self.alive_t, float(BR * BR), nt)
            ev.append(("impact", m[0], m[1], m[2])); self.meteors.remove(m)
        # boss
        if f == self.boss_f:
            best = None
            for _ in range(300):
                p = rng.uniform(G * .2, G * .8, 2); d = np.hypot(*(self.bases - p).T).min()
                if best is None or d > best[0]: best = (d, p)
            bx, by = int(best[1][0]), int(best[1][1]); yy, xx = np.ogrid[0:G, 0:G]
            self.grid[(xx - bx) ** 2 + (yy - by) ** 2 <= 42 * 42] = nt + 1
            self.boss = dict(x=bx, y=by, hp=14000, hp0=14000); ev.append(("boss", bx, by))
            ev.append(("cap", "中立Boss降临！击破者得8倍弹药", -1))
        if self.boss and (f - self.boss_f) % 150 == 149:
            crater(self.grid, self.boss["x"], self.boss["y"], 100, nt, self.bases, self.alive_t, float(BR * BR), nt)
            ev.append(("bshock", self.boss["x"], self.boss["y"]))
        if f == self.bomb_f:
            self.alive[:] = False; ev.append(("bomb",)); ev.append(("cap", "清屏炸弹！全场粒子清空", -1))
        if f >= self.ring_f:
            fr = (f - self.ring_f) / max(1, self.maxf - self.ring_f)
            self.ring = (G / 2, G / 2, G * (.72 - .32 * fr))
            if f == self.ring_f: ev.append(("ring",)); ev.append(("cap", "毒圈收缩！最终决战！", -1))
            if f % 3 == 0: apply_ring(self.grid, G / 2, G / 2, self.ring[2], nt + 2)
        # fire
        for t in aidx:
            o = self.target(t)
            self.beam[t] = None
            if o < 0: continue
            bx, by = self.bases[t]; ox, oy = self.bases[o]
            ba = math.atan2(oy - by, ox - bx); self.ang[t] = ba + .55 * math.sin(f * .05 + self.phs[t])
            L = int(self.level[t]); lg = max(.6, math.log10(self.ammo[t] + 10) - 1.6)
            n = 3.2 * lg * (1 + .9 * weak[t]) * (1 + .45 * ph) * (1.6 if L == 3 else 1.0)
            energy, spread, speed, bounce = 30 + 5 * L, .10, 1.0, .45
            w = self.weap[t] if self.wt[t] > 0 else -1
            if w == 0: spread, n = 1.2, n * 2
            elif w == 1: n, spread = n * 3, .04
            elif w == 3: n, energy, bounce = max(.3, n / 10), 1500.0, 0.0
            elif w == 4: self.ang[t] = ba; n, spread, energy, bounce = n / 2, .02, 300.0, 0.0
            for off in BARRELS[L]:
                k = int(n + rng.random())
                if k: self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, k, bx, by,
                                     self.ang[t] + off, spread, speed, energy, bounce, self.cur, 36.0)
            if L >= 4:
                if self.laser_t[t] > 0:
                    self.laser_t[t] -= 1
                elif (f + t * 23) % 110 == 0:
                    self.laser_t[t] = 26; ev.append(("laser", t))
            if L == 5:
                if f % 6 == 0:
                    self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, 3, bx, by,
                                    ba, .06, 1.2, 260.0, 0.0, self.cur, 36.0)
                self.ult_cd[t] -= 1
                if self.ult_cd[t] <= 0:
                    self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, 1500, bx, by,
                                    0.0, 2 * math.pi, 1.1, 45.0, .3, self.cur, 36.0)
                    self.ult_cd[t] = 8 * FPS; ev.append(("ult", t))
            inc = 6 * (1 + 25 * sh[t]) * (1 + 2 * weak[t]) * 10 ** (f / FPS / 22)
            self.ammo[t] = (self.ammo[t] + inc) * (1 - .012 - .002 * L)
        self.wt -= 1; self.shield = np.maximum(self.shield - 1, 0)
        prot = ((self.shield > 0) | (f < self.protect_f)).astype(np.int64)
        conv = np.zeros(nt, np.int64)
        for t in aidx:
            if self.laser_t[t] > 0:
                L = 330 + 20 * self.phase
                e = beam(self.grid, self.bases[t, 0], self.bases[t, 1], self.ang[t], L, 4, t, prot, self.bases, float(BR * BR), nt, conv)
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
        # eliminations
        if f >= self.protect_f:
            for t in aidx:
                if not self.alive_t[t]: continue
                c = disk_counts(self.grid, int(self.bases[t, 0]), int(self.bases[t, 1]), BR, nt + 3)
                if c[t] / max(1, c.sum()) < (.3 if ph < 2 else .5) or self.share[t] < .0015:
                    oth = [o for o in range(nt) if o != t and self.alive_t[o]]
                    if not oth: continue
                    conq = max(oth, key=lambda o: (c[o], self.share[o]))
                    self.eliminate(t, conq, ev)
        for fd in self.fades:
            if not self.alive_t[fd[1]] and fd[1] in self.elim_by: fd[1] = self.elim_by[fd[1]]
            fade(self.grid, fd[0], fd[1], 1.0 / max(fd[2], 1)); fd[2] -= 1
        self.fades = [fd for fd in self.fades if fd[2] > 0]
        self.share = count(self.grid, nt + 3) / float(G * G); sh = self.share[:nt]
        # drama stats
        if f % 15 == 0:
            self.hist.append(sh.copy())
            al2 = [t for t in range(nt) if self.alive_t[t]]
            if al2:
                lead = max(al2, key=lambda t: sh[t]); low = min(al2, key=lambda t: sh[t])
                self.low_f[low] = f
                if lead != self.lead and self.lead >= 0:
                    self.lead_changes += 1; ev.append(("lead", lead))
                    if f - self.low_f.get(lead, -10 ** 9) < 18 * FPS and self.cb_cd[lead] <= f and len(al2) >= 2:
                        self.comebacks += 1; self.cb_cd[lead] = f + 12 * FPS
                        ev.append(("cap", f"{TEAM_POOL[lead][0]}绝地反击！", lead)); ev.append(("comeback", lead))
                    else:
                        ev.append(("cap", f"{TEAM_POOL[lead][0]}反超，登顶第一！", lead))
                self.lead = lead
                if len(al2) == 2 and abs(sh[al2[0]] - sh[al2[1]]) < .05 and f >= self.close_cd:
                    self.close_cd = f + 9 * FPS; ev.append(("cap", "势均力敌，胜负难料！", -1))
        self.f += 1
        if self.alive_t.sum() <= 1 or self.f >= self.maxf:
            al2 = [t for t in range(nt) if self.alive_t[t]]
            self.winner = max(al2, key=lambda t: sh[t]); self.done = True; ev.append(("win", self.winner))
        return int(conv.sum()), ev


def run_headless(args):
    seed, nt, dur = args
    s = Sim(seed, nt, dur)
    while not s.done: s.tick()
    return seed, score(s)


def score(s):
    hist = np.array(s.hist); dur = s.maxf / FPS; el = [e / FPS for e in s.elims]; ne = len(el)
    sc = min(s.lead_changes, 10) * 3 + min(s.comebacks, 4) * 5 + ne * 7 + (10 if ne >= s.nt - 2 else 0)
    if el and el[0] < .22 * dur: sc -= 15
    if ne >= 2:
        g = np.diff([0] + el); sc += 10 * max(0, 1 - g.std() / g.mean())
        if np.diff(el).min() < 4: sc -= 8
    natural = s.alive_t.sum() == 1; end = s.f / FPS
    if natural and end > .85 * dur: sc += 12
    if natural and end < .7 * dur: sc -= 20
    tail = hist[int(len(hist) * .8):]
    top2 = np.sort(tail, 1)[:, -2:]; closeness = float((top2[:, 1] - top2[:, 0]).min()) if len(tail) else 1
    if closeness < .06: sc += 10
    mid = hist[int(len(hist) * .4)]
    if mid.max() > .4: sc -= 15
    return float(sc), dict(lead_changes=s.lead_changes, comebacks=s.comebacks, elims=[round(e, 1) for e in el],
                           end=round(end, 1), natural=bool(natural), winner=int(s.winner), close=round(closeness, 3),
                           mid_max=round(float(mid.max()), 3))


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

    # background beat (120 bpm), intensity by phase
    beat = 0.5; nb = int(nframes / FPS / beat)
    bass = [55, 55, 65.4, 49]
    for i in range(nb):
        ts = i * beat; ph = frames_ev[min(len(frames_ev) - 1, int(ts * FPS))][2]
        if ph < 0: continue
        add(ts, tone(110, .22, .16 + .05 * ph, 14, -.6))
        add(ts + beat / 2, noise(.05, .025 + .01 * ph, 60) - noise(.05, 0, 60))
        if ph >= 1 and i % 2 == 1: add(ts, noise(.12, .05, 25, 6))
        if ph == 2: add(ts, tone(bass[(i // 4) % 4], .45, .08, 4, 0, "saw"))
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
            elif k == "weap": add(ts, tone(330, .35, .18, 7, 1.2)); add(ts + .08, tone(660, .25, .12, 9))
            elif k == "upg": add(ts, tone(700, .15, .12, 14, .4))
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
            elif k in ("siege", "ring", "boss"):
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


def build_bg(sim, pal):
    bg = Image.new("RGB", (W, H), (8, 10, 24)); d = ImageDraw.Draw(bg)
    arr = np.asarray(bg).copy(); yy = np.arange(H)[:, None]
    arr[:] = np.stack([8 + 10 * yy / H, 10 + 4 * yy / H, 26 + 20 * yy / H], -1).astype(np.uint8)
    bg = Image.fromarray(arr); d = ImageDraw.Draw(bg)
    d.rectangle((MX - 6, MY - 6, MX + G + 5, MY + G + 5), outline=(70, 230, 255), width=2)
    lw = sim.lw
    for t, x0 in sim.lane_x.items():
        c = tuple(int(v) for v in pal[t]); dim = tuple(int(v * .45) for v in pal[t]); ln = sim.lanes[t]
        d.rounded_rectangle((x0, LANE_TOP, x0 + lw, BOARD_TOP - 6), 10, fill=(18, 22, 46), outline=dim, width=2)
        d.rectangle((x0 + 2, LANE_TOP + 2, x0 + lw - 2, LANE_TOP + 9), fill=c)
        d.rounded_rectangle((x0, BOARD_TOP, x0 + lw, BOARD_BOT), 10, fill=(13, 16, 34), outline=dim, width=2)
        for px, py in ln.pegs():
            X, Y = x0 + px, BOARD_TOP + py
            d.ellipse((X - 3, Y - 3, X + 3, Y + 3), fill=(150, 165, 215))
        for j in range(1, Lane.NS):
            X = x0 + j * ln.sw; d.line((X, BOARD_TOP + SLOT_Y - 40, X, BOARD_BOT - 4), fill=(110, 120, 170), width=2)
    return bg


def draw_slots(d, sim, t, x0, pal):
    ln = sim.lanes[t]; sw = ln.sw; fs = min(22, int(sw * .7)); y0 = BOARD_TOP + SLOT_Y + 8
    for s in range(Lane.NS):
        lab = ln.label(s); X0 = x0 + s * sw + 3; X1 = x0 + (s + 1) * sw - 3
        col = SLOT_COL[lab]
        fill = (30, 34, 62)
        if lab == "x10": fill = (120, 90, 10) if (sim.f // 4) % 2 else (70, 50, 6)
        if ln.flash[s]: k = ln.flash[s] / 24; fill = tuple(int(fill[i] * (1 - k) + pal[t][i] * k) for i in range(3))
        d.rounded_rectangle((X0, y0, X1, BOARD_BOT - 6), 5, fill=fill, outline=col, width=1)
        cx = (X0 + X1) / 2
        if lab in ("升级", "武器"):
            fn = font(fs); ctext(d, cx, y0 + 6, lab[0], fn, col, 2); ctext(d, cx, y0 + 8 + fs, lab[1], fn, col, 2)
        else:
            fn = font(fs if lab != "x10" else fs * .8); ctext(d, cx, y0 + 18, lab, fn, col, 2)


class FX:
    def __init__(self, seed):
        self.rng = np.random.default_rng(seed + 999)
        self.fx = np.zeros((G, G, 3), np.float32)
        self.sp = np.zeros((0, 8), np.float32)  # x y vx vy life r g b
        self.rings, self.banners, self.caps, self.pops = [], [], [], []
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


def render(seed, nt, dur, episode, out, prefix):
    names = [n for n, _ in TEAM_POOL[:nt]]
    pal = np.array([c for _, c in TEAM_POOL[:nt]] + [NEU_C, BOSS_C, VOID_C], np.uint8)
    pf = pal.astype(np.float32)
    core = np.clip(pf * .35 + 255 * .65, 0, 255).astype(np.uint8)
    edge = np.clip(pf * .5, 0, 255).astype(np.uint8)
    glow = np.clip(pf * 1.15 + 30, 0, 255).astype(np.float32)
    sim = Sim(seed, nt, dur); fx = FX(seed); bg = build_bg(sim, pal); bg_np = np.asarray(bg)
    gl = np.zeros((G, G), bool); gl[::48, :] = True; gl[:, ::48] = True
    tmp = out + ".video.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "22",
                          "-maxrate", "6.5M", "-bufsize", "13M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
                         stdin=subprocess.PIPE)
    frames_ev = []; fi = 0; end_f = None; hold = 4 * FPS; snaps = {}; lw = sim.lw; elim_info = {}
    fx.banners.append(["粒子领地大战 第%d集  %d队混战 开始！" % (episode, nt), (120, 240, 255), 75, 75])
    T = lambda t: tuple(int(v) for v in pal[t])
    while True:
        conv, ev = 0, []
        if end_f is None:
            if fx.slow <= 0 or fi % 2 == 0:
                conv, ev = sim.tick()
            if sim.done and end_f is None and any(e[0] == "win" for e in ev): end_f = fi
        frames_ev.append((conv, ev, sim.phase if end_f is None else 2))
        # ---- react to events
        for e in ev:
            k = e[0]
            if k == "lvl":
                t, L = e[1], e[2]; bx, by = sim.bases[t]
                fx.banners.append([f"{names[t]} 升级 Lv.{L}！", T(t), 55, 55]); fx.rings.append([bx, by, 10, 26, T(t), 26])
                fx.burst(bx, by, 250, glow[t], 4, 30); fx.shake = max(fx.shake, 5 + L); fx.flash = max(fx.flash, .12)
            elif k == "elim":
                t, c = e[1], e[2]; bx, by = sim.bases[t]; elim_info[t] = (c, sim.f)
                fx.banners.append([f"{names[t]} 基地被 {names[c]} 攻破！", T(c), 80, 80])
                fx.burst(bx, by, 1800, glow[t], 7, 60); fx.burst(bx, by, 600, (255, 255, 230), 5, 40)
                fx.rings.append([bx, by, 10, 40, (255, 255, 255), 40]); fx.rings.append([bx, by, 5, 50, T(c), 50])
                fx.shake = 16; fx.flash = max(fx.flash, .45); fx.slow = 36
            elif k == "ult":
                t = e[1]; bx, by = sim.bases[t]
                fx.flash = max(fx.flash, .55); fx.shake = max(fx.shake, 10); fx.rings.append([bx, by, 20, 34, T(t), 34])
                fx.banners.append([f"{names[t]} 终极炮！", T(t), 45, 45]); fx.burst(bx, by, 500, glow[t], 6, 40)
            elif k == "impact":
                _, x, y, r = e; fx.shake = max(fx.shake, 12); fx.flash = max(fx.flash, .18)
                fx.burst(x, y, 900, (255, 170, 70), 5, 45); fx.rings.append([x, y, r * .5, 30, (255, 200, 120), 30])
            elif k == "meteor":
                fx.banners.append(["陨石来袭！", (255, 170, 70), 45, 45])
            elif k == "bomb":
                fx.flash = .9; fx.shake = 10; fx.banners.append(["清屏炸弹！", (255, 255, 255), 60, 60])
                fx.rings.append([G / 2, G / 2, 20, 40, (255, 255, 255), 40])
            elif k == "siege":
                fx.banners.append([f"围剿 {names[e[1]]}！全员集火领先者", T(e[1]), 75, 75]); fx.shake = max(fx.shake, 6)
            elif k == "boss":
                fx.banners.append(["中立 Boss 出现！", (210, 120, 255), 60, 60]); fx.rings.append([e[1], e[2], 10, 40, (210, 120, 255), 40])
            elif k == "bshock":
                fx.rings.append([e[1], e[2], 40, 30, (210, 120, 255), 30]); fx.shake = max(fx.shake, 5)
            elif k == "bkill":
                t = e[1]; b = (sim.bases[t]); fx.banners.append([f"{names[t]} 击破 Boss！", T(t), 70, 70])
                fx.flash = max(fx.flash, .4); fx.shake = 12; fx.slow = 24
            elif k == "ring":
                fx.banners.append(["决战期 · 毒圈收缩", (255, 80, 80), 70, 70])
            elif k == "phase" and e[1] == 1:
                fx.banners.append(["混战期 开始！", (255, 230, 120), 55, 55])
            elif k == "jack":
                fx.banners.append([f"{names[e[1]]} 中了 x10 大奖！", (255, 230, 90), 55, 55])
            elif k == "cap":
                fx.caps.append(e[1]); fx.caps = fx.caps[-2:]
            elif k == "win":
                fx.slow = 0; fx.flash = .6; fx.shake = 12
            if k in ("mult", "weap", "upg"):
                t = e[1]; ln = sim.lanes[t]; x0 = sim.lane_x[t]
                if ln.last:
                    txt = f"x{e[2]}" if k == "mult" else ("升级" if k == "upg" else WEAP[e[2]])
                    fx.pops.append([x0 + (ln.last[1] + .5) * ln.sw, BOARD_TOP + SLOT_Y - 20, txt, SLOT_COL.get(
                        "x5" if k == "mult" else ("升级" if k == "upg" else "武器")), 40])
        # ---- map layer
        fx.fx *= .72
        fx.update_sparks()
        if sim.nh[0]:
            h = sim.hits[:sim.nh[0]]
            for j in range(0, len(h), 3):
                fx.burst(h[j, 0], h[j, 1], 4, glow[int(h[j, 2])], 1.8, 10)
        for t in range(nt):
            if sim.alive_t[t]:
                L = sim.level[t]; fx_disk(fx.fx, sim.bases[t, 0], sim.bases[t, 1], BR + 10 + 8 * L,
                                          *(glow[t] * (.05 + .03 * L) * (1 + .3 * math.sin(fi * .2))))
                if sim.beam[t]:
                    x0, y0, x1, y1 = sim.beam[t]; fx_line(fx.fx, x0, y0, x1, y1, 5, *(glow[t] * .5))
        for m in sim.meteors:
            k = (m[3] - sim.f) / 24; mx, my = m[0] + 300 * k, m[1] - 500 * k
            fx_disk(fx.fx, mx, my, 16, 255, 150, 60); fx.burst(mx, my, 6, (255, 140, 40), .8, 16)
        mp = pal[sim.grid]
        mp[gl] = (mp[gl] * .8 + 34).astype(np.uint8)
        gimg = Image.fromarray(np.clip(fx.fx, 0, 255).astype(np.uint8)).resize((G // 4, G // 4), Image.BOX)
        gimg = np.asarray(gimg.filter(ImageFilter.GaussianBlur(3)).resize((G, G), Image.BILINEAR), np.float32)
        comp = mp.astype(np.float32) + fx.fx * .55 + gimg * 1.6
        if sim.ring:
            pass
        mp = np.clip(comp, 0, 255).astype(np.uint8)
        draw_parts(mp, fx.fx, sim.x, sim.y, sim.tm, sim.en, sim.alive, core, edge, glow)
        img = bg_np.copy(); img[MY:MY + G, MX:MX + G] = mp
        im = Image.fromarray(img); d = ImageDraw.Draw(im)
        ox, oy = MX, MY
        # ring
        if sim.ring and sim.ring[2] < G / 2 - 4:
            cx, cy, r = sim.ring
            for wdt, col in ((9, (120, 20, 30)), (3, (255, 90, 90))):
                d.ellipse((ox + cx - r, oy + cy - r, ox + cx + r, oy + cy + r), outline=col, width=wdt)
        # beams
        for t in range(nt):
            if sim.alive_t[t] and sim.beam[t]:
                x0, y0, x1, y1 = sim.beam[t]
                d.line((ox + x0, oy + y0, ox + x1, oy + y1), fill=T(t), width=10)
                d.line((ox + x0, oy + y0, ox + x1, oy + y1), fill=(255, 255, 255), width=3)
        # boss
        if sim.boss:
            b = sim.boss; X, Y = ox + b["x"], oy + b["y"]; pr = 44 + 3 * math.sin(fi * .3)
            d.ellipse((X - pr, Y - pr, X + pr, Y + pr), outline=(210, 120, 255), width=4)
            ctext(d, X, Y - 18, "BOSS", font(24), (235, 200, 255))
            hp = max(0, b["hp"] / b["hp0"]); d.rectangle((X - 40, Y + 50, X + 40, Y + 58), fill=(30, 10, 40))
            d.rectangle((X - 40, Y + 50, X - 40 + 80 * hp, Y + 58), fill=(210, 120, 255))
        # shockwave rings
        for rg in fx.rings:
            x, y, r0, life, col, l0 = rg; k = 1 - life / l0; r = r0 + k * (150 if l0 >= 40 else 90)
            d.ellipse((ox + x - r, oy + y - r, ox + x + r, oy + y + r), outline=col, width=max(1, int(8 * (1 - k))))
            rg[3] -= 1
        fx.rings = [r for r in fx.rings if r[3] > 0]
        # bases / cannons
        for t in range(nt):
            bx, by = ox + sim.bases[t, 0], oy + sim.bases[t, 1]
            if not sim.alive_t[t]:
                d.ellipse((bx - 22, by - 22, bx + 22, by + 22), fill=(30, 30, 36), outline=(80, 80, 90), width=3)
                d.line((bx - 12, by - 12, bx + 12, by + 12), fill=(150, 150, 160), width=4)
                d.line((bx - 12, by + 12, bx + 12, by - 12), fill=(150, 150, 160), width=4)
                continue
            L = int(sim.level[t]); c = T(t); R = 22 + 3 * L; a = sim.ang[t]
            if sim.f < sim.protect_f:
                d.ellipse((bx - BR * 1.5, by - BR * 1.5, bx + BR * 1.5, by + BR * 1.5), outline=(230, 230, 255), width=2)
            if sim.shield[t] > 0:
                d.ellipse((bx - BR * 1.5, by - BR * 1.5, bx + BR * 1.5, by + BR * 1.5), outline=(120, 240, 255), width=6)
            if L >= 3:
                ar = R + 12 + 2 * L
                for j in range(6):
                    st = fi * 6 + j * 60
                    d.arc((bx - ar, by - ar, bx + ar, by + ar), st, st + 32, fill=c, width=3)
            blen = R + 16 + 4 * L
            for off in BARRELS[L]:
                aa = a + off
                d.line((bx, by, bx + math.cos(aa) * blen, by + math.sin(aa) * blen), fill=(20, 20, 30), width=12 if L < 5 else 14)
                d.line((bx, by, bx + math.cos(aa) * (blen - 2), by + math.sin(aa) * (blen - 2)), fill=c, width=7 if L < 5 else 9)
            d.ellipse((bx - R, by - R, bx + R, by + R), fill=c, outline=(255, 255, 255), width=3)
            ctext(d, bx, by - 15, f"Lv{L}", font(20), (255, 255, 255))
            if sim.siege_left > 0 and sim.siege_t == t:
                d.ellipse((bx - R - 26, by - R - 26, bx + R + 26, by + R + 26), outline=(255, 60, 60), width=3)
                ctext(d, bx, by + R + 6, "被围剿", font(20), (255, 90, 90))
        # meteor shadow target
        for m in sim.meteors:
            X, Y, r = ox + m[0], oy + m[1], m[2]
            d.ellipse((X - r, Y - r, X + r, Y + r), outline=(255, 160, 60), width=2)
        # ---- lanes
        for t, x0 in sim.lane_x.items():
            ln = sim.lanes[t]; c = T(t); s = min(1.0, lw / 146); cx = x0 + lw / 2
            draw_slots(d, sim, t, x0, pal)
            if ln.ball is not None and sim.alive_t[t]:
                X, Y = x0 + ln.ball[0], BOARD_TOP + ln.ball[1]
                d.ellipse((X - 11, Y - 11, X + 11, Y + 11), fill=tuple(int(v * .4) for v in c))
                d.ellipse((X - 7, Y - 7, X + 7, Y + 7), fill=c, outline=(255, 255, 255), width=2)
            if ln.last and ln.last[2] > 0:
                X = x0 + ln.last[0]; Y = BOARD_TOP + SLOT_Y + 2; ln.last[2] -= 1
                d.ellipse((X - 7, Y - 7, X + 7, Y + 7), fill=c, outline=(255, 255, 255), width=2)
            y = LANE_TOP + 14
            ctext(d, cx, y, names[t], font(30 * s), c, 3); y += 40 * s
            ctext(d, cx, y, fmt(sim.ammo[t]), font(34 * s), (255, 255, 255), 3); y += 46 * s
            L = int(sim.level[t])
            ctext(d, cx, y, f"Lv.{L} {PATTERN[L]}", font(21 * s), (255, 235, 140), 2); y += 30 * s
            need = NEED.get(L, 1); pw = (lw - 30) / 5
            for j in range(5):
                X0 = x0 + 15 + j * pw
                d.rectangle((X0 + 2, y, X0 + pw - 2, y + 6), fill=(255, 220, 90) if j < L else (50, 54, 80))
            y += 14
            if sim.shield[t] > 0: wt, wc = f"护盾 {sim.shield[t]/FPS:.0f}s", (120, 240, 255)
            elif sim.wt[t] > 0 and sim.weap[t] >= 0: wt, wc = f"{WEAP[sim.weap[t]]} {sim.wt[t]/FPS:.0f}s", (255, 140, 220)
            else: wt, wc = "武器 —", (120, 125, 160)
            ctext(d, cx, y, wt, font(19 * s), wc, 2); y += 28 * s
            ctext(d, cx, y, f"领地 {sim.share[t]*100:.1f}%", font(20 * s), (230, 235, 255), 2)
            yb = BOARD_TOP - 18; d.rectangle((x0 + 10, yb, x0 + lw - 10, yb + 6), fill=(40, 44, 70))
            d.rectangle((x0 + 10, yb, x0 + 10 + (lw - 20) * min(1, sim.share[t] / .5), yb + 6), fill=c)
            if not sim.alive_t[t]:
                ov = Image.new("RGBA", (int(lw), BOARD_BOT - LANE_TOP), (5, 5, 10, 175))
                im.paste(ov, (int(x0), LANE_TOP), ov); d = ImageDraw.Draw(im)
                ctext(d, cx, 520, "已淘汰", font(32 * s), (200, 200, 210), 3)
                if t in elim_info:
                    ctext(d, cx, 570, f"被{names[elim_info[t][0]]}攻破", font(20 * s), T(elim_info[t][0]), 2)
                    ctext(d, cx, 600, f"{elim_info[t][1]/FPS:.0f}秒", font(20 * s), (180, 180, 190), 2)
        for pp in fx.pops:
            x, y, txt, col, life = pp
            ctext(d, x, y - (40 - life) * 1.5, txt, font(26 * min(1, lw / 146)), col, 3); pp[4] -= 1
        fx.pops = [pp for pp in fx.pops if pp[4] > 0]
        # ---- top bar
        d.text((22, 16), "粒子领地大战", font=font(46), fill=(120, 240, 255), stroke_width=3, stroke_fill=(20, 40, 90))
        tx = 22 + d.textlength("粒子领地大战", font=font(46)) + 14
        d.rounded_rectangle((tx, 26, tx + 96, 66), 10, fill=(255, 80, 150))
        ctext(d, tx + 48, 28, f"第{episode}集", font(26), (255, 255, 255), 0)
        ph = sim.phase; pc = [(120, 220, 255), (255, 210, 90), (255, 80, 80)][ph]
        d.text((W - 360, 18), PHASES[ph], font=font(40), fill=pc, stroke_width=3, stroke_fill=(0, 0, 0))
        d.text((W - 190, 26), f"{sim.f/FPS:4.1f}s", font=font(32), fill=(230, 235, 255))
        # share bar
        x = MX; by0 = 30
        order = sorted(range(nt), key=lambda t: -sim.share[t])
        for t in order:
            wd = G * sim.share[t]
            if wd < 1: continue
            d.rectangle((x, by0, x + wd, by0 + 36), fill=T(t))
            if wd > 70: ctext(d, x + wd / 2, by0 + 4, f"{sim.share[t]*100:.0f}%", font(22), (255, 255, 255), 2)
            x += wd
        d.rectangle((MX, by0, MX + G, by0 + 36), outline=(200, 220, 255), width=2)
        d.text((MX, by0 - 26), "领地占比", font=font(18), fill=(150, 160, 200))
        # ---- banners (top of map) & captions (bottom of map)
        yb = MY + 70
        for b in [b for b in fx.banners if b[2] > 0][-2:]:
            txt, col, life, l0 = b; age = l0 - life; sc = 1.0 + max(0, .35 - age * .05)
            fn = font(52 * sc); tw = d.textlength(txt, font=fn)
            d.rounded_rectangle((MX + (G - tw) / 2 - 30, yb - 10, MX + (G + tw) / 2 + 30, yb + 52 * sc + 22), 18,
                                fill=(10, 12, 28), outline=col, width=4)
            d.text((MX + (G - tw) / 2, yb), txt, font=fn, fill=col, stroke_width=3, stroke_fill=(0, 0, 0))
            yb += 100
        for b in fx.banners: b[2] -= 1
        fx.banners = [b for b in fx.banners if b[2] > 0]
        if fx.cap is None and fx.caps: fx.cap = [fx.caps.pop(0), 66]
        if fx.cap:
            txt = "解说｜" + fx.cap[0]; fn = font(36); tw = d.textlength(txt, font=fn); yc = MY + G - 84
            d.rounded_rectangle((MX + (G - tw) / 2 - 22, yc - 8, MX + (G + tw) / 2 + 22, yc + 52), 12, fill=(0, 0, 0))
            d.text((MX + (G - tw) / 2, yc), txt, font=fn, fill=(255, 240, 150))
            fx.cap[1] -= 1
            if fx.cap[1] <= 0: fx.cap = None
        # ---- ending
        if end_f is not None:
            k = fi - end_f; w = sim.winner
            if k > 20:
                ov = Image.new("RGBA", (W, H), (0, 0, 0, min(170, (k - 20) * 10)))
                im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"); d = ImageDraw.Draw(im)
            if k > 26:
                el = sorted(elim_info.items(), key=lambda kv: kv[1][1])
                lines = [("冠军", font(46), (255, 230, 120)), (names[w], font(120), T(w)),
                         (f"占领 {sim.share[w]*100:.1f}% 领地 · 炮台 Lv.{sim.level[w]}", font(40), (255, 255, 255)),
                         (f"领先易主 {sim.lead_changes} 次 · 绝地反击 {sim.comebacks} 次", font(32), (210, 215, 240)),
                         ("你押中了吗？评论区见 · 下集更多队伍！", font(32), (210, 215, 240))]
                y = 250
                for txt, fn, col in lines:
                    ctext(d, W / 2, y, txt, fn, col, 5); y += fn.size + 30
            if k % 3 == 0 and k < 100:
                for _ in range(3):
                    fx.burst(fx.rng.uniform(100, G - 100), fx.rng.uniform(100, G - 100), 120,
                             glow[w] if fx.rng.random() < .6 else (255, 240, 160), 4, 40)
        frame = np.asarray(im)
        # flash & shake
        if fx.flash > .01:
            frame = (frame * (1 - fx.flash) + 255 * fx.flash).astype(np.uint8); fx.flash *= .8
        if fx.shake > .5:
            dx, dy = (fx.rng.uniform(-1, 1, 2) * fx.shake).astype(int)
            frame = np.roll(frame, (dy, dx), (0, 1)); fx.shake *= .85
        fx.slow -= 1
        frame = np.ascontiguousarray(frame)
        if prefix and fi in snap_frames(sim.maxf):
            Image.fromarray(frame).save(f"{prefix}_{fi:04d}.png")
        p.stdin.write(frame.tobytes()); fi += 1
        if end_f is not None and fi - end_f >= hold:
            if prefix: Image.fromarray(frame).save(f"{prefix}_end.png")
            break
    p.stdin.close(); p.wait()
    wav = out + ".wav"; make_audio(wav, frames_ev, fi)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "128k", "-shortest", "-movflags", "+faststart", out], check=True)
    os.remove(tmp); os.remove(wav)
    return fi, sim


def snap_frames(maxf):
    return {int(maxf * k) for k in (.05, .2, .35, .5, .65, .8, .95)}


def main():
    ap = argparse.ArgumentParser(description="粒子领地大战 v2")
    ap.add_argument("--teams", type=int, default=6); ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--seed-start", type=int, default=0); ap.add_argument("--seed", type=int)
    ap.add_argument("--duration", type=float, default=72.0); ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--out", default="marble_v2_sample.mp4"); ap.add_argument("--preview", default="marble_v2_preview")
    a = ap.parse_args(); nt = max(4, min(8, a.teams)); seed = a.seed
    if seed is None:
        t0 = time.time(); best = None
        with Pool(a.jobs) as pool:
            for s, (sc, info) in pool.imap_unordered(run_headless, [(s, nt, a.duration) for s in range(a.seed_start, a.seed_start + a.seeds)]):
                print(f"seed {s:3d} score {sc:6.1f} {info}", flush=True)
                if best is None or sc > best[0]: best = (sc, s, info)
        seed = best[1]; print(f"chosen seed {seed} score {best[0]:.1f} {best[2]} (screening {time.time()-t0:.0f}s)")
    t0 = time.time(); fi, sim = render(seed, nt, a.duration, a.episode, a.out, a.preview)
    sc, info = score(sim)
    print(f"rendered {fi} frames ({fi/FPS:.1f}s) in {time.time()-t0:.0f}s; seed {seed} winner {TEAM_POOL[sim.winner][0]} {info}")


if __name__ == "__main__":
    main()
