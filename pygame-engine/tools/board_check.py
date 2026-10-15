"""Board self-test: stuck marbles, gate rule by value, item-slot trigger + consume.
usage: python tools/board_check.py [seed] [seconds]"""
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from war4balls.sim import Game
from war4balls.config import DT, GATE_VALUE, ITEM_TOP
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
T = float(sys.argv[2]) if len(sys.argv) > 2 else 300
g = Game(seed=seed, match=float(sys.argv[3]) if len(sys.argv) > 3 else 660); b = g.board
last_pos = {}; max_stuck = 0.0; stuck_where = None
bad_pass = 0; passes = 0; seen_pass = set()
items_before = 0; consumed_ok = 0; bounced_out = 0; in_slot = {}
while g.t < T and not g.over:
    g.tick(DT)
    ids = set()
    for m in b.marbles:
        if m.wait > 0 or m.queued: continue
        x, y = m.body.position; ids.add(m.uid)
        lp = last_pos.get(m.uid)
        if lp is None or math.hypot(x - lp[0], y - lp[1]) > 5:
            last_pos[m.uid] = (x, y, g.t)
        else:
            st = g.t - lp[2]
            if st > max_stuck: max_stuck, stuck_where = st, (round(x), round(y), m.v)
        if m.passing and m.uid not in seen_pass:
            seen_pass.add(m.uid); passes += 1
            if m.v < GATE_VALUE: bad_pass += 1
        if y > ITEM_TOP + 18: in_slot[m.uid] = in_slot.get(m.uid, 0) + 1
        elif m.uid in in_slot: bounced_out += 1; del in_slot[m.uid]
items = sum(g.item_total)
print(f'seed {seed} t={g.t:.0f}s  max stuck {max_stuck:.2f}s at {stuck_where}')
print(f'gate passes {passes}, below 262K: {bad_pass}')
print(f'items triggered {items}, marbles that entered a slot and came back out: {bounced_out}')
print('cup hits', b.hit)
