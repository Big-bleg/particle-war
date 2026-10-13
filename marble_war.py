#!/usr/bin/env python3
"""球球领土战争 (MarblePi 风格复刻) - 横屏 1920x1080.

左: 弹珠台 (Plinko). 4 队弹珠穿过钉阵 → 中层倍率槽 (x2/x4/x8) 放大弹药; 落入中央闸门 →
    下层钉阵 → 武器槽 (霰弹/机枪/护盾/大球/狙击).
右: 1000x1000 (百万像素) 领土地图, 四角基地炮台旋转发射海量粒子, 粒子撞到异色像素即染色.
    基地中心被占 → 淘汰, 领土与一半弹药归占领者. 最后存活或时间到领土最大者获胜.
"""
import argparse, os, subprocess, wave, time, math
import numpy as np
from numba import njit
from PIL import Image, ImageDraw, ImageFont

TEAMS = [("红队", (230, 50, 50)), ("蓝队", (40, 110, 240)), ("绿队", (30, 180, 70)), ("黄队", (240, 200, 20))]
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FPS, W, H, G = 30, 1920, 1080, 1000
MX, MY = 880, 50                  # map origin on screen
PX, PY, PW, PH = 40, 120, 560, 940  # plinko panel
NMAX = 30000
SUB = 6
BASE_R = 46
BASES = np.array([[110, 110], [G - 110, 110], [110, G - 110], [G - 110, G - 110]], float)  # (x,y)
MAXF = 54 * FPS
MID = ["x2", "x8", "x4", "x2", "闸门", "x2", "x4", "x8", "x2"]
WEAP = ["霰弹", "机枪", "护盾", "大球", "狙击"]


@njit(cache=True)
def nb_seed(s):
    np.random.seed(s)


@njit(cache=True)
def step(grid, x, y, vx, vy, tm, en, bp, alive, conv, shield, bases, br2):
    g = grid.shape[0]
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
                    blocked = False
                    if shield[o] > 0:
                        dx = nx - bases[o, 0]; dy = ny - bases[o, 1]
                        if dx * dx + dy * dy < br2 * 2.2:
                            blocked = True
                    if blocked:
                        en[i] -= 3.0
                    else:
                        grid[cy, cx] = t; en[i] -= 1.0; conv[t] += 1
                    if blocked or np.random.random() < bp[i]:
                        if ax == 0: vx[i] = -vx[i]
                        else: vy[i] = -vy[i]
                        continue
                x[i] = nx; y[i] = ny
            if en[i] <= 0:
                alive[i] = False
                break


@njit(cache=True)
def count(grid, nt):
    c = np.zeros(nt, np.int64)
    for v in grid.ravel():
        c[v] += 1
    return c


@njit(cache=True)
def fire(x, y, vx, vy, tm, en, bp, alive, t, n, bx, by, ang, spread, speed, energy, bounce, start):
    m = x.shape[0]; made = 0; i = start
    for _ in range(m):
        if made >= n:
            break
        i = (i + 1) % m
        if alive[i]:
            continue
        a = ang + (np.random.random() - 0.5) * spread
        sp = speed * (0.8 + 0.4 * np.random.random())
        x[i] = bx + math.cos(a) * 30; y[i] = by + math.sin(a) * 30
        vx[i] = math.cos(a) * sp; vy[i] = math.sin(a) * sp
        tm[i] = t; en[i] = energy; bp[i] = bounce; alive[i] = True
        made += 1
    return i


@njit(cache=True)
def draw_parts(img, x, y, tm, en, alive, col, ox, oy):
    for i in range(x.shape[0]):
        if not alive[i]:
            continue
        cx = int(x[i]) + ox; cy = int(y[i]) + oy
        r = 3 if en[i] > 200 else 1
        for dy in range(-r + 1, r):
            for dx in range(-r + 1, r):
                px, py = cx + dx, cy + dy
                img[py, px, 0] = col[tm[i], 0]; img[py, px, 1] = col[tm[i], 1]; img[py, px, 2] = col[tm[i], 2]


def fmt(v):
    v = float(v)
    for u, d in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= d:
            s = f"{v/d:.1f}".rstrip("0").rstrip(".")
            return s + u
    return str(int(v))


class Plinko:
    """简单弹珠台物理 (面板坐标)."""
    def __init__(self, rng):
        self.rng = rng
        pegs = []
        for r, yy in enumerate(range(40, 430, 34)):
            off = 20 if r % 2 else 0
            for xx in range(20 + off, PW - 10, 40):
                pegs.append((xx, yy))
        for r, yy in enumerate(range(560, 800, 34)):
            off = 20 if r % 2 else 0
            for xx in range(20 + off, PW - 10, 40):
                pegs.append((xx, yy))
        self.pegs = np.array(pegs, float)
        self.mid_y, self.bot_y = 470, 860
        self.balls = [self.new(t) for t in range(4)]
        self.mid_hits = np.zeros(len(MID), int); self.bot_hits = np.zeros(len(WEAP), int)

    def new(self, t):
        return dict(t=t, x=self.rng.uniform(60, PW - 60), y=8.0, vx=self.rng.uniform(-1, 1), vy=0.0, low=False)

    def tick(self, alive_t):
        ev = []
        for k, b in enumerate(self.balls):
            if not alive_t[b["t"]]:
                continue
            for _ in range(3):
                b["vy"] += 0.25; b["x"] += b["vx"]; b["y"] += b["vy"]
                if b["x"] < 11: b["x"] = 11; b["vx"] = abs(b["vx"]) * 0.6
                if b["x"] > PW - 11: b["x"] = PW - 11; b["vx"] = -abs(b["vx"]) * 0.6
                d = self.pegs - (b["x"], b["y"]); dist = np.hypot(d[:, 0], d[:, 1])
                j = int(dist.argmin())
                if dist[j] < 15:
                    nx, ny = -d[j] / max(dist[j], 1e-3)
                    b["x"] = self.pegs[j, 0] + nx * 15; b["y"] = self.pegs[j, 1] + ny * 15
                    vn = b["vx"] * nx + b["vy"] * ny
                    if vn < 0:
                        b["vx"] -= 1.5 * vn * nx; b["vy"] -= 1.5 * vn * ny
                    b["vx"] += self.rng.normal(0, 0.35)
                sp = math.hypot(b["vx"], b["vy"])
                if sp > 6: b["vx"] *= 6 / sp; b["vy"] *= 6 / sp
            if not b["low"] and b["y"] >= self.mid_y:
                s = min(len(MID) - 1, int(b["x"] / (PW / len(MID))))
                self.mid_hits[s] += 1
                if MID[s] == "闸门":
                    b["low"] = True; b["y"] = self.mid_y + 50; b["vy"] = 1
                else:
                    ev.append(("mult", b["t"], int(MID[s][1:]))); self.balls[k] = self.new(b["t"])
            elif b["low"] and b["y"] >= self.bot_y:
                s = min(len(WEAP) - 1, int(b["x"] / (PW / len(WEAP))))
                self.bot_hits[s] += 1
                ev.append(("weap", b["t"], s)); self.balls[k] = self.new(b["t"])
        return ev


class Sim:
    def __init__(self, seed):
        self.nt = nt = 4
        rng = self.rng = np.random.default_rng(seed); nb_seed(seed)
        g = np.zeros((G, G), np.int8); h = G // 2
        g[:h, h:] = 1; g[h:, :h] = 2; g[h:, h:] = 3
        self.grid = g
        z = lambda dt=float: np.zeros(NMAX, dt)
        self.x, self.y, self.vx, self.vy, self.en, self.bp = z(), z(), z(), z(), z(), z()
        self.tm = z(np.int8); self.alive = z(bool)
        self.ammo = np.full(nt, 2000.0)
        self.alive_t = np.ones(nt, bool)
        self.shield = np.zeros(nt, np.int64); self.weap = np.full(nt, -1); self.wt = np.zeros(nt, int)
        self.ang = np.array([math.atan2(G / 2 - b[1], G / 2 - b[0]) for b in BASES])
        self.phase = rng.uniform(0, 6.28, nt); self.cur = 0
        self.plinko = Plinko(rng)
        self.f = 0

    def tick(self):
        nt, f, ev = self.nt, self.f, []
        for e in self.plinko.tick(self.alive_t):
            if e[0] == "mult":
                self.ammo[e[1]] = min(self.ammo[e[1]] * e[2], 5e9); ev.append(e)
            else:
                t, s = e[1], e[2]
                if WEAP[s] == "护盾": self.shield[t] = 6 * FPS
                else: self.weap[t] = s; self.wt[t] = 4 * FPS
                ev.append(e)
        for t in range(nt):
            if not self.alive_t[t]:
                continue
            self.ammo[t] += 150
            base_a = math.atan2(G / 2 - BASES[t, 1], G / 2 - BASES[t, 0])
            self.ang[t] = base_a + 0.75 * math.sin(f * 0.045 + self.phase[t])
            n = int(min(self.ammo[t], 25 * math.log10(self.ammo[t] + 10) * (1 + 2.5 * f / MAXF)))
            spread, speed, energy, bounce = 0.12, 1.0, 40.0, 0.5
            w = self.weap[t] if self.wt[t] > 0 else -1
            if w == 0: spread, n = 1.4, n * 2                    # 霰弹
            elif w == 1: n, spread = n * 3, 0.05                 # 机枪
            elif w == 3: n, energy, bounce = max(1, n // 12), 1500.0, 0.0   # 大球
            elif w == 4:                                          # 狙击: 瞄准最近的敌方基地
                tg = [o for o in range(nt) if o != t and self.alive_t[o]]
                if tg:
                    o = min(tg, key=lambda o: np.hypot(*(BASES[o] - BASES[t])))
                    self.ang[t] = math.atan2(BASES[o, 1] - BASES[t, 1], BASES[o, 0] - BASES[t, 0])
                n, spread, energy, bounce, speed = max(1, n // 3), 0.02, 300.0, 0.0, 1.0
            self.ammo[t] -= 0.25 * (n if w != 3 else n * 12)
            self.ammo[t] = max(self.ammo[t], 0)
            self.cur = fire(self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, t, n,
                            BASES[t, 0], BASES[t, 1], self.ang[t], spread, speed, energy, bounce, self.cur)
        self.wt -= 1; self.shield = np.maximum(self.shield - 1, 0)
        conv = np.zeros(nt, np.int64)
        step(self.grid, self.x, self.y, self.vx, self.vy, self.tm, self.en, self.bp, self.alive, conv,
             self.shield, BASES, float(BASE_R * BASE_R))
        for t in range(nt):
            if not self.alive_t[t]:
                continue
            bx, by = int(BASES[t, 0]), int(BASES[t, 1])
            o = int(self.grid[by, bx])
            if o != t:
                self.alive_t[t] = False
                self.grid[self.grid == t] = o
                self.ammo[o] += self.ammo[t] * 0.5; self.ammo[t] = 0
                self.alive[self.alive & (self.tm == t)] = False
                ev.append(("elim", t, o))
            elif self.shield[t] == 0:
                pass
        cnt = count(self.grid, nt)
        self.share = cnt / float(G * G)
        self.f += 1
        return conv, ev


def run_headless(seed):
    s = Sim(seed); hist, evs = [], []
    while s.f < MAXF:
        _, ev = s.tick(); hist.append(s.share.copy()); evs += [(s.f, *e) for e in ev]
        if s.alive_t.sum() <= 1:
            break
    return np.array(hist), evs, s.f


def score(hist, evs, nf):
    el = [e[0] for e in evs if e[1] == "elim"]
    dur = nf / FPS
    leader = hist.argmax(1)
    changes = int((np.diff(leader[::15]) != 0).sum())
    natural = len(el) == 3
    sc = changes * 2 + len(el) * 4
    if natural and 42 <= dur <= 56: sc += 25
    if el and el[0] < 12 * FPS: sc -= 10          # 太早淘汰
    if len(el) >= 2: sc -= abs(np.diff(el).min() / FPS < 3) * 4
    w = sum(1 for e in evs if e[1] == "weap")
    sc += min(w, 12) * 0.5
    return sc, dict(dur=round(dur, 1), elims=len(el), changes=changes, natural=natural, weap=w)


def font(sz): return ImageFont.truetype(FONT, sz)


def make_audio(path, frames_ev, nframes, sr=44100):
    n = int((nframes / FPS + 2.5) * sr); a = np.zeros(n, np.float32); rng = np.random.default_rng(1)
    def add(st, sig):
        s = int(st * sr); e = min(n, s + len(sig)); a[s:e] += sig[:e - s]
    def tone(fr, dur, vol, dec=30, sw=0.0):
        t = np.arange(int(dur * sr)) / sr; f = fr * (1 + sw * t / dur)
        return (np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-dec * t) * vol).astype(np.float32)
    last = -1
    for fi, (conv, ev) in enumerate(frames_ev):
        ts = fi / FPS
        if conv > 0 and ts - last >= 1 / 12:
            add(ts, tone(rng.uniform(900, 1600), 0.04, 0.04 + 0.06 * min(1, conv / 20000), 80)); last = ts
        for e in ev:
            k = e[0]
            if k == "peg": add(ts, tone(rng.uniform(2000, 2600), 0.02, 0.03, 150))
            elif k == "mult": add(ts, tone(600 + 80 * e[2], 0.25, 0.18, 10, 0.6))
            elif k == "weap": add(ts, tone(330, 0.4, 0.22, 6, 1.2)); add(ts + 0.1, tone(660, 0.3, 0.15, 8))
            elif k == "elim": add(ts, tone(440, 0.7, 0.35, 4, -0.5)); add(ts + .05, tone(220, .8, .3, 4, -.5))
            elif k == "win":
                for j, fr in enumerate([523, 659, 784, 1047]): add(ts + j * .12, tone(fr, 1.2, .25, 2.5))
    a = np.clip(a, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes((a * 32000).astype(np.int16).tobytes())


def render(seed, episode, out, preview):
    names = [n for n, _ in TEAMS]; pal = np.array([c for _, c in TEAMS], np.uint8)
    pale = np.clip(pal.astype(int) * 0.35 + 255 * 0.65, 0, 255).astype(np.uint8)
    f64, f40, f30, f24, f20, f16, f90 = (font(s) for s in (60, 40, 30, 24, 20, 15, 90))
    sim = Sim(seed); pk = sim.plinko
    tmp = out + ".video.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "23",
                          "-maxrate", "6M", "-bufsize", "12M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp],
                         stdin=subprocess.PIPE)
    # static background: grid lines layer + plinko board
    gl = np.zeros((G, G), bool); gl[::50, :] = True; gl[:, ::50] = True
    bg = Image.new("RGB", (W, H), (0, 0, 0)); d = ImageDraw.Draw(bg)
    d.rounded_rectangle((PX - 10, PY - 10, PX + PW + 10, PY + PH + 10), 18, fill=(40, 42, 48))
    for (x, y) in pk.pegs:
        d.ellipse((PX + x - 4, PY + y - 4, PX + x + 4, PY + y + 4), fill=(235, 235, 235))
    sw = PW / len(MID)
    for i, lab in enumerate(MID):
        x0 = PX + i * sw; y0 = PY + pk.mid_y - 20
        d.rectangle((x0 + 2, y0, x0 + sw - 2, y0 + 44), fill=(255, 255, 255) if lab == "闸门" else (70, 72, 82))
        fnt = f20 if lab == "闸门" else f24
        d.text((x0 + (sw - d.textlength(lab, font=fnt)) / 2, y0 + 8), lab, font=fnt, fill=(0, 0, 0) if lab == "闸门" else (255, 230, 120))
    bw_ = PW / len(WEAP)
    for i, lab in enumerate(WEAP):
        x0 = PX + i * bw_; y0 = PY + pk.bot_y - 10
        d.rectangle((x0 + 3, y0, x0 + bw_ - 3, y0 + 70), fill=(70, 72, 82))
        d.text((x0 + (bw_ - d.textlength(lab, font=f24)) / 2, y0 + 6), lab, font=f24, fill=(120, 230, 255))
    bg_np = np.asarray(bg).copy()
    frames_ev, banners, snaps = [], [], {}
    end_f = winner = None; fi = 0; hold = 4 * FPS; el_order = []
    while True:
        if end_f is None:
            conv, ev = sim.tick()
            for e in ev:
                c = pal[e[1]]
                if e[0] == "elim":
                    el_order.append(e[1]); banners.append([f"{names[e[1]]} 基地被 {names[e[2]]} 攻破，淘汰！", c, 75])
                elif e[0] == "weap":
                    banners.append([f"{names[e[1]]} 获得【{WEAP[e[2]]}】", c, 45])
                elif e[0] == "mult" and e[2] >= 8:
                    banners.append([f"{names[e[1]]} 弹药 x{e[2]}！", c, 35])
            if sim.alive_t.sum() <= 1 or sim.f >= MAXF:
                winner = int(np.argmax(sim.share)); end_f = fi; ev = ev + [("win", winner)]
            frames_ev.append((int(conv.sum()), ev))
        else:
            frames_ev.append((0, []))
        img = bg_np.copy()
        mp = pal[sim.grid].copy()
        mp[gl] = (mp[gl].astype(np.uint16) * 3 // 5 + 100).astype(np.uint8)
        img[MY:MY + G, MX:MX + G] = mp
        draw_parts(img, sim.x, sim.y, sim.tm, sim.en, sim.alive, pale, MX, MY)
        im = Image.fromarray(img); d = ImageDraw.Draw(im)
        # title
        d.text((PX, 18), f"球球领土战争 第{episode}集", font=f40, fill="white")
        d.text((PX, 70), f"百万像素+海量粒子   {sim.f/FPS:04.1f}s   粒子 {fmt(sim.alive.sum())}", font=f20, fill=(170, 170, 180))
        # plinko counters & marbles
        for i in range(len(MID)):
            s = str(pk.mid_hits[i]); x0 = PX + i * sw
            d.text((x0 + (sw - d.textlength(s, font=f16)) / 2, PY + pk.mid_y + 26), s, font=f16, fill=(200, 200, 200))
        for i in range(len(WEAP)):
            s = f"×{pk.bot_hits[i]}"; x0 = PX + i * bw_
            d.text((x0 + (bw_ - d.textlength(s, font=f20)) / 2, PY + pk.bot_y + 30), s, font=f20, fill=(220, 220, 220))
        for b in pk.balls:
            if not sim.alive_t[b["t"]]: continue
            x, y = PX + b["x"], PY + b["y"]; c = tuple(int(v) for v in pal[b["t"]])
            d.ellipse((x - 13, y - 13, x + 13, y + 13), fill=c, outline=(255, 255, 255), width=2)
            s = fmt(sim.ammo[b["t"]])
            d.text((x - d.textlength(s, font=f16) / 2, y - 10), s, font=f16, fill="white", stroke_width=2, stroke_fill="black")
        # bases
        for t in range(4):
            bx, by = MX + BASES[t, 0], MY + BASES[t, 1]; c = tuple(int(v) for v in pal[t])
            if not sim.alive_t[t]:
                d.ellipse((bx - BASE_R, by - BASE_R, bx + BASE_R, by + BASE_R), fill=(50, 50, 50), outline=(20, 20, 20), width=4)
                d.text((bx - d.textlength("淘汰", font=f24) / 2, by - 16), "淘汰", font=f24, fill=(160, 160, 160)); continue
            if sim.shield[t] > 0:
                d.ellipse((bx - BASE_R - 16, by - BASE_R - 16, bx + BASE_R + 16, by + BASE_R + 16), outline=(140, 230, 255), width=6)
            a = sim.ang[t]
            d.line((bx, by, bx + math.cos(a) * (BASE_R + 40), by + math.sin(a) * (BASE_R + 40)), fill=(30, 30, 30), width=18)
            d.line((bx, by, bx + math.cos(a) * (BASE_R + 38), by + math.sin(a) * (BASE_R + 38)), fill=c, width=12)
            d.ellipse((bx - BASE_R, by - BASE_R, bx + BASE_R, by + BASE_R), fill=c, outline=(255, 255, 255), width=4)
            s = fmt(sim.ammo[t])
            d.text((bx - d.textlength(s, font=f30) / 2, by - 30), s, font=f30, fill="white", stroke_width=3, stroke_fill="black")
            s2 = f"{sim.share[t]*100:.1f}%"
            d.text((bx - d.textlength(s2, font=f20) / 2, by + 6), s2, font=f20, fill="white", stroke_width=2, stroke_fill="black")
            if sim.wt[t] > 0 and sim.weap[t] >= 0:
                s3 = WEAP[sim.weap[t]]
                d.text((bx - d.textlength(s3, font=f20) / 2, by + BASE_R + 4), s3, font=f20, fill=(255, 255, 160), stroke_width=3, stroke_fill="black")
        # leaderboard (right of title area)
        order = sorted(range(4), key=lambda t: -sim.share[t])
        x0 = PX + PW + 40
        d.text((x0, MY + 4), "排行", font=f24, fill=(180, 180, 190))
        for i, t in enumerate(order):
            y = MY + 44 + i * 70; c = tuple(int(v) for v in pal[t]) if sim.alive_t[t] else (90, 90, 90)
            d.text((x0, y), names[t], font=f24, fill=c)
            d.text((x0, y + 30), f"{sim.share[t]*100:.1f}%" if sim.alive_t[t] else "淘汰", font=f20, fill="white")
        # banners over map
        by = MY + G // 2 - 140
        for b in [b for b in banners if b[2] > 0][-3:]:
            tw = d.textlength(b[0], font=f40)
            d.rounded_rectangle((MX + (G - tw) / 2 - 24, by - 8, MX + (G + tw) / 2 + 24, by + 58), 16, fill=(0, 0, 0))
            d.text((MX + (G - tw) / 2, by), b[0], font=f40, fill=tuple(int(v) for v in b[1]))
            by += 80
        for b in banners: b[2] -= 1
        if end_f is not None:
            k = fi - end_f
            ov = Image.new("RGBA", (W, H), (0, 0, 0, min(160, k * 10)))
            im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB"); d = ImageDraw.Draw(im)
            if k > 6:
                lines = [("冠军", f40, (255, 230, 120)), (names[winner], f90, tuple(int(v) for v in pal[winner])),
                         (f"占领 {sim.share[winner]*100:.1f}% 领土", f40, (255, 255, 255)),
                         ("统一全图！" if sim.alive_t.sum() == 1 else "时间到 · 按领土判定", f30, (210, 210, 210)),
                         ("你押中了吗？评论区见", f30, (210, 210, 210))]
                y = 300
                for txt, fn, col in lines:
                    tw = d.textlength(txt, font=fn)
                    d.text(((W - tw) / 2, y), txt, font=fn, fill=col, stroke_width=5, stroke_fill="black"); y += fn.size + 34
        frame = np.asarray(im)
        if fi in (90, 450, 900, 1200) or (end_f is not None and fi == end_f - 15):
            snaps[fi] = frame.copy()
        p.stdin.write(frame.tobytes()); fi += 1
        if end_f is not None and fi - end_f >= hold:
            Image.fromarray(frame).save(preview.replace(".png", "_end.png")); break
    p.stdin.close(); p.wait()
    for k, fr in snaps.items():
        Image.fromarray(fr).save(preview.replace(".png", f"_f{k}.png"))
    Image.fromarray(snaps[450]).save(preview)
    wav = out + ".wav"; make_audio(wav, frames_ev, fi)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "128k", "-shortest", out], check=True)
    os.remove(tmp); os.remove(wav)
    return fi, winner, el_order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24); ap.add_argument("--seed", type=int)
    ap.add_argument("--episode", type=int, default=1)
    ap.add_argument("--out", default="marble_sample.mp4"); ap.add_argument("--preview", default="marble_preview.png")
    a = ap.parse_args(); seed = a.seed
    if seed is None:
        best = None
        for s in range(a.seeds):
            t0 = time.time(); hist, evs, nf = run_headless(s); sc, info = score(hist, evs, nf)
            print(f"seed {s:3d} score {sc:6.1f} {info} ({time.time()-t0:.1f}s)", flush=True)
            if best is None or sc > best[0]: best = (sc, s)
        seed = best[1]; print("chosen seed", seed)
    t0 = time.time(); fi, w, el = render(seed, a.episode, a.out, a.preview)
    print(f"rendered {fi} frames ({fi/FPS:.1f}s) winner {TEAMS[w][0]} elim {[TEAMS[t][0] for t in el]} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
