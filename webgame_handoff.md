# War4Balls Web Game · Handoff

**日期：** 2026-10-14（Asia/Shanghai）  
**路径：** `side-income/pixel-war/web-game/`  
**包：** `side-income/pixel-war/web-game-play.tar.gz`

## 引擎

- **PixiJS v8.6.6 WebGL**（`web-game/vendor/pixi.min.js`，无 bundler）
- 游戏逻辑：plain JS（`js/game.js`）
- 左 Plinko：Canvas2D → Pixi 纹理；右战场：领土纹理 + BlurFilter 软边 + ParticleContainer 丝绸粒子

## 怎么跑

```sh
cd web-game && python3 -m http.server 8765
# 浏览器打开 http://127.0.0.1:8765/
```

选队或「直接开战」。不要碰 `marble_war_v5*`。

## 证据截图

| 文件 | 含义 |
|------|------|
| `shots/t10s.png` / `t30s.png` | 本机 headless 约 10s / 30s |
| `shots/compare_webgl_t10.png` | 参考 vs 本版（~10s） |
| `shots/compare_webgl_t30.png` | 参考 vs 本版（~30s） |
| `shots/capture_meta.json` | 粒子数 / share / 无 error 日志 |

最近一次 capture：silk ≈ **13.8k**（池满），shots ≈ 150–260，无 pageerror。

## 第二轮（01:06 后）

- 只靠子弹涂格（无圆形扩张），噪声泡沫锋线 + 暗缝 + 边缘火花，细丝扇 + 队色光束，光束遇敌即停
- 对比：`shots/compare_webgl_rounds.png`（t0010/t0100/t0300），`compare_webgl_t10.png`，`compare_webgl_t30.png`，另有 `t60s.png`
- 性能：JS 每帧 ~6–10ms；headless 软件 GL 约 3.5fps，**未在真 GPU 上测过**

## 第三轮（01:17 后）

暗色内部 + 颗粒断续霓虹边、不对称战局、后期洪泛（风暴弧 + 多 M 大球 + 实心光盘基地）、性能优化。对比 `shots/compare_webgl_rounds.png`（t0010/t0100/t0200/t0300），快进截图 `shots/w010/w060/w120/w180.png`，数据 `shots/capture_warp_meta.json`。

## 是否够给用户看？

可以给用户看，作为「接近、可评审」的版本。1:00 / 2:00 的观感（暗内部 + 霓虹边 + 不均衡战线）和 3:00 的洪泛事件都对上了。还差：0:10 的色块比 ref 更暗、描边更重；霓虹边比 ref 薄；3:00 缺 ref 那种粗的径向射线纹理；洪泛方是随机的（不一定是黄队）；真 GPU 帧率未实测。

## 明确未做

- 未改 `marble_war_v5*`
- 未用 Codex
- 未引入构建链 / npm 运行时依赖（puppeteer 仅截图用）

## 2026-10-14 02:07 UTC+8 pass
Left panel rebuilt from ref coords; turrets rotate and lock; published as commit 1aecbef. See web-game/REVIEW_CHECKLIST.md.

## 2026-10-14 pass 2 (UTC+8)
Rounds 6–9: lift, meter text, straight bands, peg lattice, t0000 grow-in, base growth. See REVIEW_CHECKLIST.md.

## 2026-10-14 pass 3 (UTC+8)
Rounds 10–14: slower early paint, late crisp edges, forced big-ball window, start labels. See REVIEW_CHECKLIST.md.

## 2026-10-14 pass 4 (UTC+8)
Rounds 15–17: big-ball paint brushes and tubes, dark interiors and thick rims, flood disc, lasers, less silk.

## 2026-10-14 pass 5 (UTC+8)
Rounds 18–20: wide tubes, black interiors with saturated rims, linear rim filtering, thicker lasers, bigger flood disc.

## 2026-10-14 pass 6 (UTC+8)
Physics solver, wall bounce, buoyancy membrane, 散弹, sniper opening, strict 1-cell paint, world scale 1.75, hex peg clusters, ball/shield exchange. See REVIEW_CHECKLIST.md 40–56.

## 2026-10-14 pass 7 (UTC+8)
Pacing rubber band, batched draws, team-coloured streaks, cup multiply+relaunch, compact skeleton cups. Items 57–63.

## ref2 pass (UTC+8 ~07:00)
ref2 items 1-7 plus part-2 clarifications implemented; see REVIEW_CHECKLIST 64-71.

## pass r34
See REVIEW_CHECKLIST 72-76.

## Python + moderngl rebuild (UTC+8 ~09:30)
New codebase at pygame-engine/ (see README). Realtime: python main.py. Export: python main.py --export out.mp4 --seed N --duration 660. Sample clips in pygame-engine/out/.

## Python 10-min story pick (UTC+8 ~11:45)
Searched 96 seeds at --match 660. Top: seed 104 (score 56.9), 蓝队 wins at ~10:20 after 红/绿/橙 elim at 7:48 / 8:49 / 10:20; mid-match comeback (rank 3→win); all items used; 7 ball hits.
Runner-up seed 147 (橙队, 18 lead changes).
Highlight frames: pygame-engine/out/hl660_s104/.
Full ranking: pygame-engine/story_search_660.json.
Do not re-ping for seed195 review unless visuals feedback arrives; 5-min cut already attached ~10:38.
