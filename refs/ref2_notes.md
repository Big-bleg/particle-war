# ref2 — 球球派MarblePi 球球领土战争 S1 第六十七期 (skeleton notes)

Source: user-uploaded phone screen recording `ref2.mov` (1280×720, 60 fps, 386.7 s). Douyin id 7689451033604476200.
The game area is cropped to **1196×686 at offset (64,12)**. The Douyin watermark overlays the top-left at t=0 and the bottom-right later; it covers the yellow base label.

## Files
- `ref2_tNNNN.png`: 174 frames (NNNN = seconds). Every 1 s for 0–119 s, then every 5 s for 120–385 s. All are cropped.
- `ref2_clip_a_buffer/` 43.5–48.0 s @10 fps: a 262K yellow ball passes through the arrow strip while 4K balls bounce off.
- `ref2_clip_b_bigball_shield/` 107.5–112.0 s @10 fps: a red 4.2M big ball hits the green shield.
- `ref2_clip_c_opening/` 0–4.5 s @10 fps: the four opening sniper shots collide at the center.
- `ref2_contact_sheet.png`: 10 key frames with captions.

## Layout and proportions (cropped px, 1196×686)
- **Left: marble board**, x≈0–426 (about 36% of the width), full height. It has a grey border frame.
  - Upper peg field: rows of white dots at y≈100–200.
  - **Cup row at y≈234–275 (about 35–40% of board height).**
    - Left to right: `x2 | x8 | x4 | x2 (wide)` … **arrow strip** … `x2 (wide) | x4 | x8 | x2`. The outermost x2 cups touch the walls.
    - Each cup shows a small hit counter above it; the counters climb (e.g. 17/4/9/23 at 45 s, 92/43/58/181 at 385 s).
    - Two more counters sit on the side walls next to the outer cups.
  - **Arrow strip ("buffer strip")**: an upward-arrow (↑↑↑) grate between the two inner x2 cups. It spans x≈160–275, about 38–64% of the board width.
  - Lower half is an empty drop zone. Two staggered peg rows sit at about 78% and 82% of the height (y≈515/547).
  - **Item bar** along the bottom edge has 5 slots, each with a count: **霰弹 (shotgun) · 机枪 (machine gun) · 护盾 (shield) · 大球 (big ball) · 狙击 (sniper)**. Counts at 200 s were 2/10/5/3/5; at 385 s they were 5/17/11/14/6.
- **Right: territory map**, a square of about 670×670 at x≈523–1192 on a 10×10 grey grid. The bases are 4 corner circles: red top-left, green top-right, blue bottom-left, yellow bottom-right.
  - Each base is a translucent disc with a **turret barrel** that rotates to aim.
  - The **top number is the shield/HP** (starts at 8.0M).
  - The **bottom number starts at 249,968**. It ticks down steadily while the turret fires and later grows into the millions for the dominant team. My best guess is the base's ammo/pixel pool, not HP.

## Opening sequence (clip c)
- At t=0 the map is empty and every base shows 8.0M / 249,968.
- At about 0.5 s each base fires a **sniper** diagonally toward the center. The sniper is a long pointed colored bolt that paints a thick straight line behind it.
- At about 2.0 s the four snipers meet in the center and burst into a radial spray of paint lines.
- By 10–30 s each color has a quadrant blob, and the fronts meet in an X at the center.

## Buffer strip pass condition (clip a, plus passes at about 102, 163, 232 and 305 s)
- Ordinary balls (128 to 131K) landing on the arrow strip are bounced back up and never fall through.
- Balls that got through: **262K yellow (about 45.5 s), 4M red, 524K red, 262K red.** Every one had a sparkle/particle comet trail.
- **Conclusion: balls worth about ≥262K (2^18) pass through the strip and fall into the lower zone.** Smaller balls are boosted back up. A 131K ball was seen bouncing, so the threshold is somewhere between 131K and 262K.
- Ball values are powers of 2 (2, 4, 8, … 4K, 16K, 66K, 131K, 262K, 524K, 1M, 2M, 4M, 34M). Values double through the multiplier cups.

## Big ball vs shield (clip b, green base)
| t (s) | ball | green shield | green bottom counter |
|---|---|---|---|
| 106 | 4.2M (appears) | 7.9M | ~495K |
| 108.6 | 4.1M | 7.9M | 463,624 |
| 108.7–110.3 | 3.5M → 3.1M → 3.0M (green turret fire shrinks it) | 7.9M | ↓ about 3.6K per 0.1 s |
| **110.5 impact** | **3.0M → 585K** | **7.9M → 5.4M** | 454,984 |
| 111–112 | 581K → 575K (keeps painting) | 5.4M | 436K |

- **About a 1:1 trade: the ball lost ~2.4M and the shield lost ~2.5M** (display rounding).
- The ball is a big circle labelled with its value. It paints a stroke as wide as its own diameter. It shrinks as its value drops, and it survives with the leftover value.
- Other shield history:
  - Shields grow from the 护盾 item: blue 8.0 → 8.3M (≈96 s) → 10M → 15M (≈200 s) → 24M → 20M.
  - Green fell to 5.1M then 3.1M (≈184–190 s) and later recovered to 6.0M.
  - Red sat at 7.7M then fell to 6.2M.
  - Red and blue are eliminated by about 360 s (bottom counter 0, disc turns pale). Green covers almost the whole map at the end (bottom counter about 14.9M).

## Bullets, turrets and paint
- Turrets fire continuous streams of small white particles at the nearest enemy paint or ball. Those particles convert pixels and grind down incoming big balls (−1.1M over about 2 s in clip b).
- Big ball (大球) and sniper (狙击) paint solid strokes. Machine gun (机枪) and shotgun (霰弹) show up as fans of thin colored lines.
- Paint = pixel ownership. Fronts are jagged and pixelated, with no gradient (unlike ref1, which is the 16:18 War4Balls video in `douyin_detail_notes.md`).
- Big ball spawn: at about 60 s a yellow 166K big ball draws a wide yellow band across the map. The 大球 item count goes up when a ball lands in that slot.

---
# Part 2 (`ref2_part2.mov`, 397.6 s): appended findings

## Does part 2 continue part 1 or overlap?
**Neither. It is a later, non-overlapping segment, and there is a gap between them.**
- The counters only go up across the two files. Item slots read 5/17/11/14/6 at the end of part 1 and 10/24/24/25/8 at the start of part 2. Cup counters read 92/43/58/181 at the end of part 1 and 148/72/101/320 at the start of part 2.
- The map state does not join up. Part 1 ends with green dominant and red/blue at bottom-counter 0. Part 2 opens with red 123M / 2.89M and green 10M.
- Both points mean **a bottom counter of 0 is not elimination**. A base with counter 0 still has its shield, idles (the turret spins without firing) and can recover (blue goes 0 → 161K in part 2). My part 1 note saying red/blue were "eliminated" is wrong.
- Frames: `ref2b_tNNNN.png`, every 2 s, cropped like part 1 (199 files).

## (a) Marble mechanisms
**Multiply-and-teleport: confirmed, seen in 2 cases.** In both, a ball entered a multiplier cup, the cup counter went up by 1, and **one** ball with the multiplied value reappeared at the top centre of the board. No copies were made.
- Part 2 at ~22.0 s: a red **1M** ball entered the inner wide **x2** cup (counter 331→332). A red **2M** ball appeared at the top centre in the next few frames.
- Part 2 at ~29.0 s: a blue **33K** ball entered the left **x8** cup (counter 73→74). A blue **262K** ball appeared at the top centre (32,768 × 8 = 262,144).
- Clips: `ref2_clip_multiply/p2_x2_1M_t*.png` (20.5–23.0 s) and `p2_x8_33K_t*.png` (28.2–30.4 s).

**Release N marbles: not found yet.**
- The only spawn I saw is an **emitter at the top centre**. At the start of the match (part 1, 0.5–2.5 s) it lets out a stream of small balls of every colour (values 1–8), a few at a time. The clip is `ref2_clip_spawnN/p1_opening_emitter_*.png`.
- Not checked yet: (1) the half-circle openings on both side walls at cup-row height (y≈185), and (2) the bottom item slots.
- **Ruled out: the item slots are not a ball-release mechanism.** A ball that passes the arrow strip falls through the lower pegs into one of the 5 bottom slots and is used up. For example, the 262K yellow ball (part 1 at ~47.8 s) landed in 大球 (big ball) and the count went 0→1. That slot then fires the item on the map, so the bottom slots are item triggers.

## (b) Small bullets at the walls
**They bounce.** Part 1 at 29.5–30.5 s shows clean mirror reflections: a red bullet trail makes a "Λ" off the top wall and a yellow trail makes a "V" off the bottom wall. The trail keeps painting after the bounce. Bullets also drain enemy shields (see e).

## (c) Ball vs shield / ball attrition
- Part 1 at ~110.5 s, repeated here: big ball 3.0M → 585K, shield 7.9M → 5.4M. That is roughly a 1:1 trade.
- Part 2 at 130.4–132 s: a green 6.3M ball and a yellow 2.6M ball crossed blue territory. Green went 6.3 → 5.6 → 5.1 → 4.6 → 4.2 → 4.0 → 3.7 → 3.3 → 3.1 → 2.8 → 2.5 → 2.3 → 1.9 → 1.7 → 1.5M in 1.5 s. Yellow went 2.6M → 332K. **Balls keep losing value while they paint enemy pixels and take turret fire.** They stay alive after their own base is destroyed.
- Part 2 at 0–8 s: a green 690K ball near blue's base went 687K → 666K → 633K. Blue's turret was idle (counter 0) and the shield stayed at 33M.

## (d) Arrow-strip (buffer) pass threshold
Part 2 matches part 1. Balls that passed: yellow (with a comet trail), red 4M (~34 s), red 262K (~35 s, seen below the strip), blue 4B (~357 s). Balls of 131K and below always bounced back up. **The threshold sits between 131K and 262K, and balls of 2^18 (262,144) or more pass.**

## (e) Shield changes and elimination
- **Elimination happens when the shield reaches 0, not when the counter does.** Green's shield in part 2 drained under blue bullet fire: 1.3M → 1.2M → 1.1M → 756K → ~56xK → 201K → 0 at about 129.9–130.6 s, while green's counter was still ~8M. The base disc disappeared and the area was repainted. Clip: `ref2b_clip_green_elim/` (128.8–133.2 s).
- Shield jumps in part 2 are large and step-like:
  - Blue: 33M → 32M → 16–20M → 54M → 34M → 25M → 14M → 5.0M → ~537M → 4.8B (end).
  - Red: 123M → 28M (around a 44M ball event at ~224–232 s) → 5.0M → 9.8M → 60M.
  - I could not read the 护盾 (shield) item effect cleanly. The step-ups line up with that slot being triggered, and the size of the jumps suggests a multiplier, but I did not confirm this frame by frame.
- **End of part 2 (396 s):** red covers almost the whole map (shield 60M, counter 49.99M). Blue is alive (shield 4.8B, counter 149K). Yellow is alive (shield 6.1M?). Green is gone. A **1B** ball is in the lower board. The match does not finish in this recording.

Contact sheet: `ref2b_contact_sheet.png`.
