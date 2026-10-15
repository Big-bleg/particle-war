"""War4Balls - Python + moderngl edition.

  python main.py                                   realtime window (watch / play)
  python main.py --export out.mp4 --seed 7 --duration 660
  python main.py --shots 2,30,300 --seed 7         write PNG frames at those seconds
"""
import argparse
import os
import subprocess
import sys
import time

from war4balls.config import W, H, DT, FPS


def build_args():
    ap = argparse.ArgumentParser(description='War4Balls (moderngl)')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--match', type=float, default=660.0, help='match length preset in seconds (660 standard, 300 = 5-minute story cut)')
    ap.add_argument('--player', type=int, default=0, help='team you control with keys 1-5 (0 red,1 green,2 blue,3 orange)')
    ap.add_argument('--export', metavar='OUT.mp4', help='render offline video instead of opening a window')
    ap.add_argument('--start', type=float, default=0.0, help='export: simulate (without rendering) up to this second first')
    ap.add_argument('--duration', type=float, default=660.0, help='export: seconds of video')
    ap.add_argument('--crf', type=int, default=12, help='export: x264 quality (lower = higher bitrate)')
    ap.add_argument('--preset', default='slow')
    ap.add_argument('--shots', help='comma list of seconds: save PNG frames (headless) and exit')
    ap.add_argument('--outdir', default='shots')
    ap.add_argument('--samples', type=int, default=4, help='MSAA samples')
    ap.add_argument('--glow', type=float, default=.55, help='bloom strength (subtle additive layer)')
    ap.add_argument('--window', default='1600x900', help='realtime window size')
    return ap.parse_args()


def headless_ctx():
    import moderngl
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    for kw in ({}, {'backend': 'egl'}):
        try:
            return moderngl.create_standalone_context(require=330, **kw)
        except Exception as e:  # noqa
            err = e
    raise SystemExit(f'could not create an OpenGL 3.3 context: {err}')


def run_offline(a):
    import moderngl
    import numpy as np
    from war4balls.sim import Game
    from war4balls.render import Renderer
    ctx = headless_ctx()
    print('GL:', ctx.info['GL_RENDERER'], file=sys.stderr)
    tex = ctx.texture((W, H), 3)
    fbo = ctx.framebuffer(color_attachments=[tex])
    game = Game(seed=a.seed, player=a.player, match=a.match)
    rnd = Renderer(ctx, samples=a.samples, glow=a.glow)
    if a.shots:
        from PIL import Image
        os.makedirs(a.outdir, exist_ok=True)
        times = sorted(float(s) for s in a.shots.split(','))
        for T in times:
            while game.t < T - 1e-9 and not game.over:
                game.tick(DT)
            rnd.render(game, fbo)
            img = Image.frombytes('RGB', (W, H), fbo.read(components=3)).transpose(Image.FLIP_TOP_BOTTOM)
            p = os.path.join(a.outdir, f'frame_s{a.seed}_t{T:07.2f}.png')
            img.save(p); print(p, flush=True)
        return
    while game.t < a.start - 1e-9 and not game.over:
        game.tick(DT)
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
           '-vf', 'vflip', '-c:v', 'libx264', '-preset', a.preset, '-crf', str(a.crf), '-profile:v', 'high', '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', a.export]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frames = int(round(a.duration * FPS)); t0 = time.time()
    for f in range(frames):
        game.tick(DT)
        rnd.render(game, fbo)
        ff.stdin.write(fbo.read(components=3))
        if f % 300 == 0:
            el = time.time() - t0
            print(f'frame {f}/{frames}  sim t={game.t:.1f}s  {f / max(el, 1e-6):.1f} fps', file=sys.stderr, flush=True)
    ff.stdin.close(); ff.wait()
    print('wrote', a.export, f'({frames} frames, winner={game.winner})')


def run_realtime(a):
    import pygame
    import moderngl
    from war4balls.sim import Game
    from war4balls.render import Renderer
    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
    ww, wh = (int(v) for v in a.window.split('x'))
    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    def set_mode(size, fl):
        try:
            return pygame.display.set_mode(size, fl, vsync=1)
        except pygame.error:                       # some drivers refuse vsync
            return pygame.display.set_mode(size, fl)
    set_mode((ww, wh), flags)
    pygame.display.set_caption('War4Balls  [space] pause  [1-5] items  [+/-] speed  [R] restart  [F11] fullscreen')
    ctx = moderngl.create_context()
    game = Game(seed=a.seed, player=a.player, match=a.match)
    rnd = Renderer(ctx, samples=a.samples, glow=a.glow)
    clock = pygame.time.Clock()
    acc = 0.0; speed = 1.0; paused = False; full = False
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit(); return
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_SPACE: paused = not paused
                elif e.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS): speed = min(8.0, speed * 2)
                elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS): speed = max(.25, speed / 2)
                elif e.key == pygame.K_r: game = Game(seed=game.seed + 1, player=a.player, match=a.match); rnd = Renderer(ctx, samples=a.samples, glow=a.glow)
                elif e.key == pygame.K_F11:
                    full = not full
                    set_mode((0, 0) if full else (ww, wh), flags | (pygame.FULLSCREEN if full else 0))
                elif pygame.K_1 <= e.key <= pygame.K_5: game.use(game.player, e.key - pygame.K_1)
        dt = clock.tick(144) / 1000.0
        if not paused:
            acc = min(acc + dt * speed, .25)
            steps = 0
            while acc >= DT and steps < 32:
                game.tick(DT); acc -= DT; steps += 1
        sw, sh = pygame.display.get_window_size()
        s = min(sw / W, sh / H); vw, vh = int(W * s), int(H * s)
        ctx.screen.use(); ctx.viewport = (0, 0, sw, sh); ctx.clear(0, 0, 0)
        rnd.render(game, ctx.screen, viewport=((sw - vw) // 2, (sh - vh) // 2, vw, vh))
        pygame.display.flip()


if __name__ == '__main__':
    args = build_args()
    if args.export or args.shots:
        run_offline(args)
    else:
        run_realtime(args)
