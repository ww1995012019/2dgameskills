# 2dgameskills 工作规范

两个独立安装的 Claude skill：`game-sprite-animator`（横版 RPG 动作）和 `game-shooter-animator`（横版射击）。
进度、决定和环境坑见 `HANDOVER.md`，动手前先读。

## 代码布局

- 每个 skill 文件夹必须能单独复制、单独打包使用，所以两边共用的文件在两个 skill 里各存一份。
- **共用文件只改 `shared/`**，然后运行 `python dev/sync_shared.py` 复制到两边。直接改 skill 里的副本，`--check` 会报不一致。
  目前共用：`sprite_anim/` 下的 `constraints.py`、`cloth.py`、`mathx.py`、`export.py`，以及 `visual_review.py`、
  `SpriteSetImporter.cs`、`references/visual-review.md`。
- `rig.py`、`motions.py`、`render.py`、`art.py`、`fx.py`、`qa_motion.py`、`generate.py` 两边已经分开演化，各改各的。
  要把它们合进 `shared/`，先证明两边输出不变（见下面的 `--strict`）。
- `dev/` 是开发工具，不进 skill 包。

## 改完要跑的

```bash
python3 -m unittest discover -s dev/tests -v      # 故障注入、CSS 回放、引擎实测、同步和打包检查
bash dev/engines/get_godot.sh && npm install --prefix dev/engines   # 引擎测试要的 Godot、Phaser、PixiJS，装一次
bash dev/regress_all.sh                          # 18 套全量回归，4 核约 9 分钟，放后台
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

## 已知的 QA 缺口

见 `dev/tests/test_qa_faults.py` 里的 `expectedFailure`：
- 截短的走路、跑步循环查不出：每帧本来就改变大半剪影，像素接缝比例总在阈值内。
- 动作衔接处姿势错误，只要其中一个动作本身变化快就查不出（比如把死亡姿势接到起跳）。

两者都需要基于关节位置（`rig_trace.json`）的接缝和衔接检查。
