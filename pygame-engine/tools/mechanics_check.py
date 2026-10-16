"""Regression checks for strict bullet sweeps, outcomes, item triggers, and match pacing.

Usage: python3 tools/mechanics_check.py [seed[,seed...]]
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from war4balls import kernels as K
from war4balls.config import BASE_R, DT, G, GS, ITEM_FLOOR, ITEM_TOP, ITEM_X, MATCH, MG_DURATION, NEUTRAL, S
from war4balls.sim import Game


PATH_CELLS = 64


def run_kernel(bullets, grid, order):
    n = len(bullets)
    x = np.array([b[0] for b in bullets], np.float64)
    y = np.array([b[1] for b in bullets], np.float64)
    vx = np.array([b[2] for b in bullets], np.float64)
    vy = np.array([b[3] for b in bullets], np.float64)
    team = np.array([b[4] for b in bullets], np.int8)
    kind = np.zeros(n, np.int8)
    bounce = np.zeros(n, np.int8)
    heat = np.zeros(GS * GS, np.float32)
    dead = np.zeros(4, np.int8)
    dmg = np.zeros(4, np.float64)
    paints = np.zeros(4, np.int64)
    owner = np.zeros(GS * GS, np.uint8)
    path_cells = np.zeros((n, PATH_CELLS), np.int32)
    path_len = np.zeros(n, np.int32); path_stop = np.zeros(n, np.int8)
    occ_head = np.empty(GS * GS, np.int32)
    occ_next = np.empty(n * PATH_CELLS, np.int32)
    occ_bullet = np.empty(n * PATH_CELLS, np.int32)
    collided = np.zeros(n, np.int8)
    start_x = np.zeros(n); start_y = np.zeros(n)
    turn_x = np.zeros((n, 2)); turn_y = np.zeros((n, 2)); turn_n = np.zeros(n, np.int8)
    alive = np.zeros(n, np.int8)
    new_n = K.step_bullets(n, x, y, vx, vy, team, kind, bounce, np.asarray(order, np.int64), grid, heat, dead, dmg, paints,
                           owner, path_cells, path_len, path_stop, occ_head, occ_next, occ_bullet, collided,
                           start_x, start_y, turn_x, turn_y, turn_n, DT, alive)
    return new_n, grid, dmg, bounce, x, vx


def check_bullet_cancel(seed):
    """Opposing sweeps through a shared cell cancel for every processing permutation."""
    del seed
    gy = int(500 / S)
    left, shared, right = int(100 / S), int(105 / S), int(108 / S)
    expected = None
    for order in ([0, 1], [1, 0]):
        grid = np.full(GS * GS, NEUTRAL, np.uint8)
        grid[gy * GS + left] = 0
        grid[gy * GS + right] = 1
        bullets = [(100.0, 500.0, 5.0, 0.0, 0), (108.0, 500.0, -5.0, 0.0, 1)]
        result = run_kernel(bullets, grid, order)
        state = (result[0], result[1].copy(), result[2].copy())
        if expected is None:
            expected = state
        assert state[0] == 0, f"seed={seed}: opposing bullets did not both cancel"
        assert np.array_equal(state[1], expected[1]) and np.array_equal(state[2], expected[2]), f"seed={seed}: order changed cancellation"
        assert state[1][gy * GS + shared] == NEUTRAL, f"seed={seed}: canceled bullets painted their collision cell"


def check_sweep_and_shield_edge(seed):
    del seed
    gy = int(500 / S)
    grid = np.full(GS * GS, NEUTRAL, np.uint8)
    first = int(100 / S)
    target = int(110 / S)
    for gx in range(first, target):
        grid[gy * GS + gx] = 0
    grid[gy * GS + target] = 1
    end = int(135 / S)
    n, painted, _, _, _, _ = run_kernel([(100.0, 500.0, 35.0, 0.0, 0)], grid, [0])
    assert n == 0, "bullet should die on the swept foreign cell"
    assert painted[gy * GS + target] == 0, "bullet tunneled past the thin foreign cell"
    assert painted[gy * GS + end] == NEUTRAL, "bullet painted beyond its first foreign cell"

    # Hit a thin shield-edge cell but finish the tick outside the shield radius.
    sy = int(120 / S)
    grid = np.full(GS * GS, 0, np.uint8)
    shield_edge = int(930 / S)
    grid[sy * GS + shield_edge] = 1
    n, painted, dmg, _, _, _ = run_kernel([(900.0, 120.0, 60.0, 0.0, 0)], grid, [0])
    assert n == 0, "bullet crossed a shield edge without stopping"
    assert dmg[1] == 1, f"shield edge was not hit (radius={BASE_R}, dmg={dmg})"
    assert painted[sy * GS + shield_edge] == 1, "shield cell should remain owned by its base"

    # A wall crossing reflects the path and preserves the configured bounce loss.
    grid = np.full(GS * GS, 0, np.uint8)
    n, _, _, bounce, x, vx = run_kernel([(G - 1.0, 400.0, 5.0, 0.0, 0)], grid, [0])
    assert n == 1 and bounce[0] == 1 and vx[0] < 0 and x[0] < G, "arena wall did not reflect the bullet"


def check_win_draw_timeout(seed):
    g = Game(seed=seed, match=300)
    g.dead = [True, False, True, True]
    g.t = 100.0
    assert g.resolve_result() and g.winner == 1, f"seed={seed}: last shield-positive base did not win"
    before = (g.t, g.frame, g.grid.copy())
    g.tick(DT)
    assert g.t == before[0] and g.frame == before[1] and np.array_equal(g.grid, before[2]), "post-game simulation did not freeze"

    g = Game(seed=seed, match=300)
    g.dead = [True] * 4
    g.t = g.k * 445
    g.tick(DT)  # Must safely bypass late-wave max() with no alive teams.
    assert g.over and g.winner == -1, f"seed={seed}: all-dead match should be a draw"

    g = Game(seed=seed, match=300)
    g.dead = [False, False, True, True]
    g.share = [.45, .45, 0.0, 0.0]
    g.hp = [8e6, 9e6, 0.0, 0.0]
    g.t = g.k * MATCH
    assert g.resolve_result() and g.winner == 1, f"seed={seed}: timeout shield tiebreak failed"


def check_shield_cap(seed):
    g = Game(seed=seed, match=300)
    g.hp[0] = 16e6
    g.items[0][2] = 1
    assert not g.use(0, 2, force=True)
    assert g.items[0][2] == 1, "capped shield consumed a stored charge"
    assert not g.events and not g.floaters and g.item_total[2] == 0, "capped shield reported a fake success"
    assert not g.fire_item(0, 2)
    assert not g.events and not g.floaters and g.item_total[2] == 0, "capped direct shield reported a fake success"

    # A real slot landing at the cap records only the failed landing, with no success UI.
    for m in list(g.board.marbles):
        g.board._consume(m)
    g.board.queue_launch.clear()
    g.board.fx.clear()
    m = g.board.add_marble(0, 2 ** 20)
    if m in g.board.queue_launch:
        g.board.queue_launch.remove(m)
    if m.body not in g.board.space.bodies:
        g.board.space.add(m.body, m.shape)
    m.queued = False
    m.body.position = ((ITEM_X[2] + ITEM_X[3]) / 2, (ITEM_TOP + ITEM_FLOOR) / 2)
    m.body.velocity = (0, 0)
    g.tick(DT)
    lands = [e for e in g.events if e[1] == 'item_land']
    assert len(lands) == 1 and lands[0][2:5] == (0, 2, False), f"capped landing did not report a failed fire: {lands}"
    assert g.board.item_flash[2] is None and not g.board.fx, "capped landing flashed success UI"
    assert not any(e[1] in ('use', 'shield') for e in g.events) and not g.floaters and g.item_total[2] == 0, "capped landing emitted a success event"


def check_big_ball_scaling(seed):
    for value in (2 ** 18, 2 ** 24, 2 ** 30):
        g = Game(seed=seed, match=300)
        assert g.fire_item(1, 3, strength=value)
        p = g.balls[-1]
        expected = max(3e6, 2.0 * value)
        assert p.value == expected and p.v0 == expected, f"landed value {value} did not scale to big-ball strength"
        assert abs((p.vx ** 2 + p.vy ** 2) ** .5 - 1.2) < 1e-12, "big-ball speed changed"
        assert p.lock_grace == 5.0, "big-ball turret grace period changed"
    g = Game(seed=seed, match=300)
    assert g.fire_item(1, 1)
    assert abs(g.mg[1] - MG_DURATION * g.k) < 1e-12, "machine-gun duration was not scaled"
    g = Game(seed=seed, match=300)
    g.opened = True
    g.mg[0] = MG_DURATION * g.k
    g.tick(DT)
    expected_fraction = (12 * 60 * DT / g.k) % 1
    assert abs(g.mg_emit_acc[0] - expected_fraction) < 1e-9, "machine-gun firing cadence was not scaled"
    g = Game(seed=seed, match=300)
    assert abs(g.board.emit_clock - .5 * g.k) < 1e-12, "initial emitter timer was not scaled"
    g.power_clock = 6 * g.k - DT / 2
    g.tick(DT)
    assert g.power_clock == 0, "power drift timer was not scaled"
    g = Game(seed=seed, match=300)
    g.fire_item(0, 3, strength=1e6)
    g.balls[0].age = 30 * g.k - DT / 2
    g.tick(DT)
    assert not g.balls, "big-ball lifetime was not scaled"
    g = Game(seed=seed, match=300)
    g.items[0][0] = 99
    assert g.manual_item(0, 0), "keyboard-style item activation required an inventory charge"
    assert g.items[0][0] == 99, "direct activation consumed stored inventory"


def run(seeds):
    checks = [check_bullet_cancel, check_sweep_and_shield_edge, check_win_draw_timeout, check_shield_cap, check_big_ball_scaling]
    for seed in seeds:
        for check in checks:
            check(seed)
        print(f"seed={seed}: PASS ({len(checks)} mechanics groups)")
    print(f"PASS seeds={','.join(map(str, seeds))}")
    return 0


if __name__ == '__main__':
    raw = sys.argv[1] if len(sys.argv) > 1 else '1,7,42,2001'
    seeds = [int(x) for x in raw.split(',') if x]
    raise SystemExit(run(seeds))
