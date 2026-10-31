# 2dgameskills 工作规范

四个独立安装的 Claude skill：`game-sprite-animator`（横版 RPG）、`game-shooter-animator`（横版射击）、`game-topdown-animator`（3/4 俯视八方向自由移动）、`game-quadruped-animator`（侧视狼）。
进度、决定和环境坑见 `HANDOVER.md`，后续计划见 `docs/roadmap.md`，动手前先读。

**方向（2026-10-31）：** 外观用 AI 生图，我们负责绑定、动作、质检、导出；四个 skill 要合并成一个；生物用配置描述，动作按运动方式写。不要再为单个物种新开 skill 或写专门代码。每个阶段要用户看过效果、认可后再往下做。详见 `docs/roadmap.md` 第 3 节。

## 代码布局

- 统一入口首版是 `game-animator/`，包含四个模式的原样快照。改了原模式后运行
  `python dev/sync_modes.py` 更新快照，再重新打包；`--check` 检查文件一致性。统一包目前
  不代表角色配置通用；实验性飞行流程的限制见 `game-animator/references/creature-rig.md`，
  原四个 skill 仍保留。

- 每个 skill 文件夹必须能单独复制、单独打包使用，所以两边共用的文件在两个 skill 里各存一份。
- **共用文件只改 `shared/`**，然后运行 `python dev/sync_shared.py` 复制到两边。直接改 skill 里的副本，`--check` 会报不一致。
  目前共用：`sprite_anim/` 下的 `constraints.py`、`cloth.py`、`mathx.py`、`export.py`，以及 `visual_review.py`、
  `SpriteSetImporter.cs`、`references/visual-review.md`。
- `rig.py`、`motions.py`、`render.py`、`art.py`、`fx.py`、`qa_motion.py`、`generate.py` 两边已经分开演化，各改各的。
  要把它们合进 `shared/`，先证明两边输出不变（见下面的 `--strict`）。
- 俯视模块的绘制、2.5D 骨骼、QA 和播放器独立实现；只复用共用 `export.py` 和 Unity 导入器，
  由 `sync_shared.py` 的文件列表选择同步。不要把侧视 rig、地面线检查或整套无关共用文件复制过去。
- 四足仅复用 exporter、Unity importer、mathx、cloth 和 rig_data。尾巴给共用 `simulate` 传
  `state_at(t)`，人形保留原路径。`JointRecorder` 接收命名二维关节映射，人形与四足共用记录格式；
  骨骼求解和接触规则仍按解剖分别实现，不要把这个小接口描述成完整通用骨骼框架。
- AI 美术流程（阶段 A）：`game-sprite-animator/scripts/cut_parts.py`（template / cut / check），流程见该 skill 的
  `references/ai-art.md`。剪纸模式的武器挂在 `art.hand_grip`，和程序画法共用，改它要跑严格基准。
  示例 `assets/characters/cutout_demo/` 必须是工具对 `source.png` + `joints.json` 的当前输出（测试会比对），
  改了 `cut_parts.py` 就重新生成它。`dev/cutout_match.py` 量切块后和原版的相似度。
- `dev/` 是开发工具，不进 skill 包。
- `regress_all.sh` 现在覆盖 26 套（含 `cutout_demo`；剪纸角色是文件夹，脚本读其中的 `character.json`）；新增模板要加入脚本及 `baseline.json`。新文件打包前用 `git add -N` 登记路径，包内容保持可审查。

## 改完要跑的

```bash
python3 -m unittest discover -s dev/tests -v      # 故障注入、CSS 回放、引擎实测、同步和打包检查
bash dev/engines/get_godot.sh && npm install --prefix dev/engines   # 引擎测试要的 Godot、Phaser、PixiJS，装一次
bash dev/regress_all.sh                          # 26 套全量回归，放后台并检查各套真实退出码
python3 dev/baseline.py                          # 和 dev/baseline.json 比较：状态变差就失败
python3 dev/baseline.py --strict                 # 重构时用：任何像素变化都算失败
python3 dev/package_skills.py                    # 改了 skill 里的文件后重新打包 .skill
```

- 有意改动画面后，确认没有回退，再 `python3 dev/baseline.py --update`，把 `dev/baseline.json` 和改动一起提交。
- `dev/verify_exports_*.py <结果目录>` 校验导出文件，`node dev/test_shooter_demo.js all/<套>` 跑射击试玩页。

## 规则

- 不准用放宽阈值、跳过检查、删掉失败项的办法让 QA 通过。修根因；确实是误判才调阈值，并在 `references/*qa*.md` 写明原因。
- 一个检查查不出某类问题时，写成 `unittest.expectedFailure` 的测试并说明缺口，不要假装能查出。
- 新增 QA 检查要配一个故障注入测试，证明它能抓到植入的问题，并定位到动作和帧。
- 导出按验证程度描述，不夸大：只生成了文件 → 结构校验 → 在引擎里导入 → 实际播放。没在某个引擎里实测，就不能说“支持”或“已验证”。
  每个 skill 的 `references/*integration.md` 里的验证表，必须和实际做过的一致。
- AI 视觉质检的结论是人工判断，写成“需复核”或“观感问题”，不能当作数值证明。
- 不做一次性大重写。分步改，每步保持全量回归 0 FAIL。
- 汇报时写清改了哪些文件、跑了什么命令、真实结果和没解决的问题。

## 骨骼完整性 QA

关节数字正确不代表画面正确：部件丢了中段，rig 照样解得出来。所以五个模式都在像素上检查，规则和阈值见
`shared/references/skeleton-qa.md`，共用代码是 `shared/scripts/sprite_anim/integrity.py`。

- `float`（逐帧，碎块脱离身体）、`bones`（逐帧，骨段上没有画面）、`parts`（整套一次，切块部件缺失、骨段断裂、
  有孤块、枢轴不在图上）。`part_check.py` 只在横版 RPG 里。
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
