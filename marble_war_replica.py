#!/usr/bin/env python3
"""Douyin War4Balls-style visual replica · ~18s growth demo.

Faithful look from refs/douyin_marblepi_*.png:
  left ~40% Plinko (X8 X4 X2 | X2 X4 X8, items 风暴/机枪/护盾/大球/狙击),
  right ~60% navy arena with softGRADIENT team fills, jagged bright frontier,
  evolving bullets (dots → neon beams), huge translucent big-balls.
Mechanics nod to UnityDotsBallBattle: bullet paints foreign cell then dies.
Separate from the v5 5min track — do not touch marble_v5_5min*.
"""
from __future__ import annotations
import math, os, subprocess, wave, time, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FPS, W, H = 30, 1920, 1080
DEMO_SEC = 18.0
DEMO_F = int(DEMO_SEC * FPS)  # 540

# layout: left ~38% plinko, right square arena
LEFT_W = int(W * 0.38)
G = min(H - 48, W - LEFT_W - 40)  # display arena px (~1032)
MX = W - G - 20
MY = (H - G) // 2
PX0, PX1 = 16, LEFT_W - 12
PTOP, PBOT = 52, H - 40
PW = PX1 - PX0

# low-res paint grid (fast fill), upscaled to G
GS = 280
SCALE = G / GS

MULTS = [8, 4, 2, 2, 4, 8]
ITEMS = ["风暴", "机枪", "护盾", "大球", "狙击"]
# TL red, TR green, BL blue, BR orange  (Douyin order)
TEAMS = [
    ("红队", (235, 55, 90), (255, 150, 190)),   # 0 TL
    ("绿队", (30, 210, 140), (80, 255, 230)),   # 1 TR
    ("蓝队", (50, 130, 255), (100, 220, 255)),  # 2 BL
    ("橙队", (255, 145, 40), (255, 215, 90)),   # 3 BR
]
NEU = (18, 24, 48)
NMAX = 9000
PROT_R = G / 10.5

_fc = {}
def font(sz, bold=False):
    sz = max(10, int(sz))
    key = (sz, bold)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(FONT_B if bold else FONT, sz)
    return _fc[key]

def ctext(d, cx, y, s, fn, fill, sw=1, sf=(0, 0, 0)):
    d.text((cx - d.textlength(s, font=fn) / 2, y), s, font=fn, fill=fill,
           stroke_width=sw, stroke_fill=sf)

def fmt_abbr(v):
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


class Game:
    def __init__(self, seed=7, nt=4):
        self.nt = nt
        self.rng = np.random.default_rng(seed)
        self.f = 0
        self.maxf = DEMO_F
        m = PROT_R / SCALE + 8  # in grid units
        # TL, TR, BL, BR
        self.bases_g = np.array([
            [m, m],
            [GS - m, m],
            [m, GS - m],
            [GS - m, GS - m],
        ], float)
        self.bases = self.bases_g * SCALE  # display coords
        self.grid = np.full((GS, GS), nt, np.int8)
        # seed soft corner blobs (opening push)
        for t in range(nt):
            self._blob(t, radius=int(GS * 0.14))
        self.ang = np.array([
            math.atan2(GS / 2 - self.bases_g[t, 1], GS / 2 - self.bases_g[t, 0])
            for t in range(nt)
        ])
        self.spin = 0.042
        self.fire_cd = np.zeros(nt, int)
        self.ammo = np.array([2.6e6, 2.55e6, 2.5e6, 2.58e6])
        self.score2 = np.array([1.98e5, 2.96e5, 8.0e4, 2.99e5])
        self.shield = np.array([198000., 296000., 80000., 299000.])
        self.level = np.zeros(nt, int)
        self.item_cnt = np.zeros((nt, len(ITEMS)), int)
        self.global_items = np.zeros(len(ITEMS), int)
        self.slot_hits = np.zeros(6, int)
        z = lambda dt=float: np.zeros(NMAX, dt)
        self.px = z(); self.py = z(); self.pvx = z(); self.pvy = z()
        self.ptm = z(np.int8); self.pval = z(); self.pbase = z()
        self.palive = z(bool); self.pkind = z(np.int8)  # 0 dot 1 beam 2 big
        self.pscale = z(); self.page = z(np.int16)
        self.pcur = 0
        self.share = np.zeros(nt)
        self.sparks = []
        self.phase = 0
        self.marbles = []
        self.pegs = self._make_pegs()
        self.next_drop = [4 + t * 8 for t in range(nt)]
        self._paint_kernel_cache = {}

    def _blob(self, t, radius):
        bx, by = self.bases_g[t]
        yy, xx = np.ogrid[0:GS, 0:GS]
        dist = np.sqrt((xx - bx) ** 2 + (yy - by) ** 2)
        # soft ellipse bias toward center for "push"
        cx, cy = GS / 2, GS / 2
        toward = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        mask = dist < radius * (1.0 + 0.35 * (1 - toward / (GS * 0.7)))
        # jagged: noise
        noise = self.rng.random((GS, GS))
        mask &= (dist < radius * 0.85) | (noise > 0.35)
        self.grid[mask] = t

    def _make_pegs(self):
        """Collision pegs (upper only). Visual lower pegs drawn separately."""
        pegs = []
        for r in range(6):
            stagger = r % 2
            y = PTOP + 55 + r * 36
            x0 = 28 + (22 if stagger else 0)
            x = x0
            while x < PW - 28:
                pegs.append((x, y))
                x += 44
        return pegs

    def _visual_lower_pegs(self):
        pegs = []
        for r in range(4):
            stagger = r % 2
            y = PTOP + 455 + r * 38
            x0 = 28 + (22 if stagger else 0)
            x = x0
            while x < PW - 28:
                pegs.append((x, y))
                x += 44
        return pegs

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

    def spawn_marble(self, t):
        age = self.f / DEMO_F
        base = 400 * (1 + 80 * age ** 1.5)
        val = base * float(self.rng.choice([1, 2, 4, 8, 16, 32],
                                           p=[0.28, 0.28, 0.2, 0.12, 0.08, 0.04]))
        lane = self.rng.uniform(0.15, 0.85)
        self.marbles.append({
            "t": t,
            "x": PW * lane,
            "y": PTOP + 28.0,
            "vx": self.rng.uniform(-1.8, 1.8),
            "vy": self.rng.uniform(2.2, 3.5),
            "val": val,
            "alive": True,
            "age": 0,
            "hit": None,
        })

    def fire(self, t):
        if self.fire_cd[t] > 0:
            return
        bx, by = self.bases[t]  # display
        ang = self.ang[t]
        age = self.f / DEMO_F
        if age < 0.30:
            period, n_shot, speed, kind = 2, 16, 5.5, 0
        elif age < 0.60:
            period, n_shot, speed, kind = 2, 20, 6.5, 1
        else:
            period, n_shot, speed, kind = 1, 24, 7.2, 1
        self.fire_cd[t] = period
        spread = 0.55 if kind == 0 else 0.28
        ids = self._alloc(n_shot)
        for k, i in enumerate(ids):
            a = ang + (k - (n_shot - 1) / 2) * (spread / max(1, n_shot - 1))
            a += self.rng.uniform(-0.04, 0.04)
            sp = speed * self.rng.uniform(0.88, 1.12)
            self.px[i] = bx + math.cos(a) * 28
            self.py[i] = by + math.sin(a) * 28
            self.pvx[i] = math.cos(a) * sp
            self.pvy[i] = math.sin(a) * sp
            self.ptm[i] = t
            self.pval[i] = 8; self.pbase[i] = 8
            self.palive[i] = True; self.pkind[i] = kind
            self.pscale[i] = 1.0; self.page[i] = 0

        # big balls mid/late
        if age > 0.18 and self.rng.random() < 0.018 + 0.04 * age:
            bi = self._alloc(1)
            if bi:
                i = bi[0]
                a = ang + self.rng.uniform(-0.15, 0.15)
                val = 6e6 * (1 + 12 * age) * self.rng.uniform(0.55, 1.5)
                self.px[i] = bx + math.cos(a) * 40
                self.py[i] = by + math.sin(a) * 40
                sp = 2.4
                self.pvx[i] = math.cos(a) * sp
                self.pvy[i] = math.sin(a) * sp
                self.ptm[i] = t; self.pval[i] = val; self.pbase[i] = val
                self.palive[i] = True; self.pkind[i] = 2
                self.pscale[i] = 0.0; self.page[i] = 0

    def _paint_disk(self, ix, iy, t, pr):
        key = pr
        if key not in self._paint_kernel_cache:
            yy, xx = np.ogrid[-pr:pr + 1, -pr:pr + 1]
            self._paint_kernel_cache[key] = xx * xx + yy * yy <= pr * pr
        kern = self._paint_kernel_cache[key]
        y0, y1 = max(0, iy - pr), min(GS, iy + pr + 1)
        x0, x1 = max(0, ix - pr), min(GS, ix + pr + 1)
        ky0, kx0 = y0 - (iy - pr), x0 - (ix - pr)
        ky1, kx1 = ky0 + (y1 - y0), kx0 + (x1 - x0)
        sub = self.grid[y0:y1, x0:x1]
        mask = kern[ky0:ky1, kx0:kx1] & (sub != t)
        sub[mask] = t

    def tick_projectiles(self):
        big = self.palive & (self.pkind == 2)
        if big.any():
            idx = np.nonzero(big)[0]
            self.page[idx] = np.minimum(self.page[idx] + 1, 12)
            u = self.page[idx].astype(np.float32) / 12.0
            self.pscale[idx] = 1.0 - (1.0 - u) ** 3

        alive_idx = np.nonzero(self.palive)[0]
        for i in alive_idx:
            t = int(self.ptm[i])
            kind = int(self.pkind[i])
            vx, vy = float(self.pvx[i]), float(self.pvy[i])
            # move in display space, collide in grid space
            self.px[i] += vx
            self.py[i] += vy
            x, y = float(self.px[i]), float(self.py[i])
            if x < 2 or x >= G - 2 or y < 2 or y >= G - 2:
                self.palive[i] = False
                continue
            gx, gy = int(x / SCALE), int(y / SCALE)
            if gx < 0 or gx >= GS or gy < 0 or gy >= GS:
                self.palive[i] = False
                continue
            o = int(self.grid[gy, gx])
            if o == t:
                continue
            # foreign/neutral: paint then die (UnityDotsBallBattle)
            pr = 1 if kind == 0 else (2 if kind == 1 else 6)
            self._paint_disk(gx, gy, t, pr)
            if self.rng.random() < 0.4:
                tip = TEAMS[t][2]
                self.sparks.append([x, y, 12, tip])
            if kind != 2:
                self.palive[i] = False
            else:
                self.pval[i] *= 0.992
                # keep painting while moving — step extra paints along path
                for _ in range(2):
                    self.px[i] += vx * 0.4
                    self.py[i] += vy * 0.4
                    gx2, gy2 = int(self.px[i] / SCALE), int(self.py[i] / SCALE)
                    if 0 <= gx2 < GS and 0 <= gy2 < GS:
                        self._paint_disk(gx2, gy2, t, pr)
                if self.pval[i] < self.pbase[i] * 0.12:
                    self.palive[i] = False

    def tick_marbles(self):
        LEDGE = PTOP + 340
        LEDGE_H = 48
        ROW = PBOT - 100
        age = self.f / DEMO_F
        for t in range(self.nt):
            if self.f >= self.next_drop[t]:
                gap = int(36 - 20 * age)
                self.next_drop[t] = self.f + max(12, gap)
                self.spawn_marble(t)
                if age > 0.25 and self.rng.random() < 0.45:
                    self.spawn_marble(t)
                if age > 0.55 and self.rng.random() < 0.4:
                    self.spawn_marble(t)
        alive = []
        for m in self.marbles:
            if not m["alive"]:
                continue
            m["age"] += 1
            m["vy"] += 0.22
            m["vy"] = min(m["vy"], 14)
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            # soft peg collisions (only before multiplier hit)
            if m["hit"] is None:
                for px, py in self.pegs:
                    dx, dy = m["x"] - px, m["y"] - py
                    if dx * dx + dy * dy < 13 * 13:
                        ang = math.atan2(dy, dx)
                        m["vx"] = math.cos(ang) * 2.4 + self.rng.uniform(-0.4, 0.4)
                        m["vy"] = abs(math.sin(ang)) * 2.0 + 0.8
                        m["x"] += math.cos(ang) * 3
                        m["y"] += abs(math.sin(ang)) * 2
            else:
                m["vy"] = max(m["vy"], 6.0)
            if m["x"] < 14:
                m["x"] = 14; m["vx"] = abs(m["vx"]) * 0.7
            if m["x"] > PW - 14:
                m["x"] = PW - 14; m["vx"] = -abs(m["vx"]) * 0.7
            # multiplier ledge
            if m["hit"] is None and LEDGE <= m["y"] < LEDGE + LEDGE_H:
                rel = max(0.0, min(0.999, m["x"] / PW))
                si = int(rel * 6)
                m["val"] *= MULTS[si]
                self.slot_hits[si] += 1
                m["hit"] = si
                m["vy"] = abs(m["vy"]) * 0.5 + 1.5
            # items row
            if m["y"] >= ROW:
                # weighted toward middle items early
                it = int(self.rng.choice(5, p=[0.18, 0.22, 0.2, 0.22, 0.18]))
                self.global_items[it] += 1
                self.item_cnt[m["t"], it] += 1
                if it == 3:
                    self.ammo[m["t"]] *= 1.025
                elif it == 2:
                    self.shield[m["t"]] += 8000
                elif it == 1:
                    self.ammo[m["t"]] *= 1.01
                m["alive"] = False
                continue
            if m["y"] > PBOT + 20:
                m["alive"] = False
                continue
            alive.append(m)
        self.marbles = alive[-80:]

    def opening_push(self):
        """First ~2s: expand soft blobs from corners toward center."""
        if self.f > 70:
            return
        t_idx = self.f % self.nt
        grow = int(GS * (0.14 + 0.22 * (self.f / 70.0)))
        self._blob(t_idx, radius=grow)
        # slight organic growth each frame
        if self.f % 3 == 0:
            for t in range(self.nt):
                mask = self.grid == t
                if not mask.any():
                    continue
                # dilate a bit with noise for jagged frontier
                from numpy.lib.stride_tricks import sliding_window_view
                # simple neighbor expand
                up = np.roll(mask, -1, 0); dn = np.roll(mask, 1, 0)
                lf = np.roll(mask, -1, 1); rt = np.roll(mask, 1, 1)
                border = (~mask) & (up | dn | lf | rt) & (self.grid == self.nt)
                noise = self.rng.random((GS, GS))
                self.grid[border & (noise > 0.55)] = t

    def tick(self):
        self.fire_cd = np.maximum(self.fire_cd - 1, 0)
        age = self.f / DEMO_F
        self.phase = 0 if age < 0.30 else 1
        self.opening_push()
        for t in range(self.nt):
            bx, by = self.bases[t]
            if self.f < int(2.2 * FPS):
                self.ang[t] = math.atan2(G / 2 - by, G / 2 - bx)
            else:
                self.ang[t] = (self.ang[t] + self.spin) % (2 * math.pi)
            if self.f >= 8:
                self.fire(t)
        self.tick_projectiles()
        self.tick_marbles()
        ns = []
        for s in self.sparks:
            s[2] -= 1
            if s[2] > 0:
                ns.append(s)
        self.sparks = ns[-500:]
        flat = self.grid.ravel()
        for t in range(self.nt):
            self.share[t] = np.count_nonzero(flat == t) / float(GS * GS)
        self.ammo *= 1.0018
        self.score2 *= 1.0012
        self.shield *= 1.0004
        if self.f > 0 and self.f % 120 == 0:
            self.level = np.minimum(self.level + 1, 9)
        self.f += 1


def build_gradient_map(grid, nt):
    """Soft gradient team fills (core→tip) + navy neutral. Returns GS×GS×3 float."""
    h, w = grid.shape
    out = np.zeros((h, w, 3), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    fx, fy = xx / max(1, w - 1), yy / max(1, h - 1)
    # corner-based sheen per team
    sheens = [
        1.0 - np.sqrt(fx * fx + fy * fy) / 1.42,           # TL
        1.0 - np.sqrt((1 - fx) ** 2 + fy * fy) / 1.42,     # TR
        1.0 - np.sqrt(fx * fx + (1 - fy) ** 2) / 1.42,     # BL
        1.0 - np.sqrt((1 - fx) ** 2 + (1 - fy) ** 2) / 1.42,  # BR
    ]
    for t in range(nt):
        mask = grid == t
        if not mask.any():
            continue
        c0 = np.array(TEAMS[t][1], np.float32)
        c1 = np.array(TEAMS[t][2], np.float32)
        u = np.clip(sheens[t], 0, 1)
        # softer mid tones
        blend = c0 * (0.55 + 0.45 * u[..., None]) + c1 * (0.45 * (1 - u[..., None]))
        # darken slightly toward frontier feel
        out[mask] = blend[mask] * 0.92
    neu = grid == nt
    out[neu] = np.array(NEU, np.float32)
    return out


def frontier_mask(grid, nt):
    g = grid
    fr = np.zeros_like(g, bool)
    for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        shifted = np.roll(np.roll(g, dy, 0), dx, 1)
        fr |= (g < nt) & (shifted != g)
    fr[0, :] = fr[-1, :] = fr[:, 0] = fr[:, -1] = False
    return fr


def render(out_path, seed=7):
    g = Game(seed=seed)
    bg = Image.new("RGB", (W, H), (8, 12, 28))
    d = ImageDraw.Draw(bg)
    # left panel
    d.rounded_rectangle((PX0 - 8, PTOP - 14, PX1 + 8, PBOT + 10), 14,
                        fill=(12, 16, 36), outline=(70, 150, 230), width=2)
    ctext(d, (PX0 + PX1) / 2, PTOP - 8, "弹珠台 · 倍率 / 道具", font(18), (170, 210, 255), 1)
    for px, py in g.pegs + g._visual_lower_pegs():
        d.ellipse((PX0 + px - 3.5, py - 3.5, PX0 + px + 3.5, py + 3.5), fill=(225, 232, 245))
    LEDGE = PTOP + 340
    sw = PW / 6
    for si, mlt in enumerate(MULTS):
        a = PX0 + si * sw
        d.rectangle((a + 2, LEDGE, a + sw - 2, LEDGE + 34),
                    fill=(36, 44, 68), outline=(210, 220, 235), width=1)
        ctext(d, a + sw / 2, LEDGE + 5, f"X{mlt}", font(17, True), (245, 248, 255), 1)
    ROW = PBOT - 92
    iw = PW / 5
    ICOL = [(160, 210, 255), (255, 170, 90), (100, 220, 255), (255, 110, 200), (190, 150, 255)]
    for ii, name in enumerate(ITEMS):
        a = PX0 + ii * iw
        d.rounded_rectangle((a + 3, ROW, a + iw - 3, ROW + 68), 8,
                            fill=(24, 28, 52), outline=ICOL[ii], width=2)
        ctext(d, a + iw / 2, ROW + 6, name, font(15), ICOL[ii], 1)

    bg_np = np.asarray(bg).copy()
    tmp = out_path + ".video.mp4"
    wav = out_path + ".wav"
    # clean stale
    for p in (tmp, wav, out_path):
        if os.path.exists(p) and p != out_path:
            try:
                os.remove(p)
            except OSError:
                pass
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "warning",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "pipe:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
         "-pix_fmt", "yuv420p",
         "-movflags", "frag_keyframe+empty_moov+default_base_moof",
         tmp],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    t0 = time.time()
    # faint grid on display arena
    grid_overlay = np.zeros((G, G, 3), np.float32)
    grid_overlay[::28] += 14
    grid_overlay[:, ::28] += 14

    for fi in range(g.maxf):
        g.tick()
        frame = bg_np.copy()

        # arena fill (low-res → upscale)
        img_s = build_gradient_map(g.grid, g.nt)
        fr_s = frontier_mask(g.grid, g.nt)
        # bright frontier
        img_s[fr_s] = np.minimum(
            img_s[fr_s] * 0.25 + np.array([230, 245, 255], np.float32), 255)
        # upscale nearest for pixel look, then slight blur for soft fills
        small = Image.fromarray(img_s.astype(np.uint8)).resize((G, G), Image.NEAREST)
        soft = small.filter(ImageFilter.GaussianBlur(radius=1.2))
        arena = np.asarray(soft).astype(np.float32)
        # re-sharpen frontier after blur
        fr_big = np.array(
            Image.fromarray((fr_s.astype(np.uint8) * 255)).resize((G, G), Image.NEAREST)
        ) > 128
        arena[fr_big] = np.minimum(
            arena[fr_big] * 0.3 + np.array([235, 250, 255], np.float32), 255)
        arena = np.clip(arena + grid_overlay, 0, 255)
        frame[MY:MY + G, MX:MX + G] = arena.astype(np.uint8)

        im = Image.fromarray(frame)
        # glow bloom on frontier
        if fi % 2 == 0:
            edge = Image.fromarray((fr_big.astype(np.uint8) * 200))
            edge = edge.filter(ImageFilter.GaussianBlur(3))
            ov = Image.new("RGBA", (G, G), (0, 0, 0, 0))
            ov.paste((190, 235, 255, 55), (0, 0), edge)
            arena_rgba = im.crop((MX, MY, MX + G, MY + G)).convert("RGBA")
            arena_rgba = Image.alpha_composite(arena_rgba, ov)
            im.paste(arena_rgba.convert("RGB"), (MX, MY))

        d = ImageDraw.Draw(im)
        # hit counts
        for si in range(6):
            ctext(d, PX0 + si * sw + sw / 2, LEDGE + 38,
                  str(int(g.slot_hits[si])), font(13), (220, 230, 245), 1)
        for ii in range(5):
            ctext(d, PX0 + ii * iw + iw / 2, ROW + 38,
                  str(int(g.global_items[ii])), font(18, True), (255, 255, 255), 1)
        # marbles
        for m in g.marbles:
            if not m["alive"]:
                continue
            X, Y = PX0 + m["x"], m["y"]
            c = TEAMS[m["t"]][1]
            r = 8 + min(18, math.log10(max(10, m["val"])) * 3.2)
            d.ellipse((X - r, Y - r, X + r, Y + r), fill=c, outline=(255, 255, 255), width=2)
            ctext(d, X, Y - 7, fmt_abbr(m["val"]), font(11), (255, 255, 255), 1)

        d.rectangle((MX - 2, MY - 2, MX + G + 1, MY + G + 1), outline=(80, 180, 255), width=2)

        # projectiles — batch dots/beams first, bigs with alpha
        big_list = []
        for i in range(NMAX):
            if not g.palive[i]:
                continue
            t = int(g.ptm[i])
            X, Y = MX + g.px[i], MY + g.py[i]
            kind = int(g.pkind[i])
            c = TEAMS[t][2]
            if kind == 2:
                big_list.append((i, t, X, Y))
            elif kind == 1:
                vx, vy = float(g.pvx[i]), float(g.pvy[i])
                L = 16
                d.line((X - vx * L * 0.15, Y - vy * L * 0.15,
                        X + vx * 0.35, Y + vy * 0.35), fill=c, width=2)
                d.ellipse((X - 2, Y - 2, X + 2, Y + 2), fill=(255, 255, 255))
            else:
                d.ellipse((X - 2.2, Y - 2.2, X + 2.2, Y + 2.2), fill=(255, 255, 255))

        if big_list:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for i, t, X, Y in big_list:
                pop = float(g.pscale[i])
                val = float(g.pval[i])
                rad = min(G / 13, 20 + math.sqrt(val / 1e6) * 11) * max(0.15, pop)
                col = TEAMS[t][1]
                od.ellipse((X - rad, Y - rad, X + rad, Y + rad),
                           fill=(col[0], col[1], col[2], 95),
                           outline=(255, 255, 255, 210), width=3)
            im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
            d = ImageDraw.Draw(im)
            for i, t, X, Y in big_list:
                ctext(d, X, Y - 14, fmt_abbr(g.pval[i]), font(22, True), (255, 255, 255), 1)

        for sx, sy, life, col in g.sparks:
            d.ellipse((MX + sx - 1.8, MY + sy - 1.8, MX + sx + 1.8, MY + sy + 1.8), fill=col)

        # base rings
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for t in range(g.nt):
            bx, by = g.bases[t]
            X, Y = MX + bx, MY + by
            c = TEAMS[t][1]
            pr = PROT_R
            for w, aa in ((pr + 8, 50), (pr + 2, 110), (pr - 10, 60)):
                od.ellipse((X - w, Y - w, X + w, Y + w), outline=(*c, aa + 50), width=3)
            od.ellipse((X - pr, Y - pr, X + pr, Y + pr), fill=(*c, 40))
            ca, sa = math.cos(g.ang[t]), math.sin(g.ang[t])
            od.line((X, Y, X + ca * (pr - 8), Y + sa * (pr - 8)),
                    fill=(255, 255, 255, 230), width=4)
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
        d = ImageDraw.Draw(im)
        for t in range(g.nt):
            bx, by = g.bases[t]
            X, Y = MX + bx, MY + by
            ctext(d, X, Y - 30, fmt_abbr(g.ammo[t]), font(28, True), (255, 255, 255), 2)
            ctext(d, X, Y + 10, fmt_abbr(g.score2[t]), font(14), TEAMS[t][2], 1)
            ctext(d, X, Y + 28, f"🛡{fmt_abbr(g.shield[t])}", font(12), (160, 230, 255), 1)

        # side meters
        def meter(x0, shares_side):
            d.rectangle((x0, MY, x0 + 16, MY + G), fill=(14, 18, 36), outline=(50, 80, 120))
            y = MY + G
            for t in shares_side:
                hgt = max(2, g.share[t] * G)
                d.rectangle((x0 + 1, y - hgt, x0 + 15, y), fill=TEAMS[t][1])
                y -= hgt
            for pct, yy in ((0.25, 0.75), (0.5, 0.5), (0.75, 0.25), (1.0, 0.0)):
                d.text((x0 - 4, MY + G * yy - 6), f"{int(pct * 100)}%",
                       font=font(9), fill=(140, 160, 190))
        meter(MX - 26, [0, 2])  # left: red + blue
        meter(MX + G + 8, [1, 3])  # right: green + orange
        for t, (ox, oy) in enumerate(((0.14, 0.10), (0.86, 0.10), (0.14, 0.90), (0.86, 0.90))):
            ctext(d, MX + G * ox, MY + G * oy, f"{g.share[t] * 100:.1f}%",
                  font(14), TEAMS[t][2], 1)
            bx = MX + G * ox
            by = MY + G * oy + 22
            d.ellipse((bx - 11, by - 11, bx + 11, by + 11),
                      fill=TEAMS[t][1], outline=(255, 255, 255))
            ctext(d, bx, by - 8, str(int(g.level[t])), font(12), (255, 255, 255), 1)

        ctext(d, MX + G / 2, MY - 30, "Douyin 风格复刻 · 成长演示", font(22), (200, 230, 255), 1)
        d.text((MX + 10, MY + 8), f"{fi / FPS:04.1f}s", font=font(16), fill=(180, 200, 230))
        phase = "早期点射" if g.phase == 0 else "中期光束"
        d.text((MX + G - 130, MY + 8), phase, font=font(14), fill=(255, 220, 140))

        if fi < 40:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 150))
            od = ImageDraw.Draw(ov)
            ctext(od, W / 2, H / 2 - 36, "小球领土战争 · 复刻演示", font(46), (220, 240, 255), 2)
            ctext(od, W / 2, H / 2 + 28, "开局四色推角 → 点射 → 霓虹光束", font(24), (180, 210, 240), 1)
            im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")

        try:
            proc.stdin.write(np.asarray(im, dtype=np.uint8).tobytes())
        except BrokenPipeError as e:
            err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
            raise RuntimeError(f"ffmpeg broken pipe at frame {fi}: {err[:800]}") from e
        if fi % 60 == 0:
            print(f"  frame {fi}/{g.maxf} ({fi / FPS:.1f}s) elapsed {time.time() - t0:.1f}s "
                  f"shares={[round(float(s), 3) for s in g.share]} hits={g.slot_hits.tolist()}",
                  flush=True)
        if fi in (45, 150, 300, 450):
            im.save(out_path.replace(".mp4", f"_preview_{fi:03d}.png"))

    proc.stdin.close()
    err_b = proc.stderr.read() if proc.stderr else b""
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg video encode failed rc={rc}: {err_b.decode('utf-8','replace')[:800]}")
    print(f"  video tmp size={os.path.getsize(tmp)}  ffmpeg warn: {err_b.decode('utf-8','replace')[:200]!r}", flush=True)
    # soft ambient pad
    n = int((g.maxf / FPS + 0.4) * 44100)
    t = np.arange(n) / 44100.0
    a = (0.035 * np.sin(2 * np.pi * 82 * t)
         + 0.02 * np.sin(2 * np.pi * 123 * t)) * np.exp(-t / (DEMO_SEC + 1) * 0.25)
    a = a.astype(np.float32)
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes((np.clip(a, -1, 1) * 28000).astype(np.int16).tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-i", wav,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-shortest",
         "-movflags", "+faststart", out_path],
        check=True,
    )
    os.remove(tmp); os.remove(wav)
    print(f"done → {out_path}", flush=True)
    return g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/workspace/side-income/pixel-war/marble_replica_demo.mp4")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    print("rendering Douyin-style replica demo…", flush=True)
    render(args.out, seed=args.seed)
