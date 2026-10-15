"""Game rules (ported from web-game/js/game.js) - deterministic given a seed."""
import math
import numpy as np
from .config import (G, GS, S, WS, NEUTRAL, BASES, BASE_R, MATCH, TAU, fmt, clamp)
from . import kernels as K
from .board import Board

MAXB = 9000


class BigBall:
    __slots__ = ('team', 'x', 'y', 'vx', 'vy', 'value', 'v0', 'age', 'hit_cd', 'trail', 'alive')

    def __init__(self, team, x, y, a, value):
        self.team, self.x, self.y = team, x, y
        self.vx, self.vy = math.cos(a) * 1.8, math.sin(a) * 1.8
        self.value = self.v0 = value
        self.age = 0.0; self.hit_cd = 0.0; self.trail = []; self.alive = True

    @property
    def rr(self):
        return clamp(84 + math.sqrt(self.value / 1e6) * 26, 84, 150) / WS


class Game:
    def __init__(self, seed=1, player=0, match=MATCH):
        self.seed = seed
        self.k = match / MATCH          # pacing scale: 300 s preset compresses every pacing timer by 300/660
        self.rng = np.random.default_rng(seed)
        self.player = player
        self.t = 0.0; self.frame = 0
        self.over = False; self.winner = -1
        self.grid = np.full(GS * GS, NEUTRAL, np.uint8)
        self.heat = np.zeros(GS * GS, np.float32)
        self.share = [0.0] * 4
        self.hp = [8e6] * 4
        self.ammo = [249968.0] * 4
        self.dead = [False] * 4
        self.power = [float(self.rng.uniform(.8, 1.25)) for _ in range(4)]
        self.power_clock = 0.0
        self.spin = [float((-1 if self.rng.random() < .5 else 1) * self.rng.uniform(.45, .7)) for _ in range(4)]
        self.aim = [math.atan2(G / 2 - by, G / 2 - bx) for bx, by in BASES]
        self.lock = [None] * 4
        self.cool = [0.0] * 4
        self.emit_acc = [0.0] * 4
        self.mg = [0.0] * 4
        self.items = [[0] * 5 for _ in range(4)]
        self.item_total = [0] * 5
        self.opened = False; self.opening = None; self.burst = None
        self.lasers = []; self.snipers = []; self.sparks = []; self.floaters = []; self.events = []; self.waves = []
        self.last_storm = {}
        self.balls = []
        # bullet SoA
        self.n = 0
        self.bx = np.zeros(MAXB); self.by = np.zeros(MAXB); self.bvx = np.zeros(MAXB); self.bvy = np.zeros(MAXB)
        self.bteam = np.zeros(MAXB, np.int8); self.bkind = np.zeros(MAXB, np.int8); self.bbounce = np.zeros(MAXB, np.int8)
        self._alive = np.zeros(MAXB, np.int8)
        self._occ_t = np.zeros(GS * GS, np.int8); self._occ_i = np.zeros(GS * GS, np.int32); self._occ_s = np.zeros(GS * GS, np.int32)
        self._dead = np.zeros(4, np.int8); self._dmg = np.zeros(4); self._paints = np.zeros(4, np.int64); self._cnt = np.zeros(4, np.int64)
        self.board = Board(self)

    @property
    def tp(self):
        """pacing time on the 660 s reference timeline"""
        return self.t / self.k

    # ---- helpers ------------------------------------------------------------
    def U(self, a, b):
        return float(self.rng.uniform(a, b))

    def alive_teams(self):
        return [t for t in range(4) if not self.dead[t]]

    def floater(self, x, y, text, team, life=1.6):
        self.floaters.append(dict(x=x, y=y, text=text, team=team, life=life, max=life))

    def burst_sparks(self, x, y, team, n, vmax, life=1.4):
        for _ in range(n):
            a = self.U(0, TAU); v = self.U(40, vmax)
            self.sparks.append([x, y, math.cos(a) * v, math.sin(a) * v, life, team])

    # ---- economy -----------------------------------------------------------
    def award(self, team, slot, value):
        from .config import MULT
        v = value * MULT[slot]
        self.ammo[team] = min(999e6, self.ammo[team] + v * .004 * (1 + self.tp / 90))

    def give_item(self, team, it):
        self.items[team][it] = min(99, self.items[team][it] + 1)
        self.item_total[it] += 1

    def late_k(self, b):
        """Staggered eliminations: weakest alive base ramps after ~7:10/8:40/10:10; all non-leaders after 10:15."""
        al = self.alive_teams()
        if len(al) <= 1:
            return 1.0
        T = [430, 520, 610][min(2, 4 - len(al))]
        weak = min(al, key=lambda t: self.share[t] + self.hp[t] / 4e7)
        lead = max(al, key=lambda t: self.share[t])
        k = 1.0
        if b == weak and self.tp > T:
            x = (self.tp - T) / 20; k = 1 + x * x * 4
        if self.tp > 615 and b != lead:
            x = (self.tp - 615) / 6; k = max(k, 1 + x * x * 20)
        return k

    def hit_base(self, b, dmg):
        if self.dead[b]:
            return
        self.hp[b] = max(0.0, self.hp[b] - dmg)
        if self.hp[b] <= 0:
            self.dead[b] = True; self.ammo[b] = 0; self.lock[b] = None
            bx, by = BASES[b]
            self.burst_sparks(bx, by, b, 160, 520, 2.0)
            self.events.append((self.t, 'eliminated', b))

    # ---- weapons -----------------------------------------------------------
    def emit(self, team, count, kind, speed, half_spread, jitter_t=0.0, ang=None):
        """Add `count` bullets; each gets a random sub-tick age so a stream is continuous (no puffs)."""
        bxs, bys = BASES[team]
        a0 = self.aim[team] if ang is None else ang
        for _ in range(count):
            if self.n >= MAXB:
                return
            # triangular distribution: dense core, soft edge
            a = a0 + (self.U(-half_spread, half_spread) + self.U(-half_spread, half_spread)) * .5
            v = self.U(speed * .9, speed * 1.12)
            sub = self.U(0, 1) * jitter_t * 60
            i = self.n
            self.bx[i] = bxs + math.cos(a) * (10 + v * sub); self.by[i] = bys + math.sin(a) * (10 + v * sub)
            self.bvx[i] = math.cos(a) * v; self.bvy[i] = math.sin(a) * v
            self.bteam[i] = team; self.bkind[i] = kind; self.bbounce[i] = 0
            self.n += 1

    def use(self, team, i):
        bag = self.items[team]
        if bag[i] <= 0 or self.dead[team] or (i == 3 and self.tp < 45):
            return False
        if i == 3 and len(self.balls) >= (2 if self.tp > 420 else 1):
            return False
        bag[i] -= 1
        self.events.append((self.t, 'use', team, i))
        a = self.aim[team]; bx, by = BASES[team]
        if i == 0:                                   # 散弹: 90 normal bullets fanned over ±12.5° around the barrel
            # 25° cone, symmetric ±12.5° around the barrel: big burst of NORMAL bullets (same kind/speed/rules as the stream)
            age = self.tp / MATCH
            kind, speed = (0, 4.2) if age < .12 else (1, 5.0) if age < .75 else (4, 4.6)
            n, half = 90, math.radians(12.5)
            bxs, bys = BASES[team]
            for k in range(n):
                if self.n >= MAXB:
                    break
                ang = a - half + 2 * half * (k + self.U(.15, .85)) / n
                v = self.U(speed * .9, speed * 1.12)
                i = self.n
                self.bx[i] = bxs + math.cos(ang) * 10; self.by[i] = bys + math.sin(ang) * 10
                self.bvx[i] = math.cos(ang) * v; self.bvy[i] = math.sin(ang) * v
                self.bteam[i] = team; self.bkind[i] = kind; self.bbounce[i] = 0
                self.n += 1
            self.shotgun_fx = (team, self.t, a)
            self.events.append((self.t, 'shotgun', team))
        elif i == 1:                                 # 机枪: rapid straight stream for 2.5 s
            self.mg[team] = 3.0
            self.events.append((self.t, 'machinegun', team))
        elif i == 2:                                 # 护盾: adds HP, "+20K" floater
            add = round(2e4 * 2 ** min(4, int(self.tp / 90)))
            self.hp[team] = min(16e6, self.hp[team] + add)
            self.floater(bx, by - 30, '+' + fmt(add), team)
        elif i == 3:                                 # 大球
            v = 2 ** min(23, 17 + int(self.U(0, 2.5) + self.tp / 90))
            self.balls.append(BigBall(team, bx + math.cos(a) * 30, by + math.sin(a) * 30, a, v))
            self.ammo[team] += 2e5
            self.events.append((self.t, 'bigball', team))
        elif i == 4:                                 # 狙击: instant beam painting a solid line to the edge
            # a single big, fast piercing round: flies ~2400 px/s, paints a solid line behind it, chips every enemy shield it crosses
            self.snipers.append(dict(team=team, x=bx + math.cos(a) * 40, y=by + math.sin(a) * 40, vx=math.cos(a) * 1500, vy=math.sin(a) * 1500,
                                     x0=bx, y0=by, hit=set(), done=False, fade=0.0))
            self.events.append((self.t, 'sniper', team))
        return True

    # ---- main tick ---------------------------------------------------------
    def tick(self, dt):
        # after the result the match keeps animating (winner keeps painting, marbles keep falling); the result is frozen
        self.t += dt; self.frame += 1
        rng = self.rng
        # turret aim: centre during opening; then sweep + snap-lock onto enemy big balls
        for t in range(4):
            bx, by = BASES[t]
            if not self.opened:
                self.aim[t] = math.atan2(G / 2 - by, G / 2 - bx); continue
            if (self.frame + t) % 3 == 0:
                best, bd = None, G * .5
                for q in self.balls:
                    if q.team == t:
                        continue
                    d = math.hypot(q.x - bx, q.y - by)
                    if d < bd:
                        bd, best = d, q
                self.lock[t] = best
            L = self.lock[t]
            if L is not None and L.alive:
                want = math.atan2(L.y - by, L.x - bx)
                da = (want - self.aim[t] + math.pi * 3) % TAU - math.pi
                self.aim[t] += clamp(da, -9 * dt, 9 * dt)
            else:
                self.aim[t] += self.spin[t] * dt
            self.aim[t] = (self.aim[t] + math.pi) % TAU - math.pi
        # firing: continuous stream (constant bullets/s), cadence clock only drives AI item decisions
        if self.opened:
            age = self.tp / MATCH
            kind, speed = (0, 4.2) if age < .12 else (1, 5.0) if age < .75 else (4, 4.6)
            for t in range(4):
                if self.dead[t]:
                    continue
                band = (.3 if self.share[t] > .29 else .65 if self.share[t] > .24 else 1.4 if self.share[t] < .18 else 1.0) if self.tp < 420 else 1.0
                rate = clamp(.11 - self.tp * .0001, .04, .11) / (self.power[t] * band)
                nvol = 18 if self.tp < 12 else 24 if self.tp < 50 else 32
                bps = nvol / (rate * .875)
                if self.ammo[t] >= 800:
                    self.emit_acc[t] += bps * dt
                    n = int(self.emit_acc[t]); self.emit_acc[t] -= n
                    if n:
                        self.ammo[t] = max(0.0, self.ammo[t] - n * 22)
                        self.emit(t, n, kind, speed, .063, dt)
                if self.mg[t] > 0:
                    self.mg[t] -= dt
                    self.emit(t, 9, 7, 7.5, .014, dt)          # machine gun: dense, fast, tight (kind 7, normal paint rules)
                self.cool[t] -= dt
                if self.cool[t] <= 0:
                    self.cool[t] = rate * self.U(.7, 1.05)
                    p = (.002 if self.tp < 40 else .02 if self.tp < 120 else .06) * self.power[t]
                    if rng.random() < p and any(v > 0 for v in self.items[t]):
                        self.use(t, next(i for i, v in enumerate(self.items[t]) if v > 0))
        # opening: four sniper rounds paint lines to the centre and burst
        if not self.opened:
            if self.opening is None and self.t > .5:
                self.opening = []
                for t, (bx, by) in enumerate(BASES):
                    a = math.atan2(G / 2 - by, G / 2 - bx)
                    self.opening.append(dict(t=t, x=bx + math.cos(a) * 30, y=by + math.sin(a) * 30, vx=math.cos(a) * 360, vy=math.sin(a) * 360))
            if self.opening:
                for o in self.opening:
                    x0, y0 = o['x'], o['y']
                    o['x'] += o['vx'] * dt; o['y'] += o['vy'] * dt
                    K.paint_line(self.grid, self.heat, x0, y0, o['x'], o['y'], o['t'], S * 2.6)
                o = self.opening[0]
                if math.hypot(o['x'] - G / 2, o['y'] - G / 2) < 14:
                    for t in range(4):
                        self.burst_sparks(G / 2, G / 2, t, 40, 420, 1.6)
                        for _ in range(9):
                            a = math.atan2(BASES[t][1] - G / 2, BASES[t][0] - G / 2) + self.U(-1.1, 1.1); Ln = self.U(50, 170)
                            d = 12.0
                            while d < Ln:
                                K.paint_solid(self.grid, self.heat, G / 2 + math.cos(a) * d, G / 2 + math.sin(a) * d, t, S * (1.6 - d / Ln))
                                d += S
                    self.burst = dict(t=self.t, life=2.0); self.opened = True; self.opening = None
        if self.burst:
            self.burst['life'] -= dt
            if self.burst['life'] <= 0:
                self.burst = None
        self.board.tick(dt)
        # power drift / late leader boosts
        self.power_clock += dt
        if self.power_clock > 6:
            self.power_clock = 0
            lo, hi = (.75, 1.3) if self.tp < 90 else (.35, 1.9)
            for t in range(4):
                self.power[t] = clamp(self.power[t] * self.U(.8, 1.25), lo, hi)
            if self.tp > 420:
                lead = int(np.argmax(self.share)); last = int(np.argmin(self.share))
                self.power[lead] = min(1.6, self.power[lead] * 1.05); self.power[last] = min(1.9, self.power[last] * 1.2)
        # heat decay (paint glow)
        if self.frame % 15 == 0:
            K.decay_heat(self.heat, .8 if self.t > 20 else .96)
        # late flood waves + extra big balls
        if self.tp > 440:
            al = self.alive_teams()
            lead = max(al, key=lambda t: self.share[t])
            if not any(w['team'] == lead for w in self.waves) and self.tp - self.last_storm.get(lead, -99) > 9:
                self.last_storm[lead] = self.tp
                bx, by = BASES[lead]
                self.waves.append(dict(team=lead, r=90.0, a=math.atan2(G / 2 - by, G / 2 - bx) + self.U(-.25, .25), half=.9, sp=170.0, life=0.0))
            if rng.random() < dt * .08 and len(self.balls) < 2:
                t = al[int(rng.integers(0, len(al)))]
                self.items[t][3] += 1; self.use(t, 3)
        for w in self.waves:
            w['r'] += w['sp'] * dt; w['life'] += dt
            bx, by = BASES[w['team']]
            K.wave_paint(self.grid, self.heat, bx, by, w['r'], w['a'], w['half'], w['team'])
        self.waves = [w for w in self.waves if w['r'] < 820 and w['life'] < 8 and not self.dead[w['team']]]
        # big balls: brushes that paint, erode over enemy paint, trade 1:1 with shields
        for p in self.balls:
            rr = p.rr
            p.x += p.vx * 60 * dt; p.y += p.vy * 60 * dt; p.age += dt
            gx, gy = int(clamp(p.x / S, 0, GS - 1)), int(clamp(p.y / S, 0, GS - 1))
            ow = self.grid[gy * GS + gx]
            if ow != NEUTRAL and ow != p.team:
                p.value *= math.exp(-.95 * dt)
            m = rr * .6
            if p.x < m: p.x = m; p.vx = abs(p.vx)
            if p.x > G - m: p.x = G - m; p.vx = -abs(p.vx)
            if p.y < m: p.y = m; p.vy = abs(p.vy)
            if p.y > G - m: p.y = G - m; p.vy = -abs(p.vy)
            p.hit_cd = max(0.0, p.hit_cd - dt)
            for b in range(4):
                if b == p.team or self.dead[b]:
                    continue
                bx, by = BASES[b]; dx, dy = p.x - bx, p.y - by; d = math.hypot(dx, dy) or 1; R0 = 92 / WS + rr * .8
                if d < R0:
                    nx, ny = dx / d, dy / d; vn = p.vx * nx + p.vy * ny
                    p.x, p.y = bx + nx * R0, by + ny * R0
                    if vn < 0:
                        p.vx -= 2 * vn * nx; p.vy -= 2 * vn * ny
                    if p.hit_cd <= 0:
                        dd = min(p.value, self.hp[b]) * .81
                        p.value -= dd; self.hit_base(b, dd * self.late_k(b)); p.hit_cd = .6
                        self.events.append((self.t, 'ballHit', p.team, b, dd))
                        self.burst_sparks(bx + nx * 92 / WS, by + ny * 92 / WS, b, 30, 260, 1.0)
            for b in range(4):
                if b != p.team and self.lock[b] is p and not self.dead[b]:
                    p.value -= 5.5e5 * dt
            p.trail.append((p.x, p.y))
            if len(p.trail) > 260:
                p.trail.pop(0)
            if p.value < 5e4 or p.age > 22:
                p.alive = False
                continue
            K.paint_solid(self.grid, self.heat, p.x, p.y, p.team, rr * .95)
            p.value *= .97 ** dt
        self.balls = [p for p in self.balls if p.alive]
        # bullets
        if self.n:
            order = rng.permutation(self.n).astype(np.int64)
            for t in range(4):
                self._dead[t] = 1 if self.dead[t] else 0
            self._dmg[:] = 0
            self.n = K.step_bullets(self.n, self.bx, self.by, self.bvx, self.bvy, self.bteam, self.bkind, self.bbounce, order,
                                    self.grid, self.heat, self._dead, self._dmg, self._paints, self._occ_t, self._occ_i, self._occ_s,
                                    self.frame, dt, self._alive)
            for b in range(4):
                if self._dmg[b] > 0:
                    self.hit_base(b, self._dmg[b] * 1500 * self.late_k(b))
        # fx lifetimes
        for sn in self.snipers:
            if sn['done']:
                sn['fade'] += dt
                continue
            x0, y0 = sn['x'], sn['y']
            sn['x'] += sn['vx'] * dt; sn['y'] += sn['vy'] * dt
            out = not (0 <= sn['x'] <= G and 0 <= sn['y'] <= G)
            xe, ye = clamp(sn['x'], 0, G), clamp(sn['y'], 0, G)
            K.paint_line(self.grid, self.heat, x0, y0, xe, ye, sn['team'], S * 2.4)
            for b in range(4):
                if b != sn['team'] and not self.dead[b] and b not in sn['hit']:
                    bx2, by2 = BASES[b]
                    if math.hypot(xe - bx2, ye - by2) < BASE_R:
                        sn['hit'].add(b); self.hit_base(b, 3e5 * self.late_k(b)); self.burst_sparks(xe, ye, b, 40, 300, 1.0)
            if out:
                sn['done'] = True; sn['x'], sn['y'] = xe, ye
                self.burst_sparks(xe, ye, sn['team'], 30, 260, .9)
        self.snipers = [sn for sn in self.snipers if sn['fade'] < .6]
        for L in self.lasers:
            L['life'] -= dt
        self.lasers = [L for L in self.lasers if L['life'] > 0]
        for f in self.floaters:
            f['life'] -= dt
        self.floaters = [f for f in self.floaters if f['life'] > 0][-12:]
        sp = []
        for s in self.sparks:
            s[0] += s[2] * dt; s[1] += s[3] * dt; s[2] *= .985; s[3] *= .985; s[4] -= dt * .7
            if s[4] > 0:
                sp.append(s)
        self.sparks = sp[-1200:]
        # shares, economy, sudden death, end
        K.count_share(self.grid, self._cnt)
        self.share = [float(c) / (GS * GS) for c in self._cnt]
        for t in range(4):
            if self.dead[t]:
                continue
            if self.tp > 615:
                al = self.alive_teams(); lead = max(al, key=lambda q: self.share[q])
                if len(al) > 1 and t != lead:
                    self.hit_base(t, dt / self.k * (self.tp - 615) * 1.5e5)        # sudden death -> survivor by ~10:50
            if not self.dead[t]:
                self.ammo[t] = min(3e6, self.ammo[t] + dt / self.k * (400 + self.share[t] * 8000) * self.power[t])
        al = self.alive_teams()
        if self.over:
            return
        if len(al) == 1:
            self.winner = al[0]; self.over = True
        elif self.tp >= MATCH:
            self.winner = max(al, key=lambda t: self.share[t]); self.over = True
