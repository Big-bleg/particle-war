"""Headless rule sims (no rendering): winner distribution, elimination times, items at 6:25.
usage: python tools/sim_batch.py N [first_seed]"""
import sys, os
from multiprocessing import Pool
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def run(seed):
    from war4balls.sim import Game
    from war4balls.config import DT
    g = Game(seed=seed)
    items385 = None
    while not g.over and g.t < 700:
        g.tick(DT)
        if items385 is None and g.t >= 385:
            items385 = list(g.item_total)
    return dict(seed=seed, winner=g.winner, end=round(g.t), deaths=[(e[2], round(e[0])) for e in g.events if e[1] == 'eliminated'],
                items385=items385, gate=g.board.gate_pass)


if __name__ == '__main__':
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    s0 = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    with Pool(min(8, N)) as p:
        res = p.map(run, range(s0, s0 + N))
    wins = [0] * 5
    it = [0] * 5
    for r in res:
        print(r)
        wins[r['winner'] if r['winner'] >= 0 else 4] += 1
        for i in range(5):
            it[i] += (r['items385'] or [0] * 5)[i]
    print('WINS r/g/b/y/none', '/'.join(map(str, wins)))
    print('avg items@6:25', '/'.join(f'{v / N:.1f}' for v in it), 'total', f'{sum(it) / N:.1f}', '(ref2 5/17/11/14/6 = 53)')
