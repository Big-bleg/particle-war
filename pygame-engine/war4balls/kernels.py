"""numba kernels for the bullet swarm and territory grid (strict UnityDots paint rule)."""
import numpy as np
from numba import njit
from .config import GS, S, G, NEUTRAL, BASES, BASE_R

BX = np.array([b[0] for b in BASES], np.float64)
BY = np.array([b[1] for b in BASES], np.float64)


@njit(cache=True)
def step_bullets(n, x, y, vx, vy, team, kind, bounce, order, grid, heat, dead, dmg, paints, occ_t, occ_i, occ_s, stamp, dt, alive):
    """Move every bullet one tick. Rules:
    - travelling over own territory: keep flying
    - entering a foreign/neutral cell: convert exactly that cell and die
    - entering a live enemy shield (inside BASE_R): chip that base (dmg[b] += 1) and die; shotgun (kind 5) ignores shields
    - leaving the arena: reflect, 15% speed loss, max 2 bounces
    - two opposing bullets in the same cell in the same tick cancel each other
    `order` is a random permutation so no team is processed first."""
    k = 60.0 * dt
    for oi in range(n):
        i = order[oi]
        alive[i] = 1
        x[i] += vx[i] * k
        y[i] += vy[i] * k
        if x[i] < 0 or x[i] > G or y[i] < 0 or y[i] > G:
            bounce[i] += 1
            if bounce[i] > 2:
                alive[i] = 0
                continue
            if x[i] < 0:
                x[i] = -x[i]; vx[i] = -vx[i] * .85
            elif x[i] > G:
                x[i] = 2 * G - x[i]; vx[i] = -vx[i] * .85
            if y[i] < 0:
                y[i] = -y[i]; vy[i] = -vy[i] * .85
            elif y[i] > G:
                y[i] = 2 * G - y[i]; vy[i] = -vy[i] * .85
        gx = int(x[i] / S); gy = int(y[i] / S)
        if gx < 0 or gy < 0 or gx >= GS or gy >= GS:
            alive[i] = 0
            continue
        c = gy * GS + gx
        t = team[i]
        ow = grid[c]
        if ow == t:
            # opposing-bullet cancellation inside one cell
            if occ_s[c] == stamp and occ_t[c] != t and alive[occ_i[c]] == 1:
                alive[occ_i[c]] = 0
                alive[i] = 0
                continue
            occ_s[c] = stamp; occ_t[c] = t; occ_i[c] = i
            continue
        if ow < 4 and kind[i] != 5 and dead[ow] == 0:
            dx = x[i] - BX[ow]; dy = y[i] - BY[ow]
            if dx * dx + dy * dy < BASE_R * BASE_R:
                dmg[ow] += 1.0
                alive[i] = 0
                continue
        grid[c] = t
        heat[c] = 1.0
        paints[t] += 1
        alive[i] = 0
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
