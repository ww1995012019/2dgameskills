# Game Sprite Animator 2.0
## 通用 2D 角色动画生产框架：完整技术方案与实施规格

- **目标仓库**：https://github.com/ww1995012019/2dgameskills
- **目标版本**：Game Sprite Animator 2.0
- **文档状态**：工程设计草案；不是已实现功能清单
- **用途**：可直接交给 Codex / Claude Code 做仓库审计、分阶段重构和验收

> 重要：本方案把“现有基础能力”和“计划新增能力”分开。实施前必须重新检查目标仓库当前分支、目录、代码、依赖和测试。本方案不代表任何新功能已经实现，也不代表所有引擎导出已经通过实际验证。

---

# 1. 项目目标

将现有 `game-sprite-animator` Skill 从以横版人形角色为中心的动画生成工具，逐步升级为一个**多角色、多视角、可组合动作、可自动质检、可导出到游戏引擎的 2D 动画生产框架**。

用户可以通过自然语言描述角色，也可以提供分层 PNG、现有 Sprite Sheet 或自定义角色配置。系统负责角色结构、骨骼绑定、动作生成、逐帧渲染、质量检测、问题定位、有限自动修复和资源导出。

## 1.1 核心目标

1. 支持人形、机甲、四足动物、飞行生物、蛇形生物、软体怪物、多肢生物和自定义骨骼。
2. 支持横版侧视、俯视 4 方向、俯视 8 方向。
3. 支持内置动作、自定义动作、动作过渡、动作混合、分层动画和事件轨道。
4. 支持程序化角色、分层 PNG 角色和已有 Sprite Sheet。
5. 支持 FK、IK、关节约束、武器挂点、脚部接触、尾巴/披风弹性和基础网格变形。
6. 建立结构、运动、几何、挂点、视觉和导出/运行时六层 QA。
7. 输出 PNG 序列帧、Sprite Sheet、Atlas、统一动画 Manifest 和目标引擎资源。
8. 保留旧版生成流程，采用渐进式迁移，不一次性推翻现有代码。

## 1.2 非目标与边界

首期不承诺：
- 任意一张扁平图片都能无人工干预地准确拆成所有身体部件。
- 任意角色都能自动获得完美骨骼和完美动作。
- 所有二维重叠都能被正确判断为穿模或正常遮挡。
- 真实 3D 深度重建、真实体积碰撞或完整 3D 物理。
- AI 视觉模型能够保证发现所有美术问题。
- 所有游戏引擎、所有版本都一次性完成实际导入验证。

---

# 2. 现有能力基线与审计要求

从当前项目的既有设计讨论来看，现有系统以**横版侧视人形角色**为核心，已有程序化姿势/骨骼计算、动作曲线、逐帧渲染、运动 QA 和资源导出基础。已有 QA 设计覆盖重复帧、循环接缝、帧间突变、脚部抖动/滑步以及部分动作交接检查。

这些能力不等于已经具备通用骨骼、多视角、穿模检测或完整引擎验证。开始开发前，Codex/Claude Code 必须检查当前仓库，核实实际文件名、入口、数据格式、依赖和测试。

## 2.1 Phase 0 必须确认

- 当前分支、工作区状态、未提交修改。
- README、SKILL.md、references、scripts、assets、tests 的完整内容。
- 当前角色配置格式、动作配置格式、输出目录结构。
- 实际 CLI 入口和 Python 依赖。
- 原始样例能否在干净环境运行。
- QA 脚本的真实检查项和报告格式。
- 每个导出器的验证级别：仅生成、结构校验、引擎导入、运行时播放。
- 当前已知缺陷和不可复现功能。

## 2.2 向后兼容原则

- 旧配置标记为 `schema_version: 1`。
- 新配置使用 `schema_version: 2`。
- 提供 v1 到 v2 转换器。
- 旧人形 Rig 通过 `LegacyHumanoidRigAdapter` 接入新接口。
- 保留原有 CLI 参数和输出文件名；如需变更，提供兼容 wrapper。
- 为原始样例建立 golden tests，避免重构造成无声回归。
- 不覆盖用户未提交修改，不擅自删除旧素材和输出。

---

# 3. 产品架构

## 3.1 总体数据流

```text
Skill / CLI / Editor
        |
        v
Project Orchestrator
        |
        +-- Character Definition & Asset Import
        |
        +-- Rig Registry
        |      +-- Humanoid
        |      +-- Mechanical
        |      +-- Quadruped
        |      +-- Flying
        |      +-- Serpentine
        |      +-- Deformable
        |      +-- Multi-limb
        |      +-- Custom
        |
        +-- View System
        |      +-- Side View
        |      +-- Top-down 4-dir
        |      +-- Top-down 8-dir
        |
        +-- Animation Runtime
        |      +-- Motion Library
        |      +-- State Machine
        |      +-- Blend Tree / Layers / Masks
        |      +-- Events / Transitions
        |
        +-- Pose Solver
        |      +-- FK / IK
        |      +-- Constraints
        |      +-- Attachments
        |      +-- Contact / Spring / Deformation
        |
        +-- Renderer
        |      +-- Procedural
        |      +-- Layered Sprite / Cutout
        |      +-- Mesh Deformation
        |
        +-- QA Pipeline
        |      +-- Structural / Motion / Geometry
        |      +-- Attachment / Visual / Runtime
        |
        +-- Export Pipeline
               +-- PNG / Sprite Sheet / Atlas / JSON
               +-- Web / Phaser / PixiJS
               +-- Godot / Unity / Cocos (逐个验证)
```

## 3.2 模块职责

| 模块 | 主要职责 |
|---|---|
| Skill | 理解需求、选择角色/视角/动作模板、组织 CLI 调用 |
| Orchestrator | 串联素材导入、Rig、动作、渲染、QA 和导出 |
| Character Schema | 描述角色、素材、Rig、视角和装备 |
| Rig | 骨骼拓扑、姿势求解、约束、挂点 |
| Motion | 动作通道、关键帧、时间、事件、混合 |
| Renderer | 将 Pose 和素材绘制为帧 |
| QA | 检测问题、定位帧/部件、输出证据 |
| Exporter | 输出统一 Manifest 和目标引擎资源 |

## 3.3 推荐目录

```text
game-sprite-animator/
├── SKILL.md
├── README.md
├── pyproject.toml
├── schemas/
│   ├── character.schema.json
│   ├── rig.schema.json
│   ├── animation.schema.json
│   └── export.schema.json
├── core/
│   ├── project.py
│   ├── character.py
│   ├── skeleton.py
│   ├── pose.py
│   ├── animation.py
│   ├── constraints.py
│   ├── interpolation.py
│   ├── state_machine.py
│   ├── blend.py
│   └── events.py
├── rigs/
│   ├── registry.py
│   ├── base.py
│   ├── humanoid/
│   ├── mechanical/
│   ├── quadruped/
│   ├── flying/
│   ├── serpentine/
│   ├── deformable/
│   ├── multi_limb/
│   └── custom/
├── views/
│   ├── base.py
│   ├── side/
│   └── top_down/
├── assets/
│   ├── importer.py
│   ├── layers.py
│   ├── anchors.py
│   ├── masks.py
│   └── bleed.py
├── motions/
│   ├── library.py
│   ├── retarget.py
│   ├── common/
│   ├── humanoid/
│   ├── mechanical/
│   ├── quadruped/
│   ├── flying/
│   └── top_down/
├── solver/
│   ├── fk.py
│   ├── ik/
│   ├── joint_limits.py
│   ├── contact.py
│   ├── spring.py
│   └── deformation/
├── renderer/
│   ├── base.py
│   ├── procedural/
│   ├── cutout/
│   ├── mesh/
│   └── effects/
├── qa/
│   ├── pipeline.py
│   ├── structural.py
│   ├── motion.py
│   ├── geometry.py
│   ├── attachment.py
│   ├── visual.py
│   ├── runtime.py
│   └── report.py
├── exporters/
│   ├── base.py
│   ├── spritesheet/
│   ├── atlas/
│   ├── web/
│   ├── phaser/
│   ├── pixijs/
│   ├── godot/
│   ├── unity/
│   └── cocos/
├── editor/
│   ├── preview/
│   └── timeline/
├── templates/
│   ├── characters/
│   ├── rigs/
│   └── motions/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   ├── fixtures/
│   └── engine_smoke/
├── scripts/
└── docs/
```

这是目标结构，不要求一次性搬迁。按阶段将旧模块迁移到新位置，旧入口通过 wrapper 保留。

---

# 4. 八类角色骨骼家族

所有 Rig 遵循统一接口，但不强制共享相同的骨骼拓扑和约束。

## 4.1 Humanoid：人形

适用：人类、士兵、骑士、法师、忍者、丧尸、骷髅和类人怪物。

典型节点：
- root、pelvis、spine、chest、neck、head。
- shoulder、elbow、wrist、hand。
- hip、knee、ankle、foot。
- near/far 或 left/right limb。

能力：
- 双足步态、脚底接触、双骨骼 IK。
- 头部朝向、上半身瞄准。
- 武器/盾牌挂点。
- 横版前后肢体遮挡。

## 4.2 Mechanical：机械

适用：机甲骑士、机器人、机械士兵、机械 Boss。

可以复用人形拓扑，但增加：
- 机械关节角度/轴向限制。
- 多边形装甲轮廓。
- 液压杆和连杆长度约束。
- 武器、盾牌、炮管、推进器、背包挂点。
- 机械变形和模块开合。
- 可选履带、轮式、多足子系统。

机械膝、液压连杆和装甲板不能简单视为普通生物关节。

## 4.3 Quadruped：四足

适用：狼、狗、猫、马、恐龙、四足怪物。

节点：
- root、spine segments、neck、head、tail。
- 四条腿的 shoulder/elbow/wrist/paw 或 hip/knee/ankle/paw。

能力：
- walk、trot、run、gallop。
- 步态相位、落脚点、接触锁定。
- 脊柱弯曲、头部稳定、尾巴跟随。
- 按体型配置步幅、周期和占空比。

## 4.4 Flying：飞行

适用：鸟、蝙蝠、飞龙、飞行机器人。

节点：
- body、neck、head、tail。
- 左右翼的 root、upper、lower、tip。
- 可选腿、爪和推进器。

能力：
- flap、glide、hover、dive、takeoff、landing。
- 左右翼相位、翼展和关节范围。
- 身体姿态、飞行方向、翅膀遮挡。

## 4.5 Serpentine：蛇形/长体

适用：蛇、长身龙、触手、链节机械体。

能力：
- 可变数量骨骼链。
- 曲线跟随和延迟传播。
- 转弯半径、波长、波速。
- 头部目标跟随和尾部衰减。
- 自碰撞检测（允许忽略相邻节）。

## 4.6 Deformable：软体/变形

适用：史莱姆、果冻怪、软体怪物。

能力：
- squash/stretch。
- 2D 网格顶点或轮廓控制点变形。
- 弹性回弹和形变范围限制。
- 轮廓自交、网格三角形翻转检测。
- 面积变化阈值作为近似质量检查。

首期不实现通用有限元或真实流体模拟。

## 4.7 Multi-limb：多肢

适用：蜘蛛、章鱼、多臂机械、多足怪物。

能力：
- 可配置 N 条肢体链。
- 每条链独立 FK/IK。
- 足端目标规划、步态分组和相位协调。
- 肢体间碰撞和遮挡规则。

## 4.8 Custom：自定义

允许 JSON 定义关节、骨骼链、约束、挂点和绘制层级；高级模式允许注册 Python Rig 插件。

安全要求：
- 不允许不可信 JSON 执行任意 Python。
- 插件必须显式注册/安装。
- 配置错误要给出字段路径和具体原因。

## 4.9 统一 Rig 接口

```python
class BaseRig:
    rig_type: str
    capabilities: set[str]

    def load_spec(self, spec): ...
    def build(self): ...
    def solve_pose(self, pose, context): ...
    def get_joint_world_positions(self): ...
    def get_bone_segments(self): ...
    def get_attachment_transforms(self): ...
    def get_collision_shapes(self): ...
    def validate_structure(self): ...
```

每个 Rig 声明 `capabilities`。动作按能力筛选，不兼容时必须明确报错或降级，不能静默忽略。

---

# 5. 视角系统

横版与俯视角必须是不同的 ViewProfile，不能把横版图片旋转 90 度当成俯视动画。

## 5.1 Side View（横版侧视）

- 默认朝右；左向可镜像，但非对称装备/武器可声明禁止镜像。
- 明确 near/far limb 和绘制顺序。
- 全部帧使用稳定 pivot 和地面基线。
- 区分角色世界移动、动画 root offset 和游戏引擎位移。
- 支持 walk/run/jump/dash/attack/hurt/death 等动作。

## 5.2 Top-down（俯视角）

先做 4 方向，再扩展 8 方向。

**4 方向**：up、down、left、right。先实现 idle、walk、attack、hurt。

**8 方向**：N、NE、E、SE、S、SW、W、NW。需要方向动作映射、对角线速度归一化、武器朝向和遮挡层级。

关键规则：
- 移动方向与瞄准/攻击方向可独立。
- 俯视角有独立身体投影和遮挡规则。
- 方向选择优先级：精确方向动画 > 合法镜像/邻方向映射 > 明确降级回退。
- 不得默认把侧视动作旋转生成俯视动作。

示例 ViewProfile：

```json
{
  "view": "top_down",
  "directions": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"],
  "projection": "top_down_2d",
  "depth_sort": {
    "mode": "foot_point",
    "tie_breaker": "layer_order"
  },
  "mirror_policy": {
    "enabled": true,
    "excluded_clips": ["asymmetric_attack"]
  }
}
```

---

# 6. 角色素材与绑定

## 6.1 两条素材输入路径

**A. 分层 PNG（推荐）**
- 每个身体部件独立 RGBA PNG。
- 定义 parent、pivot、z-index、碰撞轮廓和关节锚点。
- 适合机甲、装备、武器和可替换部件。

**B. 扁平 Sprite / Sprite Sheet**
- 支持导入已有帧序列、Atlas 和 Manifest。
- 可执行帧级 QA 和锚点校验。
- 可以提供人工分割/标注辅助流程。
- 不承诺自动分割任意扁平图都准确。

## 6.2 部件数据

```json
{
  "id": "right_forearm",
  "file": "parts/right_forearm.png",
  "parent": "right_elbow",
  "pivot": [12, 8],
  "z_index": 30,
  "collision_profile": "forearm_hull",
  "mirrorable": true
}
```

每个部件应记录：
- 文件路径、尺寸、hash。
- 父节点和 pivot。
- 关节锚点。
- 绘制层级。
- 碰撞多边形或轮廓。
- 是否可镜像、旋转、缩放。
- 材质/颜色组（可选）。

## 6.3 导入和绑定步骤

1. 检查 PNG、透明通道、画布尺寸和文件路径。
2. 选择 Rig 模板。
3. 验证关节和锚点。
4. 建立父子变换树。
5. 生成静止姿势预览。
6. 执行锚点、部件边界和遮挡 QA。
7. 用户确认后再生成动作。

统一帧 pivot，不允许用每帧裁切边界作为动态锚点。Atlas 导出要提供透明边缘 bleed/extrude，减少采样黑边。

---

# 7. 动作系统

## 7.1 动作分类

| 类别 | 示例 |
|---|---|
| Idle | 待机、呼吸、观察、警戒 |
| Locomotion | 行走、奔跑、爬行、游泳、飞行 |
| Jump | 起跳、上升、滞空、下降、落地 |
| Combat | 轻击、重击、连击、刺击、投掷 |
| Defense | 格挡、闪避、弹反、盾击 |
| Skill | 施法、激光、冲锋、召唤、爆炸 |
| Interaction | 拾取、开门、推动、搬运 |
| Damage | 受击、击退、失衡、眩晕 |
| Death | 倒地、解体、爆炸、消散 |
| Special | 变形、进化、启动、关闭、胜利 |

## 7.2 动作通道

统一使用语义化轨道：
- `transform`：位置、旋转、缩放。
- `joint`：关节角度、IK 目标。
- `attachment`：武器、盾牌、工具。
- `deform`：网格顶点/形状参数。
- `effect`：发光、拖尾、粒子触发。
- `root_motion`：世界位移/速度。
- `event`：脚步、命中、起跳、落地等事件。

## 7.3 动作定义示例

```json
{
  "schema_version": 2,
  "id": "heavy_slash",
  "family": "combat",
  "compatible_rigs": ["humanoid", "mechanical_humanoid"],
  "required_capabilities": ["weapon_attachment"],
  "view_profiles": ["side"],
  "duration": 0.9,
  "fps": 30,
  "loop": false,
  "tracks": [
    {
      "target": "right_arm",
      "property": "rotation",
      "keys": [
        {"t": 0.0, "value": -55, "curve": "ease_in"},
        {"t": 0.3, "value": -110, "curve": "cubic"},
        {"t": 0.5, "value": 65, "curve": "ease_out"},
        {"t": 0.9, "value": 0, "curve": "ease_in_out"}
      ]
    }
  ],
  "events": [
    {"t": 0.48, "name": "hit_on"},
    {"t": 0.62, "name": "hit_off"}
  ],
  "tags": ["grounded", "attack", "one_shot"]
}
```

统一使用秒作为时间单位；渲染采样时转换为帧。每个轨道明确插值方式、循环行为和超出时间范围的采样策略。

## 7.4 状态机、混合和分层

新增：
- Animation State Machine：Idle、Move、Attack、Hurt、Dead 等。
- Blend Tree：按速度、方向、姿态参数混合。
- Layers：身体、上半身、武器、表情、特效。
- Masks：限制动作影响的骨骼。
- Transition：过渡时长、条件和中断规则。
- Event Track：动作事件。

必须定义优先级和中断策略。例如死亡状态锁定普通移动；受击是否打断攻击由配置决定。

## 7.5 Root Motion

区分：
- 姿势中的 root offset。
- 游戏世界坐标中的 root motion。
- 引擎控制器移动速度。

禁止重复应用位移。每个 clip 声明 `in_place` 或 `root_motion`。

---

# 8. 求解器

## 8.1 FK / IK

- FK：父关节变换向子关节传播。
- Two-bone IK：人形手臂和腿。
- FABRIK 或等价链求解：多节肢体、尾巴、触手。
- Contact Lock：支撑期间锁定脚/爪目标。
- Soft IK：接近伸展极限时平滑压缩。

必须处理不可达目标、奇异姿态、数值容差和确定性测试。

## 8.2 关节约束

支持：
- 角度 min/max。
- 固定轴/允许轴。
- 骨骼长度约束。
- 机械铰链和限位旋转。
- Attachment 约束。
- 可选弹簧约束。

约束失败报告实际值、允许范围、关节 ID 和帧号。

## 8.3 弹簧和延迟

用于尾巴、披风、耳朵、天线、软管、翼尖和机械液压视觉延迟。首期采用稳定、可复现的弹簧近似，不承诺真实布料模拟。模拟需要固定时间步或稳定积分策略，避免结果严重依赖显示帧率。

## 8.4 变形

软体角色支持：
- 2D 网格或轮廓控制点。
- squash/stretch。
- 弹性回弹。
- 网格三角形翻转检测。
- 轮廓自交检测。
- 面积/边长异常阈值。

首期不实现通用有限元和真实流体。

---

# 9. 自动质检 QA 2.0

QA 必须输出结构化报告、证据图和可定位的问题。不能只输出一个 PASS。

## 9.1 六层 QA

### QA-1 Structural：结构

检查：
- 节点 ID 重复/缺失。
- 父节点不存在或父子循环。
- 骨骼长度为零/异常。
- 锚点、部件、素材引用无效。
- 动作通道不存在。
- Rig、View、Clip 能力不兼容。

### QA-2 Motion：运动

保留并扩展现有运动检查：
- hold：连续重复帧。
- seam：循环首尾变化。
- spike：单帧异常突变。
- jitter：接触点抖动。
- slide：脚/爪支撑期间滑动。
- transition：动作交接姿势突变。
- speed consistency：root motion 与声明速度不一致。
- direction continuity：方向切换异常。

不同动作类别使用不同阈值。攻击允许更高的速度峰值，不能用待机阈值统一判断。

### QA-3 Geometry：几何与穿插

每个部件可定义 polygon、capsule、segment、circle 等碰撞轮廓。配置：
- 部件类别。
- z-order。
- 允许接触/允许重叠表。
- 禁止穿越区域。
- 特定动作阶段的例外。

检测：
- 不允许部件相交。
- 手臂/腿/武器进入躯干禁区。
- 装甲板穿插。
- 关节与部件脱离。
- 机械连杆长度异常。
- 软体轮廓自交。
- 多肢异常交叉。

**重要：** 2D 重叠可能是正常遮挡。不能把所有像素重叠都判定为穿模。必须结合碰撞轮廓、z-order、遮挡规则、允许接触表和动作阶段。2D 视觉无法证明隐藏在画面后的真实三维关系。

### QA-4 Attachment：挂点

检查：
- 武器/盾牌是否绑定到正确挂点。
- 挂点变换是否突变。
- 装备与握持点误差。
- 装备是否异常远离角色。
- 镜像后非对称装备是否错误翻转。

### QA-5 Visual：视觉

输出：
- 每个动作关键帧 contact sheet。
- 透明背景预览。
- 骨骼、锚点和碰撞体 overlay。
- 可疑帧截图和问题列表。

视觉模型辅助检查部件错位、轮廓漂移、装备方向和遮挡不自然。结果标记为 `advisory` / `needs_review`，不能冒充严格几何证明。

### QA-6 Runtime / Export：运行时和导出

检查：
- Manifest schema。
- Atlas bounds、帧矩形和 pivot。
- 文件引用完整性。
- 帧数、帧率、事件时间。
- 透明边缘和 bleed。
- 不同刷新率下播放器采样稳定。
- 目标引擎导入/运行 smoke test。

## 9.2 QA 报告示例

```json
{
  "schema_version": 2,
  "project": "mech_knight",
  "status": "needs_review",
  "summary": {"pass": 124, "warn": 3, "fail": 1},
  "issues": [
    {
      "id": "geometry.weapon_torso_intersection",
      "severity": "error",
      "clip": "heavy_slash",
      "frame": 14,
      "parts": ["sword", "torso"],
      "message": "武器碰撞轮廓进入躯干禁入区域",
      "evidence": "qa/evidence/heavy_slash_014.png",
      "confidence": 0.96,
      "repair_hint": "检查 weapon attachment offset 或该帧手腕角度",
      "auto_fixable": false
    }
  ]
}
```

## 9.3 自动修复策略

安全自动修复：
- 缺失默认参数。
- 无效帧路径。
- 可确定的重复终帧。
- 可重建的缓存。

建议人工确认：
- 关节角度调整。
- 武器挂点偏移。
- 部件层级。
- 碰撞轮廓修改。

禁止静默自动修复：
- 重绘角色素材。
- 改变角色比例。
- 放宽 QA 阈值来掩盖问题。
- 删除动作事件或跳过失败检查。

修复循环必须有最大迭代次数、修改 diff、复检结果和人工待办清单。

---

# 10. 渲染和导出

## 10.1 统一中间 Manifest

Manifest 至少包含：
- schema_version。
- 角色 ID、Rig 类型和 View。
- frame/canvas size、pivot。
- directions。
- clips、frames、fps、loop。
- root motion。
- events。
- atlas 文件和 frame bounds。
- 资源 hash、工具版本。
- QA 状态和验证级别。

## 10.2 导出优先级

第一优先：
1. PNG frame sequence。
2. Sprite Sheet。
3. Atlas PNG + JSON。
4. animations.json / animation manifest。
5. HTML/Canvas preview。

第二优先：
- Phaser。
- PixiJS。
- Godot。
- Unity。
- Cocos Creator。

每个导出器必须有 schema validation、最小样例和实际导入验证。验证状态分级：
- `generated`：文件已生成。
- `schema_validated`：结构校验通过。
- `import_smoke_tested`：目标引擎实际导入。
- `runtime_playback_tested`：实际运行播放。
- `not_verified`：尚未验证。

不得把“生成了某引擎文件”表述为“已在该引擎验证”。

---

# 11. CLI 与 Skill 工作流

## 11.1 建议 CLI（名称可按现有入口兼容调整）

```bash
# 验证角色配置
python -m game_sprite_animator validate character.json

# 预览角色绑定
python -m game_sprite_animator preview character.json

# 生成动作
python -m game_sprite_animator generate character.json --clips idle,walk,attack

# 运行 QA
python -m game_sprite_animator qa out/mech_knight

# 导出
python -m game_sprite_animator export out/mech_knight --target phaser

# 完整流水线
python -m game_sprite_animator build character.json --qa --export phaser
```

旧 CLI 必须保留兼容 wrapper，直至迁移完成。

## 11.2 Skill 执行步骤

收到“制作俯视角机甲骑士，8 方向移动和攻击”时：

1. 识别角色家族：mechanical_humanoid。
2. 识别视角：top_down。
3. 识别方向：8。
4. 检查素材来源和必需部件。
5. 检查 Rig capabilities。
6. 生成/验证角色配置。
7. 生成或绑定素材。
8. 生成动作。
9. 运行 QA。
10. 展示关键帧、问题帧和报告。
11. 执行安全修复并复检。
12. 导出并报告实际验证等级。

信息不足时只询问最关键缺失项。Skill 负责调度工具，不把复杂算法写成纯提示词。

---

# 12. 测试策略与验收

## 12.1 单元测试

- Rig 拓扑、FK、IK、关节约束。
- 动作插值、循环采样、事件时间。
- 镜像和方向映射。
- Attachment 变换。
- 几何碰撞和允许接触规则。
- Manifest 序列化。
- Atlas bounds 和 pivot。

## 12.2 集成测试角色

建立固定 fixture：
- `test_humanoid_side`
- `test_mech_knight_side`
- `test_humanoid_topdown_4dir`
- `test_humanoid_topdown_8dir`
- `test_wolf_quadruped`
- `test_bird_flying`
- `test_slime_deformable`
- `test_spider_multilimb`

每个角色生成适用的 idle、move、attack、hurt、death 并运行 QA。

## 12.3 故障注入测试（非常重要）

人工植入：
- 手臂关节反向。
- 武器挂点偏移。
- 刀刃进入躯干禁区。
- 重复帧。
- 循环接缝突变。
- 脚掌支撑时滑动。
- 俯视角方向标签错配。
- Atlas bounds 越界。
- 父骨骼循环引用。

QA 必须识别问题类型、clip、frame/part/joint 和证据。未实现的检查必须标 `not_implemented`，不能虚报通过。

## 12.4 MVP 验收矩阵

| 能力 | 验收要求 |
|---|---|
| 旧版人形侧视 | 原样例仍可生成，回归测试通过 |
| 机械人形侧视 | 机甲骑士至少 8 个基础动作 |
| 俯视 4 方向 | idle/move/attack/hurt |
| 俯视 8 方向 | 8 向移动和方向攻击 |
| 四足 | 狼 walk/trot/run/idle |
| 飞行 | 鸟 flap/glide/turn |
| Geometry QA | 故意穿插 fixture 能被发现 |
| Attachment QA | 武器挂点偏移 fixture 能被发现 |
| Visual QA | 输出证据和人工复核标记 |
| Web 导出 | 播放器实际运行通过 |
| 其他引擎 | 通过对应 smoke test 后才标记支持 |

---

# 13. 分阶段实施路线

所有时间仅为粗略工程量级，不是交付承诺。以验收结果为准。

## Phase 0：仓库审计与基线（必须先做）

任务：
- 检查分支、工作区、目录、依赖、入口和测试。
- 运行现有角色生成、QA 和导出流程。
- 记录当前输出、性能、已知缺陷和引擎验证状态。
- 绘制实际模块依赖图。

交付：
- `docs/audit.md`
- `docs/current-architecture.md`
- baseline test report
- Phase 1 最小任务列表

验收：
- 干净环境至少能复现一个现有样例。
- 所有失败都有记录。
- 不改核心行为。

## Phase 1：核心抽象与向后兼容

任务：
- schema v2。
- Character、Rig、Pose、Motion、ViewProfile 接口。
- LegacyHumanoidRigAdapter。
- Rig Registry。
- v1 转换器。
- CLI/Orchestrator 适配。
- 回归测试。

验收：
- 旧版样例仍可运行。
- 新旧配置均可验证。
- 无未解释行为回归。

## Phase 2：人形/机甲 + 横版侧视

任务：
- 完善 Humanoid Rig。
- 增加机械关节和部件。
- 分层 PNG 导入。
- 武器/盾牌/推进器 Attachment。
- 机甲动作模板：idle、walk、run、dash、light_attack、heavy_slash、block、hurt、death。

验收：
- 机甲骑士可生成。
- 武器在攻击中保持挂点。
- 机械关节约束测试通过。
- 输出关键帧预览和 QA 报告。

## Phase 3：俯视 4/8 方向

任务：
- 新建 TopDown ViewProfile。
- 4 方向移动和待机。
- 移动方向与瞄准方向分离。
- 8 方向映射和对角线速度归一化。
- 遮挡/depth sorting。
- 非对称武器镜像例外。

验收：
- 8 方向预览无方向错配。
- 对角线速度与轴向速度一致。
- 移动方向和攻击方向可独立。
- 关键动作有方向 QA。

## Phase 4：四足与飞行

任务：
- 四足 Rig、步态相位和脚掌接触。
- 飞行 Rig、翼拍/滑翔/俯冲。
- 通用骨骼链求解器。
- 尾巴/脊柱跟随。

验收：
- 狼 walk/trot/run 循环通过运动 QA。
- 鸟 flap/glide 循环通过接缝和运动 QA。
- 故意植入的滑步/断链能被发现。

## Phase 5：多肢、蛇形和软体

任务：
- FABRIK 或等价链求解。
- 多肢步态分组。
- 长体曲线传播。
- 网格变形和自交检测。

验收：
- 蜘蛛/章鱼 Rig 可配置。
- 史莱姆 squash/stretch 可循环。
- 网格翻转、自交 fixture 能被识别。

## Phase 6：QA 2.0

任务：
- Structural、Geometry、Attachment、Visual、Runtime QA。
- 证据截图和报告。
- 安全自动修复、diff、迭代上限。
- 故障注入测试。

验收：
- 已知故障被对应 QA 识别。
- 报告含帧号、部件、严重度和证据。
- 视觉模型结论明确标注不确定性。

## Phase 7：编辑器、批量生产和引擎验证

任务：
- Canvas 预览和时间轴。
- 角色/动作模板管理。
- 批量生成。
- 各引擎适配器 smoke test。
- 文档、示例、发布流程。

验收：
- 可查看、定位和复播问题帧。
- 至少一个目标引擎真实导入和播放通过。
- 其他引擎有准确验证等级。

---

# 14. 工程规范、性能和风险

## 14.1 性能

- Pose 计算与图片渲染分离。
- 缓存静态部件和不变变换。
- 帧渲染可并行，但输出顺序确定。
- 大图集分片，遵守目标平台纹理限制。
- QA 支持抽帧与全帧模式；发布前关键动作必须全帧检查。
- 视觉模型只检查关键帧和可疑帧。
- 固定随机种子并记录工具版本。

## 14.2 质量规范

- 坐标系、角度方向、单位统一并文档化。
- 使用稳定 pivot/ground anchor。
- 所有素材记录尺寸、路径和 hash。
- 时间轴用明确时间基准，不依赖 setInterval 作为真值。
- QA 问题必须可定位、可复现。
- 新 Rig、新动作、新 Exporter 必须带 fixture 和测试。

## 14.3 主要风险

| 风险 | 影响 | 对策 |
|---|---|---|
| 一次性大重写 | 旧功能损坏 | 适配器、分阶段迁移、回归测试 |
| 强制所有角色共用骨骼 | 动作僵硬/结构错误 | 多 Rig 家族和统一接口 |
| 俯视角直接旋转侧视图 | 遮挡和姿势错误 | 独立 ViewProfile |
| 扁平图自动分割不稳 | 部件/绑定错误 | 分层素材优先、人工修订 |
| 正常遮挡被误判穿模 | QA 噪声 | 碰撞轮廓、z-order、允许重叠规则 |
| AI 视觉不确定 | 错误修复 | advisory、证据、人工确认 |
| 引擎格式不一致 | 导出故障 | 中间 Manifest 和独立 smoke test |
| 范围膨胀 | 无法交付 | MVP 验收矩阵 |

---

# 15. 推荐 MVP 顺序

不要第一版就实现全部八类 Rig。建议按以下顺序交付：

## MVP-A：人形/机甲 + 横版
- 旧版人形兼容。
- 机械人形 Rig。
- 分层 PNG。
- 武器/盾牌/推进器挂点。
- 8～12 个常用动作。
- 结构 QA、运动 QA、Attachment QA。
- Web 预览和 Sprite Sheet 导出。

## MVP-B：人形 + 俯视 4/8 方向
- 先 4 方向，后 8 方向。
- 独立瞄准/移动方向。
- 遮挡排序。
- 方向性攻击和受击。

## MVP-C：非人形角色
- 四足。
- 飞行。
- 多肢。
- 蛇形。
- 软体。

## MVP-D：完整 QA 和生产工具
- 几何 QA。
- 视觉 QA。
- 故障注入。
- 安全自动修复。
- 时间轴编辑器。
- 多引擎验证。

**首个完整验收样例：**
1. 横版机甲骑士：idle、walk、run、dash、light_attack、heavy_slash、block、hurt、death。
2. 俯视士兵：4/8 方向 idle、walk、attack、hurt。
3. 四足狼：idle、walk、trot、run。
4. 飞行鸟：hover、flap、glide、dive。

---

# 16. Codex / Claude Code 执行指令

以下指令可作为后续工程任务的总规范。

## 16.1 执行前

1. 检查仓库分支、工作区状态和未提交修改。
2. 阅读完整 README、SKILL.md、references、脚本、测试和配置。
3. 找出真实入口、数据结构和输出目录。
4. 运行现有安装、生成、QA 流程。
5. 记录实际能力和未验证项。
6. 先创建 `docs/audit.md`、`docs/current-architecture.md`、`docs/implementation-roadmap.md`。
7. 不覆盖用户未提交修改，不删除现有素材。

## 16.2 实施约束

- 不允许一次性重写整个项目。
- 每个 Phase 独立提交或形成可审查变更集。
- 新模块先定义接口和测试，再接入主流程。
- 旧流程必须持续可运行。
- 不得通过降低 QA 阈值、屏蔽检查或删除失败项制造 PASS。
- 不得把未运行的引擎导入称为已验证。
- 不得声称 AI 能保证检测所有穿模。
- 新配置必须有 schema 和样例。
- 每阶段汇报改动文件、实现内容、测试命令、真实结果和未解决问题。

## 16.3 第一轮只做 Phase 0

**第一轮任务限定为仓库审计，不要立刻进行大规模重构。**

交付：
- `docs/audit.md`
- `docs/current-architecture.md`
- `docs/implementation-roadmap.md`
- 现有测试、生成、QA、导出的运行记录
- Phase 1 的最小任务列表

审计结束后，提交实施计划并等待用户确认，除非用户已明确授权连续执行全部阶段。

---

# 17. Definition of Done

只有满足实际验收，才可以宣称对应能力完成：

- [ ] 旧版横版人形流程有回归测试。
- [ ] Rig Registry 和统一接口已实现。
- [ ] 人形和机械人形 Rig 可用。
- [ ] 横版与俯视角数据模型已分离。
- [ ] 俯视 4 方向和 8 方向有实际样例。
- [ ] 动作通道、事件、状态机和混合有测试。
- [ ] 分层 PNG、锚点和部件层级可工作。
- [ ] QA 能识别已知结构/运动/几何/挂点故障。
- [ ] 视觉 QA 输出证据并标记不确定性。
- [ ] Sprite Sheet/Atlas/Manifest 可复现生成。
- [ ] 至少一个目标引擎实际导入并播放通过。
- [ ] 文档、示例、安装步骤和 Skill 说明完整。

建议版本标记：
- `2.0-alpha`：核心抽象和人形/机械 MVP。
- `2.0-beta`：双视角、多 Rig、主要 QA。
- `2.0`：验收矩阵通过、文档完整、至少一个引擎完成验证。

---

# 附录 A：机甲骑士配置示例（简化）

```json
{
  "schema_version": 2,
  "id": "mech_knight",
  "name": "Mech Knight",
  "rig": {
    "type": "mechanical_humanoid",
    "template": "humanoid_heavy",
    "capabilities": [
      "biped_locomotion",
      "weapon_attachment",
      "shield_attachment",
      "jetpack",
      "mechanical_joint_limits"
    ]
  },
  "view": {
    "type": "side",
    "facing": "right",
    "mirror_policy": "safe_only"
  },
  "render": {
    "mode": "layered_sprite",
    "canvas": [256, 256],
    "fps": 30,
    "pivot": [128, 224]
  },
  "parts": [],
  "attachments": [
    {"id": "sword_grip", "joint": "right_hand", "offset": [0, 0]},
    {"id": "shield_grip", "joint": "left_hand", "offset": [0, 0]},
    {"id": "jetpack", "joint": "upper_back", "offset": [0, 0]}
  ],
  "clips": [
    "idle", "walk", "run", "dash", "light_attack",
    "heavy_slash", "block", "hurt", "death"
  ],
  "qa": {
    "structural": true,
    "motion": true,
    "geometry": true,
    "attachment": true,
    "visual": "advisory"
  },
  "export": {
    "targets": ["web"],
    "formats": [
      "png_sequence",
      "spritesheet",
      "atlas_json",
      "animation_manifest"
    ]
  }
}
```

# 附录 B：术语

| 术语 | 含义 |
|---|---|
| Rig | 角色骨骼、关节、约束和绑定结构 |
| FK | 正向运动学 |
| IK | 反向运动学 |
| Attachment | 武器、盾牌等装备挂点 |
| Sprite Sheet | 多帧精灵图 |
| Atlas | 图集及帧区域索引 |
| Pivot | 动画帧共享锚点 |
| Root Motion | 动画驱动角色在游戏世界中的位移 |
| Blend Tree | 根据参数混合多个动作 |
| Z-order | 2D 部件绘制前后顺序 |
| Contact Lock | 脚/爪支撑期间固定接触点 |
| Golden Test | 固定输入与基准输出的回归测试 |

---

**文档结束。**
