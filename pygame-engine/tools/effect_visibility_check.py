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
from war4balls.config import BASES, DT, G, GS, ITEM_NAMES, MATCH, S, fmt
from war4balls import kernels as K
from war4balls.sim import Game


WINDOW = 90.0
ITEM_WINDOWS = {0: 3.0, 1: 3.0, 2: 2.0, 3: 15.0, 4: 3.0}
THRESHOLDS = {
    0: "shotgun: 240 bullets centered on the fire-time barrel in a 25-degree cone; useful-aim visibility is reported, not required for every random heading",
    1: "machinegun: >=400 added MG rounds; later rounds follow the live sweeping barrel; useful-aim visibility is reported",
    2: "shield: >=1% HP, changed HUD text, and >=1.5s shield FX (aim independent)",
    3: "bigball: alive >=8s; useful-aim visibility is reported, and lifetime failure is always real",
    4: "sniper: follows the fire-time barrel; useful-aim visibility is reported",
}


def angle_delta(a, b):
    return (a - b + math.pi) % math.tau - math.pi


def classify_aim(team, angle, grid):
    """Classify a fire-time ray without treating a bad random heading as a code failure."""
    bx, by = BASES[team]
    dx, dy = math.cos(angle), math.sin(angle)
    edge = min((G - 20 - bx) / dx if dx > 0 else (20 - bx) / dx if dx < 0 else math.inf,
               (G - 20 - by) / dy if dy > 0 else (20 - by) / dy if dy < 0 else math.inf)
    if edge < 150:
        return "wall"
    reach = min(500.0, edge)
    for distance in range(100, int(reach) + 1, 20):
        x, y = bx + dx * distance, by + dy * distance
        gx = int(max(0, min(GS - 1, x / S))); gy = int(max(0, min(GS - 1, y / S)))
        if int(grid[gy * GS + gx]) != team:
            return "open/enemy"
    return "own"


def check_barrel_direction_assertions():
    """Exercise each item through each public cast route and guard its fire-time heading."""
    failures = []
    routes = ("slot", "keyboard", "ai")
    for route in routes:
        for item in range(5):
            game = Game(seed=918 + item, match=300)
            game.t = 30.0
            game.opened = True
            game.spin = [0.0] * 4
            game.cool = [1000.0] * 4
            team = item % 4
            # Deliberately point away from the nearest enemy so the old auto-aim fails.
            game.aim[team] = (1.13, .73, .51, -2.21)[team]
            casts = []
            original = Game._fire_item

            def tracked(self, t, i, strength=None):
                n_before, balls_before, snipers_before = int(self.n), len(self.balls), len(self.snipers)
                angle = float(self.aim[t]) if self is game else 0.0
                ok = original(self, t, i, strength)
                if self is game and ok:
                    cast = dict(team=t, item=i, angle=angle, aim_after=float(self.aim[t]))
                    if i == 0:
                        cast["directions"] = np.arctan2(self.bvy[n_before:self.n], self.bvx[n_before:self.n]).copy()
                    elif i == 3:
                        ball = self.balls[balls_before]
                        cast["direction"] = math.atan2(ball.vy, ball.vx)
                    elif i == 4:
                        sniper = self.snipers[snipers_before]
                        cast["direction"] = math.atan2(sniper["vy"], sniper["vx"])
                    casts.append(cast)
                return ok

            Game._fire_item = tracked
            try:
                if route == "slot":
                    from war4balls.config import ITEM_FLOOR, ITEM_TOP, ITEM_X
                    for marble in list(game.board.marbles):
                        game.board._consume(marble)
                    game.board.queue_launch.clear()
                    marble = game.board.add_marble(team, 2 ** 20)
                    if marble in game.board.queue_launch:
                        game.board.queue_launch.remove(marble)
                    if marble.body not in game.board.space.bodies:
                        game.board.space.add(marble.body, marble.shape)
                    marble.queued = False
                    x0, x1 = ITEM_X[item] + 20, ITEM_X[item + 1] - 20
                    marble.body.position = ((x0 + x1) / 2, (ITEM_TOP + ITEM_FLOOR) / 2)
                    marble.body.velocity = (0, 40)
                    game.tick(DT)
                elif route == "keyboard":
                    game.manual_item(team, item)
                elif route == "ai":
                    game.give_item(team, item)
                    game.use(team, item)
                if not casts:
                    failures.append(f"{route}/{ITEM_NAMES[item]}: cast route did not fire")
                    continue
                cast = casts[-1]
                angle = cast["angle"]
                if cast["item"] != item:
                    failures.append(f"{route}/{ITEM_NAMES[item]}: route fired item {cast['item']}")
                    continue
                if item == 0:
                    aa = cast["directions"]
                    dev = [abs(angle_delta(float(a), angle)) for a in aa]
                    if len(dev) < 90 or max(dev, default=math.inf) > math.radians(12.6):
                        failures.append(f"{route}/{ITEM_NAMES[item]}: pellet cone not centered on fire-time barrel")
                    elif abs(angle_delta(math.atan2(np.sin(aa).mean(), np.cos(aa).mean()), angle)) > .002:
                        failures.append(f"{route}/{ITEM_NAMES[item]}: pellet cone center differs from fire-time barrel")
                elif item == 1:
                    if abs(angle_delta(cast["aim_after"], angle)) > 1e-10:
                        failures.append(f"{route}/{ITEM_NAMES[item]}: cast changed barrel heading")
                elif item == 2:
                    if abs(angle_delta(cast["aim_after"], angle)) > 1e-10:
                        failures.append(f"{route}/{ITEM_NAMES[item]}: shield unexpectedly changed heading")
                elif item in (3, 4):
                    if abs(angle_delta(cast["direction"], angle)) > 1e-10:
                        kind = "ball" if item == 3 else "sniper"
                        failures.append(f"{route}/{ITEM_NAMES[item]}: {kind} direction differs from fire-time barrel")
            finally:
                Game._fire_item = original
    # Late pacing invokes a dedicated helper but must still use the same barrel angle.
    game = Game(seed=992, match=300); game.t = 240.0; team = 1
    game.opened = True; game.spin = [0.0] * 4; game.aim[team] = -.79
    casts = []
    original = Game._fire_item
    def tracked_late(self, t, i, strength=None):
        angle = float(self.aim[t]) if self is game else 0.0
        balls_before = len(self.balls)
        ok = original(self, t, i, strength)
        if self is game and ok:
            ball = self.balls[balls_before]
            casts.append((angle, math.atan2(ball.vy, ball.vx)))
        return ok
    Game._fire_item = tracked_late
    try:
        game._fire_late_extra_bigball(team)
        if not casts or abs(angle_delta(casts[-1][0], casts[-1][1])) > 1e-10:
            failures.append("late extra big ball: direction differs from fire-time barrel")
    finally:
        Game._fire_item = original
    # The MG stream is live-barrel: later emissions must use the then-current angle.
    game = Game(seed=991, match=300)
    game.opened = True; game.t = 30.0; game.spin = [0.0] * 4
    game.cool = [1000.0] * 4; game.aim[0] = 1.41
    original = Game._fire_item
    Game._fire_item = original
    try:
        game.fire_item(0, 1)
        game.spin[0] = .7
        emitted_at = []
        original_emit = game.emit
        def tracked_emit(team, count, kind, speed, half_spread, jitter_t=0.0, ang=None):
            if team == 0 and kind == 7:
                emitted_at.append((float(game.aim[team]), int(game.n), count))
            return original_emit(team, count, kind, speed, half_spread, jitter_t, ang)
        game.emit = tracked_emit
        game.tick(DT)
        if not emitted_at:
            failures.append("live-barrel machinegun: no round emitted in assertion tick")
        else:
            angle, n0, count = emitted_at[0]
            aa = np.arctan2(game.bvy[n0:n0 + count], game.bvx[n0:n0 + count])
            if any(abs(angle_delta(float(a), angle)) > math.radians(.81) for a in aa):
                failures.append("live-barrel machinegun: rounds did not follow barrel at emission time")
    finally:
        Game._fire_item = original
    return failures


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

    extra_cells += int(meta.get("kernel_extra_cells", 0))
    enemy_damage += float(meta.get("kernel_enemy_damage", 0.0))
    region = meta.get("aim_region")
    if item == 0:
        direct["visible"] = (extra_cells >= 150 or
                             (direct.get("live_after_cast", 0) >= 90 and direct.get("shotgun_fx_life", 0) >= .75))
    elif item == 1:
        direct["visible"] = (direct.get("extra_mg_rounds", 0) >= 400 or extra_cells >= 400 or enemy_damage > 0)
    elif item == 2:
        direct["visible"] = (direct.get("hp_fraction", 0) >= .01 and direct.get("hud_changed", False)
                             and direct.get("fx_life", 0) >= 1.5)
    elif item == 3:
        direct["visible"] = (direct.get("enemy_ball_hit", False) or extra_cells >= 1500
                             or direct.get("ball_distance", 0) >= 600)
    else:
        direct["visible"] = (extra_cells >= 300 or enemy_damage > 0 or direct.get("sniper_distance", 0) >= 300)
    delay_events = [e for e in post.events if e[1] == "item_delay_fired" and e[2] == team and e[3] == item
                    and abs(e[0] - meta["t"]) <= DT * 1.1]
    direct["delay_seconds"] = float(delay_events[-1][4]) if delay_events else 0.0
    row = dict(t=meta["t"], team=team, item=item, aim_region=region,
               extra_cells=extra_cells, enemy_damage=max(0.0, enemy_damage), direct=direct)
    return row


def failures(row):
    i, d = row["item"], row["direct"]
    bad = []
    if i == 0:
        if d.get("bullets", 0) < 240:
            bad.append("shotgun-burst-under-240-bullets")
        if not d.get("cone_ok", False):
            bad.append("cone-not-centered-on-fire-time-barrel")
    elif i == 1:
        if d.get("extra_mg_rounds", 0) < 400:
            bad.append("machinegun-density-under-400-extra-rounds")
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
                      aim_region=(classify_aim(team, float(self.aim[team]), self.grid) if item != 2 else None),
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
                          cast_angle=before["aim_before"])
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


def run_seed(seed, seconds, delay_enabled=False):
    game = Game(seed=seed, match=300)
    game.item_cast_aim_delay_enabled = delay_enabled
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
    if "--aim-only" in sys.argv:
        fails = check_barrel_direction_assertions()
        print("barrel-direction assertions:")
        for failure in fails:
            print("FAIL:", failure)
        if not fails:
            print("PASS")
        return 1 if fails else 0
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    delay_enabled = "--aim-delay" in sys.argv
    seeds = [6, 1, 7, 42, 2001]
    seconds = WINDOW
    if args:
        seeds = [int(s) for s in args[0].split(",") if s]
    if len(args) > 1:
        seconds = float(args[1])
    all_rows = []
    aim_fails = check_barrel_direction_assertions()
    print("barrel-direction assertions:", "PASS" if not aim_fails else f"FAIL ({len(aim_fails)})")
    for failure in aim_fails:
        print("  FAIL:", failure)
    print(f"effect visibility check: match=300, horizon={seconds:g}s, seeds={seeds}, aim_delay={'ON' if delay_enabled else 'OFF'}")
    print("minimum thresholds:")
    for i in range(5):
        print(f"  {ITEM_NAMES[i]}: {THRESHOLDS[i]}")
    for seed in seeds:
        game, rows = run_seed(seed, seconds, delay_enabled)
        all_rows.extend(rows)
        counts = {ITEM_NAMES[i]: sum(r["item"] == i for r in rows) for i in range(5)}
        print(f"seed {seed}: sim_t={game.t:.2f}s casts={len(rows)} by_item={counts}")
        for r in rows:
            d = r["direct"]
            print(f"  t={r['t']:6.2f} team={r['team']} {ITEM_NAMES[r['item']]} "
                  f"aim={r['aim_region'] or 'none'} visible={d['visible']} "
                  f"extra_cells={r['extra_cells']:+5d} enemy_damage={r['enemy_damage']:.0f} "
                  f"delay={d['delay_seconds']:.3f}s direct={d} "
                  f"{'FAIL ' + ','.join(r['bad']) if r['bad'] else 'PASS'}")
    fails = [r for r in all_rows if r["bad"]]
    print("SUMMARY by item:")
    for item in range(5):
        rows = [r for r in all_rows if r["item"] == item]
        visible = sum(bool(r["direct"]["visible"]) for r in rows)
        if item == 2:
            wasted = 0
        else:
            wasted = sum(r["aim_region"] != "open/enemy" for r in rows)
        useful_rows = [r for r in rows if r["aim_region"] == "open/enemy"]
        useful_visible = sum(bool(r["direct"]["visible"]) for r in useful_rows)
        delays = [r["direct"]["delay_seconds"] for r in rows]
        print(f"  {ITEM_NAMES[item]}: visible={visible}/{len(rows)}; aimed useful={useful_visible}/{len(useful_rows)}; "
              f"wasted-by-aim={wasted}/{len(rows)} ({(100*wasted/len(rows)) if rows else 0:.1f}%); "
              f"mean-delay={(sum(delays)/len(delays)) if delays else 0:.3f}s")
    print("SUMMARY per seed and item (visible/total; wasted/total):")
    for seed in seeds:
        seed_rows = [r for r in all_rows if r["seed"] == seed]
        details = []
        for item in range(5):
            rows = [r for r in seed_rows if r["item"] == item]
            visible = sum(bool(r["direct"]["visible"]) for r in rows)
            wasted = sum(r["aim_region"] != "open/enemy" for r in rows) if item != 2 else 0
            details.append(f"{ITEM_NAMES[item]} {visible}/{len(rows)}; {wasted}/{len(rows)} wasted")
        print(f"  seed {seed}: " + " | ".join(details))
    if delay_enabled:
        delayed = [r for r in all_rows if r["direct"]["delay_seconds"] > 0]
        timed_out = [r for r in delayed if r["direct"]["delay_seconds"] >= 1.49]
        print(f"delay evaluation: delayed={len(delayed)}/{sum(r['item'] != 2 for r in all_rows)} offensive casts; "
              f"waited-to-limit={len(timed_out)}; max-delay="
              f"{max((r['direct']['delay_seconds'] for r in all_rows), default=0):.3f}s")
    # A heading can be poor by chance. Fail a visible-effect regression only if there
    # were useful headings for that item and none produced a visible causal effect.
    for item in (0, 1, 3, 4):
        useful = [r for r in all_rows if r["item"] == item and r["aim_region"] == "open/enemy"]
        if useful and not any(r["direct"]["visible"] for r in useful):
            fails.append(dict(item=item, bad=["no-visible-effect-on-any-useful-aim"]))
    print(f"SUMMARY casts={len(all_rows)} failed={len(fails)}")
    if not all_rows:
        print("FAIL: no item casts observed")
        return 1
    if aim_fails:
        return 1
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
