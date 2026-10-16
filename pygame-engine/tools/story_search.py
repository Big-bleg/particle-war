"""Search seeds for the most dramatic match at a given length and rank them.
usage: python tools/story_search.py N first_seed match_seconds"""
import sys, os, json
from multiprocessing import Pool
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def run(args):
    seed, match = args
    from war4balls.sim import Game
    from war4balls.config import DT
    g = Game(seed=seed, match=match)
    leaders = []; nxt = 1.0
    while not g.over and g.t < match + 30:
        g.tick(DT)
        if g.t >= nxt:
            nxt += 1
            al = g.alive_teams()
            lead = max(al, key=lambda t: g.share[t]) if al else -1
            leaders.append((round(g.t), lead, [round(s, 3) for s in g.share], [round(h) for h in g.hp]))
    # lead changes with hysteresis (new leader holds 4 s)
    changes = 0; cur = None; cand = None; hold = 0; lead_hist = []
    for t, L, sh, hp in leaders:
        if t < 15: continue
        if cur is None: cur = L
        if L != cur:
            if L == cand: hold += 1
            else: cand, hold = L, 1
            if hold >= 4: cur = L; changes += 1; lead_hist.append((t, L)); cand = None
        else: cand = None
    deaths = [(round(e[0]), e[2]) for e in g.events if e[1] == 'eliminated']
    hits = sum(1 for e in g.events if e[1] == 'ballHit')
    used = set(e[3] for e in g.events if e[1] == 'use')
    end = round(g.t)
    # comeback: winner's share rank at the midpoint
    mid = min(leaders, key=lambda row: abs(row[0] - match * .5)) if leaders else (0, -1, [0.0] * 4, [0] * 4)
    rank_mid = sorted(range(4), key=lambda t: -mid[2][t]).index(g.winner) if g.winner >= 0 else 4
    score = 0.0
    score += min(changes, 6) * 3
    score += len(deaths) == 3 and 10 or 0
    if len(deaths) == 3:
        gaps = [deaths[0][0] - match * .5, deaths[1][0] - deaths[0][0], deaths[2][0] - deaths[1][0]]
        score += sum(min(gp, 40) for gp in gaps[1:]) / 8              # spacing up to 40 s each
    score -= abs(end - (match - 20)) / 5                                # prefer a late finish near 280 s
    sn = sum(1 for e in g.events if e[1] == 'sniper'); mgc = sum(1 for e in g.events if e[1] == 'machinegun')
    score += min(hits, 8) * 1.2 + len(used) * 1.5 + rank_mid * 4
    score += min(sn, 5) * 1.5 + min(mgc, 5) * 1.5 - (sn < 3) * 6 - (mgc < 3) * 6
    qualified = bool(changes > 0 and 260 <= end <= 300 and len(used) == 5 and rank_mid > 0 and sn > 0 and mgc > 0)
    use_times = {str(i): [round(e[0], 2) for e in g.events if e[1] == 'use' and e[3] == i] for i in range(5)}
    return dict(seed=seed, score=round(score, 1), end=end, winner=g.winner, deaths=deaths, lead_changes=changes, lead_hist=lead_hist,
                ball_hits=hits, items_used=sorted(used), winner_rank_mid=rank_mid, snipers=sn, mgs=mgc,
                item_use_times=use_times, qualified=qualified)


if __name__ == '__main__':
    N, s0, match = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
    with Pool(8) as p:
        res = []
        for i, result in enumerate(p.imap_unordered(run, [(s, match) for s in range(s0, s0 + N)], chunksize=1), 1):
            res.append(result)
            if i % 10 == 0 or i == N:
                print(f'SEARCH progress {i}/{N}', flush=True)
    res.sort(key=lambda r: (not r['qualified'], -r['score']))
    wins = [0] * 5
    for r in res: wins[r['winner'] if r['winner'] >= 0 else 4] += 1
    for r in res[:10]: print(json.dumps(r))
    print('WINS', wins, 'ends', sorted(r['end'] for r in res))
    os.makedirs('out', exist_ok=True)
    json.dump(res, open(f'out/story_search_{int(match)}.json', 'w'), indent=1)
