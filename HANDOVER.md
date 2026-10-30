# 交接文档

更新于 2026-10-31。前三轮在分支 `claude/elegant-brown-0q6iwm` 上完成（从 `wip/shooter-and-qa` 接着做），分两次合并到 `main`。第四轮（工程基础：共用代码、基准回归、故障注入、CSS 回放）在 `claude/wizardly-wright-kwbjaj` 上。工作规范见根目录 `CLAUDE.md`。

## 接手时直接说

把下面这段发给 Claude 就能继续：

> 克隆 https://github.com/ww1995012019/2dgameskills 的 `claude/wizardly-wright-kwbjaj` 分支（合并到 `main` 之后改用 `main`），读根目录的 `CLAUDE.md`、`HANDOVER.md` 和 `docs/roadmap.md`，从路线图第 3 节按顺序继续。

**2026-10-31 方向调整：** 角色外观改用 AI 生图，skill 合并成一个，生物改用配置描述。详见 `docs/roadmap.md` 第 3 节。

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

## 第六轮：关节连续性质检

- 两个 `qa_motion.py` 增加关节 RMS 接缝和动作衔接检查，保留原有像素检查，取较差状态。
  循环检查相对帧间位移；衔接用站立身高归一化，不再依赖较快动作的速度。
- 射击生成器原先没有 `joints`，现已记录与普通角色相同的九个关节。仅增加 trace 数据，未改动作或绘制。
- 两个 `expectedFailure` 已改成正常测试，故障同时修改 PNG 和 trace；两种 skill 都覆盖截短循环、
  错误衔接、纯关节故障、缩放不变性和旧 trace 兼容。射击另有后坐力和移动开火故障测试。
- 开火循环的起点本来就有后坐力脉冲，不能用普通步态速度作判断：用与衔接相同的绝对位移限值；
  整身开火组合仍检查下半身步态。规则和误报原因写在 `references/motion-qa.md`。
- 浏览器测试补上 `CHROMIUM_EXECUTABLE_PATH`，CSS 测试使用 Playwright 内存资源路由，兼容禁止 file:// 的环境。
  本次使用系统 Chromium 154、Godot 4.3、Phaser 3.80.1、PixiJS 8.6.6。
- **本轮新发现的动作问题（第七轮已修复）：** `block_hit` 在 GUARD 结束，而 `block` 第一帧是 idle0。
  关节位移约身高的 12%，所以新增 WARN。没有放宽阈值，也没有更新基准掩盖该问题。
  下一步应修正格挡恢复的动作/播放衔接，再进入俯视角色工作。

验证记录：
- 故障注入测试：29 个全部通过，没有 expectedFailure；CSS 播放及其故障注入：3 个通过。
- Godot、Phaser、PixiJS 引擎测试：6 个通过；包同步和打包检查：2 个通过。
- 初次完整测试因缺少 Playwright 自带 Chromium、file:// 策略而有 3 个 CSS 失败；
  配置系统 Chromium 并调整 CSS 资源加载后，受影响的 3 个测试已全部重跑通过。
- 18 套、864 个动作全量生成后，用最终版 QA 逐套重新检查：0 FAIL、10 WARN。
  10 个 WARN 全是 5 个普通角色 × 高清/像素的 `block_hit -> block`，射击 8 套全部无警告。
- `python3 dev/baseline.py /workspace/onboarding-results/qa-update/spr/all --strict`：
  10 regressions、0 changed、0 drifted，退出码 1。10 项都是上述 PASS -> WARN，
  没有像素或帧数变化；不能将这次基准比较称为通过。`dev/baseline.json` 未更新。
- 两个 `.skill` 已重新打包且 `--check` 通过；共用文件 `--check` 通过。

## 第七轮：格挡受击恢复

- 保留 `block` 的 idle → GUARD 入场段；`block_hit` 的 `next_at=1` 声明接回最后的 GUARD 保持姿势。
  生成器按目标动作的实际帧数写入 `animations.json` 的零基 `next_frame`，兼容 FPS override。
- 两边 QA 用真实的入口帧同时比较像素和关节，并在报告中记录目标帧号；没有改阈值。
  将入口故意改回 0 仍得到原来的 WARN，将保持姿势改成死亡姿势会 FAIL。
- 共用布料在 `shared/scripts/sprite_anim/cloth.py` 修改并同步：收尾形状同样指向目标保持帧，
  不再向待机首帧的布料形状收敛。预期画面变化只在普通角色的 `block_hit`。
- 试玩里按住 I、按 H 会触发格挡受击并恢复保持帧；恢复后能立即再次受击，火花每次只触发一次。
  释放 I 后受击按普通 `hurt` 处理；反应不会被同一模拟步的普通输入覆盖。
- 新增 `dev/test_sprite_demo.js`，以手动时钟运行真实预览脚本并断言状态和帧号。
  Python 故障注入测试也覆盖播放路径、错误入口、错误目标姿势和目标帧率覆盖。
- 集成文档明确 `next`/`next_frame` 是控制器提示；Canvas 示例按入口帧播放。
  各游戏引擎仍需自行连接状态；未声称所有引擎都实测了这条游戏状态转换。
- 已看过 5 角色 × 高清/像素的 `block_hit` 条形图，没有发现明显新增视觉问题；这是人工观感检查。

验证结果：
- `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium python3 -m unittest discover -s dev/tests -v`：46 项全部通过，无跳过、无 expectedFailure。
- `TEMP=/workspace/onboarding-results/block-fix-regression JOBS=4 bash dev/regress_all.sh`：
  18 套、864 个动作全部完成，逐套报告确认 0 FAIL、0 WARN。
- 更新基准前比较：0 regressions、10 changed、3 drifted。10 个像素变化全部是普通角色的
  `block_hit` 布料收尾，3 项 QA 数值变化也在 `block_hit`，且仍为 PASS；其他 854 个动作帧数和像素相同。
- 10 套普通角色的最终预览均通过 `node dev/test_sprite_demo.js <结果目录>/preview.html`，
  包括立即再次受击、反应中释放格挡、释放与受击同一步发生、每次只触发一次火花。
- 人工检查后执行 `python3 dev/baseline.py <完整结果目录> --update`，保留这次有意变化，
  并记录新增关节检查数值；更新后的 `--strict` 比较为 0 regressions、0 changed、0 drifted。
- 两份 `.skill` 已重新打包，共用文件和包检查通过。下一项是路线图 3.2 的俯视 4 方向人形，开始前确认产品选择。


## 第八轮：俯视八方向自由移动

用户选择自由移动、八方向；采用此前建议的 3/4 相机、独立 `game-topdown-animator`、六种动作。

- 新 skill 的 `topdown.py` 用地面坐标与高度计算人形姿势和两段 IK，`art.py` 按深度绘制正/背/侧/斜向。
  没有旋转原侧视位图。腿/臂及武器长度固定，死亡降低身体并闭眼。
- 五基础方向加三种烘焙镜像，全方向共用 pivot；镜像装备换手的限制写入 manifest 和文档。
- wanderer / warden × hd / pixel，四套、192 个片段；每套 48 个，高清 1248 帧、像素 632 帧。
- 独立 QA 检查方向与帧数据绑定、时序、双分量滑步、关节与武器长度、循环、衔接、裁切。
  帧哈希可以发现方向帧错换，但不能理解朝向语义；不能宣称它能自动理解错误生成的图画。
- `TopDownController` 归一化斜向速度，转向/走跑保留相位和子帧时间，避免重复脚步事件；
  动作期间锁定移动、死亡等待复活。真实浏览器使用相同代码。
- 仅复用 `shared/` 的 exporter 和 Unity importer，通过 sync_shared 的选择列表同步。
  三个包均独立，新的包也做了隔离解压后的生成/QA 测试。新路径用 `git add -N` 登记，未提交。
- `regress_all.sh` 加入新四套，并保留底层失败退出码；PowerShell 旧脚本仍仅覆盖原 18 套。
- 基准扩充前：0 regressions、4 new sets、0 drift，原 18 套逐像素、帧数与 QA 数值完全不变。
  扩充后 22 套、1056 片段，严格比较 0 regressions、0 changed、0 drifted；全量 0 FAIL、0 WARN。
- 四套完整新素材分别通过逐帧导出还原、Godot 4.3、Phaser 3.80.1、PixiJS 8.6.6 的导入/播放检查；
  四套都通过 controller 和真实 Chromium 键盘试玩检查。日志 `/tmp/topdown-native-<套>-<检查>.log`。
- 所有 24 张颜色/剪影审查图已查看，结论存在结果目录的 `review/verdict.json`。
  没发现明显阻断问题；简洁的插腰待机姿势、细剑轮廓和背面倒地的透视压缩属于观感复核项。
- 第一版不含独立瞄准、枪械、怪物、自定义 PNG 或物理布料；Unity 未编译，Cocos 仅结构验证。
  引擎原生逐帧播放检查不代表各引擎中的完整八方向游戏状态机已实测。

完整测试：`CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium python3 -m unittest discover -s dev/tests -v`，
62 项通过，无跳过/expectedFailure，含独立解包安装和故障注入。新增 Python 源码格式整理前后 AST 相同。

完整结果：`/workspace/onboarding-results/topdown-regression/spr/all/`。
示例：`wanderer-pixel/preview.html`；新包 `game-topdown-animator.skill`；使用见新 SKILL.md 和 README。

## 第九轮：侧视四足狼

用户确认继续四足方向，首版为独立 `game-quadruped-animator`，狼的 idle、walk、trot、run 四个循环。

- `rig.py`：三段脊柱、颈/头、四条三段腿；每条腿上/下段 18/20 单位，脚腕/跗骨到爪固定。
  前肘向后、后膝向前，IK 超出范围直接报错，不拉伸。走路四相位，慢跑对角腿配对，奔跑含腾空。
- `art.py`：长嘴、尖耳、胸毛、后腿跗骨和近远腿分层。高清/像素分别 116/60 帧，每套 4 个动作。
- 尾巴复用 `shared/cloth.py`，新增可选 `state_at(t) -> (anchor, angle)`；原人形默认路径不改变数值运算。
  分数模拟采样时，把插值尾巴整体平移到精确身体根部，避免非 180Hz 整数采样时根部微小脱离。
- `shared/rig_data.py` 的 `JointRecorder` 从两种真实解剖实现提炼，接收命名二维关节映射。
  两个侧视人形生成器和四足使用它记录原有格式；没有把它描述成通用骨骼/约束求解器。
- QA 分别检查四脚滑步/接触高度，固定骨长及保持骨长的膝肘反折，步态/事件一致性，
  尾巴根部/长度/地面，循环/跳帧/重复帧、裁切及非有限值。
- 新增 17 项故障/行为测试，包含逐脚故障、24fps 分数采样、独立解包和实际播放器。
  开始时安装包尚未生成导致隔离包测试失败；打包后该组 17 项已全部重跑通过。
- 原生测试工具新增 `--all-clips`，避免四足全为循环时只测试 idle。
  高清和像素的每个动作都在 Godot 4.3、Phaser 3.80.1、PixiJS 8.6.6 以 60/144Hz 播放通过。
  导入后逐帧还原也一致；两套真实 Chromium 键盘试玩测试均通过走/慢跑/奔跑、方向切换和停止。
- 8 张颜色/剪影审查图全部看过，结论在 `/workspace/onboarding-results/quadruped-final/wolf-<预设>/review/verdict.json`。
  没发现明显阻断问题；远近腿在待机剪影中会重叠、毛发为棱角风、尾巴偏细，仍需按游戏风格复核。
- 全量回归扩到 24 套、1064 片段，全套 0 FAIL、0 WARN。
  更新基准前严格核对：旧 22 套逐像素、帧数和 QA 数值完全不变，仅新增 wolf-hd / wolf-pixel。
- `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium python3 -m unittest discover -s dev/tests -v`：79 项通过，无跳过/expectedFailure。
  回归基准扩充到 24 套后，`baseline.py --strict` 为 0 regressions、0 changed、0 drifted。
- 共用文件与四个 `.skill` 包同步；新 Python 文件格式整理前后 AST 相同。用户文件与前几轮改动保留，未提交。

结果：`/workspace/onboarding-results/quadruped-final/wolf-pixel/preview.html`；完整回归位于
`/workspace/onboarding-results/quadruped-regression/spr/all/`；日志 `/tmp/quadruped-<预设>-<检查>.log`。

当前限制：只有侧视狼、四个循环，无攻击/受击/死亡、俯视四足、其他犬种/马骨骼或自定义部件图。
步态切换保留相位，但不做接触约束混合；Unity 未编译，Cocos 仅结构检查。
下一步先按游戏需要补四足攻击、受击、死亡，再考虑俯视或其他动物。

## 第十轮：狼的战斗动作

- 新增 attack、hurt、death 三个非循环，分别输出 hit_on/hit_off、恢复待机、body_thud 与终止姿势。
  攻击是四爪着地的前探咬击，没有宣称空中跃扑或自动追击 AI。死亡为伏地闭眼，不是侧翻。
- 骨长与爪接触保持约束；新增胸腹/下颚地面检查。attack/hurt 的尾巴末段向 idle 首帧收敛，
  身体和尾巴分别检查恢复衔接。非循环保留最后一帧，不做循环接缝判断。
- 试玩 J 攻击、H 受击、X 死亡/复活，动作期间锁定移动；训练靶只在面向目标且足够近的 hit_on 记录一次命中。
- 增加事件缺失、恢复姿势破坏、下颚穿地和战斗状态测试；原有四个循环的生成逻辑保留。
- 高清/像素的七动作已分别完成导出还原、Godot/Phaser/PixiJS 60/144Hz 全动作播放和真实浏览器战斗键盘测试。
- 完整测试 83 项通过，无跳过；格式整理后的四足 21 项亦重跑通过。
- 全量回归 24 套、1070 片段，0 FAIL、0 WARN；基准扩充前确认原有 1064 片段的像素、帧数、QA 数值不变，仅新增六个战斗片段。
- 基准分别保存身体/尾巴恢复边的 group，避免同名边覆盖；扩充后严格比较无回退、无变化。
- 六张新增动作颜色/剪影图已经查看，记录在 `/workspace/onboarding-results/wolf-combat-final/wolf-<预设>/review/verdict.json`。
  没发现明显穿地或断肢；简洁伏地造型和无接触混合的状态切换仍需在目标游戏里复核手感。

## 第三轮回归结果（历史）

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
2. 关节位置循环接缝和动作衔接检查已在第六轮补齐；该警告已在第七轮通过恢复 GUARD 保持帧修复。
3. 八方向俯视人形首版已在第八轮完成；下一步按游戏需求补动作/装备，或继续四足攻击/受击/死亡；狼的四个循环已在第九轮完成。
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
