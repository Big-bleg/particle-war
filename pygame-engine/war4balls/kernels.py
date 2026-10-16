"""numba kernels for the bullet swarm and territory grid (strict UnityDots paint rule)."""
import numpy as np
from numba import njit
from .config import GS, S, G, NEUTRAL, BASES, BASE_R

BX = np.array([b[0] for b in BASES], np.float64)
BY = np.array([b[1] for b in BASES], np.float64)


@njit(cache=True)
def _append_cell(cells, count, gx, gy):
    if gx < 0 or gy < 0 or gx >= GS or gy >= GS:
        return count
    c = gy * GS + gx
    if count and cells[count - 1] == c:
        return count
    if count >= cells.size:
        raise ValueError("bullet sweep path capacity exceeded")
    cells[count] = c
    return count + 1


@njit(cache=True)
def _trace_segment(cells, count, x0, y0, x1, y1, grid, t):
    """Append every grid cell touched by a segment, including corner-touch cells."""
    dx, dy = x1 - x0, y1 - y0
    gx0 = min(GS - 1, max(0, int(x0 / S)))
    gy0 = min(GS - 1, max(0, int(y0 / S)))
    gx1 = min(GS - 1, max(0, int(x1 / S)))
    gy1 = min(GS - 1, max(0, int(y1 / S)))
    gx, gy = gx0, gy0

    count = _append_cell(cells, count, gx, gy)
    if grid[gy * GS + gx] != t:
        return count, True

    sx = 1 if dx > 0 else -1 if dx < 0 else 0
    sy = 1 if dy > 0 else -1 if dy < 0 else 0
    inf = 1.0e30
    if sx:
        bx = (gx + 1) * S if sx > 0 else gx * S
        tx = (bx - x0) / dx
        dtx = S / abs(dx)
    else:
        tx = inf; dtx = inf
    if sy:
        by = (gy + 1) * S if sy > 0 else gy * S
        ty = (by - y0) / dy
        dty = S / abs(dy)
    else:
        ty = inf; dty = inf

    while gx != gx1 or gy != gy1:
        if tx < ty - 1e-12:
            gx += sx; tx += dtx
            count = _append_cell(cells, count, gx, gy)
            if grid[gy * GS + gx] != t:
                return count, True
        elif ty < tx - 1e-12:
            gy += sy; ty += dty
            count = _append_cell(cells, count, gx, gy)
            if grid[gy * GS + gx] != t:
                return count, True
        else:
            # A corner crossing touches both side cells as well as the diagonal.
            nx, ny = gx + sx, gy + sy
            count = _append_cell(cells, count, nx, gy)
            if nx >= 0 and nx < GS and gy >= 0 and gy < GS and grid[gy * GS + nx] != t:
                return count, True
            count = _append_cell(cells, count, gx, ny)
            if gx >= 0 and gx < GS and ny >= 0 and ny < GS and grid[ny * GS + gx] != t:
                return count, True
            gx, gy = nx, ny
            tx += dtx; ty += dty
            count = _append_cell(cells, count, gx, gy)
            if grid[gy * GS + gx] != t:
                return count, True
    return count, False


@njit(cache=True)
def step_bullets(n, x, y, vx, vy, team, kind, bounce, order, grid, heat, dead, dmg, paints,
                 owner, path_cells, path_len, path_stop, occ_head, occ_next, occ_bullet, collided,
                 start_x, start_y, turn_x, turn_y, turn_n, dt, alive):
    """Move every bullet one tick. Rules:
    - travelling over own territory: keep flying
    - sweep all cells crossed, converting only the first foreign/neutral cell
    - entering a live enemy shield (inside BASE_R): chip that base (dmg[b] += 1) and die; shotgun (kind 5) ignores shields
    - leaving the arena: reflect, 15% speed loss, max 2 bounces
    - opposing bullets whose swept paths touch the same cell in a tick cancel symmetrically

    Collision paths are collected before any bullet paints, so the cancellation result does
    not depend on `order` (which remains a randomized paint-order permutation)."""
    k = 60.0 * dt
    owner[:] = grid
    for i in range(n):
        alive[i] = 1
        collided[i] = 0
        turn_n[i] = 0
        start_x[i] = x[i]; start_y[i] = y[i]
        px, py = x[i], y[i]
        vxi, vyi = vx[i], vy[i]
        remaining = 1.0
        for _ in range(3):
            dx, dy = vxi * k * remaining, vyi * k * remaining
            ex, ey = px + dx, py + dy
            tx, ty = 1.0, 1.0
            hit_x = False; hit_y = False
            if ex < 0:
                tx = (0.0 - px) / dx; hit_x = True
            elif ex > G:
                tx = (G - px) / dx; hit_x = True
            if ey < 0:
                ty = (0.0 - py) / dy; hit_y = True
            elif ey > G:
                ty = (G - py) / dy; hit_y = True
            at = min(tx, ty)
            if at >= 1.0:
                px, py = ex, ey
                break
            hx, hy = px + dx * at, py + dy * at
            if turn_n[i] >= 2:
                alive[i] = 0
                break
            turn_x[i, turn_n[i]] = hx; turn_y[i, turn_n[i]] = hy
            turn_n[i] += 1
            bounce[i] += 1
            if bounce[i] > 2:
                alive[i] = 0
                break
            if hit_x and tx <= ty + 1e-12: vxi = -vxi * .85
            if hit_y and ty <= tx + 1e-12: vyi = -vyi * .85
            px, py = hx, hy
            remaining *= 1.0 - at
        x[i], y[i], vx[i], vy[i] = px, py, vxi, vyi

    # Trace each route against the tick-start paint. Paths stop at the first foreign cell.
    for i in range(n):
        path_len[i] = 0
        path_stop[i] = 0
        if alive[i] == 0:
            continue
        count = 0; sx, sy = start_x[i], start_y[i]
        stopped = False
        for turn in range(turn_n[i]):
            count, stop = _trace_segment(path_cells[i], count, sx, sy, turn_x[i, turn], turn_y[i, turn], owner, team[i])
            sx, sy = turn_x[i, turn], turn_y[i, turn]
            if stop:
                stopped = True
                break
        if not stopped:
            count, stopped = _trace_segment(path_cells[i], count, sx, sy, x[i], y[i], owner, team[i])
        path_len[i] = count
        path_stop[i] = 1 if stopped else 0

    # Linked per-cell occupancy lists mark every opposing pair before any paint mutates the grid.
    occ_head[:] = -1
    node_count = 0
    for i in range(n):
        if alive[i] == 0:
            continue
        for p in range(path_len[i]):
            c = path_cells[i, p]
            node = occ_head[c]
            while node >= 0:
                other = occ_bullet[node]
                if team[other] != team[i]:
                    collided[other] = 1; collided[i] = 1
                node = occ_next[node]
            if node_count >= occ_next.size:
                raise ValueError("bullet collision occupancy capacity exceeded")
            occ_bullet[node_count] = i
            occ_next[node_count] = occ_head[c]
            occ_head[c] = node_count
            node_count += 1

    # Tick-start ownership defines each bullet's first foreign cell, so a prior friendly paint cannot
    # make a later bullet tunnel through that cell during the same tick.
    for oi in range(n):
        i = order[oi]
        if alive[i] == 0 or collided[i] != 0:
            alive[i] = 0
            continue
        t = team[i]
        for p in range(path_len[i]):
            c = path_cells[i, p]
            if path_stop[i] == 0 or p < path_len[i] - 1:
                continue
            ow = owner[c]
            if ow < 4 and kind[i] != 5 and dead[ow] == 0:
                gx, gy = c % GS, c // GS
                near_x = min((gx + 1) * S, max(gx * S, BX[ow]))
                near_y = min((gy + 1) * S, max(gy * S, BY[ow]))
                dx, dy = near_x - BX[ow], near_y - BY[ow]
                if dx * dx + dy * dy < BASE_R * BASE_R:
                    dmg[ow] += 1.0
                    alive[i] = 0
                    break
            if grid[c] != t:
                grid[c] = t
                heat[c] = 1.0
                paints[t] += 1
            alive[i] = 0
            break
    # compact
    w = 0
    for i in range(n):
        if alive[i] == 1:
            x[w] = x[i]; y[w] = y[i]; vx[w] = vx[i]; vy[w] = vy[i]
            team[w] = team[i]; kind[w] = kind[i]; bounce[w] = bounce[i]
            w += 1
    return w


@njit(cache=True)
def paint_solid(grid, heat, x, y, t, r):
    gx = x / S; gy = y / S; gr = r / S; g0 = int(np.ceil(gr))
    for dy in range(-g0, g0 + 1):
        for dx in range(-g0, g0 + 1):
            if dx * dx + dy * dy > gr * gr:
                continue
            xx = int(round(gx + dx)); yy = int(round(gy + dy))
            if xx < 0 or yy < 0 or xx >= GS or yy >= GS:
                continue
            c = yy * GS + xx
            grid[c] = t
            if heat[c] < .5:
                heat[c] = .5


@njit(cache=True)
def paint_line(grid, heat, x0, y0, x1, y1, t, r):
    L = np.hypot(x1 - x0, y1 - y0)
    n = int(L / S) + 1
    for k in range(n + 1):
        f = k / n
        paint_solid(grid, heat, x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, t, r)


@njit(cache=True)
def count_share(grid, out):
    out[:] = 0
    for c in range(grid.size):
        v = grid[c]
        if v < 4:
            out[v] += 1


@njit(cache=True)
def decay_heat(heat, k):
    for c in range(heat.size):
        heat[c] *= k


@njit(cache=True)
def wave_paint(grid, heat, bx, by, r, a0, half, t):
    step = (S * .8) / r
    a = a0 - half
    while a <= a0 + half:
        for dr in range(3):
            xx = bx + np.cos(a) * (r - dr * S); yy = by + np.sin(a) * (r - dr * S)
            gx = int(xx / S); gy = int(yy / S)
            if gx < 0 or gy < 0 or gx >= GS or gy >= GS:
                continue
            c = gy * GS + gx
            grid[c] = t; heat[c] = 1.0
        a += step
