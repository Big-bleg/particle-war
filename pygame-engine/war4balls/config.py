"""Shared constants (ported 1:1 from web-game/js/game.js layout, 1920x1080 space)."""
import math

W, H = 1920, 1080
LEFT = 760                      # marble board width (left panel)
G = 1000                        # territory map size in px
AX, AY = 860, 40                # map origin on screen
WS = 1.75
GS = round(168 * WS)            # 294 territory cells per side
S = G / GS                      # cell size in px
FPS = 60
DT = 1.0 / FPS
MATCH = 660.0

NEUTRAL = 4
BASES = [(120.0, 120.0), (880.0, 120.0), (120.0, 880.0), (880.0, 880.0)]
BASE_R = 100 / WS               # shield radius (bullets hitting inside it chip HP)

TEAMS = [
    dict(name='红队', c=(255, 20, 70), hi=(255, 90, 130), edge=(255, 200, 220)),
    dict(name='绿队', c=(0, 230, 140), hi=(80, 255, 200), edge=(160, 255, 220)),
    dict(name='蓝队', c=(0, 140, 255), hi=(70, 210, 255), edge=(160, 220, 255)),
    dict(name='橙队', c=(255, 165, 20), hi=(255, 220, 80), edge=(255, 240, 180)),
]

# ---- left board -------------------------------------------------------------
GRAV = 300.0
PEG_R = 6.5
GAP = (266.0, 494.0)            # buffer (arrow) strip between the inner x2 cups
BUOY_Y0, BUOY_Y1 = 448.0, 476.0
CUP_FLOOR = 472.0
LPILLARS = [(0, 6, 392), (92, 6, 404), (136, 6, 418), (180, 6, 432), (260, 6, 446)]   # x, w, top (mirrored)
SLOT_X = [(6, 92, 0), (98, 136, 1), (142, 180, 2), (186, 260, 3), (500, 574, 4), (580, 618, 5), (624, 662, 6), (668, 754, 7)]
SLOT_TOP = [398, 410, 424, 438, 438, 424, 410, 398]
MULT = [2, 8, 4, 2, 2, 4, 8, 2]
CLUSTERS = [(190, 240, .9), (570, 240, -.9), (190, 730, -.9), (570, 730, .9)]       # rotating hexagon peg clusters
CLUSTER_R = 62
ITEM_X = [0, 138, 290, 448, 601, 760]
IPILLARS = [(0, 12), (137, 23), (290, 23), (448, 23), (601, 23), (748, 12)]          # item-slot dividers x, w
ITEM_TOP, ITEM_FLOOR = 990.0, 1052.0
ITEM_NAMES = ['散弹', '机枪', '护盾', '大球', '狙击']
ITEM_MIX = [5, 17, 11, 14, 6]   # ref2 observed counts at 6:25; informational, not enforced by the engine
GATE_VALUE = 262144             # 2^18: marbles >= this pass the buffer strip
MG_DURATION = 5.0                # deliberate longer cast window; Game scales this by its match preset
SNIPER_SPEED = 1500.0            # px/s; sniper is a moving projectile, not an instant beam
ITEM_CAST_AIM_DELAY_ENABLED = False  # opt-in: wait for a useful barrel heading after an offensive cast
ITEM_CAST_AIM_DELAY_MAX = 1.5    # simulation seconds; immediate firing remains the default

def marble_radius(v):
    return .85 * (25 if v >= 1e6 else 20 if v >= 1e5 else 18 if v >= 5e4 else 16.5 if v >= 2e4 else 15 if v >= 1e4 else 13 if v >= 1e3 else 10 if v >= 100 else 8.5)

def fmt(v):
    v = max(0.0, float(v))
    if v >= 1e6:
        n = v / 1e6; s = f'{n:.0f}' if n >= 100 else f'{n:.2f}'
        if '.' in s:
            s = s.rstrip('0')
            if s.endswith('.'):
                s += '0'          # 8.0M like the reference HUD
        return s + 'M'
    if v >= 1e3:
        n = v / 1e3; s = f'{n:.0f}' if n >= 100 else f'{n:.1f}'
        return (s[:-2] if s.endswith('.0') else s) + 'K'
    return f'{int(round(v)):,}'

def fmt_score(v):
    return f'{max(0, int(round(v))):,}'

def clamp(v, a, b):
    return a if v < a else b if v > b else v

TAU = math.tau
