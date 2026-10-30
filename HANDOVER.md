# 交接文档

更新于 2026-10-30。前三轮在分支 `claude/elegant-brown-0q6iwm` 上完成（从 `wip/shooter-and-qa` 接着做），分两次合并到 `main`。第四轮（工程基础：共用代码、基准回归、故障注入、CSS 回放）在 `claude/wizardly-wright-kwbjaj` 上。工作规范见根目录 `CLAUDE.md`。

## 接手时直接说

把下面这段发给 Claude 就能继续：

> 克隆 https://github.com/ww1995012019/2dgameskills 的 `main` 分支，读根目录的 `CLAUDE.md`、`HANDOVER.md` 和 `docs/roadmap.md`，从路线图第 3 节按顺序继续。

## 这两个 skill 是什么

| Skill | 用途 | 状态 |
|---|---|---|
| `game-sprite-animator` | 横版 RPG、动作游戏的 2D 角色动画，27 个动作 | 已打包，在 `main` |
| `game-shooter-animator` | 横版枪战，6 种枪、9 方向瞄准、上下半身分层 | 已打包，在 `main` |

## 当前进度

已完成：
- 射击 skill：士兵角色、6 种枪、瞄准、开火、换弹、手雷、枪托、全身动作、分层导出、烘焙组合、特效、试玩页、文档
- 两个 skill 新增的骨骼约束（`scripts/sprite_anim/constraints.py`，两边是同一份文件）
  - 头、脊柱、肘关节软限位
  - 深蹲抬脚跟
  - 武器地面约束
  - 翻滚时身体贴地、倒地时不沉入地面
  - 转动的脚不穿地
  - 披风弯折限制
- 穿模检测：武器挡脸、武器和身体穿地、画面被帧边缘裁切（`qa_motion.py` 的 `limits`、`clip`、`bounds` 列）
- AI 视觉质检工具：`scripts/visual_review.py`，流程见 `references/visual-review.md`
- 生成前自动适配角色比例，让最大动作不出画（`render.py` 的 `fit_scale`）
- 2026-10-30 第二轮（下面「接下来要做的事」第 1～5 步）：
  - `attack_3` 右边裁切：剑约 30 毫秒扫过 200°，最远点落在 `fit_scale` 每秒 30 次的采样之间。改成每秒 120 次，并把刀光样条也算进去。刀光原来用当前帧的压扁画历史位置，现在每个点用它自己那一帧的压扁。`attack_3` 的前冲 `root_x` 从 8～9 改成 2，否则量准之后所有角色要缩小 6～10%。
  - ghost 狙击枪朝正上方瞄准时扶枪手够不着（grip FAIL）：扶枪点超出手臂长度时，沿枪身往回滑（`rig.py` 的 `_slide_in`），间隙从 1.56 降到 0.14 单位。
  - 视觉质检发现死亡、翻滚时披风和头发穿到地面以下最多 20 像素：布料地面碰撞改成按画出来的带宽留空间（`cloth.py` 的 `_ground`、`ChainDef.width`），头上的链也加了地面，地面改成非弹性（否则披风会弹起）。
  - 试玩页测试改成按当前武器算弹药，并新增「投弹最后一帧按 R」「换弹最后一帧按 G」两个用例。
  - 新增 `dev/regress_all.sh`，Linux 和 macOS 用，可并行，`ONLY=ghost,swat` 只跑部分角色。

## 第四轮：工程基础

按 Game Sprite Animator 2.0 方案的评审意见，先补工程基础，不加新功能。画面没有任何变化：全量回归和改动前逐像素相同。

- **共用代码只有一份。** `shared/` 是两边共用文件的唯一来源，`dev/sync_shared.py` 复制到两个 skill，`--check` 检查是否一致。`export.py` 原来两边差 1 行（CSS 跳过分层动作），改成 `c.get("layer", "full")` 后两边相同。
- **打包不再依赖 skill-creator。** `dev/package_skills.py` 直接打包 git 跟踪的文件，固定时间戳，内容不变包就不变；`--check` 检查包是否过期。不需要 PyYAML。
- **基准回归。** `dev/baseline.json` 记录 18 套、864 个动作的帧数、每项 QA 状态、QA 数值和解码后像素的哈希。`dev/baseline.py` 比较：状态变差就失败；`--strict` 下像素变了也失败（重构用）。
- **故障注入测试。** `dev/tests/test_qa_faults.py` 故意植入问题，确认 QA 能报出来并定位到帧：重复帧、循环接缝、跳帧、出画、滑步、站立脚抖动、骨骼拉长、膝盖反折、武器穿地、武器挡脸、握枪脱手、开火没有枪口火光、图集越界、图集区域错位。
- **找到并修了一个漏洞：** `dev/verify_exports_*.py` 发现图集还原的帧和原图不一致时只打印数字，最后仍输出 OK。现在会失败；透明边缘没有渗色也会失败。
- **找到两个 QA 缺口，没修**，写成 `expectedFailure` 测试：
  - 截短的走路循环查不出：走路每帧本来就改变大半剪影，像素接缝比例总在 1.7 以下。
  - 衔接姿势错误（把死亡最后一帧接到起跳）查不出：衔接比例除以较快动作的典型步长，像素差又会饱和，只有约 1.5，阈值是 2.5。
  - 两者都要改成基于 `rig_trace.json` 关节位置的检查。
- **CSS 实际播放过了。** `dev/css_playback.js` 在 Chromium 里播放 `sprites.css`，每帧暂停在时间段中点截图，和原始帧逐像素比较（`dev/tests/test_css_playback.py`，含一个故意把关键帧错一位的用例）。验证表已更新。
- **Godot、Phaser、PixiJS** 在用户同意下载后做了实测，见下一节。

## 第五轮：引擎实测

- **Godot 4.3**（无界面运行，`dev/godot_smoke.py` + `dev/godot/smoke_test.gd`）：按文档把图集和 `.tres` 放进新项目，让编辑器导入；加载 SpriteFrames，核对每个动作的帧数、帧率、循环；用导入后的贴图按 region + margin 还原每一帧，和原图比较；在 `AnimatedSprite2D` 上以 60 Hz 和 144 Hz 播放，检查帧序、每帧停留时长、循环和 `animation_finished`。
- **发现并修了一个问题：** Godot 默认导入开着 Fix Alpha Border，会把透明度 7% 以下的像素重新上色。像素版没影响，但高清版柔和的边缘会出现一圈很淡的深色描边（例如淡蓝光晕变成深灰）。图集本来就做了边缘渗色，不需要它。现在导出时附带 `engine/godot/atlas.png.import`（无损、关掉 Fix Alpha Border），Godot 会自动补全 uid 和路径。用了这个文件，导入后和原图逐像素相同。
- **Phaser 3.80、PixiJS 8.6**（Chromium，`dev/web_engines.js` + `web_engines_page.js`）：完全照文档里的代码加载，逐帧按 pivot 画出来和原图比较；手动推进时钟，在 60 Hz 和 144 Hz 下检查帧序、停留时长、循环和完成事件。
- **发现并修了一个文档 bug：** 图集超过 4096 像素会拆成 `atlas_0`、`atlas_1`（mercenary-hd 就是），但文档里的 Phaser、PixiJS 示例只加载单个 `atlas.json`，大套直接报错。示例改成从 `animations.json` 的 `pages` 加载每一页、按帧名找贴图，单页多页都适用；Godot 一节也写明要复制每一页。
- PixiJS 的 `renderer.extract.canvas` 读回来的半透明像素被多乘了一次透明度，但屏幕上的画面是对的，所以测试读页面上显示的画布。
- 测试用例在 `dev/tests/test_engines.py`，含故障注入（错误的 margin、帧率、裁切偏移、少一帧，以及不带 `.import` 文件时的高清描边）。引擎没装就自动跳过。
- 安装：`bash dev/engines/get_godot.sh`（Linux，官方 4.3），`npm install --prefix dev/engines`（版本固定在 `dev/engines/package.json`）。都不进 git。
- 还没测：Cocos、Unity（需要图形界面和授权，容器里装不了）；射击 skill 的分层挂点在引擎里的对齐（只测了逐帧画面和播放）。

## 最后一次回归结果

2026-10-30 第三轮，最新代码，18 套全部跑完：**0 FAIL、0 WARN**。导出校验 18 套 OK，多页图集两边 OK，射击试玩页 8 套全部通过（包括两个按键缓冲用例）。

自动适配比例（`[fit]`）：knight 0.939、hero 0.929、mage 0.905、ninja 0.891、goblin 0.852；swat 1.000、mercenary 0.990、commando 0.977、ghost 0.848。

## 视觉质检记录

2026-10-30 第三轮：按 `references/visual-review.md` 看完了全部 18 套（9 个角色 × 高清、像素，共 140 张审查图），每套都用 `--record` 记录，没有未解决的 bug 级问题。

已修的问题：
- 死亡、翻滚时披风和头发穿地（bug 级，第二轮）
- 站着朝正下方开火时，枪口火光和火箭筒后喷画到地面以下：现在落到地面上向两边散开（`soldier.py` 的 `_splash`）
- hero `skid` 急停时披风卷成半圆：布料加了整条链的累计弯折上限 140°（`cloth.py` 的 `max_curl`），只能弯成弧，卷不成圈

留下的观感问题，没修：
- commando 等角色朝正下方瞄准时，枪和腿叠在一起，剪影里看不清枪，彩色能看清。试过把枪往前推 12 个单位，但朝下看时头低下来，枪会穿过脸（数值检测 FAIL），所以撤回了
- ghost 站着朝正下方瞄准狙击枪时，长枪管搁在地面上。地面约束允许武器接触地面，不算穿地
- goblin `attack_3` 起手时枪杆横过脸，在检测容忍的 0.22 秒内
- ninja 像素版 `attack_2` 第 2 帧：64 像素下刀光是生硬的折线，不像弧线
- goblin 像素版的深色枪杆、swat 的黑色冲锋枪和深色衣服颜色接近，剪影里不太显眼。属于配色，改角色文件里的颜色就行

## 接下来要做的事

**完整的后续计划、验收标准和待用户确认的问题见 `docs/roadmap.md`。** 下面是摘要。

第四轮之后，按优先级：

1. ~~引擎实测~~ 第五轮完成了 Godot、Phaser、PixiJS。
2. 补上两个 QA 缺口：基于关节位置的循环接缝和动作衔接检查。加上后先跑全量回归，看会不会冒出新的 FAIL。
3. 新方向：用户的游戏横版、俯视都有，也需要怪物。建议顺序：俯视 4 方向人形 → 8 方向 → 四足。一次只推进一类。
4. 「视觉质检记录」里留下的观感问题；Unity、Cocos 实测。

以下是前三轮的记录。1～9 都已完成（修 `attack_3`、全量回归、hero 和 commando 的视觉质检、试玩页测试、导出校验、打包、README、比例、合并）。第三轮把剩下的视觉质检做完了，修了 2 个观感问题，见「视觉质检记录」。

第 6 步打包：根目录的 `game-sprite-animator.skill` 和 `game-shooter-animator.skill` 都是本分支的最新代码，包内文件和 git 跟踪的文件一一对应。解压到全新目录后，按 SKILL.md 的流程跑通了预览图、生成（像素）、数值检测（0 FAIL）、审查图，射击的试玩页测试也通过了。试运行时发现 `contact_sheet.py` 遇到角色没有的动作名会直接抛 `KeyError`（SKILL.md 示例里的 `rifle_reload`，swat 拿的是冲锋枪），已改成和 `generate.py` 一样列出可用动作名，SKILL.md 也补了说明。改了 skill 里的文件之后要重新打包（第四轮起不再用 skill-creator）：

```bash
python dev/package_skills.py
```
7. ~~更新 README~~ 已完成：加入射击 skill、约束、穿模检测和视觉质检；`docs/preview.png` 用最新代码重新生成，新增 `docs/preview-shooter.png`（commando 的跑动射击、跳跃射击、翻滚、炸飞）。
8. ~~检查自动适配的缩放比例~~ 已完成。量出来的武器尖原来比画出来的短 4～9 个单位（从手腕量，长度表是旧的：长枪 62 实际画到 66，斧 40 实际 47），一直靠 `fit_scale` 留的 6 个单位余量撑着。现在 `art.py` 的 `WEAPON_REACH` 记录每种武器实际画出的长度，`blade_points`、武器绘制和地面约束共用同一个起点（`weapon_origin`），余量降到 4。长枪和法杖改成握在更靠中间的位置（`WEAPON_GRIP`，总长不变）。比例：hero 0.929（不变）、knight 0.939、mage 0.905（原 0.849）、ninja 0.891、goblin 0.852（原 0.787），最大和最小的差距从 27% 缩到 10%。地面约束改成绕武器的真实起点算（`rig.py` 的 `pivot_y`），否则 goblin `attack_3` 落地时枪尖会插进地面 1 个单位。
9. ~~合并到 `main`~~ 用户同意后通过 PR 合并。之后的新工作从最新的 `main` 开新分支。

## 常用命令

都在对应 skill 的根目录运行。

```bash
python scripts/contact_sheet.py --character assets/characters/hero.json --clips attack_3 --size 192 --max-frames 8 --out sheet.png
python scripts/generate.py --character assets/characters/hero.json --preset hd --out out/hero
python scripts/qa_motion.py out/hero
python scripts/visual_review.py out/hero
python scripts/visual_review.py out/hero --record verdict.json
```

全量回归：Windows 用 `dev/regress_all.ps1`，要在 `game-shooter-animator/scripts` 目录下运行，结果写到 `%TEMP%\spr\all`。Linux 和 macOS 在仓库根目录运行 `dev/regress_all.sh`，结果写到 `$TEMP/spr/all`（默认 `/tmp`），日志在 `$TEMP/spr/logs`。然后：

```bash
python dev/qa_failures.py
python dev/qa_flags.py all/hero-hd all/commando-hd
```

`qa_failures.py` 列出每套失败的项目和裁切的边缘，`qa_flags.py` 列出具体帧和原因。

## `dev/` 里的工具

这些是开发用的，不属于 skill，打包时不包含。

| 文件 | 作用 |
|---|---|
| `regress_all.ps1`、`regress_all.sh` | 跑 9 个角色的全量回归（Windows、Linux 和 macOS） |
| `qa_failures.py` | 汇总每套的失败项，定位裁切边缘 |
| `qa_flags.py` | 列出标记的帧和原因 |
| `verify_exports_sprite.py`、`verify_exports_shooter.py` | 校验图集还原、plist、tres、CSS |
| `test_shooter_demo.js` | 用 Node 跑试玩页的真实脚本，按固定时钟推进，不需要浏览器 |
| `test_atlas_pages.py` | 强制多页图集并校验 |
| `sync_shared.py` | 把 `shared/` 复制到两个 skill；`--check` 检查是否一致 |
| `package_skills.py` | 打包两个 `.skill`；`--check` 检查是否过期 |
| `baseline.py`、`baseline.json` | 全量回归结果和基准比较；`--strict` 像素变化也算失败，`--update` 更新基准 |
| `css_playback.js` | 在 Chromium 里播放 `sprites.css` 并逐帧截图 |
| `godot_smoke.py`、`godot/smoke_test.gd` | Godot 4.3 无界面导入和播放测试 |
| `web_engines.js` | Phaser、PixiJS 在 Chromium 里加载和播放测试 |
| `engines/` | `get_godot.sh` 和固定版本的 `package.json`；下载的引擎不进 git |
| `tests/` | `python3 -m unittest discover -s dev/tests -v`：故障注入、CSS 回放、引擎实测、同步和打包检查 |

`test_shooter_demo.js` 和 `dev/qa_*.py` 读 `%TEMP%\spr\` 下的结果。`test_shooter_demo.js` 的参数是子目录名，例如 `node dev/test_shooter_demo.js all/commando-pixel`。

## 关键决定

- **射击 skill 是独立的一份代码**，不依赖第一个 skill，这样能单独安装。代价是公共代码有两份。第四轮起完全相同的文件放在 `shared/`，只改那里，用 `dev/sync_shared.py` 同步；`rig.py`、`render.py`、`motions.py`、`art.py` 两边有差异，各改各的。
- **射击类用上下半身分层**，学合金弹头，否则动作、角度、武器组合会爆帧。同时烘焙几个常用组合给想省事的引擎用。
- **AI 视觉质检不调用 API**，由运行 skill 的 Claude 自己看图，不需要密钥。
- **只做横版。** 俯视角要另做角色。
- **约束是软的**，用平滑曲线收住，不是硬夹断，否则约束本身会造成卡顿。
- 武器短暂扫过脸不算问题，停留超过约 0.1 秒（攻击动作 0.22 秒）才算。Q 版手臂短，高举时必然压发顶，所以只检测脸部区域。
- 修问题优先改根因，不放宽阈值。放宽过的只有确实误判的项目，原因写在 `motion-qa.md`。

## 环境坑

- **中文 Windows 默认 GBK。** skill 自己的脚本和 `dev/` 下的新脚本都显式用 UTF-8。旧的 skill-creator 打包脚本没有，要先设 `PYTHONUTF8=1`；现在用 `dev/package_skills.py`，不需要。
- Windows 那台机器没有 `gh`、`dotnet`、Godot、Unity、Cocos。Godot、Phaser、PixiJS 第五轮在 Linux 容器里测过，Unity、Cocos 没有，`references` 里写了每项的验证程度。
- 会话文件夹路径很长，Windows 上 `../..` 这类相对路径可能超 260 字符，要先规范化。
- 预览窗格隐藏时浏览器的 `requestAnimationFrame` 会暂停，自动化测试用 Node 脚本。
- 全量回归超过 10 分钟，要放后台。
- 仓库本地配置的提交邮箱是 GitHub 匿名邮箱，不要用机器的全局身份，全局是公司邮箱，而这个仓库是公开的。
