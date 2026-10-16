"""Measure whether each natural item cast has a visible, causal effect.

Usage: python3 tools/effect_visibility_check.py [seed[,seed...]] [seconds]

For each successful cast, two deep copies are made at the end of its tick. One
keeps the cast; the other has only that cast's state change removed. Both then
advance deterministically for the item's observation window. The check reports
the extra territory and enemy shield damage caused by the cast, alongside
item-specific direct measures.
"""
import copy
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from war4balls.config import BASES, DT, ITEM_NAMES, MATCH, fmt
from war4balls import kernels as K
from war4balls.sim import Game


WINDOW = 90.0
ITEM_WINDOWS = {0: 3.0, 1: 3.0, 2: 2.0, 3: 15.0, 4: 3.0}
THRESHOLDS = {
    0: "shotgun: >=90 cast bullets in the 25-degree cone, plus >=150 extra cells or >=90 live tracers with a visible fan",
    1: "machinegun: >=400 extra MG rounds, >=400 extra cells, or enemy shield damage",
    2: "shield: >=1% HP, changed HUD text, and >=1.5s shield FX",
    3: "bigball: alive >=8s and (enemy shield trade, >=1500 extra cells, or >=600px visible travel)",
    4: "sniper: aimed toward an enemy and (>=300 extra cells, enemy shield damage, or >=300px visible flight)",
}


def angle_delta(a, b):
    return (a - b + math.pi) % math.tau - math.pi


def target_angle(team, alive):
    bx, by = BASES[team]
    candidates = [q for q in range(4) if q != team and not alive[q]]
    if not candidates:
        candidates = [q for q in range(4) if q != team]
    target = min(candidates, key=lambda q: math.hypot(BASES[q][0] - bx, BASES[q][1] - by))
    ex, ey = BASES[target]
    return math.atan2(ey - by, ex - bx), target


def strip_cast(g, meta):
    """Undo one successful cast in a post-tick copy."""
    team, item = meta["team"], meta["item"]
    if item == 0:
        if "bullet_marker" in meta:
            keep = g.bkind[:g.n] != meta["bullet_marker"]
            kept = int(np.count_nonzero(keep))
            for name in ("bx", "by", "bvx", "bvy", "bteam", "bkind", "bbounce"):
                arr = getattr(g, name)
                arr[:kept] = arr[:g.n][keep].copy()
            g.n = kept
        if isinstance(getattr(g, "shotgun_fx", None), list):
            del g.shotgun_fx[meta["shotgun_fx_before"]:meta["shotgun_fx_after"]]
        elif meta["shotgun_fx_before_value"] is None:
            if hasattr(g, "shotgun_fx"):
                del g.shotgun_fx
        else:
            g.shotgun_fx = meta["shotgun_fx_before_value"]
    elif item == 1:
        g.mg[team] = meta["mg_before"]
        g.mg_emit_acc[team] = meta["mg_emit_before"]
    elif item == 2:
        g.hp[team] = meta["hp_before"]
        del g.floaters[meta["floaters_before"]:meta["floaters_after"]]
        if hasattr(g, "shield_fx"):
            del g.shield_fx[meta["shield_fx_before"]:meta["shield_fx_after"]]
    elif item == 3:
        ball = find_cast_ball(g, meta)
        if ball is not None:
            g.balls.remove(ball)
        g.ammo[team] = meta["ammo_before"]
    elif item == 4:
        sniper = find_cast_sniper(g, meta)
        if sniper is not None:
            g.snipers.remove(sniper)
    g.aim[team] = meta["aim_before"]
    if hasattr(g, "aim_hold"):
        g.aim_hold[team] = meta["aim_hold_before"]
    g.item_total[item] = meta["item_total_before"]


def count_team_cells(g, team):
    return int(np.count_nonzero(g.grid == team))


def find_cast_ball(g, meta):
    candidates = [p for p in g.balls if p.team == meta["team"] and
                  math.isclose(p.v0, meta["ball_value"], rel_tol=1e-9, abs_tol=1e-6)]
    if not candidates:
        return None
    return min(candidates, key=lambda p: math.hypot(p.x - meta["ball_x"], p.y - meta["ball_y"]))


def find_cast_sniper(g, meta):
    candidates = [s for s in g.snipers if s["team"] == meta["team"]]
    if not candidates:
        return None
    return min(candidates, key=lambda s: math.hypot(s["x0"] - meta["sniper_x0"],
                                                    s["y0"] - meta["sniper_y0"]))


def measure_cast(post, meta):
    with_cast = copy.deepcopy(post)
    without_cast = copy.deepcopy(post)
    strip_cast(without_cast, meta)
    focus_ball = find_cast_ball(with_cast, meta) if meta["item"] == 3 else None
    focus_sniper = find_cast_sniper(with_cast, meta) if meta["item"] == 4 else None
    team = meta["team"]
    window = ITEM_WINDOWS[meta["item"]]
    mg_rounds = [0, 0]

    def count_mg_rounds(game, slot):
        original_emit = game.emit

        def emit(team_arg, count, kind, speed, half_spread, jitter_t=0.0, ang=None):
            before_n = game.n
            result = original_emit(team_arg, count, kind, speed, half_spread, jitter_t, ang)
            if kind == 7:
                mg_rounds[slot] += game.n - before_n
            return result

        game.emit = emit

    count_mg_rounds(with_cast, 0)
    count_mg_rounds(without_cast, 1)
    target_teams = [q for q in range(4) if q != team]
    elapsed = 0.0
    ball_distance = 0.0
    ball_last = (focus_ball.x, focus_ball.y) if focus_ball is not None else None
    sniper_distance = 0.0
    sniper_last = ((focus_sniper["x"], focus_sniper["y"]) if focus_sniper is not None else None)
    while elapsed < window - 1e-9:
        dt = min(DT, window - elapsed)
        with_cast.tick(dt)
        without_cast.tick(dt)
        if focus_ball is not None:
            here = (focus_ball.x, focus_ball.y)
            ball_distance += math.hypot(here[0] - ball_last[0], here[1] - ball_last[1])
            ball_last = here
        if focus_sniper is not None:
            here = (focus_sniper["x"], focus_sniper["y"])
            sniper_distance += math.hypot(here[0] - sniper_last[0], here[1] - sniper_last[1])
            sniper_last = here
        elapsed += dt
    extra_cells = count_team_cells(with_cast, team) - count_team_cells(without_cast, team)
    enemy_damage = sum(without_cast.hp[q] - with_cast.hp[q] for q in target_teams)

    item, direct = meta["item"], {}
    if item == 0:
        direct.update(bullets=meta["cast_bullets"], cone_ok=meta["cone_ok"],
                      live_after_cast=meta.get("live_cast_bullets", 0),
                      shotgun_fx_life=meta.get("shotgun_fx_life", 0.0))
    elif item == 1:
        direct["extra_mg_rounds"] = max(0, mg_rounds[0] - mg_rounds[1])
    elif item == 2:
        add = meta["hp_after"] - meta["hp_before"]
        shield_fx = post.shield_fx[meta["shield_fx_before"]:meta["shield_fx_after"]] if hasattr(post, "shield_fx") else []
        floater_fx = post.floaters[meta["floaters_before"]:meta["floaters_after"]]
        lives = [float(x.get("max", x.get("life", 0))) for x in shield_fx + floater_fx]
        lives.extend(2.8 - (post.t - x["t"]) for x in shield_fx)
        direct.update(hp_gain=add, hp_fraction=add / max(meta["hp_before"], 1.0),
                      hud_before=fmt(meta["hp_before"]), hud_after=fmt(meta["hp_after"]),
                      hud_changed=fmt(meta["hp_before"]) != fmt(meta["hp_after"]),
                      fx_life=max(lives, default=0.0))
    elif item == 3:
        focus = focus_ball
        if focus is not None:
            direct.update(ball_alive=bool(focus.alive), ball_age=focus.age,
                          ball_distance=ball_distance,
                          ball_strength=meta["ball_value"])
        else:
            direct.update(ball_alive=False, ball_age=0.0, ball_distance=0.0,
                          ball_strength=meta["ball_value"])
        with_hits = sum(e[1] == "ballHit" and e[2] == team and e[3] in target_teams
                        for e in with_cast.events[meta["events_before"]:])
        no_hits = sum(e[1] == "ballHit" and e[2] == team and e[3] in target_teams
                      for e in without_cast.events[meta["events_before"]:])
        direct["enemy_ball_hit"] = with_hits > no_hits
    elif item == 4:
        direct.update(extra_cells=extra_cells, sniper_distance=sniper_distance)

    aimed, target = target_angle(team, post.dead)
    aimed_ok = abs(angle_delta(meta["cast_angle"], aimed)) <= math.radians(35)
    extra_cells += int(meta.get("kernel_extra_cells", 0))
    enemy_damage += float(meta.get("kernel_enemy_damage", 0.0))
    row = dict(t=meta["t"], team=team, item=item, angle_ok=aimed_ok, target=target,
               extra_cells=extra_cells, enemy_damage=max(0.0, enemy_damage), direct=direct)
    return row


def failures(row):
    i, d = row["item"], row["direct"]
    bad = []
    if i == 0:
        if d.get("bullets", 0) < 90:
            bad.append("fewer-than-90-cast-bullets")
        if not d.get("cone_ok", False):
            bad.append("cone-not-centered-on-barrel")
        visible_burst = d.get("live_after_cast", 0) >= 90 and d.get("shotgun_fx_life", 0) >= .75
        if row["extra_cells"] < 150 and not visible_burst:
            bad.append("fewer-than-150-extra-cells-or-visible-burst")
        if d.get("shotgun_fx_life", 0) < .75:
            bad.append("no-visible-shotgun-fan")
        if not row["angle_ok"]:
            bad.append("not-aimed-at-enemy")
    elif i == 1:
        if not (d.get("extra_mg_rounds", 0) >= 400 or row["extra_cells"] >= 400 or row["enemy_damage"] > 0):
            bad.append("no-visible-mg-delta")
        if not row["angle_ok"]:
            bad.append("not-aimed-at-enemy")
    elif i == 2:
        if d.get("hp_fraction", 0) < .01:
            bad.append("shield-gain-under-1-percent")
        if not d.get("hud_changed", False):
            bad.append("shield-hud-did-not-change")
        if d.get("fx_life", 0) < 1.5:
            bad.append("no-persistent-shield-fx")
    elif i == 3:
        if d.get("ball_age", 0) < 8.0:
            bad.append("ball-died-before-8-seconds")
        if not (d.get("enemy_ball_hit", False) or row["extra_cells"] >= 1500 or d.get("ball_distance", 0) >= 600):
            bad.append("no-ball-trade-1500-cells-or-600px-travel")
        if not row["angle_ok"]:
            bad.append("not-aimed-at-enemy")
    elif i == 4:
        if not row["angle_ok"]:
            bad.append("not-aimed-toward-enemy")
        if not (row["extra_cells"] >= 300 or row["enemy_damage"] > 0 or d.get("sniper_distance", 0) >= 300):
            bad.append("no-300-cell-or-shield-effect")
    return bad


def install_cast_recorder(game):
    original = Game._fire_item
    original_step = K.step_bullets
    records = []
    control = {"enabled": False}

    def tracked(self, team, item, strength=None):
        if self is not game:
            return original(self, team, item, strength)
        shotgun_fx = getattr(self, "shotgun_fx", None)
        before = dict(team=team, item=item, t=float(self.t), n_before=int(self.n),
                      hp_before=float(self.hp[team]), ammo_before=float(self.ammo[team]),
                      mg_before=float(self.mg[team]), mg_emit_before=float(self.mg_emit_acc[team]),
                      aim_before=float(self.aim[team]), aim_hold_before=float(getattr(self, "aim_hold", [0.0] * 4)[team]),
                      item_total_before=int(self.item_total[item]),
                      floaters_before=len(self.floaters), events_before=len(self.events),
                      ball_index=len(self.balls), sniper_index=len(self.snipers),
                      shotgun_fx_before=len(shotgun_fx) if isinstance(shotgun_fx, list) else 0,
                      shotgun_fx_before_value=shotgun_fx,
                      shield_fx_before=len(getattr(self, "shield_fx", [])))
        ok = original(self, team, item, strength)
        if ok:
            shotgun_fx = getattr(self, "shotgun_fx", None)
            before.update(n_after=int(self.n), hp_after=float(self.hp[team]),
                          floaters_after=len(self.floaters),
                          shotgun_fx_after=len(shotgun_fx) if isinstance(shotgun_fx, list) else 0,
                          shield_fx_after=len(getattr(self, "shield_fx", [])),
                          cast_angle=float(self.aim[team]))
            if item == 0:
                lo, hi = before["n_before"], before["n_after"]
                before["cast_bullets"] = hi - lo
                before["cone_ok"] = True
                if hi > lo:
                    aa = np.arctan2(self.bvy[lo:hi], self.bvx[lo:hi])
                    dev = [abs(angle_delta(float(a), before["cast_angle"])) for a in aa]
                    before["cone_ok"] = max(dev, default=0.0) <= math.radians(12.6)
                before["bullet_marker"] = 100 + (len(records) % 20)
                if hi > lo:
                    self.bkind[lo:hi] = before["bullet_marker"]
                before["shotgun_fx_life"] = max(
                    (0.9 - (self.t - f["t"]) for f in shotgun_fx[before["shotgun_fx_before"]:]),
                    default=0.0) if isinstance(shotgun_fx, list) else 0.0
            if item == 3:
                ball = self.balls[before["ball_index"]]
                before.update(ball_x=float(ball.x), ball_y=float(ball.y), ball_value=float(ball.value))
            elif item == 4:
                sniper = self.snipers[before["sniper_index"]]
                before.update(sniper_x0=float(sniper["x0"]), sniper_y0=float(sniper["y0"]))
            records.append(before)
        return ok

    def watched_step(*args):
        if not control["enabled"]:
            return original_step(*args)
        n = int(args[0])
        kinds = args[6]
        current = [r for r in records if r["item"] == 0 and r["t"] == game.t]
        current = [r for r in current if np.any(kinds[:n] == r["bullet_marker"])]
        if not current:
            return original_step(*args)
        pre = copy.deepcopy(game)
        result = original_step(*args)
        game.n = result
        real_cells = {r["team"]: count_team_cells(game, r["team"]) for r in current}
        real_dmg = game._dmg.copy()
        for meta in current:
            branch = copy.deepcopy(pre)
            marker = meta["bullet_marker"]
            keep = branch.bkind[:branch.n] != marker
            old_n = branch.n
            kept_ix = np.flatnonzero(keep)
            old_to_new = np.full(old_n, -1, dtype=np.int64)
            old_to_new[kept_ix] = np.arange(len(kept_ix), dtype=np.int64)
            for name in ("bx", "by", "bvx", "bvy", "bteam", "bkind", "bbounce"):
                arr = getattr(branch, name)
                arr[:len(kept_ix)] = arr[:old_n][keep].copy()
            branch.n = len(kept_ix)
            old_order = args[8]
            filtered = old_order[keep[old_order]]
            order = old_to_new[filtered]
            original_step(branch.n, branch.bx, branch.by, branch.bvx, branch.bvy,
                          branch.bteam, branch.bkind, branch.bbounce, order,
                          branch.grid, branch.heat, branch._dead, branch._dmg,
                          branch._paints, branch._bullet_owner, branch._path_cells,
                          branch._path_len, branch._path_stop, branch._occ_head,
                          branch._occ_next, branch._occ_bullet, branch._collided,
                          branch._start_x, branch._start_y, branch._turn_x,
                          branch._turn_y, branch._turn_n, args[-2], branch._alive)
            meta["kernel_extra_cells"] = real_cells[meta["team"]] - count_team_cells(branch, meta["team"])
            meta["kernel_enemy_damage"] = sum((branch._dmg[q] - real_dmg[q]) * 1500.0
                                               for q in range(4) if q != meta["team"])
            live = int(np.count_nonzero(game.bkind[:game.n] == marker))
            meta["live_cast_bullets"] = live
        return result

    Game._fire_item = tracked
    K.step_bullets = watched_step
    return original, original_step, records, control


def run_seed(seed, seconds):
    game = Game(seed=seed, match=300)
    original, original_step, records, control = install_cast_recorder(game)
    measured = []
    seen = 0
    try:
        while game.t < seconds - 1e-9 and not game.over:
            control["enabled"] = True
            game.tick(DT)
            control["enabled"] = False
            while seen < len(records):
                meta = records[seen]
                seen += 1
                if meta["t"] <= seconds + 1e-9:
                    row = measure_cast(game, meta)
                    row["seed"] = seed
                    row["bad"] = failures(row)
                    measured.append(row)
    finally:
        control["enabled"] = False
        Game._fire_item = original
        K.step_bullets = original_step
    return game, measured


def main():
    seeds = [6, 1, 7, 42, 2001]
    seconds = WINDOW
    if len(sys.argv) > 1:
        seeds = [int(s) for s in sys.argv[1].split(",") if s]
    if len(sys.argv) > 2:
        seconds = float(sys.argv[2])
    all_rows = []
    print(f"effect visibility check: match=300, horizon={seconds:g}s, seeds={seeds}")
    print("minimum thresholds:")
    for i in range(5):
        print(f"  {ITEM_NAMES[i]}: {THRESHOLDS[i]}")
    for seed in seeds:
        game, rows = run_seed(seed, seconds)
        all_rows.extend(rows)
        counts = {ITEM_NAMES[i]: sum(r["item"] == i for r in rows) for i in range(5)}
        print(f"seed {seed}: sim_t={game.t:.2f}s casts={len(rows)} by_item={counts}")
        for r in rows:
            d = r["direct"]
            print(f"  t={r['t']:6.2f} team={r['team']} {ITEM_NAMES[r['item']]} "
                  f"extra_cells={r['extra_cells']:+5d} enemy_damage={r['enemy_damage']:.0f} "
                  f"angle_ok={r['angle_ok']} direct={d} "
                  f"{'FAIL ' + ','.join(r['bad']) if r['bad'] else 'PASS'}")
    fails = [r for r in all_rows if r["bad"]]
    print(f"SUMMARY casts={len(all_rows)} failed={len(fails)}")
    if not all_rows:
        print("FAIL: no item casts observed")
        return 1
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
