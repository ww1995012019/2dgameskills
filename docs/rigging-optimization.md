# 复用素材的骨骼绑定优化

## 实现范围

侧视人形增加 `scripts/bind_known_joints.py`：完整图层 + 已知关节直接生成原有运行时能读取的
`character.json`。沿用开发模板已经验证的实测骨长、握点、靴底接触和源姿态处理，提取为正式
`known_joint_rig.py`；开发模板改为调用同一实现，避免维护两份绑定算法。

- 不调用图像模型，不推断或重画手部定位图，不运行颜色配准的穷举搜索。
- 保留输入像素。支持裁剪 PNG 的共同画布和偏移元数据，自动无损补画布；拒绝越界裁切。
- 使用实际骨段和挂点检查，不要求角色覆盖实验模板的固定轮廓。旧有骨段支撑、骨长配对、
  颈部重叠和身体核心完整性要求保留；不能用不完整素材绕过这些检查。
- 手掌远端按前臂刚性移动，前臂近端平滑混合；肩/髋根部按首骨段刚性挂接。
  只在新绑定数据显式启用，旧图层默认行为不变。靴子原有刚性混合继续复用。
- 实测脚底模式在摆动起落处对抬脚高度缓动，修复支撑高度在循环接触附近的速度问题；
  待机也按脚底支撑求身体高度，避免给不同体型硬套旧站姿造成深屈膝。
- 版本化输出，现有目标拒绝覆盖，成功前用临时目录暂存；记录输入哈希和零生图次数。
  数值绑定不冒充美术审核、用户动态验收或引擎播放验收。

用法和 manifest 字段见
[`known-joint-binding.md`](../game-sprite-animator/references/known-joint-binding.md)。

## 验证边界

本环境缺少交接里武侠剑客的外部原始分层素材，所以不能把测试说成该角色修复成功。
使用 slim/compact 两个程序合成体型验证空手、持剑、裁剪素材、像素保留、挂接、手部刚性、
非有限关节和错误画布等故障。程序合成图不代表两个真实 AI 美术角色通过验收。

外部验证产物：`/workspace/2dgameskills-output/known-rig-validation`。
最初的纯色几何占位图在手部细节项失败，原报告保留；这类占位图含处理色差且没有真实手部
线条，不能证明细节保留能力。后续以带明确手部纹理的程序测试图验证该项；没有修改、降低或
跳过原有 QA。不要将旧失败报告覆盖成通过，也不要把几何占位的通过当作美术质量结论。

初步 12fps 预览中，两体型 idle/walk 各 39 帧，逐帧 QA 为 0 FAIL / 0 WARN；
脚滑约 0.005px，脚底最大偏离约 0.095px。发现待机膝盖偏弯后增加实测支撑站姿，
两体型平均待机膝弯约 26°；最终版本验证结果见后续记录。

## 最终验证

- 两种体型的最终版本（`textured-{slim,compact}/final-build`）均为 idle/walk 39 帧，
  原有 QA 为 0 FAIL / 0 WARN；关节放大图已检查，待机膝弯改善。没有生成剩余动作。
- 两套最终预览经 Chromium 实际加载：走路选择、动画推进、暂停/逐帧、翻转和试玩切换通过，
  页面错误为 0。此处是浏览器预览，不冒充 Unity 或其他引擎播放验收。
- 新绑定耗时 2.615s / 2.915s（本环境并发负载下，仅绑定阶段，不包括渲染）；输入图层与
  导出层按偏移还原后的可见 RGBA 像素逐项完全相同。绑定生图调用均为 0。
- 当前版本专项命令 `PYTHONPATH=dev/tests python -m unittest test_known_joint_rig
  test_template_binding test_puppet_contact_bounds -v`：14 项通过，包含新增 manifest 故障测试。
- 完整套件首次执行 `python -m unittest discover -s dev/tests -v`：348 项，4 项既有
  expectedFailure，1 项错误。该进程在代码修改前已加载旧的 `root_lock` 属性访问；
  测试替身没有此属性。现行实现使用 `getattr(..., False)` 保持兼容，当前代码独立重跑
  `test_puppet_contact_bounds` 的 5 项全部通过。没有删测试或修改预期失败来放行。
  初次全量日志保留 `/tmp/rig-full-tests-final.log`，新进程复测为 `/tmp/rig-contact-final.log`，
  最终 14 项专项为 `/tmp/rig-focused-final.log`。不能将首次全量日志描述为全绿。
- 26 套旧角色回归全部 0 FAIL，`cutout_demo-pixel` 仍有 7 WARN，HD 仍有 8 WARN，
  其他 24 套 0 WARN。原样保留这些已有警告。
- 原仓库历史基准比较：0 regressions、106 changed、88 drifted，严格模式因此退出 1，
  未改写 `dev/baseline.json`。另从本轮修改前的 HEAD 导出隔离副本，完整重跑 26 套，
  与修改后输出进行逐帧和 QA 对照：26 套全部一致，0 regressions、0 changed、0 drifted。
  因此上述 106/88 项历史基准差异在本轮修改前已经存在。
- 独立/统一 `.skill` 实际解包后运行绑定入口均通过；共用文件同步、统一快照同步、
  五个技能包新鲜度及 `git diff --check` 通过。

最终产物及机器检查：`browser-check-final.json`、`pixel-reuse-check.json`、
`original-control-comparison.json` 均在外部验证目录。原始武侠案例素材不在本环境，
没有将合成测试结果当作该真实人物的最终验收。

## main发布前的新进程完整复测（2026-11-03）

使用现有系统Chromium路径，重新跑完整套件：
`CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium /workspace/2dgameskills-venv/bin/python -m unittest discover -s dev/tests -v`。
354项测试，350通过、4项原有expectedFailure，0错误、0新增失败，耗时1560.124秒。
日志 `/tmp/skill-main-tests-chromium.log`；此前旧进程root_lock兼容性错误在本次完整新进程中未复现。
首次未指定浏览器路径的尝试因缺少Playwright缓存浏览器而导致CSS启动失败，确认后中断，从头重跑。
没有改测试、跳过检查或放宽阈值。五个包的新鲜度、shared/modes同步和diff检查均通过。

## 渲染提速（2026-11-03，输出逐字节不变）

检查绑定全过程的耗时：`bind_known_joints.py` 本身约 0.8s，瓶颈在之后的出帧。
`puppet.raster` 每个三角形一次 Python 调用（idle/walk 约 49 万次）占约 59%，
`fit_scale` 以 120Hz 对每个姿态重建网格占其余大部分，其中 `rounded` 是逐点 Python 循环。

- `raster` 改为分批向量化：同一套 float64 运算、同样的包围盒和容差，像素按原来的
  “三角形→行→列”顺序写入，所以共享边仍是后画的覆盖先画的。批次按 `RASTER_BUDGET`
  限制内存，超出就二分。非有限顶点直接报错（原实现同样会在取整时报错）。
- `rounded` 去掉逐点循环，权重与原逐个标量计算逐位相同。
- 新增 `dev/tests/test_puppet_raster.py`：保留原循环实现作对照，随机网格（折叠、零面积、
  出画布、强制拆批）要求逐位相等；故障注入（交换单元格内两三角形顺序）会失败。

实测（程序合成体型，非真实美术）：slim hd idle/walk 29.5s→11.0s，110 个输出文件逐字节相同；
compact pixel 6 个动作 27.4s→9.4s，124 个文件逐字节相同。26 套回归 0 FAIL
（cutout_demo 7/8 WARN 原样），puppet 相关 64 项单测通过（1 项原有 expectedFailure）。
26 套旧角色都不走分层人偶，回归只证明没有波及其他路径；本项的证据是上面的逐字节对照。

### 审查发现的处理

第 2 项见下节（已改，输出不变）；其余五项按用户要求在下面“绑定测量修正”一节修改。

## fit_scale 只算有画面的顶点（2026-11-03，输出逐字节不变）

`Puppet.meshes(..., relax=False, used_only=True)` 直接给出 `verts[layer.used]`；`mapped`、
脚部混合、`lock_tip`、刚体层和落地压缩都按顶点独立计算，所以只算这些顶点与先算全网格再取子集相同。
`used_only` 必须配 `relax=False`（松弛要整张网格），否则报错。`fit_scale` 改用该路径，渲染与
`puppet_check` 仍走全网格。

- 两个合成体型、27 个动作、每动作 40 个时刻、每层（8640 层帧/体型）逐位相等。
- `test_puppet_raster.UsedVertexBounds` 覆盖 tube（含脚部、根/末端锁定）、robe、cloth、刚体层
  和落地压缩；故障注入（selected 路径跳过脚部混合）在 `leg_near` 处失败。
- 与原 main 的完整输出对比：slim hd idle/walk 110 个文件、compact pixel 6 动作 124 个文件
  全部逐字节相同。耗时 11.0s→10.5s、9.4s→8.4s（累计自原始 29.5s、27.4s）。
  收益小，因为剩余成本是每帧每层建曲线的固定开销，与顶点数无关。

## 绑定测量修正（2026-11-03，用户要求修改其余审查项）

这些改动只影响**新绑定**；已有 `character.json` 没有新字段，运行时走原路径。

1. **远侧肢体保留实测骨长。** `Body` 增加可选 `thigh_f/shin_f/up_arm_f/lo_arm_f`，`leg_bones`/
   `arm_bones` 按侧取值；`solve`、`measured_walk_height`、`stance_reach` 和共用
   `constraints.frame_metrics` 的骨长误差按侧计算。远侧髋座高度加上 (远腿长−近腿长)×`REACH_MID`，
   两腿站立伸展比例相同，不会一高一低。合成素材远侧 ±13%：原实现远腿 1.11/0.85、远臂 1.15/0.89 倍，
   现在四肢都是 1.000；待机两脚底离地 <0.5 单位。
2. 握点容差 = max(2px, 近臂长 2%)（`grip_tolerance`），不会比原来更严。
3. `canonical_arm` 需要镜像且肩腕距 < 臂长 5% 时拒绝（原来会除以近零得到无意义肘位）。
4. `head_size` 用 `head_length`：沿颈→头部重心方向量，倾斜 25°/−30° 与直立差 <2%；
   两个合成体型上与旧值差 <0.5%。
5. 带透明的 LA/PA/调色板 PNG 无损转 RGBA；不透明 RGB 仍拒绝。

测试 `dev/tests/test_known_joint_limbs.py`（6 项）：两体型 × 远侧 0.87/1.13 的长度比、双脚着地、
`check_layers`/`check_motion` 为空；去掉远侧字段的故障会拉伸 >8%；头长改回竖直量法的故障失败。

出帧 QA（hd idle/walk，合成纯色占位图）：4 套都有既有的“手部细节”FAIL——原代码同一占位图
同样失败，这是纯色几何没有手部纹理，见上文；compact 远侧 +13% 走路有 30° 的蹲腿 FAIL，原代码同一素材
为 31°，未修改素材的 compact 在原代码下为 32°，属既有问题。悬空 0.64–0.70px 与原代码同素材一致。
这些是程序合成体型，不是真实 AI 美术，也没有用户动态验收。

## 渲染修复：裁剪图层边缘被拉成色带（2026-11-03）

绑定把每个图层裁到紧贴画面并记录偏移；网格格子会越过裁剪边界，`puppet.raster` 原先把越界采样夹到
最后一列/行，边缘像素被拉成一条色带（实际表现为脸旁小方块、剑尖碎线）。改为图片外的采样不绘制。
`dev/tests/test_puppet_raster.py::test_cells_past_a_tight_crop_draw_nothing` 覆盖，恢复旧夹取会失败。
所有分层人偶都受影响；26 套旧角色不走分层人偶，不受影响。
