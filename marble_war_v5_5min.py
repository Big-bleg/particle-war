#!/usr/bin/env python3
"""粒子领地大战 v5 · 5 分钟完整版（自然模拟 + 种子筛选出的故事线）.

复用 marble_war_v5_demo.py 的全部规则（左 Plinko、倍率/传送叠加、四道具、
护盾吸收→HP、威胁优先瞄准、Boss 来袭 + 8× 伤害奖池、白点云、巨慢大球）。
与 10s 演示的区别：
  * 不再脚本化发球 / 不对弹珠施加引导力 / 不强制 Boss 击杀；
  * 每队按固定节奏从顶中发球（公平，同节奏错峰），落点完全由 Pymunk 决定；
  * Boss 固定在 3:00 来袭（唯一事件标记），血量由各队自然输出打掉；
  * 一队存活或 4:50 时按 (HP + 领地) 判胜，显示胜者结算卡；
  * 戏剧性靠 --screen 多种子无头模拟打分挑选，而不是写死剧情。
"""
from __future__ import annotations
import argparse, json, math, sys, time
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw

import marble_war_v5_demo as V
from marble_war_v5_demo import (Demo, FPS, G, NMAX, PROT_R, PAINT_COST, TEAMS,
                                W, H, MX, MY, font, ctext)

V.V_TITLE.t = "粒子领地大战 v5 · 5 分钟完整对局"
V.V_TITLE.sub = "完整对局 · 自然模拟 · 5 分钟"
TOTAL_F = 300 * FPS          # 5:00
BOSS_F = 180 * FPS           # 3:00 Boss 来袭
DECIDE_F = 292 * FPS         # 4:52 decision if >1 alive (knockout usually decides first)
SPAWN_GAP = 84               # frames between drops of one team (~2.8s), staggered
TINY_DRAIN = 0.03            # white dot lifetime ≈ 10/0.03 ≈ 330f → reaches across map
TINY_DMG = 1.0
FOUNTAIN_VX = 12.0           # px/frame horizontal fountain spray (reaches outer 倍率 slots)
_DISK = [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if dx * dx + dy * dy <= 4]


class _NoForce(dict):
    def get(self, k, default=None):
        return None


class FullGame(Demo):
    def __init__(self, seed=1, nt=4, hp=1000.0):
        super().__init__(seed=seed, nt=nt)
        self.maxf = TOTAL_F
        self.boss_f = BOSS_F
        self.boss_force_f = -1                  # natural kill only
        self.tele_next = _NoForce()             # teleport returns un-steered
        self.hp[:] = hp; self.max_hp[:] = hp
        self.winner = None; self.win_f = -1
        self.elim_log = []                      # (frame, victim, killer)
        self.log = []                           # (frame, kind, data) story log
        self.share_hist = []
        self.tips = []
        self.tip("开局集火中央 · 随后顺时针旋转", (200, 220, 255), 90)

    def spawn_marble(self, t, mult=1, vx=0.0, tag="", force=None):
        """Same top-center fountain, wider natural horizontal spray (no steering)."""
        m = V.Marble(t, V.PW / 2 + self.rng.uniform(-10, 10), V.LAYER1_Y + 55 + self.rng.uniform(-8, 8),
                     0.0, 0.0, mult, tag)
        m._force = None
        self._attach_body(m, vx * 0.35 + self.rng.uniform(-FOUNTAIN_VX, FOUNTAIN_VX), self.rng.uniform(-5.2, -3.4))
        self.marbles.append(m)
        return m

    def _build_spawn_plan(self):
        return []                               # no scripted drops

    # natural drops ------------------------------------------------------
    def tick_marbles(self, ev):
        for t in range(self.nt):
            if self.alive_t[t] and self.f >= 10 and (self.f - 10 - t * (SPAWN_GAP // self.nt)) % SPAWN_GAP == 0:
                self.spawn_marble(t, max(1, int(self.mult_bonus[t])), self.rng.uniform(-0.6, 0.6),
                                  tag=f"n{self.f}_{t}", force=None)
        # drop marbles of dead teams
        for m in self.marbles:
            if m.alive and not self.alive_t[m.t]:
                self._detach_body(m); m.alive = False; m.state = "done"
        super().tick_marbles(ev)

    # vectorized threat scan ---------------------------------------------
    def threat_target(self, t):
        if not self.alive_t[t]:
            return None
        m = self.palive & (self.ptm != t)
        idx = np.nonzero(m)[0]
        if idx.size == 0:
            return None
        src = self.ptm[idx].astype(int)
        idx = idx[self.alive_t[src]]
        if idx.size == 0:
            return None
        bx, by = self.bases[t]
        px, py = self.px[idx], self.py[idx]
        dx, dy = bx - px, by - py
        dist = np.hypot(dx, dy) + 1e-3
        vx, vy = self.pvx[idx], self.pvy[idx]
        spd = np.hypot(vx, vy) + 1e-6
        appr = (vx * dx + vy * dy) / (spd * dist)
        power = np.where(self.ppow[idx], self.pval[idx], 3.0)
        power = np.where(self.pkind[idx] == 2, power * 4.0, power)
        sc = power * (180.0 / dist) * np.maximum(0.2, appr)
        sc = np.where(dist < PROT_R * 2.2, sc * 3.0, sc)
        sc = np.where((appr < 0.15) | (dist > PROT_R * 4.0), 0.0, sc)
        k = int(np.argmax(sc))
        if sc[k] <= 0:
            return None
        return (float(px[k]), float(py[k]), float(dist[k]), float(power[k]))

    # vectorized white dots, parent loop for numbered balls ----------------
    def tick_projectiles(self, ev=None):
        if ev is None:
            ev = []
        nt = self.nt
        tiny = self.palive & (~self.ppow) & (self.pkind == 0)
        idx = np.nonzero(tiny)[0]
        if idx.size:
            tm = self.ptm[idx].astype(int)
            dead = ~self.alive_t[tm]
            self.palive[idx[dead]] = False
            idx = idx[~dead]; tm = tm[~dead]
        if idx.size:
            self.px[idx] += self.pvx[idx]; self.py[idx] += self.pvy[idx]
            for P, Vv in ((self.px, self.pvx), (self.py, self.pvy)):
                o = (P[idx] < 1) | (P[idx] >= G - 1)
                Vv[idx[o]] *= -1
                P[idx] = np.clip(P[idx], 1.0, G - 1.5)
            x, y = self.px[idx], self.py[idx]
            hit = np.zeros(idx.size, bool)
            for ob in range(nt):
                if not self.alive_t[ob]:
                    continue
                d2 = (x - self.bases[ob, 0]) ** 2 + (y - self.bases[ob, 1]) ** 2
                h = (d2 < PROT_R * PROT_R) & (tm != ob) & ~hit
                if h.any():
                    cnt = np.bincount(tm[h], minlength=nt)
                    for att in range(nt):
                        if cnt[att]:
                            self.apply_base_damage(ob, TINY_DMG * cnt[att], att, ev)
                    hit |= h
            self.palive[idx[hit]] = False
            keep = ~hit
            idx, tm, x, y = idx[keep], tm[keep], x[keep], y[keep]
            ix = x.astype(int); iy = y.astype(int)
            if self.boss is not None and self.boss["hp"] > 0:
                bm = self.grid[iy, ix] == nt + 1
                if bm.any():
                    np.add.at(self.boss_dmg, tm[bm], 1.5)
                    self.pval[idx[bm]] -= 1.5
                    for tt in np.unique(tm[bm])[:2]:
                        self._float_boss(int(tt), 6.0)
            for dx, dy in _DISK:
                xx = np.clip(ix + dx, 0, G - 1); yy = np.clip(iy + dy, 0, G - 1)
                o = self.grid[yy, xx]
                foe = (o < nt) & (o != tm)
                paint = (o == nt) | foe
                self.grid[yy[paint], xx[paint]] = tm[paint].astype(np.int8)
                self.pval[idx[foe]] -= PAINT_COST
            self.pval[idx] -= TINY_DRAIN
            self.palive[idx[self.pval[idx] <= 0]] = False
        # numbered balls via parent (hide tiny temporarily)
        tiny = self.palive & (~self.ppow) & (self.pkind == 0)
        self.palive[tiny] = False
        try:
            super().tick_projectiles(ev)
        finally:
            self.palive[tiny] = True

    def _kill_team(self, victim, killer, ev):
        was = self.alive_t[victim]
        super()._kill_team(victim, killer, ev)
        if was and not self.alive_t[victim]:
            self.elim_log.append((self.f, victim, killer))
            self.log.append((self.f, "elim", (TEAMS[victim][0], TEAMS[killer][0], int(self.shield_hp[victim]))))

    def tick(self):
        ev = super().tick()
        for e in ev:
            if e[0] in ("boss", "bkill", "skill", "tele", "mult"):
                self.log.append((self.f - 1, e[0], tuple(str(x) for x in e[1:])))
        if self.f % FPS == 0:
            self.share_hist.append((self.f, self.share.copy(), self.hp.copy()))
        alive = np.nonzero(self.alive_t)[0]
        if self.winner is None and (len(alive) == 1 or self.f >= DECIDE_F):
            sc = [(self.hp[t] + self.share[t] * 2000.0) if self.alive_t[t] else -1 for t in range(self.nt)]
            self.winner = int(np.argmax(sc)); self.win_f = self.f
            self.log.append((self.f, "win", (TEAMS[self.winner][0],)))
            self.banner = (f"{TEAMS[self.winner][0]} 获胜", TEAMS[self.winner][1], 9999)
        return ev


# ---------------------------------------------------------------- screening
def simulate(seed, nt=4):
    g = FullGame(seed=seed, nt=nt)
    for _ in range(TOTAL_F):
        g.tick()
        if g.winner is not None and g.f > g.win_f + 30:
            break
    sh = np.array([s for _, s, _ in g.share_hist])        # per-second shares
    leaders = sh.argmax(1) if len(sh) else np.array([0])
    lead_changes = int((np.diff(leaders) != 0).sum())
    # underdog comeback: last at 1:30 but top-2 (alive) at end
    under = int(np.argmin(sh[min(90, len(sh) - 1)]))
    final_rank = np.argsort(-sh[-1])
    comeback = bool(g.alive_t[under] and under in final_rank[:2])
    elim_f = [f for f, _, _ in g.elim_log]
    bkill = [f for f, k, _ in g.log if k == "bkill"]
    big8 = sum(1 for f, k, d in g.log if k == "mult" and d[1] == "8")
    tele = sum(1 for f, k, d in g.log if k == "tele")
    shields = sum(1 for f, k, d in g.log if k == "skill" and d[1] == "护盾")
    score = 0.0
    score += min(lead_changes, 12) * 1.0
    score += 6 if comeback else 0
    score += 8 if bkill and bkill[0] < BOSS_F + 40 * FPS else 0
    late = [f for f in elim_f if f > 200 * FPS]
    score += 8 if late else 0
    score -= 6 * sum(1 for f in elim_f if f < 150 * FPS)
    score += 10 if g.win_f >= 265 * FPS else 0
    score += min(big8, 6) + min(tele, 6) * 0.5
    return dict(seed=seed, score=round(score, 1), win=TEAMS[g.winner][0] if g.winner is not None else None,
                win_s=round(g.win_f / FPS, 1), elims=[(round(f / FPS, 1), TEAMS[v][0], TEAMS[k][0]) for f, v, k in g.elim_log],
                bkill_s=[round(f / FPS, 1) for f in bkill], lead_changes=lead_changes, comeback=comeback,
                underdog=TEAMS[under][0], big8=big8, tele=tele, shields=shields,
                hp=[int(h) for h in g.hp], share=[round(float(s), 3) for s in g.share])


# ---------------------------------------------------------------- end card
def post_draw(g, im, fi):
    if g.winner is None:
        return im
    age = fi - g.win_f
    if age < 0:
        return im
    a = min(1.0, age / 30.0)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, int(170 * a)))
    od = ImageDraw.Draw(ov)
    c = TEAMS[g.winner][1]
    ctext(od, W / 2, H / 2 - 150, "★ 胜者 ★", font(46), (255, 240, 200), 3)
    ctext(od, W / 2, H / 2 - 80, f"{TEAMS[g.winner][0]} 获胜", font(96), c, 4)
    y = H / 2 + 60
    order = sorted(range(g.nt), key=lambda t: -(g.hp[t] + g.share[t] * 2000 if g.alive_t[t] else -1))
    for r, t in enumerate(order):
        st = f"HP {int(g.hp[t])}" if g.alive_t[t] else "阵亡"
        ctext(od, W / 2, y + r * 44, f"{r + 1}. {TEAMS[t][0]}  领地 {g.share[t] * 100:.0f}%  {st}",
              font(30), TEAMS[t][1], 2)
    return Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", type=str, default="")      # e.g. 1-16
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="/workspace/side-income/pixel-war/marble_v5_5min.mp4")
    ap.add_argument("--crf", type=int, default=26)
    args = ap.parse_args()
    if args.screen:
        a, b = map(int, args.screen.split("-"))
        with Pool(6) as pool:
            for r in pool.imap_unordered(simulate, range(a, b + 1)):
                print(json.dumps(r, ensure_ascii=False), flush=True)
        return
    g = FullGame(seed=args.seed)
    snaps = {int(s * FPS): f"{i:02d}" for i, s in enumerate([8, 40, 90, 150, 182, 200, 240, 275, 295])}
    V.render(args.out, args.out.replace(".mp4", "_preview"), demo=g, crf=args.crf,
             snap_at=snaps, post_draw=post_draw, log_every=300)
    with open(args.out.replace(".mp4", "_story.json"), "w") as f:
        json.dump([(round(fr / FPS, 1), k, d) for fr, k, d in g.log if k not in ("mult",) or d[1] in ("8",)],
                  f, ensure_ascii=False, indent=0)
    print("story saved", flush=True)


if __name__ == "__main__":
    main()
