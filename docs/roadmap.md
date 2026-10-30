# 后续工作路线图

更新于 2026-10-30。这份文档列出接下来要做的所有事，按优先级排列，每项写明目标、做法、验收标准和需要用户决定的问题。

相关文档：
- `CLAUDE.md`：工作规范和常用命令，动手前必读
- `HANDOVER.md`：已完成的工作、关键决定、环境坑
- `docs/plans/game-sprite-animator-2.0-technical-plan.md`：用户提供的 2.0 技术方案原稿（未修改）。第 2 节是对它的评审结论，优化方案时请一起看

---

## 1. 现状

两个 skill，都只做**横版侧视人形角色**：

| Skill | 内容 |
|---|---|
| `game-sprite-animator` | 横版 RPG 动作，27 个动作，5 个角色模板，高清和像素两种风格 |
| `game-shooter-animator` | 横版射击，6 种枪、9 个瞄准方向，上下半身分层，4 个角色模板 |

代码约 6000 行 Python，只依赖 `pillow` 和 `numpy`。每个 skill 是独立文件夹，复制或打包成 `.skill` 就能装。

已具备：
- 骨骼和软约束（`rig.py`、`constraints.py`）、布料模拟（`cloth.py`）、程序化绘制（`art.py`）、分层 PNG 绑定（`Cutout`）
- 数值质检：重复帧、循环接缝、跳帧、滑步、脚抖、衔接、关节限位、穿模、出画、握枪、射击节奏（`qa_motion.py`）
- AI 视觉质检流程（`visual_review.py`）
- 导出：序列帧、精灵图、图集、`animations.json`、Godot、Cocos、Unity、Phaser、PixiJS、CSS、Canvas 播放器

工程基础（第四、五轮）：
- 共用代码只有一份（`shared/` + `dev/sync_shared.py`）
- 18 套全量回归基准（`dev/baseline.json`），重构可以证明逐像素不变
- 故障注入测试，覆盖每一项质检
- 实测验证：Godot 4.3、Phaser 3.80、PixiJS 8.6、Chromium CSS 都做了导入和播放测试，18 套全部逐帧和原图一致

验证程度（详见各 skill 的 `references/*integration.md`）：

| 导出 | 程度 |
|---|---|
| `atlas.png`、`animations.json`、`sprite-player.js` | 实际播放 |
| `atlas.json`（Phaser、PixiJS） | 实际导入和播放 |
| Godot `.tres` + `.import` | 实际导入和播放 |
| `sprites.css` | Chromium 里实际播放 |
| Cocos `.plist` | 只做了结构校验 |
| Unity `SpriteSetImporter.cs` | 从未编译运行 |

---

## 2. 对 2.0 技术方案的评审结论

方案原稿在 `docs/plans/`。优化它的时候请对照下面几点，并以仓库的实际代码为准。

**保留：**
- 先审计再动手、分阶段、向后兼容
- 导出分验证等级，生成文件不等于验证过（已写进 `CLAUDE.md`）
- 不准靠放宽阈值通过质检，未实现的检查要标明
- 故障注入测试（已实现，见 `dev/tests/test_qa_faults.py`）
- 俯视角不能旋转侧视图；2D 重叠不等于穿模；分层素材优先

**和仓库实际情况不符，需要改：**
- 方案没提 `game-shooter-animator`，两个 skill 都要考虑
- 方案把很多已有功能写成新功能：运动质检、约束、穿模检测、视觉质检、分层 PNG、各引擎导出、分层动作加烘焙组合（已经是离线的混合）
- 方案的目录结构（约 60 个文件、`pyproject.toml`、`python -m` 命令行、JSON Schema v1→v2 转换）会打破 skill 的安装方式：skill 必须是一个能直接复制的文件夹，用户不会 `pip install`
- Phase 0 审计文档（`audit.md`、`current-architecture.md`）已由 `HANDOVER.md`、`CLAUDE.md` 和本文档覆盖

**范围过大，建议删掉或推迟：**
- 8 类骨骼一起推进。先做俯视人形，再做四足，其他按需求再说
- 状态机、Blend Tree、过渡规则：这些是游戏引擎运行时的事，本工具离线烘焙序列帧
- 网格变形、时间轴编辑器
- 动作改成纯 JSON 关键帧：现有动作是 Python 程序算出来的（`Gait`、`Proc`），改成纯数据会失去这个能力。可以只给自定义动作开 JSON 入口

**方案低估的部分：**
- **绘制才是大头。** 角色外观来自 `art.py` 里 780 行专门画侧视人形的代码。每加一种角色类型或一个视角，都要重写一套画法，这决定画面质量和大部分工作量
- **统一 Rig 接口不要先设计。** 先把第二种骨骼写出来，再从两个真实例子里提炼共同接口

---

## 3. 接下来要做的事

### 3.1 补上两个质检缺口（优先，工作量小）

故障注入测试发现两类问题现在查不出来，写成了 `expectedFailure`（`dev/tests/test_qa_faults.py`）：

1. **截短的步态循环。** 走路每帧本来就改变大半剪影，像素接缝比例总在 1.7 以下，删掉 13 帧里的 1～6 帧都能通过
2. **衔接姿势错误。** 衔接比例除以较快动作的典型步长，像素差又会饱和。把死亡最后一帧接到起跳，比例只有约 1.5，阈值是 2.5

做法：在 `qa_motion.py` 里加基于关节位置的检查，数据来自 `rig_trace.json` 的 `joints`（`generate.py` 的 `TRACE_JOINTS`）。
- 接缝：最后一帧到第一帧的关节位移，和动作内平均每帧关节位移比较
- 衔接：A 最后一帧和 B 第一帧的关节位移，用身高归一化，不除以动作速度

验收：
- 两个 `expectedFailure` 测试变成普通测试并通过
- 全量回归仍然 0 FAIL。如果冒出新的 FAIL，先确认是真问题还是误判；真问题就修动作，不调阈值
- 两个 skill 都要改（`qa_motion.py` 两边不同，不在 `shared/`）

### 3.2 俯视 4 方向人形（下一个新功能）

用户的游戏横版、俯视都有，也需要怪物。先做俯视人形，因为能复用最多的骨骼和动作经验。

**先和用户确认：**
- 移动方式：按格子走，还是自由移动？要不要斜向？（决定 4 方向够不够，见 3.3）
- 视角：常见的 3/4 俯视（能看到脸和身体正面，像星露谷物语），还是正上方俯视？建议 3/4 俯视
- 先放进哪个 skill：新建 `game-topdown-animator`，还是加进 `game-sprite-animator`？建议新建，保持每个 skill 简单，公共代码放 `shared/`
- 需要哪些动作，建议第一批：idle、walk、run、attack、hurt、death

**做法：**
- **朝向：** 下（面朝镜头）、上（背对）、右（侧面）三套画法，左 = 右的镜像。非对称装备（比如只在右手的武器）要声明镜像规则
- **绘制（最大的工作量）：** 每个朝向需要自己的部件画法和前后层级。正面看到脸和身体正面、双臂在两侧；背面看到后脑和背；侧面接近现有横版但要压缩高度表现俯视感。参考 `art.py` 的 `CharacterArt` 和 `Canvas` 结构写新的 `TopDownArt`
- **骨骼：** 可以沿用现有关节，但投影不同。正面和背面时腿前后摆动表现为上下移动和缩短，手臂左右在两侧
- **动作：** 走路、跑步要按朝向重新设计，正面走路的摆臂和侧面不同。攻击要按朝向挥动（向下攻击时武器朝镜头，向上时被身体挡住一部分）
- **层级：** 背面时武器在身体前还是后，正面时远侧手臂被遮挡。每个朝向一张层级表
- **锚点：** 所有朝向共用脚底 pivot
- **导出：** 动作名按朝向命名，如 `walk_down`、`walk_up`、`walk_side`；`animations.json` 加 `directions` 字段和每个动作的镜像信息；引擎文件照现有格式生成
- **质检：**
  - 滑步检查改成按移动方向（正面和背面走路时，脚是上下移动，不是左右）
  - 新增朝向一致性：同一动作不同朝向的帧数、事件帧、循环时长一致
  - 视觉质检的审查图按朝向排列
- **预览页：** `preview.html` 支持 WASD 或方向键四向移动

**验收：**
- 至少 2 个角色模板 × 高清和像素，6 个动作 × 3 个朝向，全量回归 0 FAIL
- 故障注入：朝向标签错配（把 `walk_up` 的帧放进 `walk_down`）能被查出
- Godot、Phaser、PixiJS 实测通过（沿用 `dev/godot_smoke.py`、`dev/web_engines.js`）
- 视觉质检看完所有审查图，没有未解决的 bug 级问题
- 加入 `dev/regress_all.sh` 和 `dev/baseline.json`

### 3.3 俯视 8 方向

在 4 方向之上加 4 个斜向：右上、右下需要新画法，左上、左下靠镜像。一共 5 套画法。

要点：
- 斜向移动的速度要和轴向一致（对角线速度归一化），`speed_px_s` 按朝向给出
- 移动方向和瞄准方向可能分开（类似射击 skill 的上下半身分层，可以复用那套思路）
- 质检：相邻朝向之间切换时姿势连续，不跳

验收：8 方向预览里朝向没有错配；斜向和轴向速度一致；引擎实测通过。

### 3.4 四足动物

第一种非人形骨骼。先做横版侧视的狼或狗，动作：idle、walk、trot、run。

要点：
- 新的骨骼：脊柱分段、颈、头、尾，四条腿各三段
- 步态：每条腿的相位和落脚时间，walk、trot、run（gallop）的相位关系不同
- 绘制：新的 `QuadrupedArt`
- 质检：滑步检查扩展到四只脚；尾巴用现有布料链（`cloth.py`）
- 写完第二种骨骼后，再从人形和四足两个例子里提炼公共骨骼接口，放进 `shared/`

验收：狼的 walk、trot、run 循环通过所有运动质检；故意植入的滑步能被发现；引擎实测通过。

### 3.5 其他角色类型（按需求再排）

飞行（鸟、蝙蝠）、多肢（蜘蛛）、蛇形、软体（史莱姆）、机甲。等用户给出具体游戏需要的角色再做，一次一类。

### 3.6 引擎实测补全

- **射击 skill 的分层挂点：** 现在只测了逐帧画面和播放。要在 Godot 和 Phaser 里按文档把上半身放到下半身每帧的 `anchor` 上，截图和 `preview.html` 的合成结果比较
- **Unity、Cocos：** 需要装了编辑器的机器（这个 Linux 容器装不了，需要图形界面和授权）。Unity 要验证 `SpriteSetImporter.cs` 能编译、能生成 `.anim`、pivot 正确；Cocos 要验证 `.plist` 导入和 Trim 设置

### 3.7 遗留的观感问题

见 `HANDOVER.md` 的「视觉质检记录」：
- commando 等角色朝正下方瞄准时，枪和腿在剪影里叠在一起
- ghost 朝正下方瞄准狙击枪时，枪管搁在地面上
- goblin `attack_3` 起手时枪杆横过脸
- ninja 像素版 `attack_2` 第 2 帧刀光是折线
- goblin 像素版、swat 深色武器和衣服在剪影里不显眼（改角色配色即可）

### 3.8 可选的代码整理

`rig.py`、`render.py`、`motions.py`、`art.py`、`fx.py`、`qa_motion.py`、`generate.py` 两个 skill 各有一份，已经分开演化。可以逐个合进 `shared/`，每合一个都要用 `python3 dev/baseline.py --strict` 证明两边输出逐像素不变。做俯视 skill 之前合并 `render.py` 和 `qa_motion.py` 最有价值，因为第三个 skill 也要用。

---

## 4. 不做的事

- 实时状态机、Blend Tree：交给游戏引擎
- 网格变形、时间轴编辑器、通用有限元
- 自动拆分任意扁平图片成部件
- 改成 pip 包或 `python -m` 命令行
- 一次推进多类新骨骼

---

## 5. 给接手的 AI

1. 读 `CLAUDE.md`、`HANDOVER.md` 和本文档
2. 环境准备：`pip install pillow numpy`；引擎测试需要 `bash dev/engines/get_godot.sh` 和 `npm install --prefix dev/engines`
3. 先跑一遍 `python3 -m unittest discover -s dev/tests -v`，确认环境正常
4. 从第 3 节按顺序做；3.2 开始前先问用户「先和用户确认」里的问题
5. 每完成一项，更新本文档的状态和 `HANDOVER.md`
