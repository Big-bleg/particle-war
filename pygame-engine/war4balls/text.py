"""Glyph atlas text for moderngl: each glyph rasterised once by pygame-ce at the exact pixel size,
drawn as pixel-aligned quads (crisp at native resolution), outline done in the shader."""
import os
import sys
import numpy as np
import pygame

FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), '..', 'assets', 'font.ttf'),
    os.path.join(os.path.dirname(__file__), '..', 'assets', 'font.otf'),
    r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


class Atlas:
    SIZE = 2048
    PAD = 3

    def __init__(self, ctx):
        if not pygame.font.get_init():
            pygame.font.init()
        self.ctx = ctx
        self.path = find_font()
        if self.path is None:
            print('warning: no CJK font found, put one at assets/font.ttf', file=sys.stderr)
        self.fonts = {}
        self.glyphs = {}
        self.img = np.zeros((self.SIZE, self.SIZE), np.uint8)
        self.tex = ctx.texture((self.SIZE, self.SIZE), 1, dtype='f1')
        self.tex.filter = (ctx.LINEAR, ctx.LINEAR)
        self.cx = self.cy = 0; self.row = 0
        self.dirty = False

    def font(self, size):
        f = self.fonts.get(size)
        if f is None:
            f = pygame.font.Font(self.path, size) if self.path else pygame.font.SysFont('microsoftyahei,simhei,arial', size, bold=True)
            self.fonts[size] = f
        return f

    def glyph(self, ch, size):
        key = (ch, size)
        g = self.glyphs.get(key)
        if g is not None:
            return g
        f = self.font(size)
        surf = f.render(ch, True, (255, 255, 255))
        w, h = surf.get_size()
        a = pygame.surfarray.array_alpha(surf).T if w > 0 else np.zeros((h, 0), np.uint8)
        P = self.PAD
        if self.cx + w + 2 * P > self.SIZE:
            self.cx = 0; self.cy += self.row; self.row = 0
        if self.cy + h + 2 * P > self.SIZE:          # atlas full: reset (rare)
            self.glyphs.clear(); self.img[:] = 0; self.cx = self.cy = self.row = 0
        x, y = self.cx + P, self.cy + P
        self.img[y:y + h, x:x + w] = a
        self.cx += w + 2 * P; self.row = max(self.row, h + 2 * P)
        g = (x, y, w, h, f.size(ch)[0])
        self.glyphs[key] = g
        self.dirty = True
        return g

    def upload(self):
        if self.dirty:
            self.tex.write(self.img.tobytes()); self.dirty = False

    def measure(self, text, size):
        return sum(self.glyph(c, size)[4] for c in text)

    def layout(self, text, size, x, y, align='c', valign='c'):
        """Return list of quads (x, y, w, h, u0, v0, u1, v1) in pixels, pixel-aligned."""
        width = self.measure(text, size)
        h = self.font(size).get_height()
        ox = x - (width / 2 if align == 'c' else width if align == 'r' else 0)
        oy = y - (h / 2 if valign == 'c' else h if valign == 'b' else 0)
        ox = round(ox); oy = round(oy)
        out = []
        S = self.SIZE
        for c in text:
            gx, gy, w, gh, adv = self.glyph(c, size)
            if w:
                out.append((ox, oy, w, gh, gx / S, gy / S, (gx + w) / S, (gy + gh) / S))
            ox += adv
        return out
