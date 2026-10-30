# 交接文档

更新于 2026-10-30。这是未完成工作的快照，分支 `claude/elegant-brown-0q6iwm`（从 `wip/shooter-and-qa` 接着做）。`main` 上是已发布的第一版 skill，没有动过。

## 接手时直接说

把下面这段发给 Claude 就能继续：

> 克隆 https://github.com/ww1995012019/2dgameskills 的 `claude/elegant-brown-0q6iwm` 分支，读根目录的 HANDOVER.md，从「接下来要做的事」第 8 步继续。

## 这两个 skill 是什么

| Skill | 用途 | 状态 |
|---|---|---|
| `game-sprite-animator` | 横版 RPG、动作游戏的 2D 角色动画，27 个动作 | 第一版已发布在 `main`；本分支加了约束、穿模检测、视觉质检和多处修复，尚未发布 |
| `game-shooter-animator` | 横版枪战，6 种枪、9 方向瞄准、上下半身分层 | 功能写完，尚未打包，**还不能安装** |

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

## 最后一次回归结果

2026-10-30，最新代码，18 套全部跑完：**0 FAIL**。

- 唯一的 WARN：mage 像素的 `crouch_idle` `spike` 2.61，阈值 2.6。64 像素呼吸动画的取整噪声（每帧都变 20～50 像素），没有放宽阈值。
- 导出校验 18 套全部 OK，多页图集两边都 OK。
- 试玩页测试 8 套射击结果全部正常，两个按键缓冲用例都通过。

自动适配比例（`[fit]`，取自回归日志）：knight 1.000、swat 1.000、mercenary 0.990、commando 0.977、hero 0.929、ninja 0.892、mage 0.849、ghost 0.848、goblin 0.787。

## 视觉质检记录

按 `references/visual-review.md` 看完了 hero 高清（5 张）和 commando 高清（10 张），结论都用 `--record` 记录，没有未解决的 bug 级问题。

已修的 bug 级问题：死亡时披风和头发穿地（见上）。

留下的观感问题，没修：
- hero `skid` 第 4 帧：急停时披风卷成半圆
- commando `rifle_aim_m90`：枪朝正下方时和腿叠在一起，剪影看不到枪，彩色能看清
- commando `rifle_fire_m90`、`shotgun_fire_m90`：站着朝正下方开火，枪口火光画到地面以下。这个角度主要在空中用

没看的：其他 7 个角色、像素版。

## 接下来要做的事

1～7 已完成（修 `attack_3`、全量回归、hero 和 commando 的视觉质检、试玩页测试、导出校验、打包、README）。

第 6 步打包：根目录的 `game-sprite-animator.skill` 和 `game-shooter-animator.skill` 都是本分支的最新代码，包内文件和 git 跟踪的文件一一对应。解压到全新目录后，按 SKILL.md 的流程跑通了预览图、生成（像素）、数值检测（0 FAIL）、审查图，射击的试玩页测试也通过了。试运行时发现 `contact_sheet.py` 遇到角色没有的动作名会直接抛 `KeyError`（SKILL.md 示例里的 `rifle_reload`，swat 拿的是冲锋枪），已改成和 `generate.py` 一样列出可用动作名，SKILL.md 也补了说明。改了 skill 里的文件之后要重新打包：

```bash
cd <skill-creator 目录> && PYTHONUTF8=1 python -m scripts.package_skill <仓库>/game-sprite-animator <仓库>
```
7. ~~更新 README~~ 已完成：加入射击 skill、约束、穿模检测和视觉质检；`docs/preview.png` 用最新代码重新生成，新增 `docs/preview-shooter.png`（commando 的跑动射击、跳跃射击、翻滚、炸飞）。
8. **检查自动适配的缩放比例。** goblin 0.787 最小，比 hero 小约 15%；mage 0.849 和 ghost 0.848 次之。goblin 和 mage 最宽的动作是 `attack_3`，长兵器（长枪、法杖）加上下劈。可以考虑按武器长度调整挥舞幅度。ghost 是狙击枪太长。
9. **询问用户后再合并到 `main`。** 这是公开仓库，合并和发布要用户确认。

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

`test_shooter_demo.js` 和 `dev/qa_*.py` 读 `%TEMP%\spr\` 下的结果。`test_shooter_demo.js` 的参数是子目录名，例如 `node dev/test_shooter_demo.js all/commando-pixel`。

## 关键决定

- **射击 skill 是独立的一份代码**，不依赖第一个 skill，这样能单独安装。代价是公共代码有两份：`constraints.py` 两边一致，改一边要同步另一边；`rig.py`、`render.py`、`cloth.py` 大体相同但有差异。
- **射击类用上下半身分层**，学合金弹头，否则动作、角度、武器组合会爆帧。同时烘焙几个常用组合给想省事的引擎用。
- **AI 视觉质检不调用 API**，由运行 skill 的 Claude 自己看图，不需要密钥。
- **只做横版。** 俯视角要另做角色。
- **约束是软的**，用平滑曲线收住，不是硬夹断，否则约束本身会造成卡顿。
- 武器短暂扫过脸不算问题，停留超过约 0.1 秒（攻击动作 0.22 秒）才算。Q 版手臂短，高举时必然压发顶，所以只检测脸部区域。
- 修问题优先改根因，不放宽阈值。放宽过的只有确实误判的项目，原因写在 `motion-qa.md`。

## 环境坑

- **中文 Windows 默认 GBK。** skill 自己的脚本都显式用 UTF-8。skill-creator 的打包脚本没有，要先设 `PYTHONUTF8=1`。
- **打包需要 PyYAML**，本机没有。建议 `pip install --target <临时目录> pyyaml`，再设 `PYTHONPATH`。
- 这台机器没有 `gh`、`dotnet`、Godot、Unity、Cocos。引擎文件都没有在引擎里实测过，`references` 里写了每项的验证程度。
- 会话文件夹路径很长，Windows 上 `../..` 这类相对路径可能超 260 字符，要先规范化。
- 预览窗格隐藏时浏览器的 `requestAnimationFrame` 会暂停，自动化测试用 Node 脚本。
- 全量回归超过 10 分钟，要放后台。
- 仓库本地配置的提交邮箱是 GitHub 匿名邮箱，不要用机器的全局身份，全局是公司邮箱，而这个仓库是公开的。
