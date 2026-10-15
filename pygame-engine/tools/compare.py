"""Side-by-side sheet: our frames vs reference frames.
usage: python tools/compare.py shots_dir seed out.png 2:douyin_detail_t0000 30:douyin_detail_t0030 ..."""
import sys, os, glob
from PIL import Image, ImageDraw
REFS = os.path.join(os.path.dirname(__file__), '..', '..', 'refs')
d, seed, out = sys.argv[1], sys.argv[2], sys.argv[3]
pairs = [a.split(':') for a in sys.argv[4:]]
cw, ch = 960, 540
sheet = Image.new('RGB', (cw * 2, (ch + 24) * len(pairs)), (8, 10, 14))
dr = ImageDraw.Draw(sheet)
for i, (t, ref) in enumerate(pairs):
    ours = sorted(glob.glob(os.path.join(d, f'frame_s{seed}_t{float(t):07.2f}.png')))
    y = i * (ch + 24)
    if ours:
        sheet.paste(Image.open(ours[0]).convert('RGB').resize((cw, ch), Image.LANCZOS), (0, y + 24))
    rp = os.path.join(REFS, ref + '.png')
    if os.path.exists(rp):
        im = Image.open(rp).convert('RGB'); im.thumbnail((cw, ch), Image.LANCZOS)
        sheet.paste(im, (cw, y + 24))
    dr.text((8, y + 5), f'ours seed {seed} t={t}s', fill='white'); dr.text((cw + 8, y + 5), ref, fill='white')
sheet.save(out); print(out)
