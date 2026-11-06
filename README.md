# 2D Game Skills

**骨骼与服装审核：** 数字骨长正确不代表骨骼贴合原画，也不代表裤裆和腰胯连续。横版人形新增
[蒙皮与接缝审计](game-sprite-animator/references/skin-binding-audit.md)：逐帧检查显式共享源点和关节点，
审查图强制包含腰胯近景与实际骨线。开裆、断腰、重复裤片都属于 blocker；缺数据或旧报告不能交付。
自写游戏渲染器必须提供本身的证据，游戏单测通过不能当作 skill 已审核。此改进用于拦截错误，
不宣称能自动补画隐藏布料或自动判断所有人体结构。

已有完整分层 PNG 和关节数据时，可使用[免生图绑定入口](game-sprite-animator/references/known-joint-binding.md)，复用素材生成待机/走路，不再生成手部提示图。

**人物图的新默认流程：** `basic-side-v1` 先生成标准侧视图，再逐层审核、绑定并制作待机/走路；提示词、双手定位图和有限次数修复都已预设。第一版限定短发、短款/贴身服装、空手或单手简单剑。代理执行流程，用户提供图片并审核动态效果。复杂长袍、宽袖、披风和双手武器仍属实验范围。详见 [固定人物图流程](game-sprite-animator/references/basic-character-workflow.md)。


用于制作、绑定、审查与导出 2D 游戏角色动画的 skill。能否交付取决于输入素材、实际动作和当前版本的审核证据。

现在可试用统一入口 [game-animator](game-animator/SKILL.md)：安装 `game-animator.skill` 后按角色与视角选择下面四种模式。横版与俯视人形可通过一份角色描述共享名称、基础配色，并分别指定视角配置；俯视尚不支持分层 PNG 或共享身体比例。另有实验性配置驱动飞行流程，支持刚性 PNG 部件和基础动作，但示例只是骨架占位，尚未完成生物美术和引擎实测。旧的四个独立包已弃用，内容由统一包生成。

| Skill | 适合 |
|---|---|
| [game-sprite-animator](#game-sprite-animator) | 横版 RPG、动作游戏：刀剑、法术、跳跃、翻滚 |
| [game-shooter-animator](#game-shooter-animator) | 横版射击游戏：持枪士兵、多方向瞄准、开火、换弹 |
| [game-topdown-animator](#game-topdown-animator) | 3/4 俯视 RPG：自由移动、八方向、人形角色 |
| [game-quadruped-animator](#game-quadruped-animator) | 侧视四足狼：待机、走、慢跑、奔跑 |

## game-sprite-animator

![示例角色的跑步、起跳、攻击、翻滚动作](docs/preview.png)

每一帧都由骨骼和连续曲线计算生成，因此帧率可以随意设定，循环首尾闭合，走路时脚不打滑。

- **27 个动作：** 待机、走、跑、急停、起跳、上升、滞空、下落、落地、二段跳、蹲下、蹲行、翻滚、冲刺、贴墙下滑、三连击、空中攻击、施法、格挡、受击、死亡等
- **两种风格：** 高清卡通（默认 256px、30fps，可选 60fps）和像素风（48、64、96px）
- **5 个角色模板：** 英雄、骑士、法师、忍者、哥布林，可自定义外形、配色、武器和动作手感
- **细节：** 披风、头发、围巾由物理模拟带动，有脚步滚动、挤压拉伸、表情和刀光，并附带尘土、火花等特效素材
- **自己的美术：** 把分层 PNG 绑到骨骼上，复用同一套动作
- **分层人物：** 完整图层与已知关节可走免生图绑定；单张人物图默认走受限的参考图、分层与审核流程。隐藏区域缺失、错误关节和服装断片不会因数值绑定成功而被接受。复杂服装仍有实验限制，见 [layered-art.md](game-sprite-animator/references/layered-art.md)。
- **骨骼约束：** 头、脊柱、肘关节有软限位，翻滚和倒地时身体贴地，武器、脚和披风不穿地
- **质检工具：** 检测重复帧、循环接缝、跳帧、滑步和动作衔接，以及武器挡脸、武器或身体穿地、画面被帧边缘裁切；也能检查已有的序列帧
- **AI 视觉质检：** 生成审查图，由 Claude 逐张看图，找出数值查不到的问题，比如身体悬空、关节反折、剪影看不出动作，并记录结论
- **自动适配大小：** 按最大的动作缩放角色，保证任何一帧都不出画
- **导出：** 序列帧、精灵图、图集、`animations.json`，以及 Unity、Godot、Cocos、Phaser、PixiJS、H5 CSS 和 Canvas 播放器所需的文件。Godot 4.3、Phaser 3、PixiJS 8 和浏览器 CSS 已实测导入和播放，逐帧和原图一致；Unity、Cocos 尚未实测

每次生成都会附带 `preview.html`，可以逐个查看动作，也可以用键盘试玩。
为横版人形添加的自定义动作可在试玩页选择并按 Q 播放；导出时需要包含 `idle` 和该动作。

## game-shooter-animator

![持枪士兵的跑动射击、跳跃射击、翻滚、炸飞动作](docs/preview-shooter.png)

参考合金弹头的做法，把上半身和下半身分开：任意移动可以配任意瞄准角度和武器，帧数不会爆炸。

- **6 种枪：** 手枪、冲锋枪、步枪、霰弹枪、狙击枪、火箭筒，每种有自己的射速、后坐力、换弹动作和枪口位置
- **9 个瞄准方向：** 每 22.5° 一档，从正上方到正下方，扶枪的手始终握在枪上
- **分层动作：** 下半身有待机、走、跑、后退、蹲、跳跃；上半身每种武器都有瞄准、开火、换弹、投弹、枪托攻击、切枪
- **整身动作：** 冲刺、翻滚、滑铲、受击、死亡、炸飞、胜利
- **烘焙组合：** 比如跑动射击、待机瞄准，给只想每个状态一张精灵图的引擎或 H5 用
- **4 个角色模板：** 突击兵、特警、狙击手、雇佣兵
- **射击手感：** 射速对齐整帧，每发都有枪口火光；每帧都标了枪口位置，子弹从枪口射出；换弹、投弹、开枪都有事件帧
- **质检：** 与 game-sprite-animator 相同的骨骼约束、数值检测和 AI 视觉质检，另外检测握枪间隙和射击节奏
- **导出：** 与 game-sprite-animator 相同（H5 CSS 只包含整身动作），另有每帧的上半身挂点 `anchor` 和枪口 `muzzle`

`preview.html` 里有可试玩的靶场：鼠标瞄准、开火、换弹、投弹、切枪，同时也是游戏里接入分层动作的参考实现。

## game-topdown-animator

![八方向的待机、走路和攻击](docs/preview-topdown.png)

用于自由移动 RPG 的 **3/4 俯视八方向人形角色**，独立于两个横版 skill。

- 待机、走路、奔跑、攻击、受击、死亡，每种动作烘焙八个朝向，共 48 个片段。
- 两个角色模板：蓝衣旅行者 `wanderer`、绿兜帽守卫 `warden`，可改配色，支持高清和像素。
- 固定相机下计算地面和肢体高度；正面、背面、侧面和斜向有不同外观和遮挡。
- 八向自由移动，斜向速度归一化，转向和走跑切换保留步态进度。
- 质检覆盖朝向/数据完整性、方向间时序、地面平面滑步、固定骨长、循环接缝及画面裁切。
- 同样导出图集、序列帧、Godot、Phaser/PixiJS、CSS 等文件，附八方向图库和可键盘试玩的预览。

```bash
cd game-topdown-animator
python scripts/generate.py --character assets/characters/wanderer.json --preset pixel --out out/wanderer
python scripts/qa_motion.py out/wanderer
python scripts/visual_review.py out/wanderer
```

第一版只包含持剑人形、固定 3/4 相机。左方向是已烘焙的镜像，会改变装备左右手；
不支持独立瞄准、自定义分层 PNG、物理布料或怪物骨骼。数值通过不代表视觉完美，仍需看审查图和试玩。
接入与验证范围见 [integration.md](game-topdown-animator/references/integration.md)。

## game-quadruped-animator

![狼的待机、走、慢跑和奔跑](docs/preview-quadruped.png)

侧视四足狼首版，具有分段脊柱、四条三段腿和模拟尾巴：

- 四个循环：idle、walk、trot、run；慢跑对角腿配对，奔跑为交错前后腿并带腾空段。
- 四只脚分别检查落脚、滑步、抬脚高度和事件；骨长、膝肘方向、尾巴根部与地面也参与质检。
- 高清与像素素材，同一 pivot，向左在引擎水平翻转，附键盘步态试玩。
- 与已有 skill 共用图集导出和尾巴链模拟，关节记录接口也与侧视人形共用；各 skill 仍独立安装。

```bash
cd game-quadruped-animator
python scripts/generate.py --character assets/characters/wolf.json --preset pixel --out out/wolf
python scripts/qa_motion.py out/wolf
python scripts/visual_review.py out/wolf
```

![狼的扑咬、受击和伏地死亡](docs/preview-wolf-combat.png)

现已加入前探咬击、受击、伏地死亡，合计七个动作；试玩 J/H/X 触发战斗与复活，训练靶按事件帧记录命中。尚无俯视四足或接触约束的步态混合。
使用和验证范围见 [SKILL.md](game-quadruped-animator/SKILL.md) 与 [integration.md](game-quadruped-animator/references/integration.md)。

## 安装

安装统一包 [`game-animator.skill`](game-animator.skill)，它包含下面四种模式。

**Claude 桌面版：** 下载 `game-animator.skill`，在 Claude 中打开文件并保存为 skill。

**Claude Code：** 把 [`game-animator/`](game-animator) 文件夹复制到 `~/.claude/skills/`。

旧的四个独立包（`game-sprite-animator.skill`、`game-shooter-animator.skill`、`game-topdown-animator.skill`、
`game-quadruped-animator.skill`）已弃用，只为已安装的用户保留。它们由统一包自动生成，内容与对应模式一致。

需要 Python 3，以及 `pillow` 和 `numpy`：

```bash
pip install pillow numpy
```

## 使用

装好后直接描述需求，Claude 会自动完成生成、质检和导出：

```text
做一个像素风的绿皮哥布林，拿长矛，要待机、走路、跑步、跳跃和攻击，用在 Phaser 里
```

```text
做一个合金弹头风格的像素士兵，拿冲锋枪和手枪，要跑动射击、跳跃、换弹和死亡，做 H5 小游戏
```

如果没有自动触发，可以点名：

```text
用 game-sprite-animator 做一个穿黑色斗篷的刺客
```

Claude 生成后会先跑数值检测，再逐张看审查图，有 bug 级问题会先修好再交付。

也可以不通过 Claude，直接运行脚本：

```bash
cd game-sprite-animator
python scripts/generate.py --character assets/characters/hero.json --preset hd --out out/hero
python scripts/qa_motion.py out/hero
python scripts/visual_review.py out/hero
```

射击 skill 用法相同，在 `game-shooter-animator` 目录下运行，角色模板换成 `assets/characters/commando.json` 等。

预设有 `hd`、`hd60`、`hd512`、`pixel48`、`pixel`、`pixel96`。

## 接入游戏时注意

1. 移动速度使用 `animations.json` 里的 `speed_px_s`，否则会滑步。
2. 锚点使用文件里的脚底 `pivot`，不要用每帧图片自己的边界，否则角色会抖动。
3. 起跳、出伤害、脚步声用 `events` 标注的帧来触发。

射击 skill 还要注意：

4. 分层动作要把上半身画在下半身当前帧的 `anchor` 上。
5. 子弹从 `muzzle[frame]` 加 `anchor` 的位置射出，不要用固定偏移。
6. 瞄准角度变化时保留开火动作的当前帧，否则射速会变慢。

各引擎的接入方法见 [engine-integration.md](game-sprite-animator/references/engine-integration.md) 和 [integration.md](game-shooter-animator/references/integration.md)。

## 当前限制

- 两个横版 skill 只支持侧视人形角色，没有四足、飞行或史莱姆类骨骼，也没有俯视角和正面视角。射击 skill 也不支持载具、炮台和第一人称枪械。
- 角色只有一个朝向，向左时用引擎的水平翻转。
- 射击 skill 没有分层美术模式，不能绑定自己的 PNG；分层动作里，头上的布条（如头带）在跑动时不会随风飘，烘焙组合和整身动作里会。
- AI 视觉质检是 Claude 看静态帧的判断，看不出动作在播放时的手感，最终效果请在 `preview.html` 里播放确认。
- 引擎导出的验证程度不同：已有模式的 Godot、Phaser、PixiJS 和浏览器 CSS 做过导入或播放测试；Unity 导入脚本尚未编译运行，Cocos 只做过结构校验。实验性飞行模式的引擎文件也仅做结构测试。具体范围见各模式的集成文档。
