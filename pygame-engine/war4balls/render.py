"""moderngl renderer shared by the realtime window and the offline exporter.

Crisp by construction: everything is drawn at native 1920x1080 into a 4x MSAA framebuffer with
analytic SDF anti-aliasing; text is pixel-aligned glyph quads. Bloom is a separate, subtle additive
layer rendered at half resolution and blurred, never a blur of the whole frame."""
import math
import numpy as np
import moderngl
from . import shaders as SH
from .text import Atlas
from .config import (W, H, LEFT, G, GS, AX, AY, BASES, BASE_R, TEAMS, NEUTRAL, PEG_R, GAP, BUOY_Y0, CUP_FLOOR,
                     SLOT_X, SLOT_TOP, MULT, ITEM_X, IPILLARS, ITEM_TOP, ITEM_FLOOR, ITEM_NAMES, GATE_VALUE,
                     CLUSTER_R, fmt, fmt_score, clamp, WS)


def c255(c, a=1.0, k=1.0):
    return (c[0] / 255 * k, c[1] / 255 * k, c[2] / 255 * k, a)


TC = [c255(t['c']) for t in TEAMS]
THI = [c255(t['hi']) for t in TEAMS]
STEEL = (.27, .38, .47, 1.0)
STEEL_HI = (.62, .74, .82, .9)


class Batch:
    """Instanced SDF shapes: rows of 12 floats (x0,y0,x1,y1, r,soft,kind,p, r,g,b,a)."""

    def __init__(self):
        self.rows = []
        self.arrays = []

    def add(self, x0, y0, x1, y1, r, kind, col, soft=0.0, p=0.0):
        self.rows.append((x0, y0, x1, y1, r, soft, kind, p, col[0], col[1], col[2], col[3]))

    def circle(self, x, y, r, col, kind=0, soft=0.0, p=0.0):
        self.add(x, y, x, y, r, kind, col, soft, p)

    def box(self, x0, y0, x1, y1, col, r=0.0, kind=5, soft=0.0, p=0.0):
        self.add(x0, y0, x1, y1, r, kind, col, soft, p)

    def add_array(self, a):
        if len(a):
            self.arrays.append(a.astype(np.float32, copy=False))

    def data(self):
        parts = []
        if self.rows:
            parts.append(np.asarray(self.rows, np.float32))
        parts += self.arrays
        self.rows = []; self.arrays = []
        if not parts:
            return None
        return np.ascontiguousarray(np.concatenate(parts))


class Renderer:
    def __init__(self, ctx: moderngl.Context, samples=4, glow=.55):
        self.ctx = ctx
        self.glow_k = glow
        self.time = 0.0
        ctx.enable(moderngl.BLEND)
        self.corner = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32).tobytes())
        self.p_shape = ctx.program(vertex_shader=SH.SHAPE_VS, fragment_shader=SH.SHAPE_FS)
        self.p_text = ctx.program(vertex_shader=SH.TEXT_VS, fragment_shader=SH.TEXT_FS)
        self.p_terr = ctx.program(vertex_shader=SH.TERR_VS, fragment_shader=SH.TERR_FS)
        self.p_blur = ctx.program(vertex_shader=SH.QUAD_VS, fragment_shader=SH.BLUR_FS)
        self.p_comp = ctx.program(vertex_shader=SH.QUAD_VS, fragment_shader=SH.COMP_FS)
        self.inst_cap = 0; self.inst = None; self.vao_shape = None
        self.tinst_cap = 0; self.tinst = None; self.vao_text = None
        self.vao_terr = ctx.vertex_array(self.p_terr, [(self.corner, '2f', 'in_corner')])
        self.vao_blur = ctx.vertex_array(self.p_blur, [(self.corner, '2f', 'in_corner')])
        self.vao_comp = ctx.vertex_array(self.p_comp, [(self.corner, '2f', 'in_corner')])
        # targets
        samples = min(samples, ctx.max_samples)
        self.msaa = ctx.framebuffer(color_attachments=[ctx.renderbuffer((W, H), 4, samples=samples)]) if samples > 1 else None
        self.scene_tex = ctx.texture((W, H), 4)
        self.scene = ctx.framebuffer(color_attachments=[self.scene_tex])
        hw, hh = W // 2, H // 2
        self.glow_tex = [ctx.texture((hw, hh), 4) for _ in range(2)]
        for t in self.glow_tex + [self.scene_tex]:
            t.filter = (moderngl.LINEAR, moderngl.LINEAR); t.repeat_x = t.repeat_y = False
        self.glow_fbo = [ctx.framebuffer(color_attachments=[t]) for t in self.glow_tex]
        # territory textures
        self.mask_tex = ctx.texture((GS, GS), 4)
        self.mask_tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR); self.mask_tex.repeat_x = self.mask_tex.repeat_y = False
        self.heat_tex = ctx.texture((GS, GS), 1)
        self.heat_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.p_terr['uCol'].write(np.array([c[:3] for c in TC], np.float32).tobytes())
        self.p_terr['uHi'].write(np.array([c[:3] for c in THI], np.float32).tobytes())
        self.p_terr['uBase'].write(np.array(BASES, np.float32).tobytes())
        self.atlas = Atlas(ctx)
        self.eye = np.eye(5, 4, dtype=np.uint8)[:, :] * 255   # team -> one-hot RGBA (row 4 = neutral = 0)
        self.fx = []
        self.rng = np.random.default_rng(12345)
        self.fx_seen = 0

    # ------------------------------------------------------------------ GL helpers
    def _draw_shapes(self, data, additive, scale=1.0, screen=(W, H)):
        if data is None:
            return
        n = len(data)
        if n > self.inst_cap:
            self.inst_cap = max(n, int(self.inst_cap * 1.5), 4096)
            if self.inst:
                self.inst.release()
            self.inst = self.ctx.buffer(reserve=self.inst_cap * 48, dynamic=True)
            self.vao_shape = self.ctx.vertex_array(self.p_shape, [(self.corner, '2f', 'in_corner'), (self.inst, '4f 4f 4f/i', 'a', 'b', 'c')])
        self.inst.write(data.tobytes())
        self.p_shape['uScreen'].value = screen
        self.p_shape['uScale'].value = scale
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE) if additive else (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)
        self.vao_shape.render(moderngl.TRIANGLE_STRIP, instances=n)

    def _draw_text(self, items):
        rows = []
        for (s, size, x, y, col, ocol, align) in items:
            for q in self.atlas.layout(s, size, x, y, align):
                rows.append((q[0], q[1], q[2], q[3], q[4], q[5], q[6], q[7]) + tuple(col) + tuple(ocol))
        if not rows:
            return
        self.atlas.upload()
        data = np.asarray(rows, np.float32)
        n = len(data)
        if n > self.tinst_cap:
            self.tinst_cap = max(n, 2048)
            if self.tinst:
                self.tinst.release()
            self.tinst = self.ctx.buffer(reserve=self.tinst_cap * 64, dynamic=True)
            self.vao_text = self.ctx.vertex_array(self.p_text, [(self.corner, '2f', 'in_corner'), (self.tinst, '4f 4f 4f 4f/i', 'rect', 'uv', 'col', 'ocol')])
        self.tinst.write(data.tobytes())
        self.p_text['uScreen'].value = (W, H)
        self.p_text['uTexel'].value = (1 / Atlas.SIZE, 1 / Atlas.SIZE)
        self.atlas.tex.use(0); self.p_text['uAtlas'].value = 0
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA, moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)
        self.vao_text.render(moderngl.TRIANGLE_STRIP, instances=n)

    # ------------------------------------------------------------------ frame
    def render(self, game, target: moderngl.Framebuffer, viewport=None):
        ctx = self.ctx
        self.time = game.t
        # Procedural sparkle placement must match when rendering a frame directly or from video.
        self.rng = np.random.default_rng((int(game.seed) * 1000003 + int(game.frame)) & 0xFFFFFFFF)
        T = []                                  # text items
        base_a, world_a, world_add, hud_a, hud_add, glow = Batch(), Batch(), Batch(), Batch(), Batch(), Batch()
        self._left(game, base_a, hud_add, T, glow)
        self._map(game, world_a, world_add, hud_a, hud_add, T, glow)
        fb = self.msaa or self.scene
        fb.use(); ctx.viewport = (0, 0, W, H)
        fb.clear(.012, .02, .035, 1.0)
        self._draw_shapes(base_a.data(), False)
        # territory
        self.mask_tex.write(np.ascontiguousarray(self.eye[game.grid]).tobytes()); self.mask_tex.build_mipmaps()
        self.heat_tex.write(np.clip(game.heat * 255, 0, 255).astype(np.uint8).tobytes())
        self.mask_tex.use(0); self.heat_tex.use(1)
        self.p_terr['uMask'].value = 0; self.p_terr['uHeat'].value = 1
        self.p_terr['uScreen'].value = (W, H); self.p_terr['uRect'].value = (AX, AY, G, G)
        ctx.blend_func = (moderngl.ONE, moderngl.ZERO)
        self.vao_terr.render(moderngl.TRIANGLE_STRIP)
        ctx.scissor = (AX, H - AY - G, G, G)          # world layers are clipped to the map
        self._draw_shapes(world_a.data(), False)
        self._draw_shapes(world_add.data(), True)
        ctx.scissor = None
        self._draw_shapes(hud_a.data(), False)
        self._draw_shapes(hud_add.data(), True)
        self._draw_text(T)
        if self.msaa:
            ctx.copy_framebuffer(self.scene, self.msaa)
        # bloom: half-res additive layer, 2 blur passes
        g0, g1 = self.glow_fbo
        g0.use(); ctx.viewport = (0, 0, W // 2, H // 2); g0.clear(0, 0, 0, 0)
        self._draw_shapes(glow.data(), True, scale=.5, screen=(W / 2, H / 2))
        ctx.blend_func = (moderngl.ONE, moderngl.ZERO)
        for _ in range(2):
            g1.use(); self.glow_tex[0].use(0); self.p_blur['uTex'].value = 0; self.p_blur['uDir'].value = (2 / W, 0); self.vao_blur.render(moderngl.TRIANGLE_STRIP)
            g0.use(); self.glow_tex[1].use(0); self.p_blur['uDir'].value = (0, 2 / H); self.vao_blur.render(moderngl.TRIANGLE_STRIP)
        target.use()
        ctx.viewport = viewport or (0, 0, W, H)
        self.scene_tex.use(0); self.glow_tex[0].use(1)
        self.p_comp['uScene'].value = 0; self.p_comp['uGlow'].value = 1; self.p_comp['uGlowK'].value = self.glow_k
        self.vao_comp.render(moderngl.TRIANGLE_STRIP)

    # ------------------------------------------------------------------ left board
    def _left(self, game, B, ADD, T, GL):
        bd = game.board
        B.box(0, 0, LEFT, H, (.045, .085, .13, 1), kind=6, p=.55)
        for x in range(95, LEFT, 95):
            B.add(x, 0, x, H, .5, 0, (.5, .7, .9, .045))
        for y in range(90, H, 90):
            B.add(0, y, LEFT, y, .5, 0, (.5, .7, .9, .045))
        B.box(LEFT - 1, 0, LEFT + 3, H, (.25, .4, .55, .7), kind=5)
        # emitter rail
        B.box(110, 8, LEFT - 110, 14, (.2, .32, .42, .9), r=3)
        # cups
        for x0, x1, slot in SLOT_X:
            f = bd.slot_flash[slot]
            B.box(x0, SLOT_TOP[slot], x1, CUP_FLOOR, (.09, .16, .23, .85), r=3)
            if f > 0:
                B.box(x0, SLOT_TOP[slot], x1, CUP_FLOOR, (.6, .85, 1, .35 * f), r=3)
            cx = (x0 + x1) / 2
            T.append((f'x{MULT[slot]}', 17, cx, (SLOT_TOP[slot] + CUP_FLOOR) / 2 + 2, (1, 1, 1, 1), (0, 0, 0, 0), 'c'))
            T.append((str(bd.hit[slot]), 12, cx, SLOT_TOP[slot] - 11, (.7, .78, .85, 1), (0, 0, 0, 0), 'c'))
        for xx, w, top in bd.pillars:
            r = max(3.0, w / 2); cx = xx + w / 2
            B.add(cx, top + r, cx, CUP_FLOOR, r, 0, STEEL)
            B.add(cx - r * .3, top + r, cx - r * .3, CUP_FLOOR - 2, .6, 0, STEEL_HI)
        B.add(0, CUP_FLOOR + 1, GAP[0], CUP_FLOOR + 1, 2.2, 0, STEEL)
        B.add(GAP[1], CUP_FLOOR + 1, LEFT, CUP_FLOOR + 1, 2.2, 0, STEEL)
        # buffer strip arrows
        B.box(GAP[0] + 4, BUOY_Y0 - 26, GAP[1] - 4, BUOY_Y0 + 4, (.2, .7, 1, .07), r=4)
        n = 16
        for k in range(n):
            x = GAP[0] + 10 + (GAP[1] - GAP[0] - 20) * k / (n - 1)
            y = BUOY_Y0 - 4
            col = (.45, .85, 1, .85)
            B.add(x, y, x, y - 14, 1.0, 0, col)
            B.add(x, y - 15, x - 3.5, y - 10.5, 1.0, 0, col); B.add(x, y - 15, x + 3.5, y - 10.5, 1.0, 0, col)
        B.add(GAP[0] + 2, BUOY_Y0 + 3, (GAP[0] + GAP[1]) / 2, BUOY_Y0, 1.6, 0, (.45, .85, 1, .9))
        B.add((GAP[0] + GAP[1]) / 2, BUOY_Y0, GAP[1] - 2, BUOY_Y0 + 3, 1.6, 0, (.45, .85, 1, .9))
        # rotating peg clusters
        for (x, y) in bd.cluster_pegs():
            B.circle(x, y, PEG_R, (.78, .82, .87, 1), kind=3)
        # item slots
        for k in range(5):
            x0, x1 = ITEM_X[k] + 8, ITEM_X[k + 1] - 8
            f = 0.0
            fl = bd.item_flash[k]
            if fl:
                f = max(0.0, 1 - (game.t - fl[1]) * 1.5)
            B.box(x0 + 6, ITEM_TOP - 46, x1 - 6, ITEM_FLOOR, (.08, .14, .2, .75), r=6)
            if f > 0:
                B.box(x0 + 6, ITEM_TOP - 46, x1 - 6, ITEM_FLOOR, c255(TEAMS[fl[0]]['c'], .45 * f), r=6)
            cx = (ITEM_X[k] + ITEM_X[k + 1]) / 2
            T.append((ITEM_NAMES[k], 21, cx, ITEM_TOP + 4, (.88, .92, .96, 1), (0, 0, 0, 0), 'c'))
            T.append((str(game.item_total[k]), 15, cx, ITEM_FLOOR + 15, (.75, .82, .9, 1), (0, 0, 0, 0), 'c'))
        for x, w in IPILLARS:
            r = w / 2
            B.add(x + r, ITEM_TOP + r, x + r, ITEM_FLOOR, r, 0, STEEL)
            B.add(x + r * .6, ITEM_TOP + r, x + r * .6, ITEM_FLOOR - 2, .7, 0, STEEL_HI)
        B.add(0, ITEM_FLOOR + 2, LEFT, ITEM_FLOOR + 2, 2, 0, STEEL)
        # marbles
        rng = self.rng
        # top emitter spout
        from .board import EMIT
        B.box(EMIT[0] - 22, EMIT[1] - 14, EMIT[0] + 22, EMIT[1] + 6, (.16, .26, .35, 1), r=6)
        B.box(EMIT[0] - 10, EMIT[1] - 4, EMIT[0] + 10, EMIT[1] + 6, (.05, .09, .13, 1), r=4)
        if bd.queue_launch:
            q = bd.queue_launch[0]
            B.circle(EMIT[0], EMIT[1] - 2, 6, TC[q.team], kind=3)
        for m in bd.marbles:
            if m.queued:
                continue
            x, y = m.body.position
            col = TC[m.team]
            if len(m.trail) > 2 and True:
                tx, ty = m.trail[0]
                if math.hypot(x - tx, y - ty) > 3:
                    B.add(tx, ty, x, y, m.r * .8, 4, c255(TEAMS[m.team]['hi'], .45))
            if m.v >= GATE_VALUE and True:                 # sparkle comet for gate-passing values
                for (tx, ty) in m.trail[::2]:
                    ADD.circle(tx + rng.uniform(-m.r, m.r) * .6, ty + rng.uniform(-m.r, m.r) * .6, rng.uniform(.7, 1.7), (1, 1, .9, .9))
            B.circle(x, y, m.r, col, kind=3)
            GL.circle(x, y, m.r * 1.6, c255(TEAMS[m.team]['c'], .35), kind=2)
            size = int(clamp(m.r * 1.05, 12, 24))
            T.append((fmt(m.v), size, x, y, (1, 1, 1, 1), (0, 0, 0, .85), 'c'))
        # board fx (cup hit rings, item pickups)
        for e in bd.fx[self.fx_seen:]:
            self.fx.append(list(e) + [game.t])
        self.fx_seen = len(bd.fx)
        keep = []
        for e in self.fx:
            kind, x, y, team, k, t0 = e[:6]
            age = game.t - t0
            if kind == 'cup' and age < .5:
                ADD.circle(x, y, 8 + age * 60, c255(TEAMS[team]['hi'], (1 - age / .5) * .8), kind=1, p=2)
                keep.append(e)
            elif kind == 'item' and age < 1.2:
                ADD.circle(x, y, 10 + age * 70, c255(TEAMS[team]['hi'], (1 - age / 1.2) * .9), kind=1, p=3)
                T.append((ITEM_NAMES[k] + ' +1', 20, x, y - 30 - age * 40, (1, 1, 1, 1 - age / 1.2), c255(TEAMS[team]['c'], 1 - age / 1.2), 'c'))
                keep.append(e)
        self.fx = keep

    # ------------------------------------------------------------------ map
    def _map(self, g, A, ADD, HA, HADD, T, GL):
        ox, oy = AX, AY
        # frame
        HA.box(ox - 2, oy - 2, ox + G + 2, oy + G + 2, (.35, .55, .75, .55), kind=7, p=1.5)
        # bullets (vectorised): tapered streaks along velocity
        n = g.n
        if n:
            x = g.bx[:n] + ox; y = g.by[:n] + oy; vx = g.bvx[:n]; vy = g.bvy[:n]; tm = g.bteam[:n].astype(np.int64)
            k = 3.2
            hi = np.array([THI[t] for t in range(4)], np.float32)
            arr = np.empty((n, 12), np.float32)
            arr[:, 0] = x - vx * k; arr[:, 1] = y - vy * k; arr[:, 2] = x; arr[:, 3] = y
            arr[:, 4] = 1.25; arr[:, 5] = 0; arr[:, 6] = 4; arr[:, 7] = 0
            arr[:, 8:12] = hi[tm]; arr[:, 11] = .8
            mg = g.bkind[:n] == 7                       # machine-gun rounds: longer, thicker, white-hot
            if mg.any():
                arr[mg, 0] = x[mg] - vx[mg] * 4.5; arr[mg, 1] = y[mg] - vy[mg] * 4.5
                arr[mg, 4] = 2.0
                arr[mg, 8:11] = arr[mg, 8:11] * .45 + .55; arr[mg, 11] = 1.0
            ADD.add_array(arr)
            g2 = arr.copy(); g2[:, 4] = 3.0; g2[:, 11] = .25
            GL.add_array(g2)
        # big balls (no laser lines)
        for p in g.balls:
            x, y, rr = p.x + ox, p.y + oy, p.rr
            col = TC[p.team]; hi = THI[p.team]
            # tube: the carved path behind the ball, bright body fading toward the tail
            tr = p.trail[::5] + [(p.x, p.y)]
            nt = len(tr)
            for k in range(1, nt):
                f = k / nt
                (x0, y0), (x1, y1) = tr[k - 1], tr[k]
                A.add(x0 + ox, y0 + oy, x1 + ox, y1 + oy, rr * .9, 0, (col[0] * .9 + .1, col[1] * .9 + .1, col[2] * .9 + .1, .30 + .35 * f))
                A.add(x0 + ox, y0 + oy, x1 + ox, y1 + oy, rr * .45, 0, (col[0] * .35, col[1] * .35, col[2] * .35, .25 * f))
                ADD.add(x0 + ox, y0 + oy, x1 + ox, y1 + oy, 1.6, 0, (hi[0], hi[1], hi[2], .35 * f))
            GL.circle(x, y, rr * 1.2, c255(TEAMS[p.team]['c'], .8), kind=2)
            ADD.circle(x, y, rr * .9, c255(TEAMS[p.team]['c'], .35), kind=2)
            R = rr * .62
            A.circle(x, y, R, (.015, .02, .03, .96))
            HA.circle(x, y, R, (hi[0], hi[1], hi[2], .95), kind=1, p=3.0)
            T.append((fmt(p.value), int(clamp(R * .5, 16, 34)), x, y, (1, 1, 1, 1), (0, 0, 0, 0), 'c'))
        # opening sniper rounds
        if g.opening:
            for o in g.opening:
                bx, by = BASES[o['t']]
                hi = THI[o['t']]
                ADD.add(bx + ox, by + oy, o['x'] + ox, o['y'] + oy, 5, 4, (hi[0], hi[1], hi[2], .9))
                ADD.circle(o['x'] + ox, o['y'] + oy, 6, (1, 1, 1, 1))
                GL.add(bx + ox, by + oy, o['x'] + ox, o['y'] + oy, 12, 4, (hi[0], hi[1], hi[2], .8))
        for w in g.waves:                      # flood ripple rings
            bx, by = BASES[w['team']]; hi = THI[w['team']]
            a = max(0.0, 1 - w['life'] / 8)
            for k in range(3):
                r = w['r'] - k * 38
                if r > 20:
                    ADD.circle(bx + ox, by + oy, r, (hi[0], hi[1], hi[2], .55 * a * (1 - k * .3)), kind=1, p=3 - k * .7, soft=1)
        if g.burst:
            a = g.burst['life'] / 2
            r = (1 - a) * 260
            HADD.circle(G / 2 + ox, G / 2 + oy, r, (1, 1, 1, a * .7), kind=1, p=3)
            GL.circle(G / 2 + ox, G / 2 + oy, 60 + r * .3, (1, 1, 1, a), kind=2)
        for sn in g.snipers:                  # sniper round: big bright head + long tapered trail + fading painted streak
            hi = THI[sn['team']]; f = 1 - sn['fade'] / .6
            hx, hy = sn['x'] + ox, sn['y'] + oy
            L = math.hypot(sn['x'] - sn['x0'], sn['y'] - sn['y0']) or 1
            ux, uy = (sn['x'] - sn['x0']) / L, (sn['y'] - sn['y0']) / L
            ADD.add(sn['x0'] + ox, sn['y0'] + oy, hx, hy, 5 * f, 0, (hi[0], hi[1], hi[2], .55 * f))
            ADD.add(sn['x0'] + ox, sn['y0'] + oy, hx, hy, 1.6 * f, 0, (1, 1, 1, .8 * f))
            GL.add(sn['x0'] + ox, sn['y0'] + oy, hx, hy, 14 * f, 0, (hi[0], hi[1], hi[2], .7 * f))
            if not sn['done']:
                tl = min(L, 260)
                ADD.add(hx - ux * tl, hy - uy * tl, hx, hy, 11, 4, (hi[0], hi[1], hi[2], 1))
                ADD.add(hx - ux * tl * .6, hy - uy * tl * .6, hx, hy, 5, 4, (1, 1, 1, 1))
                ADD.circle(hx, hy, 9, (1, 1, 1, 1))
                ADD.circle(hx, hy, 26, (hi[0], hi[1], hi[2], .9), kind=2)
                GL.circle(hx, hy, 50, (hi[0], hi[1], hi[2], 1), kind=2)
        for L in g.lasers:
            f = L['life'] / L['max']; hi = THI[L['team']]
            ADD.add(L['x0'] + ox, L['y0'] + oy, L['x1'] + ox, L['y1'] + oy, L['w'] * f, 0, (hi[0], hi[1], hi[2], .8 * f))
            ADD.add(L['x0'] + ox, L['y0'] + oy, L['x1'] + ox, L['y1'] + oy, 1.5 * f, 0, (1, 1, 1, f))
            GL.add(L['x0'] + ox, L['y0'] + oy, L['x1'] + ox, L['y1'] + oy, L['w'] * 2.5 * f, 0, (hi[0], hi[1], hi[2], .8 * f))
        if g.sparks:
            sp = np.asarray(g.sparks, np.float32)
            m = len(sp)
            arr = np.zeros((m, 12), np.float32)
            arr[:, 0] = sp[:, 0] + ox; arr[:, 1] = sp[:, 1] + oy; arr[:, 2] = sp[:, 0] + ox - sp[:, 2] * .03; arr[:, 3] = sp[:, 1] + oy - sp[:, 3] * .03
            arr[:, 4] = 1.4; arr[:, 6] = 0
            hi = np.array([THI[t] for t in range(4)], np.float32)
            arr[:, 8:12] = hi[sp[:, 5].astype(np.int64)]
            arr[:, 11] = np.clip(sp[:, 4], 0, 1)
            ADD.add_array(arr)
        # bases
        for t, (bx, by) in enumerate(BASES):
            x, y = bx + ox, by + oy
            col = TC[t]; hi = THI[t]
            if g.dead[t]:
                HA.circle(x, y, BASE_R, (.78, .82, .86, .22)); HA.circle(x, y, BASE_R, (1, 1, 1, .35), kind=1, p=2)
                T.append(('淘汰', 22, x, y, (1, 1, 1, .85), (0, 0, 0, .8), 'c'))
                continue
            HA.circle(x, y, BASE_R, (col[0] * .25, col[1] * .25, col[2] * .25, .55))
            HADD.circle(x, y, BASE_R, (hi[0], hi[1], hi[2], .95), kind=1, p=3.2)
            HADD.circle(x, y, BASE_R + 7, (col[0], col[1], col[2], .35), kind=1, p=6, soft=4)
            GL.circle(x, y, BASE_R * 1.15, (col[0], col[1], col[2], .5), kind=1, p=10, soft=6)
            a = g.aim[t]; ca, sa = math.cos(a), math.sin(a)
            HA.add(x + ca * 8, y + sa * 8, x + ca * 34, y + sa * 34, 5.5, 0, (.05, .07, .1, .95))
            HA.add(x + ca * 8, y + sa * 8, x + ca * 33, y + sa * 33, 3.0, 0, (hi[0], hi[1], hi[2], 1))
            HA.circle(x, y, 9.5, (.05, .07, .1, 1)); HA.circle(x, y, 7, (1, 1, 1, 1)); HA.circle(x, y, 9.5, (hi[0], hi[1], hi[2], 1), kind=1, p=2)
            if g.mg[t] > 0:                      # machine-gun muzzle flash + spinning ring
                fl = .6 + .4 * math.sin(g.t * 90 + t)
                mx, my = x + ca * 38, y + sa * 38
                HADD.circle(mx, my, 16 * fl + 6, (1, 1, .9, .9), kind=2)
                for k in (-1, 0, 1):
                    aa = a + k * .35
                    HADD.add(mx, my, mx + math.cos(aa) * (18 + 10 * fl), my + math.sin(aa) * (18 + 10 * fl), 2.2, 4, (1, 1, .85, .9))
                HADD.circle(x, y, BASE_R + 12, (hi[0], hi[1], hi[2], .8), kind=1, p=2.5)
                GL.circle(mx, my, 40, (1, 1, .9, .9), kind=2)
                T.append(('机枪', 18, x, y - BASE_R - 16, (1, 1, 1, 1), (hi[0], hi[1], hi[2], 1), 'c'))
            if any(sn['team'] == t and not sn['done'] for sn in g.snipers) or any(sn['team'] == t and sn['fade'] < .3 for sn in g.snipers):
                T.append(('狙击', 18, x, y - BASE_R - 16, (1, 1, 1, 1), (hi[0], hi[1], hi[2], 1), 'c'))
            if g.lock[t] is not None and g.lock[t].alive:
                HA.circle(x, y, 13, (1, .3, .3, .9), kind=1, p=1.5)
            # shield (top) and ammo pool (bottom)
            # shield icon
            HA.box(x - 47, y - 41, x - 35, y - 34, (1, 1, 1, .95), r=1.5)
            HA.add(x - 47, y - 36, x - 41, y - 27, 1.6, 0, (1, 1, 1, .95)); HA.add(x - 35, y - 36, x - 41, y - 27, 1.6, 0, (1, 1, 1, .95))
            HA.add(x - 44, y - 35, x - 38, y - 35, 2.5, 0, (1, 1, 1, .95)); HA.add(x - 43, y - 33, x - 41, y - 29, 2.2, 0, (1, 1, 1, .95))
            T.append((fmt(g.hp[t]), 22, x - 28, y - 33, (1, 1, 1, 1), (0, 0, 0, .7), 'l'))
            HA.box(x - 50, y + 16, x + 50, y + 38, (.02, .04, .06, .75), r=5)
            T.append(((fmt(g.ammo[t]) if g.ammo[t] >= 1e6 else fmt_score(g.ammo[t])), 15, x + 6, y + 27, (1, 1, 1, 1), (0, 0, 0, 0), 'c'))
            HA.box(x - 44, y + 25, x - 30, y + 29, (.9, .9, .9, .9), r=1)
        # floaters
        for f in g.floaters:
            a = min(1.0, f['life'] / .4); rise = (f['max'] - f['life']) * 22
            same = [q for q in g.floaters if q['team'] == f['team']]
            st = same.index(f)
            T.append((f['text'], 24, f['x'] + ox, f['y'] + oy - rise - st * 22, (1, 1, 1, a), c255(TEAMS[f['team']]['c'], a), 'c'))
        # side share meters
        for t in range(4):
            mx = ox - 34 if t in (0, 2) else ox + G + 34
            y0 = oy + (40 if t < 2 else G / 2 + 40); y1 = y0 + G / 2 - 120
            col = TC[t]; hi = THI[t]
            HA.add(mx, y0, mx, y1, 2.2, 0, (.2, .28, .36, .9))
            fy = y1 - (y1 - y0) * clamp(g.share[t] / .5, 0, 1)
            HADD.add(mx, fy, mx, y1, 2.6, 0, (hi[0], hi[1], hi[2], .95))
            for q in (.25, .5, .75):
                yy = y1 - (y1 - y0) * q
                HA.add(mx - 5, yy, mx + 5, yy, .7, 0, (.6, .7, .8, .6))
            T.append((f'{g.share[t] * 100:.2f}%', 17, mx, y0 - 22, (hi[0], hi[1], hi[2], 1), (0, 0, 0, 0), 'c'))
        # timer
        tt = int(g.t)
        T.append((f'{tt // 60:02d}:{tt % 60:02d}', 18, ox + G / 2, oy - 20, (.85, .9, .95, 1), (0, 0, 0, 0), 'c'))
        if g.over and g.winner >= 0:
            HA.box(ox + G / 2 - 150, oy + 18, ox + G / 2 + 150, oy + 72, (.02, .03, .05, .5), r=12)
            T.append((TEAMS[g.winner]['name'] + ' 获胜', 34, ox + G / 2, oy + 45, c255(TEAMS[g.winner]['hi']), (0, 0, 0, .8), 'c'))
