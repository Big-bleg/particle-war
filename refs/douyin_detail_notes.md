# Douyin territory-war reference frames

Source: https://www.douyin.com/video/7686048115266178356 (short: https://v.douyin.com/TIvEuMYLf2E/)
Title (page): 【领土战争】百万像素+粒子光效+渐变梯度… · creator War4Balls
Duration: 16:18 (978.0 s). Frames extracted with ffmpeg `-ss` from the full VOD MP4 (1920×1080).
Cadence: every 10 s from 00:00 through 05:00, then every 30 s from 05:30 through 16:00, plus 16:10 (end card).
Count: 54 PNGs in this directory, named `douyin_detail_tMMSS.png`.

## Persistent layout (almost every gameplay frame)

Split screen, no Douyin chrome (clean game capture).

**Left — Plinko / ball-drop board**
- Dark navy grid, faint lines, scattered white peg dots.
- Mid-row of translucent multiplier gates, left-to-right roughly `X8 X4 X2 | X2 X4 X8`, each with a small count under it. Counts climb through the video (early single digits → ~100 / ~400 by the end).
- Colored balls (red / green / blue / yellow) fall and bounce; floating power labels (`1K`…`67M` / `537M`) ride on them. Thin colored trails follow high-value balls.
- Bottom item bar, five slots left to right: **风暴** (storm), **机枪** (machine gun), **护盾** (shield), **大球** (big ball), **狙击** (sniper). Each slot shows an icon and a use-count. A slot sometimes flashes its team color when it fires (e.g. 风暴 orange, 狙击 green, 机枪 pink).

**Right — territory map**
- Four corner bases on a dark grid: **red** top-left, **green** top-right, **blue** bottom-left, **yellow** bottom-right.
- Each base is a glowing **ring** with a shield icon, a large **火力** number (tens of millions, later hundreds of millions), and a smaller particle / pixel count under it.
- Edge **gradient bars** (0–100%, sometimes `/800` or later `/1300`) sit on the outer sides: red left-top, green right-top, blue left-bottom, yellow right-bottom. The number is territory share.
- Attacks are **beams**: solid neon strokes, dotted particle fans, concentric ripple rings, and thick “snake” / blob strokes with a black power bubble (`19K`…`347M`) on the tip.
- Territory fill is a soft color **gradient** blob with a jagged, pixelated front. Empty map stays near-black with star-like particles.

Colors: red, green, blue, yellow/gold. Later the map is often dominated by blue + yellow while red/green rings shrink or go hollow (`0`).

## Per-frame notes

### t0000 — 00:00
Empty start. Left: peg field, gates all `0`, item bar all `0`, no balls. Right: four tiny rings at the corners, each **狙击火力 +1M / 0.00**, edge bars **0.00%**. No beams, no territory fill.

### t0010 — 00:10
Left: first colored balls and short trails over the pegs; gate counts 1–6; item bar still 0. Right: four quadrant blobs already meeting at center in an X of beams. Rings ~**24.97M / 432k** (red, green), blue **24.82M / 428k**, yellow **24.98M / 432k**. Edge bars still 0%.

### t0020 — 00:20
Left: more balls, a long green beam from top, gate counts ~2–11, item bar 0. Right: quadrant fills with dotted particle fans into the center cross. Rings ~**24.99M** (red/green/yellow) and blue **24.84M**; particle counts ~360k. Edge ~0.5–0.9%.

### t0030 — 00:30
Left: dense small balls (`1K`–`4.1K`), long green diagonal. Gates up to 15. Item bar 0. Right: thicker particle hair from each ring; red/green/yellow ~**24.99M / ~320k**, blue **24.84M / 329k**. Edge **2.25–2.88%**.

### t0040 — 00:40
Left: `16K`/`66K` balls, gold and blue trails. Gates 5–20. Item bar 0. Right: cleaner quadrant split, blue pushed toward the bottom. Rings still ~24.8–25.0M / ~290k. Edge **5.75–6.38%**.

### t0050 — 00:50
Left: cluster of `16K`–`66K` just above the gates; a `66K` ball has reached the **护盾** slot. Gates 2–24. Right: four-way jagged border, green/yellow particle fans strong. Edge ~**8.9–9.4%**.

### t0100 — 01:00
Left: big gold **1M** ball on the left, `33K`–`131K` elsewhere, crossing red/green beams. Gates 3–28. Item bar 0. Right: red owns the top, blue a thin bottom band, yellow the lower right. Rings: red **25.06M / 241k** (11.75%), green **24.99M** (12.13%), blue **24.84M** (11.38%), yellow **24.99M** (12.00%).

### t0110 — 01:10
Left: two gold **1M** balls, vertical blue beam, gate counts 3–31. Item bar ticks: 风暴 1, 机枪 2, 大球 1. Right: red fill with a dotted arc; blue ring pops **大球火力 +66K** and a small cyan blob (13.00%). Yellow 14.88%, green 15.13%, red 14.50%.

### t0120 — 01:20
Left: gold **1M** mid-board, green **262K** near right gates. Item bar 3/3/0/1/0. Right: thick **blue diagonal beam** cutting red/yellow; blue particle count jumps to **1.1199M** inside the ring (火力 24.84M, 16.75%).

### t0130 — 01:30
Left: sparser board, gold trail top-left. Item bar 3/1/0/2/0. Right: yellow **beam with 167K bubble** stabbing through red into blue. Blue particle count **1.0213M**. Edge ~19.5–19.9%.

### t0140 — 01:40
Left: crossed red and green beams, `1K`–`16K` balls. Item bar 3/3/0/2/1. Right: green and blue beams cross the lower half; blue particles **826k** (22.88%), green edge 21.75%.

### t0150 — 01:50
Left: long blue diagonals, `66K` green ball low. Item bar 3/1/0/2/1, a `66K` sitting on 机枪. Right: blue has eaten the lower-left/center; red ring down to **23.83M / 149k** (23.13%). Blue **24.77M / 722k** (27%).

### t0200 — 02:00
Left: quieter, a few `16K`–`83K`. Item bar 4/5/0/3/1. Right: blue dominates bottom-left with a wide particle fan; green holds top-right (27%). Yellow squeezed bottom-right (25%). Red 23.88%.

### t0210 — 02:10
Left: red vertical beam from a `262K`, gold `131K`. Item bar 4/6/0/3/2. Right: a long **cyan beam** from blue’s ring up into green. Green edge **29.75%**, blue **37.25%**. Red still a round ring (23.83M).

### t0220 — 02:20
Left: balls bunched on the gate line (`131K`, `262K`). Item bar 4/6/0/3/2. Right: blue fill is a huge dark-blue mass; green a top-right wedge (33.38%). Rings ~23.8–25.1M.

### t0230 — 02:30
Left: `524K` blue and green balls at the gates. Item bar 4/6/0/3/2. Right: blue ~**46%**, a clean curved front against red (top) and a small yellow corner (27.75%). Green 36.25%.

### t0240 — 02:40
Left: gold **1M** on the right X2 gate, green `524K` high. Item bar 4/8/0/3/2. Right: blue **51.13%** with a long particle comet; yellow nearly pinched (28.63%, particles only 76k).

### t0250 — 02:50
Left: green **1M** and gold `524K` on the gate glow; **风暴** slot lit orange (count 5). Item bar 5/8/0/3/2. Right: yellow ring flares (**风暴火力** style pop, huge yellow disk, 29.25%) while blue leads at **56.75%**. Green shows **护盾** buff text **+524K**.

### t0300 — 03:00
Left: crossed red/blue beams, `131K` on the gates. Item bar 6/8/0/3/2. Right: **yellow storm** — concentric dotted arcs flood the center from the yellow ring (火力 25.10M but particles only 54k, edge 29.88%). Blue still 59.50%. Red a small top-left ring.

### t0310 — 03:10
Left: gold **1M**, red/gold beams; **风暴** slot flashing. Item bar 7/8/0/3/2. Right: yellow arcs everywhere; red ring shows **风暴火力 +524K** and is half-covered (32.88%). Blue 60.38%, yellow edge **40.75%**.

### t0320 — 03:20
Left: calmer, a red `524K` low, item bar 9/8/0/4/2. Right: red recovering as a big top blob (**33.13%**) with white ripple rings; a **cyan beam** with **174K** bubble runs from blue toward yellow. Yellow edge **48.88%**.

### t0330 — 03:30
Left: green diagonal, a **2.1M** gold ball. Gates up to 101. Item bar 9/8/7/4/2 (护盾 now 7). Right: **blue flood** — dense cyan particle field and a **164K** beam; blue edge **66.38%**. Red pinched to a top cap (35.13%).

### t0340 — 03:40
Left: crossed beams and a huge gold **8.4M** ball. Item bar 9/9/7/4/2. Right: blue ~**74%**, a wide translucent blue stroke across the middle; red/green/yellow rings small in the corners (red particles down to 117k).

### t0350 — 03:50
Left: `524K` green ball with a trail. Item bar 9/10/7/5/3. Right: blue **84.88%**; a thick **yellow multi-strand beam** drops from green’s side into the yellow ring. Yellow particles jump to **543k**.

### t0400 — 04:00
Left: many small balls, two `131K` on the gates. Item bar 9/11/7/6/3. Right: blue **91.13%**. A **green tongue** (19K bubble) reaches left into red; yellow beams hang like curtains. Red ring **22.06M / 69k**.

### t0410 — 04:10
Left: crossed gold/magenta beams, `66K`–`262K`. Item bar 9/11/8/6/3. Right: blue **95.63%**. Green has a forked beam into red. Yellow a large lower-right mass (57.25%, 661k particles).

### t0420 — 04:20
Left: blue diagonal, several `262K`. Item bar 9/11/8/7/3. Right: blue meter **100%** (火力 down to 18.24M). Green and red trade a thick overlapping stroke across the top. Yellow lower-right fan, edge 60%.

### t0430 — 04:30
Left: three gold **1M** balls and a blue beam. Item bar 9/12/8/8/3. Right: a **blue chevron / thick beam** (108K bubble) cuts the top. Blue’s *edge percent* resets visually to **3.83%** while the bar scale shows `/1300` — meter rebased, not a wipe. Yellow 63.75%.

### t0440 — 04:40
Left: gold **4.2M** and a green **4.2M** / red **2.1M** sitting on the item-bar (大球 / 狙击). Item bar 9/12/8/8/3. Right: blue stroke still the dominant shape; red a top-left cap (39.38%, only 40k particles).

### t0450 — 04:50
Left: red vertical beam, gold `2.1M` high. Item bar 9/13/8/10/4. Right: green owns the upper half (**56%**); a **pink/yellow beam with a 4.1M bubble** crosses the lower map. Blue edge only 10% after the rebase. Yellow 68.75%.

### t0500 — 05:00
Left: green **2.1M** ball mid-board. Item bar 10/14/9/10/4. Right: thick **blue beam, 691K bubble**, across the middle. Yellow ring is a huge glowing disk (**70%**). Red 40.88% / 16.46M, green 57.88%.

### t0530 — 05:30
Left: busy gate line, `33K`–`262K`. Item bar 10/16/11/10/4. Right: **yellow-orange fills most of the map** (edge **83.88%**, 613k particles) with a soft gradient from top-left. Blue holds bottom-left (20%). Green ring small (60% bar but visually a corner).

### t0600 — 06:00
Left: red **8.4M** high, gold **1M** in the gate cluster, thick red beam. Item bar 11/16/12/11/5. Right: yellow field with a **red diagonal slash**; green blooms top-right (61%). Yellow ring’s *percent* reads **1.08%** (bar rebased) while the fill is still huge. Blue 24%.

### t0630 — 06:30
Left: a gold **17M** ball low. Item bar 14/18/13/12/6. Right: chaotic — blue swirls lower-left, **pink beams** cut yellow, green upper-right. Yellow particles **1.94M** but edge percent 11% (rebased). Red 51% / 15.96M.

### t0700 — 07:00
Left: crossed beams, `1M`/`2.1M` balls; **狙击** slot lit green (count 8). Item bar 14/19/13/13/8. Right: yellow-orange particle web covers almost everything. Green ring shows **狙击火力 +524K** (69.75%). Red a small ring (52.75% / 14.92M). Yellow particles **11.68M** inside a small ring, edge percent 25.67%.

### t0730 — 07:30
Left: blue beam, gold **2.1M**, **机枪** slot lit (524K, count 19). Item bar 14/19/14/13/11. Right: a **yellow V / triangle beam** from bottom rings up through the orange field. Red ring small (11.60M, 6k particles). Yellow particles **6.5M**.

### t0800 — 08:00
Left: gold **34M** ball, several `1M`/`2.1M`. Item bar 16/20/14/13/13. Right: yellow ripples from the left into a red corner; green ring still round. Blue shows **狙击火力 +4.2M** (12.72M 火力, 33% bar). Yellow edge 62%.

### t0830 — 08:30
Left: two long green beams. Item bar 17/21/15/13/14. Right: red and yellow **thick strokes** (60K and 30K bubbles) over an orange field. Blue ring large but low particle count (5k) at 33%. Yellow edge **75.58%**.

### t0900 — 09:00
Left: blue **4.2M**, green **1M**, crossed blue/green beams. Item bar 18/23/15/16/15. Right: a **blue wedge with 421K bubble** splits red (top) from yellow (right). Yellow edge **81%**. Blue particles **9.5M**.

### t0930 — 09:30
Left: a full-height **green beam** into the **护盾** slot (slot lit). Item bar 19/25/17/19/15. Right: blue beam **5.2M** and a **739K** blob; yellow double rings bottom-right, green shows **护盾 +8.4M**. Yellow edge **85.83%**.

### t1000 — 10:00
Left: green beam, gold **8.4M** and **2.1M**. Item bar 21/25/18/20/15. Right: red blob top-left, blue ring bottom with a ripple, yellow strokes through the middle. Yellow edge **95.58%** / 4.53M 火力 but **5.3M** particles. Blue particles **9.3M**, 火力 41.10M.

### t1030 — 10:30
Left: crossed red/gold beams, blue **17M** and gold **1M**. Item bar 21/28/18/22/16. Right: yellow dominates; a **green beam (301K)** and **gold beam (122K)** cross it. Red ring nearly blown out (white core). Blue edge **72%**, particles 1.26M, 火力 40.90M. A small “2” badge appears by the yellow meter.

### t1100 — 11:00
Left: sparse, a gold **2.1M** on the gates. Item bar 22/30/18/22/17. Right: **blue particle storm** — beams, nodes, and a cyan shattered-glass patch top-right. Red ring hollow **0** at **74.13%** (bar stuck/full). Green bar **54.33%** with a “1” badge. Yellow **67.70%** with a “5” badge, 火力 down to 3.92M but particles **5.3M**. Blue **100%**, 火力 29.77M, particles **9.8M**, badge “2”.

### t1130 — 11:30
Left: gold **4.2M / 2.1M / 1M** balls, no strong beams. Item bar 23/30/20/22/17. Right: blue **constellation / node web** over most of the map; yellow blob only bottom-right (68.50%, 火力 rebounded to **19.75M**). Red ring still 0. Blue 火力 **31.82M**, particles 5.67M, but edge percent shows **40%** (rebased) with badge 5.

### t1200 — 12:00
Left: gold beams making triangles, `4.2M`/`8.4M`. Item bar 24/32/21/23/20. Right: blue web plus a **yellow/blue beam triangle** with a **2.6M** bubble. Yellow ring **82.60M** 火力 / 493k particles, edge 69.75%. Blue ring 72.46M / **4.5M** particles.

### t1230 — 12:30
Left: gold **17M** and **4.2M**. Item bar 24/33/23/25/20. Right: blue angular territory and a **3.1M** bubble; yellow holds the right edge (73.50%). Blue particles explode to **34.07M** (火力 only 13.51M). Yellow 火力 **72.92M**.

### t1300 — 13:00
Left: crossed dark beams, gold **8.4M / 4.2M**. Item bar 26/34/25/26/21. Right: blue/yellow collision, a black hole and a **1.3M** bubble, yellow ripples top-right. Yellow 火力 **106.05M**, particles **58.7M**, edge 76%. Blue 火力 only 4.69M but particles 17.9M.

### t1330 — 13:30
Left: gold **67M** and **17M** balls, a gold beam. Item bar 26/35/27/26/21. Right: blue brush-strokes vs yellow; **4.9M** bubble. Blue particles **128.4M** (火力 79.94M, edge 71%). Yellow 火力 **106.19M**, particles 26.6M, edge 85%.

### t1400 — 14:00
Left: several gold/blue beams, a **17M** ball. Item bar 29/36/30/27/21. Right: blue node-web fills the frame; yellow ring bottom-right **97.32M** / **36.3M** particles (87.55%). Blue **84.14M** / **75.6M** particles (80.50%). Red ring still a hollow 0 at 74.13%.

### t1430 — 14:30
Left: crossed gold beams, many **4.2M / 34M** balls on the gates (counts ~100–415). Item bar 30/37/31/27/22. Right: blue web; a **solid cyan beam** along the left edge. Blue edge **91.85%**, particles 45.99M, 火力 86.09M. Yellow 74.29M / 11.8M particles, 88%.

### t1500 — 15:00
Left: gold **17M / 34M** high, item bar 31/39/33/27/25. Right: **yellow storm arcs** (concentric dotted rings) crash into blue strokes on the left; vertical white beams. Blue edge percent collapses to **0.67%** (rebased) while particles are **73.2M** (火力 69.08M), badge 4. Yellow 火力 **101.33M**, edge 90.60%.

### t1530 — 15:30
Left: a gold **537M** ball entering the bottom (largest ball label in the set); other balls `2.1M`–`67M`. Item bar unchanged 31/39/33/27/25. Right: thick **blue strokes**, bubbles **27M** and **6.9M**, yellow corner ring 67.79M. Blue 火力 reads **0.00** with particles 24.4M (meter overflow/reset), edge 5.88%.

### t1600 — 16:00
Left: board almost empty (pegs + gates only, counts ~110–462). Item bar 32/39/33/32/25. Right: giant **blue blobs** labeled **347M** and **186M** cover the center. Both blue and yellow 火力 read **0.00**; particles 14.4M (blue) and the yellow ring is buried. Edge bars ~90% / 8.5% with badge 4. Red/green rings still hollow.

### t1610 — 16:10 (end card, not gameplay)
**终局寄语** overlay on a darkened dashboard. Thank-you line naming supporters (MINATO米娜托, 天蝎使徒, 银杏树下的记忆, bans、, 庚明u, EmbeTime, 你不干有的是饼干, 早九八) plus “谢谢大家的观看…”. Behind the text:
- **01** line chart 累计火力, 总量 **2.8B**, series 绿/红/黄/蓝.
- **02** 六维表现 radar per color (流星效率, 领土占领率, 能量收集率, 生存效率, 领土产值, 额外增值) with percents such as 黄 79.5 / 37.0 / 36.9 and 蓝 45.2 / 45.6 / 46.0; “对局 15:53 · 战报已定格”.
- **03** donut 阵营火力战报: 黄方 **961M** (风暴 175M, 大球 177M, 狙击 67M, 机枪 66K, 护盾 216M) and 蓝方 **1.8B** (风暴 654M, 机枪 291M, 大球 122M, 狙击 552M, 护盾 150M). 红/绿 called out as eliminated (阵亡).

## What to copy for a pixel-war / Plinko UI

- Left board is a classic peg Plinko: one horizontal multiplier row (x8 x4 x2 mirror), not a full peg pyramid. Balls are team-colored with a numeric power tag, not anonymous.
- Item bar is five abilities with integer charges, highlighted in team color on cast. Casts show up on the right as named popups (风暴火力 / 狙击火力 / 护盾 / 大球火力) and as thick beams or ripple rings.
- Right map is the real “territory”: soft gradient fill, jagged pixel front, four corner rings, outside percent bars, and attack strokes that carry a black power bubble.
- Numbers to support in UI: 火力 in M (and later 0.00 when overflowed), particle counts up to ~100M+, territory percents that **rebase** (drop back near 0 while the bar scale changes /800 → /1300), and ball labels from 1K to 500M+.
