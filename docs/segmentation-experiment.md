# 自动分割与受限补画实验（2026-11-02）

用户授权用原有侧视标准图先验证头、后腿、躯干三个失败部件。该方法仍是开发实验，尚未接入默认 skill，没有真实人物完整绑定/走路成功验收。

## 方法与边界

1. 仅为模型推理把品红背景换成中性灰；导出可见部件始终取原图 RGBA，不重画、不缩放、不移动。
2. YOLO 姿势检测提供自动分割提示点，SAM2/MobileSAM 提供多个区域候选。姿势检测本身会出错（本例手腕明显误定位），不能直接当绑定关节。
3. 代理看图审核候选归属，编号属于案例标注。没有给这个角色手画掩码或手设关节，但也没有自动证明区域语义正确。
4. AI 只补事先记录的遮挡掩码。`dev/masked_completion.py` 把返回图缩回登记裁剪区域，**只复制补画掩码内像素**；原可见部分和最终画布位置由程序锁住。
5. 掩码重叠、软掩码、源图/掩码/登记板改变会拒绝处理。生图前检查闭合透明洞和补画范围。20% 是最初的小范围实验目标，不是经过验证的美术质量阈值。blocker 时 CLI 退出2。
6. 无数值 blocker 也仅得 `needs_visual_review`，不会批准绑定。部件归属、接缝、背景误填、解剖完整性需视觉审核；发现透明洞不等于自动知道应填什么。

```bash
python3 dev/masked_completion.py prepare \
  --source reference.png --visible-mask torso_visible_mask.png \
  --completion-mask torso_completion_mask.png --out experiment
# 掩码预检和视觉复核通过后，才调用图像工具。
python3 dev/masked_completion.py compose experiment generated_patch.png
```

对于已完成的失败实验，compose 仍能输出诊断图和 blocked 报告，退出2，不能继续生产。每次请求保留独立目录和旧失败记录，不借此重置生产生成次数。

## 实际结果

案例 `/workspace/2dgameskills-output/wuxia-segmentation-v1`；总览 `comparison.jpg`、视觉报告 `visual_report.json`、程序证据 `final-locality-proof/integrity_report.json`。

- 输入是上轮生成并审核的短发短衣侧视标准图，**不是上传的长袍原图**。原图字节此前下载失败，旧案例已记录代理图来源，本实验不改变来源记录。
- 头和后腿可见像素原位切出，未再次出现放大头像或 Y 形多余腿。这不代表隐藏根部、抗锯齿边缘或动画挂接完成。
- 躯干实际补画3次。最终只拷指定区域后，原可见像素变化0、区域外泄漏0，但仍有4491个闭合透明像素、接缝和袖口残留。补画占26.56%，超过初设20%目标；视觉 blocker，resolved=false。
- 根因包含掩码归属和完整性错误。返回图看似完整也不能越过事先掩码整图采纳。已前置拓扑/范围预检；不追认扩大掩码来采纳本轮在区域外的改画。
- 旧 `wuxia-basic-v1` 仍终态 blocked；未绑定、未生成待机/走路，无最终 pass。

程序约束在两个不同宽高的合成输入验证，这不是两个真实人物的分割验收。下一轮先解决自动掩码归属和完整性，再验证不同真实角色，满足条件后才进入绑定。

## 环境与验证

隔离环境 `/workspace/segmentation-venv`：Python3.12、torch2.5.1+cpu、torchvision0.20.1+cpu、ultralytics8.3.200，CPU推理。官方 Ultralytics assets 权重 `yolo11n-pose.pt`、`sam2.1_t.pt`、`mobile_sam.pt` 位于 `/workspace/segmentation-models`；案例保存版本、哈希、脚本和自动提示点。模型不进 skill 包。

Ultralytics 软件及其发布权重有相应许可约束（包括 AGPL/商业许可选择）。本轮只做内部实验，未将依赖/权重纳入商业产品默认流程；产品集成前按实际分发方式选择合适许可或替代实现。

`python3 -m unittest discover -s dev/tests -p test_masked_completion.py -v`：7项通过，覆盖两种合成体型、整板乱改时原像素锁定、过期输入、掩码错误、漏填、闭合洞和补画范围。测试通过不覆盖真实美术失败。
