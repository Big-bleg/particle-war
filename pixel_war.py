#!/usr/bin/env python3
"""城市像素领地战 - 生成竖屏/横屏短视频."""
import argparse, subprocess, wave, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TEAMS = [("北京", (255, 64, 64)), ("上海", (64, 160, 255)), ("广州", (255, 200, 0)),
         ("深圳", (0, 230, 140)), ("成都", (200, 90, 255)), ("杭州", (0, 230, 255)),
         ("武汉", (255, 130, 30)), ("西安", (255, 105, 200))]
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FPS = 30

def simulate(seed, gw, gh, nteams, max_steps, record=False):
    rng = np.random.default_rng(seed)
    grid = np.zeros((gh, gw), np.int8)
    # Voronoi seeding
    pts = np.stack([rng.integers(0, gh, nteams), rng.integers(0, gw, nteams)], 1)
    yy, xx = np.mgrid[0:gh, 0:gw]
    d = np.stack([(yy - p[0])**2 + (xx - p[1])**2 for p in pts])
    grid[:] = d.argmin(0)
    base = rng.uniform(0.8, 1.2, nteams)
    boost = np.ones(nteams); boost_t = np.zeros(nteams, int)
    frames, events, shares_hist = [], [], []
    alive = np.ones(nteams, bool)
    total = gw * gh
    for step in range(max_steps):
        counts = np.bincount(grid.ravel(), minlength=nteams)
        share = counts / total
        for t in range(nteams):
            if alive[t] and counts[t] == 0:
                alive[t] = False; events.append((step, "elim", t))
        shares_hist.append(share.copy())
        if record: frames.append(grid.copy())
        if alive.sum() <= 1: break
        # random event: 爆发
        if step > 60 and rng.random() < 0.012:
            cand = np.flatnonzero(alive)
            t = rng.choice(cand)
            boost[t] = 3.0; boost_t[t] = 45
            events.append((step, "burst", t))
        boost_t -= 1; boost[boost_t <= 0] = 1.0
        base = np.clip(base * rng.uniform(0.97, 1.03, nteams), 0.5, 2.0)
        # strength: base * boost, mild underdog bonus, mild momentum
        prog = step / max_steps
        under = (0.6 + 0.4 / np.sqrt(np.maximum(share, 1e-3) * nteams)) ** max(0.0, 1 - 2 * prog)
        momentum = (np.maximum(share, 1e-3) * nteams) ** (1.2 * prog)
        strength = base * boost * under * momentum
        aggro = 0.3 + 0.6 * step / max_steps
        for _ in range(2):
            dy, dx = [(0, 1), (0, -1), (1, 0), (-1, 0)][rng.integers(4)]
            nb = np.roll(grid, (dy, dx), (0, 1))
            diff = nb != grid
            if dy == 1: diff[0, :] = False
            if dy == -1: diff[-1, :] = False
            if dx == 1: diff[:, 0] = False
            if dx == -1: diff[:, -1] = False
            sn, ss = strength[nb], strength[grid]
            p = aggro * sn / (sn + ss)
            cap = diff & (rng.random(grid.shape) < p)
            grid[cap] = nb[cap]
    return dict(frames=frames, events=events, shares=np.array(shares_hist), steps=len(shares_hist))

def drama_score(r, max_steps):
    s = r["shares"]; leader = s.argmax(1)
    lead_changes = int((np.diff(leader[30:]) != 0).sum())
    win = leader[-1]
    ranks = (-s).argsort(1).argsort(1)[:, win]
    comeback = ranks[len(s)//4:].max()          # 赢家最低曾排第几
    tail = s[int(len(s)*0.7):]; st = np.sort(tail, 1)
    closeness = 1 - (st[:, -1] - st[:, -2]).mean()
    finished = s[-1].max() > 0.999
    length_ok = 0.7 * max_steps <= r["steps"] <= max_steps
    bursts = sum(e[1] == "burst" for e in r["events"])
    score = min(lead_changes, 15) * 1.0 + comeback * 2.5 + closeness * 8 + finished * 6 + length_ok * 6 + min(bursts, 8) * 0.3
    return score, dict(lead_changes=lead_changes, comeback_rank=int(comeback) + 1, closeness=round(float(closeness), 3),
                       finished=bool(finished), steps=r["steps"], bursts=bursts)

def font(sz): return ImageFont.truetype(FONT, sz)

def render(r, teams, W, H, out, end_secs=2.0, audio=True):
    horiz = W > H
    names = [t[0] for t in teams]; cols = np.array([t[1] for t in teams] + [(0, 0, 0)], np.uint8)
    gh, gw = r["frames"][0].shape
    if horiz: gx, gy, gwpx, ghpx = 40, 100, 1080, 920
    else: gx, gy, gwpx, ghpx = 0, 330, 1080, 1320
    fT, fM, fS, fB = font(72 if not horiz else 56), font(40), font(34), font(110)
    ev = {}
    for st, kind, t in r["events"]: ev.setdefault(st, []).append((kind, t))
    nframes = len(r["frames"]) + int(end_secs * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    wav = out + ".wav"
    if audio:
        make_audio(r, wav, nframes); cmd += ["-i", wav, "-c:a", "aac", "-b:a", "96k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    banners = []  # (text, color, until_frame)
    elim_order = []
    preview = None
    for f in range(nframes):
        fi = min(f, len(r["frames"]) - 1)
        share = r["shares"][fi]
        img = Image.new("RGB", (W, H), (18, 18, 28)); d = ImageDraw.Draw(img)
        g = Image.fromarray(cols[r["frames"][fi]]).resize((gwpx, ghpx), Image.NEAREST)
        img.paste(g, (gx, gy))
        for kind, t in ev.get(fi, []) if f < len(r["frames"]) else []:
            if kind == "elim":
                elim_order.append(t); banners.append((f"{names[t]} 出局！", (255, 80, 80), f + 50))
            else: banners.append((f"{names[t]} 爆发！战力×3", teams[t][1], f + 40))
        title = "城市像素领地战 谁能统一？"
        tw = d.textlength(title, font=fT)
        tx = (W - tw) / 2 if not horiz else gx
        d.text((tx, 30 if not horiz else 18), title, font=fT, fill="white", stroke_width=4, stroke_fill="black")
        if not horiz:
            d.text((40, 130), f"第 {fi} 回合", font=fS, fill=(200, 200, 200))
        # leaderboard
        order = [t for t in np.argsort(-share)]
        if horiz: lx, ly, lw, rowh = 1170, 100, 700, 110
        else: lx, ly, lw, rowh = 40, 1680, 1000, 0
        if horiz:
            for i, t in enumerate(order):
                y = ly + i * rowh
                c = tuple(int(v) for v in cols[t]) if share[t] > 0 else (90, 90, 90)
                d.text((lx, y), names[t], font=fM, fill=c)
                bw = int((lw - 260) * share[t])
                d.rectangle([lx + 110, y + 10, lx + 110 + max(bw, 2), y + 50], fill=c)
                d.text((lx + 120 + bw, y + 4), f"{share[t]*100:.1f}%" if share[t] > 0 else "已淘汰", font=fS, fill="white")
        else:
            # 4x2 compact grid board at bottom
            cw = 250
            for i, t in enumerate(order):
                x = lx + (i % 4) * cw; y = ly + (i // 4) * 115
                c = tuple(int(v) for v in cols[t]) if share[t] > 0 else (90, 90, 90)
                d.text((x, y), f"{i+1}.{names[t]}", font=fS, fill=c)
                d.rectangle([x, y + 52, x + cw - 20, y + 82], outline=(70, 70, 80))
                d.rectangle([x, y + 52, x + int((cw - 20) * share[t]), y + 82], fill=c)
                lab = f"{share[t]*100:.1f}%" if share[t] > 0 else "已淘汰"
                d.text((x + cw - 25 - d.textlength(lab, font=font(26)), y + 4), lab, font=font(26), fill="white")
            # horizontal stacked bar
            x0 = 40
            for t in order:
                w = share[t] * 1000
                d.rectangle([x0, 200, x0 + w, 250], fill=tuple(int(v) for v in cols[t])); x0 += w
            d.text((40, 260), "领地占比", font=font(28), fill=(180, 180, 180))
        banners = [b for b in banners if b[2] > f]
        for i, (txt, c, _) in enumerate(banners[-2:]):
            bw = d.textlength(txt, font=fM)
            cx = gx + gwpx / 2; cy = gy + 60 + i * 80
            d.rounded_rectangle([cx - bw/2 - 25, cy - 8, cx + bw/2 + 25, cy + 62], 18, fill=(0, 0, 0))
            d.text((cx - bw/2, cy), txt, font=fM, fill=c)
        if f >= len(r["frames"]):
            w = order[0]; ov = Image.new("RGBA", (W, H), (0, 0, 0, 170)); img.paste(ov, (0, 0), ov); d = ImageDraw.Draw(img)
            c = tuple(int(v) for v in cols[w])
            for txt, fnt, y, fill in [("🏆 冠军" if False else "冠 军", fM, H/2 - 200, "white"),
                                       (f"{names[w]} 统一全城！" if share[w] > 0.999 else f"{names[w]} 称霸！", fB, H/2 - 120, c),
                                       (f"占领 {share[w]*100:.1f}%  ·  共 {fi} 回合", fM, H/2 + 50, "white")]:
                tw = d.textlength(txt, font=fnt)
                d.text(((W - tw)/2, y), txt, font=fnt, fill=fill, stroke_width=5, stroke_fill="black")
        if f == nframes // 2: preview = img.copy()
        ff.stdin.write(img.tobytes())
    ff.stdin.close(); ff.wait()
    if audio and os.path.exists(wav): os.remove(wav)
    return preview

def make_audio(r, path, nframes, sr=44100):
    n = int(nframes / FPS * sr); a = np.zeros(n)
    def blip(t0, f0, f1, dur, vol):
        i = int(t0 * sr); m = int(dur * sr); tt = np.arange(m) / sr
        fr = np.linspace(f0, f1, m); ph = 2 * np.pi * np.cumsum(fr) / sr
        s = np.sin(ph) * np.exp(-tt * 6 / dur) * vol
        a[i:i + m] += s[:max(0, min(m, n - i))]
    for st, kind, t in r["events"]:
        if kind == "elim": blip(st / FPS, 660, 180, 0.45, 0.5)
        else: blip(st / FPS, 400, 1200, 0.25, 0.3)
    end = len(r["frames"]) / FPS
    for k, fq in enumerate([523, 659, 784, 1047]): blip(end + k * 0.15, fq, fq, 0.6, 0.35)
    pcm = (np.clip(a, -1, 1) * 32000).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())

def main():
    ap = argparse.ArgumentParser(description="城市像素领地战")
    ap.add_argument("--seeds", type=int, default=30, help="候选随机种子数")
    ap.add_argument("--seed-start", type=int, default=1)
    ap.add_argument("--seed", type=int, help="直接指定种子(跳过筛选)")
    ap.add_argument("--teams", type=int, default=8, help="队伍数 2-8")
    ap.add_argument("--duration", type=float, default=38, help="对战最长秒数(不含结尾2秒)")
    ap.add_argument("--horizontal", action="store_true", help="横屏1920x1080")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--out", default="sample.mp4"); ap.add_argument("--preview", default="preview.png")
    a = ap.parse_args()
    teams = TEAMS[:a.teams]
    W, H = (1920, 1080) if a.horizontal else (1080, 1920)
    gw, gh = (120, 102) if a.horizontal else (120, 147)
    max_steps = int(a.duration * FPS)
    if a.seed is None:
        best = None
        for s in range(a.seed_start, a.seed_start + a.seeds):
            r = simulate(s, gw, gh, len(teams), max_steps)
            sc, info = drama_score(r, max_steps)
            print(f"seed {s}: score {sc:.2f} {info}")
            if best is None or sc > best[0]: best = (sc, s, info)
        print(f"选中 seed {best[1]} score {best[0]:.2f} {best[2]}"); seed = best[1]
    else: seed = a.seed
    r = simulate(seed, gw, gh, len(teams), max_steps, record=True)
    pv = render(r, teams, W, H, a.out, audio=not a.no_audio)
    pv.save(a.preview); print("done", a.out, a.preview)

if __name__ == "__main__": main()
