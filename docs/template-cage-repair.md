# 用现有部件修形并测试关节活动（2026-11-02）

用户要求在腿部达限后继续。此轮**追加生图0张**，仍只有原7张生成图（躯干1、臂3、腿3）。原生成任务保持blocked，不重置次数；新结果是对现有完整美术的派生修复，不是重新开始生成任务。

## 根因与修复方式

全分辨率配准进一步检验仍未通过；覆盖诊断把主要差异定位到靴筒外侧和少量裤腿边缘，髋/膝/踝/靴尖的画面支撑均完整。单靠整体缩放无法修正局部粗细差异。

新增开发模块 `dev/template_mesh_fit.py`：在已配准的完整部件上做水平笼形变换。程序逐行测量源轮廓及模板的必要区域，平滑地调整左右边缘，仅扩展已有美术，不按模板裁掉图像，也不涂画/填补透明洞。源图没画的中段仍没画；第二条腿/多余分叉也不会被裁掉。

这是**新增局部几何形变步骤**，有别于原来的整体双轴±12%配准；没有把它冒充同一种限制。局部水平拉伸上限25%，边界位移上限28px，纵向位置不变。水平Jacobian恒正，不能翻折；检查原可见像素是否被移出画布。纹理会重采样，轮廓粗细会改变，所以仍须看图确认外观。

此例最大局部拉伸23.39%，最大边界位移19.17px，无画布裁切。覆盖率96.61%→99.32%，范围内像素99.994%，四个挂点采样100%，闭合透明孔0。原98%覆盖/99%范围及挂接标准不变。靴筒变宽，金边保持连续；边缘能量约保留92.9%，原有smear检查坏块为0。这些测量不能替代观感审核。

## 记录与失效检查

`dev/template_puppet.py repair <案例> leg_near` 只读最后一次生成的已配准图，输出 `repairs/leg_near/cage_v1/part.png` 与报告。原 `registered.png`、失败报告、尝试数和生成任务phase均不修改。`repairs.json` 登记派生文件；预览检查输入/输出/合同/处理代码及报告哈希，并重新计算几何项，过期修复不能被沿用。

案例 `/workspace/2dgameskills-output/wuxia-template-v1`：

- `repair_comparison.jpg`：修前/修后。
- `leg_coverage_diagnostic.jpg`：原未覆盖区域。
- `repairs/leg_near/cage_v1/report.json`：形变、覆盖、来源和代码哈希。
- `review_history/before_cage/`：原阻断报告保留。
- 原 `job.json` 的blocked仅表示生成限额已关闭；派生修复的几何/视觉状态单独记录，不能据此开启第4次生图。

## 局部关节活动测试

新增 `dev/template_motion_probe.py`，直接复用现有生产代码 `sprite_anim/puppet.py` 的Layer、网格弯曲、松弛和raster，以及 `puppet_check.inverted`。使用模板已知关节，无手标点、无姿势检测。肘弯35°、膝弯45°，各20帧；没有完整人物、接地约束或武器，也不是idle/walk。

实际40帧骨长误差约1e-13px，网格翻折占比0、无画布裁切；沿用原FOLD_SHARE=0.002。已查看静态对照、关节叠加和最大弯曲图，修订版仍待用户看效果。首个开发试跑因校验API名称写错，在第0帧前退出，未发出通过结论；错误和中间文件保存在 `motion_probe_failed_api`，改用实际API后重新完整运行。

查看 `motion_probe/joint_range.gif`、`motion_probe/joint_review.jpg`、`motion_probe/report.json`。`preview.html` 内嵌动图及三部件图，活动报告所引用源图改动时拒绝嵌入旧测试。

验证命令：

```bash
PYTHONPATH=dev/tests python3 -m unittest test_template_puppet test_template_registration test_template_mesh_fit -v
python3 dev/template_motion_probe.py <案例>
```

测试覆盖两种合成体型的修形、缺失中段不能被补出来、额外分叉不能被裁掉、透明洞保留、派生文件失效、关闭的生成额度不重开、旧活动报告不能沿用。合成体型不算两个真实角色验收。没有修改生产skill或原动作代码，本轮未重跑旧全量动画基准。

上述代码测试共16项全部通过；离线查看器的图片、关节点和移开手臂交互经Chromium检查通过。部件活动的40帧数值检查另记录在motion_probe/report.json，不能替代完整人物动画验收。

当前只恢复了三部件几何并增加局部活动验证；尚未补齐头、另一侧肢体、髋和武器，没有完整角色rig、待机/走路或引擎播放验收，也没有最终pass。
