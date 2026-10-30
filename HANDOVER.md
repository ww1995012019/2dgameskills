# 交接文档

更新于 2026-10-30。这是未完成工作的快照，分支 `wip/shooter-and-qa`。`main` 上是已发布的第一版 skill，没有动过。

## 接手时直接说

把下面这段发给 Claude 就能继续：

> 克隆 https://github.com/ww1995012019/2dgameskills 的 `wip/shooter-and-qa` 分支，读根目录的 HANDOVER.md，从「接下来要做的事」第 1 步继续。

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

没完成：见下一节。全量回归是**手动中途停下的**，所以下面的结果不是最终结果。

## 最后一次回归结果

共 18 套（9 个角色 × 高清、像素）。跑完 14 套，停止时还差 4 套。这是最新代码的结果。

| 结果 | 套数 | 明细 |
|---|---|---|
| 全过 | 9 | commando、swat、mage、ninja 的高清和像素，knight 高清 |
| 1 个 FAIL | 5 | goblin 高清、goblin 像素、hero 高清、hero 像素、knight 像素 |
| 没跑完 | 4 | ghost 高清、ghost 像素、mercenary 高清、mercenary 像素 |

这 5 个 FAIL 是同一个问题：`attack_3` 的 `bounds`，画面**右边缘**被裁切。

| 套 | 帧 | 边缘像素 alpha |
|---|---|---|
| hero 高清 | 9、10 | 198、11 |
| hero 像素 | 5 | 255 |
| goblin 高清 | 8 | 255 |
| goblin 像素 | 4 | 255 |
| knight 像素 | 5 | 255 |

高清的 alpha 不到 255，**推测**是刀光弧线越界，尚未验证。`fit_scale` 按刀尖的路径计算，但刀光是用 Catmull-Rom 曲线插值的，曲线可能冲出采样点。另一个可能是刀光的时间窗口比 `fit_scale` 的采样更细。

ghost 和 mercenary 上一轮有过这些失败，本轮修复针对的就是它们，但**还没验证修好了**：
- `roll`：长枪穿地（`weapon_margin` 已改）
- `death`：脚穿地（已加转动脚的约束）
- sniper 高仰角的抓握 WARN（`clear` 从 15 改成 11）

## 接下来要做的事

1. **修 `attack_3` 的 `bounds`。** 先确认是刀光还是刀身。如果是刀光，把 `smear` 用的插值点也算进 `fit_scale`，或者给 `extent_points` 加余量。改动在 `game-sprite-animator`，它的 `render.py` 和 `art.py`。
2. **跑全量回归**，确认 18 套都是 0 FAIL。见下方命令，约 15 分钟，放后台跑。
3. **做完整的 AI 视觉质检，这一步还没做过。** 目前只抽看过 3 张审查图，找到了翻滚悬空、刀光裁切、披风打结，这些已修，但没有复查。至少覆盖 hero 高清和 commando 高清，按 `references/visual-review.md` 看完每张图，用 `visual_review.py --record` 记录结论。重点看翻滚贴地、死亡、披风、瞄准上下极限、换弹。
4. **重新测试射击试玩页。** 用 `dev/test_shooter_demo.js`。动作和武器参数改过之后还没重测。上次发现的「换弹结束那一帧按 R 被吞」已修，也要确认。
5. **校验导出**：`dev/verify_exports_shooter.py` 和 `dev/verify_exports_sprite.py`。
6. **打包两个 skill**，解压到全新目录试运行。根目录的 `game-sprite-animator.skill` 目前是**旧版**，没有本分支的内容。
7. **更新 README**：加入射击 skill、约束和视觉质检，换预览图。
8. **检查自动适配的缩放比例。** 生成时会打印 `[fit]`。commando 是 0.962，但 mage 是 0.806，法杖太长导致角色小了约 19%，同尺寸下看起来会偏小。比较好的做法可能是调整法杖的握持和挥舞幅度。
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

全量回归：`dev/regress_all.ps1`，要在 `game-shooter-animator/scripts` 目录下运行，结果写到 `%TEMP%\spr\all`。然后：

```bash
python dev/qa_failures.py
python dev/qa_flags.py all/hero-hd all/commando-hd
```

`qa_failures.py` 列出每套失败的项目和裁切的边缘，`qa_flags.py` 列出具体帧和原因。

## `dev/` 里的工具

这些是开发用的，不属于 skill，打包时不包含。

| 文件 | 作用 |
|---|---|
| `regress_all.ps1` | 跑 9 个角色的全量回归 |
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
