# 城市像素领地战 视频生成器

依赖：Python3 + numpy + pillow，系统需有 ffmpeg 和中文字体 fonts-noto-cjk（脚本里用的是 `/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc`，路径不同时改 `FONT`）。

## 运行
```bash
python3 pixel_war.py                 # 筛选 30 个种子，渲染最有戏剧性的一局 -> sample.mp4 + preview.png
python3 pixel_war.py --seed 22       # 直接渲染指定种子
python3 pixel_war.py --horizontal --out h.mp4 --preview h.png   # 横屏 1920x1080
```

## 参数
- `--seeds N` / `--seed-start S`：候选种子数量与起点（默认 30 个，从 1 开始）
- `--teams N`：队伍数 2-8
- `--duration 秒`：对战最长时长（另加约 2 秒冠军画面；超时则按占地最多者“称霸”）
- `--no-audio`：不加音效
- `--out` / `--preview`：输出路径

## 改队伍 / 规则
- 修改 `TEAMS` 列表（城市名 + RGB 颜色）。
- `simulate()` 里：`爆发` 概率 `0.012`、倍率 `3.0`、持续 `45` 回合；`aggro` 控制扩张速度；`under`（前期弱者加成）和 `momentum`（后期强者滚雪球）决定节奏。
- `drama_score()`：领先易主次数、冠军逆袭（最低排名）、后期胶着度、是否统一、时长合适 加权打分。

## marble_war.py —— 球球领土战争（MarblePi 风格，横屏）

参考 B站/抖音「球球派MarblePi」《【百万像素+海量粒子】球球领土战争》的画面布局，规则为自行实现：

- **左侧弹珠台**：4 队弹珠（红/蓝/绿/黄，球上显示弹药量）穿过钉阵；中层槽 `x2 x8 x4 x2 闸门 x2 x4 x8 x2` 放大该队弹药，落入中央「闸门」则进入下层，落到武器槽 `霰弹 / 机枪 / 护盾 / 大球 / 狙击` 获得 4~6 秒技能。槽位下方显示命中次数。
- **右侧地图**：1000×1000（100 万像素）带浅色网格，初始四象限。四角圆形基地 + 旋转炮管，显示弹药（K/M/B）和领土%；炮台发射海量粒子（同屏上限 3 万），撞到异色像素即染色、可能反弹或钻入。
- **淘汰**：基地中心像素被敌方染色 → 淘汰，领土与一半弹药归占领者；最后存活者获胜（54 秒仍未结束则按领土判定）。
- 自动筛选种子（时长 42~56 秒且自然结束、领先易主、技能次数多、淘汰不能太早），音效为程序合成（染色滴答声限频、倍率/技能/淘汰/胜利音）。

```bash
pip install --break-system-packages numba   # numpy pillow ffmpeg 也需要
python3 marble_war.py --seeds 24            # 筛选 24 个种子后渲染最佳 (~3 分钟筛选 + ~80 秒渲染)
python3 marble_war.py --seed 1 --episode 2  # 指定种子 / 集数
```

输出：`marble_sample.mp4`（1920x1080 30fps H.264 yuv420p + AAC，约 55 秒、约 40MB）、`marble_preview.png` 及 `marble_preview_f*.png / _end.png` 关键帧。
