# 2D Game Skills

用 Claude 生成 2D 游戏角色动画的 skill：一句话描述角色，得到完整、流畅、可直接导入引擎的动作素材。

![示例角色的跑步、起跳、攻击、翻滚动作](docs/preview.png)

## game-sprite-animator

每一帧都由骨骼和连续曲线计算生成，因此帧率可以随意设定，循环首尾闭合，走路时脚不打滑。

- **27 个动作：** 待机、走、跑、急停、起跳、上升、滞空、下落、落地、二段跳、蹲下、蹲行、翻滚、冲刺、贴墙下滑、三连击、空中攻击、施法、格挡、受击、死亡等
- **两种风格：** 高清卡通（默认 256px、30fps，可选 60fps）和像素风（48、64、96px）
- **5 个角色模板：** 英雄、骑士、法师、忍者、哥布林，可自定义外形、配色、武器和动作手感
- **细节：** 披风、头发、围巾由物理模拟带动，有脚步滚动、挤压拉伸、表情和刀光，并附带尘土、火花等特效素材
- **自己的美术：** 把分层 PNG 绑到骨骼上，复用同一套动作
- **质检工具：** 检测重复帧、循环接缝、跳帧、滑步和动作衔接，也能检查已有的序列帧
- **导出：** 序列帧、精灵图、图集、`animations.json`，以及 Unity、Godot、Cocos、Phaser、PixiJS、H5 CSS 和 Canvas 播放器所需的文件

每次生成都会附带 `preview.html`，可以逐个查看动作，也可以用键盘试玩。

## 安装

**Claude 桌面版：** 下载 [`game-sprite-animator.skill`](game-sprite-animator.skill)，在 Claude 中打开文件并保存为 skill。

**Claude Code：** 把 [`game-sprite-animator/`](game-sprite-animator) 文件夹复制到 `~/.claude/skills/`。

需要 Python 3，以及 `pillow` 和 `numpy`：

```bash
pip install pillow numpy
```

## 使用

装好后直接描述需求，Claude 会自动完成生成、质检和导出：

```text
做一个像素风的绿皮哥布林，拿长矛，要待机、走路、跑步、跳跃和攻击，用在 Phaser 里
```

如果没有自动触发，可以点名：

```text
用 game-sprite-animator 做一个穿黑色斗篷的刺客
```

也可以不通过 Claude，直接运行脚本：

```bash
cd game-sprite-animator
python scripts/generate.py --character assets/characters/hero.json --preset hd --out out/hero
python scripts/qa_motion.py out/hero
```

预设有 `hd`、`hd60`、`hd512`、`pixel48`、`pixel`、`pixel96`。

## 接入游戏时注意

1. 移动速度使用 `animations.json` 里的 `speed_px_s`，否则会滑步。
2. 锚点使用文件里的脚底 `pivot`，不要用每帧图片自己的边界，否则角色会抖动。
3. 起跳、出伤害、脚步声用 `events` 标注的帧来触发。

各引擎的接入方法见 [engine-integration.md](game-sprite-animator/references/engine-integration.md)。

## 当前限制

- 只支持横版人形角色，没有四足、飞行或史莱姆类骨骼，也没有俯视角和正面视角。
- 角色只有一个朝向，向左时用引擎的水平翻转。
- 引擎导出文件都没有在对应引擎里实测过：Unity 导入脚本未编译，Godot 和 Cocos 文件做过结构校验，`sprites.css` 和 `atlas.json` 也只查过结构。具体情况见 [engine-integration.md](game-sprite-animator/references/engine-integration.md) 中的验证表。
