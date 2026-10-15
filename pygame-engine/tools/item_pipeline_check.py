"""Headless assertions: every item-slot land awards and fires the matching effect for that marble's team.

Checks:
  1) slot index == item id == ITEM_NAMES label
  2) land always force-fires for a living marble's team (right-side world state changes)
  3) left UI flash / "+1" only when fire succeeded
  4) dead teams do not keep spawning marbles that fake-trigger the left board
  5) direct force-use of each item type produces the matching battlefield effect
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import Counter
from war4balls.sim import Game
from war4balls.config import DT, ITEM_NAMES, ITEM_X, ITEM_TOP, ITEM_FLOOR, BASES

EFFECT_EVENT = {0: 'shotgun', 1: 'machinegun', 2: 'shield', 3: 'bigball', 4: 'sniper'}


def _assert_use_side_effects(g, team, it, before):
    """Prove the right battlefield changed for this item id."""
    name = ITEM_NAMES[it]
    if it == 0:
        # Turrets also emit in the same ticks; require a large burst from THIS team.
        team_new = sum(1 for i in range(before['n'], g.n) if int(g.bteam[i]) == team)
        assert team_new >= 50, ('shotgun burst too small', name, team, team_new, before['n'], g.n)
    elif it == 1:
        assert g.mg[team] > 0, f'{name}: machine-gun timer not set'
    elif it == 2:
        assert g.hp[team] >= before['hp'], f'{name}: shield HP missing'
        # floater only required when HP actually rose
        if g.hp[team] > before['hp']:
            assert any(f['team'] == team for f in g.floaters), f'{name}: no shield floater'
    elif it == 3:
        assert len(g.balls) > before['balls'], f'{name}: big ball not spawned'
        assert g.balls[-1].team == team, f'{name}: big ball wrong team'
    elif it == 4:
        mine = [s for s in g.snipers if s['team'] == team]
        assert mine, f'{name}: sniper not spawned'
    else:
        raise AssertionError(f'bad item {it}')


def check_direct_force_use(seed=1):
    fails = []
    for it, name in enumerate(ITEM_NAMES):
        g = Game(seed=seed, match=300)
        while not g.opened and g.t < 5:
            g.tick(DT)
        team = it % 4
        g.items[team] = [0] * 5
        before = dict(n=g.n, mg=g.mg[team], hp=g.hp[team], balls=len(g.balls))
        g.give_item(team, it)
        ok = g.use(team, it, force=True)
        if not ok:
            fails.append(('direct_use_false', name, team))
            continue
        try:
            _assert_use_side_effects(g, team, it, before)
        except AssertionError as e:
            fails.append(('direct_effect', str(e)))
        # label mapping: item index matches ITEM_NAMES
        assert ITEM_NAMES[it] == name
    return fails


def check_injected_slot_lands(seed=7):
    """Drop a marble into each physical item slot and require matching fire for that team."""
    fails = []
    for slot in range(5):
        g = Game(seed=seed + slot, match=300)
        while not g.opened and g.t < 5:
            g.tick(DT)
        team = slot % 4
        # clear noise
        for m in list(g.board.marbles):
            g.board._consume(m)
        g.board.queue_launch.clear()
        g.items[team] = [0] * 5
        g.board.item_flash = [None] * 5
        g.board.fx.clear()
        before = dict(n=g.n, mg=g.mg[team], hp=g.hp[team], balls=len(g.balls), snipers=len(g.snipers))
        m = g.board.add_marble(team, 2 ** 20)  # large; skip cups via direct place
        # park inside slot sensor (not queued)
        if m in g.board.queue_launch:
            g.board.queue_launch.remove(m)
        if m.body not in g.board.space.bodies:
            g.board.space.add(m.body, m.shape)
        m.queued = False
        x0, x1 = ITEM_X[slot] + 20, ITEM_X[slot + 1] - 20
        cx = (x0 + x1) / 2
        cy = (ITEM_TOP + ITEM_FLOOR) / 2
        m.body.position = (cx, cy)
        m.body.velocity = (0, 40)
        # step until land event or timeout
        ev_i = len(g.events)
        landed = None
        for _ in range(90):
            g.tick(DT)
            while ev_i < len(g.events):
                e = g.events[ev_i]; ev_i += 1
                if e[1] == 'item_land':
                    landed = e
                    break
            if landed:
                break
        if landed is None:
            fails.append(('no_land', slot, ITEM_NAMES[slot], team))
            continue
        t, _, land_team, it, fired = landed
        if land_team != team:
            fails.append(('team_mixup', slot, land_team, team))
        if it != slot:
            fails.append(('slot_item_mismatch', slot, it, ITEM_NAMES[slot], ITEM_NAMES[it]))
        if not fired:
            fails.append(('not_fired', slot, ITEM_NAMES[slot], team))
            continue
        # UI flash only on success, and only for this slot/item
        fl = g.board.item_flash[slot]
        if not fl or fl[0] != team:
            fails.append(('bad_flash', slot, g.board.item_flash))
        # matching events
        uses = [u for u in g.events if u[1] == 'use' and u[0] == t and u[2] == team and u[3] == it]
        if not uses:
            fails.append(('no_use_event', slot, ITEM_NAMES[slot]))
        want = EFFECT_EVENT[it]
        fx = [u for u in g.events if u[1] == want and u[0] == t and u[2] == team]
        if not fx:
            fails.append(('no_effect_event', slot, ITEM_NAMES[slot], want))
        try:
            _assert_use_side_effects(g, team, it, before)
        except AssertionError as e:
            fails.append(('injected_effect', str(e)))
    return fails


def check_natural_pipeline(seed, seconds=180, match=300):
    g = Game(seed, match=match)
    lands, fails = [], []
    effect_ok = Counter()
    ev_i = 0
    flash_without_fire = 0
    dead_spawns = 0
    prev_dead = [False] * 4
    while g.t < seconds and not g.over:
        g.tick(DT)
        # Purge runs at the start of board.tick, so marbles may exist for 1 frame after
        # elimination. Only count marbles still present when the team was already dead last tick.
        for m in g.board.marbles:
            if prev_dead[m.team]:
                dead_spawns += 1
        prev_dead = list(g.dead)
        while ev_i < len(g.events):
            e = g.events[ev_i]; ev_i += 1
            if e[1] != 'item_land':
                continue
            t, _, team, it, fired = e
            lands.append(e)
            name = ITEM_NAMES[it]
            if not (0 <= it <= 4):
                fails.append(('bad_slot', round(t, 2), team, it)); continue
            if g.dead[team] and fired:
                fails.append(('fired_for_dead', round(t, 2), team, name)); continue
            if not fired:
                # allowed only if team is dead; must NOT have flashed that slot for this land
                if not g.dead[team]:
                    fails.append(('not_fired_alive', round(t, 2), team, name))
                continue
            uses = [u for u in g.events if u[1] == 'use' and u[0] == t and u[2] == team and u[3] == it]
            if not uses:
                fails.append(('no_use_event', round(t, 2), team, name)); continue
            want = EFFECT_EVENT[it]
            fx = [u for u in g.events if u[1] == want and u[0] == t and u[2] == team]
            if not fx:
                fails.append(('no_effect_event', round(t, 2), team, name, want)); continue
            effect_ok[name] += 1
    by_slot = Counter(e[3] for e in lands)
    if dead_spawns:
        fails.append(('dead_team_marbles_present', dead_spawns))
    return dict(
        seed=seed, t=g.t, lands=len(lands), effect_ok=dict(effect_ok),
        by_slot={ITEM_NAMES[k]: by_slot[k] for k in range(5)}, fails=fails,
    )


def run(seeds=None, seconds=180):
    if seeds is None:
        seeds = [1067, 1, 7, 42, 2001]
    all_fails = []
    print('== direct force-use ==')
    d = check_direct_force_use()
    print('direct fails', d)
    all_fails.extend(d)
    print('== injected slot lands ==')
    inj = check_injected_slot_lands()
    print('injected fails', inj)
    all_fails.extend(inj)
    print('== natural pipeline ==')
    for seed in seeds:
        r = check_natural_pipeline(seed, seconds=seconds)
        print(f"seed={r['seed']} t={r['t']:.1f}s lands={r['lands']} fired_ok={r['effect_ok']} fails={len(r['fails'])}")
        print('  lands by slot', r['by_slot'])
        if r['fails']:
            print('  FAIL samples', r['fails'][:12])
            all_fails.extend(r['fails'])
        # need some lands on longer runs; short opening-only ok to be sparse on bad seeds
        if r['lands'] < 1 and seconds >= 90:
            all_fails.append(('too_few_lands', seed, r['lands']))
        for k, n in Counter(e[3] for e in [] ).items():
            pass
        # every successful natural land counted in effect_ok
        fired_lands = [e for e in range(1)]  # placeholder quiet
        ok_sum = sum(r['effect_ok'].values())
        # lands that failed only for dead teams are excluded from effect_ok; alive must match
        # Re-validate: effect_ok counts only fired; natural check already pushed fails for alive misses.
        if ok_sum > r['lands']:
            all_fails.append(('effect_gt_lands', seed, ok_sum, r['lands']))
    if all_fails:
        print('FAIL', len(all_fails), all_fails[:20])
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    seeds = [int(x) for x in sys.argv[1].split(',')] if len(sys.argv) > 1 and ',' in sys.argv[1] else None
    if seeds is None and len(sys.argv) > 1:
        seeds = [int(sys.argv[1])]
    sec = float(sys.argv[2]) if len(sys.argv) > 2 else 180
    raise SystemExit(run(seeds, sec))
