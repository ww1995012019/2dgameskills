# 2dgameskills 工作规范

一个 Claude skill `game-animator`，含四个模式：`game-sprite-animator`（横版 RPG）、`game-shooter-animator`（横版射击）、`game-topdown-animator`（3/4 俯视八方向自由移动）、`game-quadruped-animator`（侧视狼），另有实验性飞行生物流程。
进度、决定和环境坑见 `HANDOVER.md`，后续计划见 `docs/roadmap.md`，动手前先读。

**方向（2026-10-31）：** 外观用 AI 生图，我们负责绑定、动作、质检、导出；四个 skill 要合并成一个；生物用配置描述，动作按运动方式写。不要再为单个物种新开 skill 或写专门代码。每个阶段要用户看过效果、认可后再往下做。详见 `docs/roadmap.md` 第 3 节。

## 代码布局

- **源码只改 `game-animator/`。** 四个模式在 `game-animator/modes/<模式>/`。多个模式共用的文件只改
  `game-animator/modes/game-sprite-animator/` 里那一份，清单见 `dev/build_standalone.py` 的 `SHARED`；
  `export.py`、`integrity.py`、`mathx.py` 在统一包里通过适配器加载这一份。
- 根目录的 `game-sprite-animator/` 等四个文件夹及其 `.skill` 是**生成的弃用副本**，只为已安装用户保留，
  不要直接改。改完源码运行 `python dev/build_standalone.py`（`--check` 只检查），再 `python dev/package_skills.py`。
  `dev/` 里的旧测试仍有不少按旧文件夹路径读文件，内容与统一包一致；新测试请用 `game-animator/modes/...` 路径。
- 统一包支持横版和俯视共享角色名称、基础配色的 manifest（`scripts/generate_character.py`）；俯视仍不支持自定义 PNG
  或统一身体比例。实验性飞行流程的限制见 `game-animator/references/creature-rig.md`。
- `rig.py`、`motions.py`、`render.py`、`art.py`、`fx.py`、`qa_motion.py`、`generate.py` 横版和射击两边已经分开演化，各改各的。
  要合成一份，先证明两边输出不变（见下面的 `--strict`）。
- 俯视模块的绘制、2.5D 骨骼、QA 和播放器独立实现；只复用共用 `export.py` 和 Unity 导入器，
  由 `build_standalone.py` 的 `SHARED` 清单分发。不要把侧视 rig、地面线检查或整套无关共用文件复制过去。
- 四足仅复用 exporter、Unity importer、mathx、cloth 和 rig_data。尾巴给共用 `simulate` 传
  `state_at(t)`，人形保留原路径。`JointRecorder` 接收命名二维关节映射，人形与四足共用记录格式；
  骨骼求解和接触规则仍按解剖分别实现，不要把这个小接口描述成完整通用骨骼框架。
- **AI 美术的正式流程是分层人偶**（`layer_parts.py`、`sprite_anim/puppet.py`、`puppet_check.py`、`layer_slots.py`，文档 `references/layered-art.md`）。
  用户 2026-11-01 明确要求：这是商用产品，只能固定输入条件和通用流程，不准为单张图手调；一张图只是测试数据，修问题要改通用规则并用两个不同角色验收；
  新角色默认走 `references/basic-character-workflow.md` 的 basic-side-v1：固定提示词，短发、短款/贴身服装、空手或单手简单剑，双手提示图必需，先待机/走路。用户审核后才考虑扩展；不自动承诺 27 动作。数值规则和绑定到图片哈希的语义复核共同把关；不能宣称代码自动识别全部不合规美术。
  动作适配角色身材的规则集中在 `layered-art.md` 的“How the clips fit a character”，遇到新问题加规则，不改单个角色数据。
- AI 美术流程（阶段 A，现仅用于贴身角色的快速测试）：`modes/game-sprite-animator/scripts/cut_parts.py`（template / cut / check），流程见该 skill 的
  `references/ai-art.md`。剪纸模式的武器挂在 `art.hand_grip`，和程序画法共用，改它要跑严格基准。
  示例 `assets/characters/cutout_demo/` 必须是工具对 `source.png` + `joints.json` 的当前输出（测试会比对），
  改了 `cut_parts.py` 就重新生成它。`dev/cutout_match.py` 量切块后和原版的相似度。
- `dev/` 是开发工具，不进 skill 包。
- `regress_all.sh` 现在覆盖 26 套（含 `cutout_demo`；剪纸角色是文件夹，脚本读其中的 `character.json`）；新增模板要加入脚本及 `baseline.json`。新文件打包前用 `git add -N` 登记路径，包内容保持可审查。

## 已有完整图层的免生图绑定

有共同画布（或裁剪偏移）和已知关节时，优先用 `modes/game-sprite-animator/scripts/bind_known_joints.py`，
见 `references/known-joint-binding.md`。复用已有像素与关节，不重新生成参考图或双手提示图。
该入口只做数值绑定，不重开旧生成任务或替代美术/用户动态验收。开发模板也调用正式的
`known_joint_rig.build_spec`，不要再复制绑定算法。具体改动和验证边界见 `docs/rigging-optimization.md`。

## 改完要跑的

**用户否决画面后的返修，先给用户看，再跑全量。** 按 `modes/game-sprite-animator/references/repair-loop.md`：
只重新渲染受影响角色的受影响动作，跑这些输出的 `qa_motion.py` 和改动模块的单测，用
`scripts/compare_clips.py` 出新旧对照 GIF 发给用户；用户认可后，再一次性跑下面的全量验证、更新视觉记录、
打包、发布网页和提交。认可前不发布网页版本、不写“已修复”。用户认可和数值通过分开汇报。

全量验证（合并、发布或交付前必须全过）：

```bash
bash dev/engines/get_godot.sh && npm install --prefix dev/engines   # 引擎测试要的 Godot、Phaser、PixiJS，装一次
python3 dev/build_standalone.py && python3 dev/package_skills.py   # 生成弃用副本，先本地重建包，归档隔离安装测试使用这些包
python3 -m unittest discover -s dev/tests -v      # 故障注入、CSS 回放、引擎实测、同步和打包检查
bash dev/regress_all.sh                          # 26 套全量回归，放后台并检查各套真实退出码
python3 dev/baseline.py                          # 和 dev/baseline.json 比较：状态变差就失败
python3 dev/baseline.py --strict                 # 重构时用：任何像素变化都算失败
```

- 用户要求源码提交不包含重新打包的 `.skill` 文件。仍须在本地重建并验证包；提交前恢复这些
  产物、显式排除 `.skill`，检查暂存区。仓库内旧包可能落后于源码，安装最新版本请使用源码目录
  或本地重建的包；不通过跳过打包/隔离安装测试来适应这项提交约定。
- 有意改动画面后，确认没有回退，再 `python3 dev/baseline.py --update`，把 `dev/baseline.json` 和改动一起提交。
- `dev/verify_exports_*.py <结果目录>` 校验导出文件，`node dev/test_shooter_demo.js all/<套>` 跑射击试玩页。

## 规则

- 不准用放宽阈值、跳过检查、删掉失败项的办法让 QA 通过。修根因；确实是误判才调阈值，并在 `references/*qa*.md` 写明原因。
- 一个检查查不出某类问题时，写成 `unittest.expectedFailure` 的测试并说明缺口，不要假装能查出。
- 新增 QA 检查要配一个故障注入测试，证明它能抓到植入的问题，并定位到动作和帧。
- 导出按验证程度描述，不夸大：只生成了文件 → 结构校验 → 在引擎里导入 → 实际播放。没在某个引擎里实测，就不能说“支持”或“已验证”。
  每个 skill 的 `references/*integration.md` 里的验证表，必须和实际做过的一致。
- AI 视觉质检的结论是人工判断，写成“需复核”或“观感问题”，不能当作数值证明。
- 复核要看 `review/joints_00.png`，不能只看全身缩略图说“没问题”。QA 标记也要放大核对后再动手：它是测量，可能测错。
- 不做一次性大重写。分步改，每步保持全量回归 0 FAIL。
- 汇报时写清改了哪些文件、跑了什么命令、真实结果和没解决的问题。

## 骨骼完整性 QA

关节数字正确不代表画面正确：部件丢了中段，rig 照样解得出来。所以五个模式都在像素上检查，规则和阈值见
`game-animator/modes/game-sprite-animator/references/skeleton-qa.md`，共用代码是同目录 `scripts/sprite_anim/integrity.py`。

- `float`（逐帧，碎块脱离身体）、`bones`（逐帧，骨段上没有画面）、`parts`（整套一次，切块部件缺失、骨段断裂、
  有孤块、枢轴不在图上，以及部件贴回原图后超出轮廓、头的像素进了躯干）。`part_check.py` 只在横版 RPG 里。
- `bind`（整套一次）：`bind_report.json` 的警告算 WARN，记录到的关节裂缝算 FAIL。QA 结果要带上 `scope` 的动作数，
  “0 FAIL, 0 WARN”只说明测量项通过，不能说成画面没问题。
- 只看合成帧不够：肢体叠在身体上时，躯干会把洞盖住，所以部件要单独检查。
- 刀光帧、射击的 fire/action 动作不判 `float`；后者显示 `n/a`，不算通过。旧数据同样是 `n/a`。
- 新增切块功能时，改完要确认 `cutout_demo` 的 `cut_parts.py check` 仍是 exit 0。

## 关节连续性 QA

两个 `qa_motion.py` 已补上基于 `rig_trace.json` 的循环接缝与动作衔接检查。
射击生成器也记录逐帧关节；故障注入覆盖截短步态、错误衔接、纯关节故障及缩放不变性。
旧数据缺少 joints 时仅运行原有像素检查，不能把它描述为关节检查通过。
规则和开火边界的处理见各 skill 的 `references/smoothness.md` / `motion-qa.md`。

`block_hit -> block` 已改为恢复格挡保持帧，保留首次格挡的入场段。
`animations.json` 的 `next_frame` 声明后续动作的入口（默认 0），播放、布料收尾和 QA 必须一致。
预览及故障注入测试覆盖恢复、连续受击、释放格挡和 FPS override；不通过跳过检查消除警告。

浏览器测试可设 `CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium` 使用现有系统 Chromium。
CSS 测试与 Web 引擎测试均通过 Playwright 在内存中提供本地资源，无需 file:// 权限或外网资源。
