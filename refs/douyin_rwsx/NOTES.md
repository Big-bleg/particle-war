# douyin_rwsx — War4Balls ep6

Source: https://v.douyin.com/RWSxLzMRJEg/
Final: https://www.douyin.com/video/7692787643410582803
Title: 第6集 | 【领土战争】百万像素+粒子光效+渐变梯度 球球战争 四色领土战争，选择你的颜色
Author: War4Balls (粉丝 2110 / 获赞 9262)
Published: 2026-10-04 20:25
Logged in: no. A modal "登录后免费畅享高清视频" offers 扫码登录 (抖音APP 扫一扫), 验证码登录 (+86 phone + SMS), and 密码登录. Video still played and the page exposed a VOD URL without submitting credentials. Modal can be closed. QR later showed 二维码失效 / 当前网络异常.

File: war4balls_ep6.mp4
- 1920x1080 h264 + aac, duration 1338.9s (22:19), 814,240,499 bytes
- ffprobe clean (not the earlier partial)

## Layout
Left: pachinko board. Fixed multiplier pockets, left to right: x8, x4, x2 | center gap | x2, x4, x8. A ball entering a pocket lights that pocket in the ball's color and increments the number under that pocket.
Below that, a ticker labeled LOOP scrolls five items in a fixed cycle: 风暴, 机枪, 护盾, 大球, 狙击. Screen position is not a stable slot; the same five names rotate. Each has one global count (not per team).

Right: four territories, red / green / blue / yellow, each with a population readout and a side percent bar. Effects are color-matched to the ball's team.

## Does a left landing always fire the matching right effect?
No, not 1:1.

- Multiplier pockets and the item ticker are different systems. There are 6 pockets and 5 item names, so they are not position-paired.
- Pocket counters run far ahead of item counters. At t=45s the two x2 pockets already read ~24 and ~25 while 风暴/机枪/护盾/大球/狙击 were all still 0. At t≈700s pocket counters are ~400+ (x2 ≈ 428 and 411) while item counts are only 大球 23, 狙击 20, 风暴 15, 机枪 14, 护盾 21.
- First item ticks (2s samples, t≈58–92): 狙击 0→1, then 护盾 0→1, then 大球 0→1→2. 风暴 and 机枪 stayed 0 through that window. Items trigger independently and rarely, not on every pocket hit.
- When items are active, the right map does show matching effect types, but sparsely: 大球 → huge team-colored sphere labeled 大球火力 (t≈700, red +34M, plus a 7.8M sphere). 护盾 → geometric shield arcs (blue arcs over blue territory in the same frame). Floating damage numbers (19K–279K, 1.2M, 2M) appear on the territory and are consistent with 狙击/机枪/风暴, but no single sampled frame isolates those three names to a unique effect.
- Many pocket hits happen while the right side is just the ongoing territory flow, with no new labeled effect. So landing in a left multiplier pocket does not always fire a visible matching right-side item effect.

Frames: frames/full_*.png (0, 20, 45, 90, 150, 240, 360, 520, 700, 900, 1100, 1280), frames/bar_*.png (item ticker zooms), frames/bar_seq_58_92.png, frames/mult_70_94_tile.png, frames/right_70_94_tile.png, frames/slots_zoom_0045.png.
