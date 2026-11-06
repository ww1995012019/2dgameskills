# 交接文档

只放当前状态、最近两轮和常用信息。更早的过程原样归档在
`docs/handover/history-2026-10-30-to-2026-11-05.md`，路线图在 `docs/roadmap.md`。

## 接手时直接说

> 克隆 https://github.com/ww1995012019/2dgameskills 的 `main`，读根目录的 `CLAUDE.md`、`HANDOVER.md`
> 和 `docs/roadmap.md`，从 HANDOVER 的“当前状态”继续。

## 当前状态（2026-11-06）

- **唯一源码是 `game-animator/`。** 四个旧 skill 文件夹和 `.skill` 包由 `dev/build_standalone.py` 生成，
  已标为弃用，只为已安装的用户保留。`shared/`、`sync_shared.py`、`sync_modes.py` 已删除。
- **用户否决后的返修顺序已改**：先只渲染受影响的动作，用 `scripts/compare_clips.py` 出新旧对照 GIF 给用户看，
  用户认可后才跑全量单测、26 套回归、打包和发布。见 `modes/game-sprite-animator/references/repair-loop.md`。
- **真实角色还没进回归。** 26 套回归全部是程序绘制模板和 `cutout_demo`。CityRunner、柯南、士兵等真实 AI 美术
  的任务文件在以前的 `/workspace/work/...`，不在仓库里；接入方法见本轮记录。
- 等用户动态验收（数值和代理视觉复核已过，不等于用户认可）：
  - CityRunner、柯南：idle 72 帧 / run 22 帧（`ordinary_run_v2`，v5 网页）
  - 蓝金持枪士兵：`side-rifle-carry-v1` 的 idle/run（私有网页版本 10 的 `/soldier.html`）
  - 白绿金剑客的刺剑、重斩；魔角战士的待机/跑步；青岚剑客新增的 25 个动作
- 已知缺口（`expectedFailure` 共 9 项）：几何相接不证明服装颜色/高度正确，以及历史记录里列出的其他缺口。
- Unity、Cocos 从未实测；飞行生物只有线条占位，没有真实美术验收。

## 本轮：工作流优化（2026-11-06）

（本轮结束时填写）
## 2026-11-06 持枪士兵待机与奔跑（独立受限试作）

- 前轮 PR #8 已按用户要求合并 main，合并提交 `cee4e50bafa8f7f387969fc30f4256aa4d3b134d`。
  本轮由该版本新建 `codex/rifle-carry-20261105`，制作用户新图的士兵 idle/run。
  保留头盔、护目镜、胡须、战术装备、迷彩裤与蓝金步枪；原上传字节本地不可读，生成身份代理后
  改为侧视登记，来源与改编记录均保留，不能把代理 PNG 称为原上传。
- 新增独立 `side-rifle-carry-v1` 受限 profile，basic 的无武器/单手剑边界不变。
  仅提供贴身装备的持枪 idle/run，不宣称瞄准、射击、换弹、换枪或通用双手 IK。
  七层身体与两个手部提示仍需原流程验收；近臂指握把手、远臂指护木支撑手，使用共同画布登记。
  自动自由配准曾把远臂移到近臂上，失败记录保留；此 profile 改为原位登记，没有放宽原匹配门槛。
- 单独步枪生图被图像工具拒绝，未重试或改写规避。当前使用已接受整图中的上身、双手和枪的
  原像素，同一表面绘制；分离手臂仅提供解剖/关节测量，不再重复绘制。没有画补片、补枪或改色。
  首轮躯干管状网格弯曲了枪身，实际 QA 检出 94 帧约 8–12px 漂移并阻断，未交付。
  现手区及枪身跟随胸部刚性运动，下方原衣料过渡连接骨盆；全保护区最终网格最大误差
  `0.267174px`，原 1 输出像素限值保留。原衣裤连接、腿型、裁边、头颈及跑步节奏检查保留。
- 质量/接触/手部测量使用实际绘制表面及对应登记部件分析掩码，原图透明洞不能被虚拟手臂补满。
  不绘制的隐藏重建袖料有平滑渐变候选，不能当作实际输出模糊；实际源上身仍执行原模糊检查。
  故障注入证明实际上身变糊仍失败。整图内部遮挡为视觉判断，不把外部遮挡数字当作自动语义识别。
- 携枪绑定要求逐帧刚性证据、准确 owner、原参考及 RGBA 哈希；删展示 profile 标记也不能省略
  数值/视觉门禁。新增 `carry_*.png`、完整播放及逐帧观察。24 项携枪测试覆盖不同合成比例、
  缺证据、错误 owner、移位/剪切、真实绘制透明洞、模糊及删标记。没有宣称两个真实携枪角色均通过。
- 当前 72 idle / 22 run，共 94 帧；数值 0 FAIL / 0 WARN。实际查看全部 19 张审查图、腰膝全帧、
  两手与颈部，并在浏览器打开七个完整近景 GIF 至少两个正常速度周期。原速截图另存；
  0.25x RAF 覆盖全部 72/22 帧，跑步头高范围 4px、相邻最大 1px、两半对应差 0。
  GIF 跑步两半各 370ms。视觉代理复核通过，用户动态验收仍 pending。
- 原同一所有者私有 Site 新增 `/soldier.html`，版本 10，源提交
  `33f9c17454456b8d1c3232cb8ae51868989952d4`，部署
  `appgdep_6aecb720b7d88191a27effc810cd0e85` succeeded，saved-version 来源核对一致。
  原两角色页面保留，访问范围仍 1 用户、0 组、0 外部访客。平台拒绝超过 256MiB 的原归档及
  展开后仍超限的 gzip 归档，失败证据保留；改为加载独立原生 PNG 图集，所有像素不变。
  当前归档 267724800 字节，展开 267659677 字节，均在限内。
  浏览器检查为与发布相同源码及原生 PNG，未重试此前已受 CONNECT 403 限制的生产 HTTP。
  ZIP 19936107 字节，包含 94 透明 PNG、图集及 JSON；网页支持暂停、单步、调速和翻转。
- 本轮全量单测首跑发现旧 `SimpleNamespace` 图层缺省字段的兼容错误，原失败保留；修正为
  可选字段读取后，接触、登记连接及携枪三模块重新运行。重新发现并逐 ID 核对当前 755 项：
  746 pass、9 已知 expectedFailure，0 failure/error/skip/unexpected success，85 模块，0 遗漏/多余。
  首跑控制器 exit 1 与修复后结果分开保存，没有把初次运行改称全通过。
- 本轮 26 套回归全部完成，xargs 总 exit 0，全部 0 FAIL；cutout_demo 原 HD8 / pixel7 WARN 保留。
  五个 `.skill`、共享同步、统一模式快照与打包 freshness 已更新；新增模式文件也登记并实际入包。
  工作证据：`/workspace/work/blue-gold-soldier-20261105`。当前代码上传状态以后续提交/PR 为准。

## 2026-11-05 跑步支撑与上下顿挫返修（v4 通过撤回）

- 用户否决 v4 跑步一上一下、左右步不均。上一节 v4 的动作自然度通过结论错误，已撤回。
  两份实际视觉记录先改为 fail，新增原缺陷 ID `{stem}-v4-uneven-run-support`，再归档到
  `build_before_run_rhythm_fix` / `rig_before_run_rhythm_fix`；`release_v4.json` 已撤回。
  原问题历史、失败帧、累计素材次数不变，没有重新生图或对角色手调坐标。
- 根因：旧 `ordinary_run_v1` 每帧调用行走用的最大伸展高度包络，把配置中的小幅 bob 覆盖掉。
  回收脚也参与决定身体高度，造成落脚前突降；旧检查只看声明 bob，不测最终高度。女角色实际
  骨盆高差 21.71 像素、左右半周期误差 6.19 像素，柯南为 15.42 / 7.35 像素。21 输出帧又把
  两步采成 10/11 帧，GIF 累计舍入还可能造成半周期时长不同。
- 现共享 `ordinary_run_v2`：按原实测骨长校准一次固定支撑基高，叠加左右半周期相同的平滑
  高度曲线；步长 0.70 腿长、抬脚 0.16 腿长、bob 0.0125 腿长。落脚轨迹按各自登记髋座
  常量平移，不逐帧移动支撑脚；两角色原 Body 数据与 v4 相同。导出成对采样为 22 帧，GIF
  两半分别量化后重复，均 370 ms，总 740 ms。原默认游戏跑步不变。
- 新门禁测实际骨盆/头高、240 相位的速度和加速度、左右半周期差、实际支撑样本和腾空顶点；
  再独立读取原生 RGBA 的头顶轮廓，检查全幅起伏、半周期差与相邻帧突降。固定画布、头高和
  地面线的 `run_support_00.png` / 完整播放 GIF，以及逐帧 `support_rhythm` 观察均为必需。
  对归档原 21 PNG 先核对存储 RGBA 哈希，再运行新检测，两角色均定位 run 9 突降；
  旧骨架只读重放也与原 trace 的两位小数精度一致，没有把换 schema 当作缺陷定位。
- 保留既有衣裤连接、隐藏裁边、材质 Jacobian、接触和翻面门槛。原严格布料求解后增加仅作用于
  超限自由三角的可行性投影，固定衣边及远端不动；当前两组完整腰带均无坏三角。失败参数
  试验保留日志，首次失败原型帧保留，没有把未保存的中间试验说成完整构建归档。
- 同时修正实际手部误报：旧方形裁剪把旁边平坦裤料算进手部细节均值，女角色比值 0.5357；
  同一原手臂 alpha 比较为 0.8726。登记手臂改用同臂范围，颜色仍从实际输出帧读取；
  原 0.55 阈值不变，模糊注入仍失败，不能用该修复屏蔽真实糊手。
- 当前两角色各 72 idle / 22 run，共 188 帧。逐项查看并记录 7 / 10 个远臂遮挡候选后，
  两组均 0 FAIL / 0 WARN；run slide/hover 仍 0。原生头顶整轮范围分别 4 / 2 像素，
  相邻帧最大变化 2 / 1 像素，左右对应帧高度差均 0。数字不等于动作自然度或用户认可。
- 实际打开每角色 17 张当前审查图，全部 94 帧腰膝、蓝底衣边、肩颈与双手，以及登记参考和
  全部 22 全身跑步帧。固定世界比例查看被拒 v4 落地前后与当前相近相位；两份当前视觉记录
  保留所有旧 issue 和失败 review_id，新增顿挫 blocker 在当前改变帧上记录解决。代理视觉判断
  与用户认可分开，用户动态验收仍 pending。
- 当前 v5 GIF / PNG ZIP / 播放器已完成，旧 GIF/ZIP 别名实际字节指向当前，旧播放器跳 v5。
  浏览器检查桌面/390px 布局、所有图片解码、下载 SHA、暂停/单步/翻转/调速。并行全量回归
  下的 1x RAF 抽样不足以覆盖所有帧，失败检查日志保留；遍历核对使用 0.5x / 0.25x，分别
  观察全 72/22 帧并测实际 canvas 高度。正常速度 captures 和 GIF 原始 740ms 时长另存，
  不把降速检查说成 1x 每帧均被观察。网页高度范围与原生均为 4/2，半周期差均 0。
- 同一原私有 Site 已更新为版本 9，来源 `0cc0f78bdd813df9d3d1b66f1d8b0b3494df7eb7`，
  部署 `appgdep_6aec909e17d481919aaa217d2760f573` succeeded，原生 saved-version 来源核对一致。
  仍为原所有者私有，分享范围未变。生产 HTTP 受环境 CONNECT 403 限制，没有重试或绕过；
  浏览器检查使用与发布完全相同的本地源码，不声称实测生产传输字节。
- 本轮当前 discover 的 84 个模块、731 个唯一测试 ID 已全部重新运行：722 pass、9 个已知
  缺口 expectedFailure，0 failure/error/skip/unexpected success，0 遗漏，所有模块进程退出 0。
  没有继承旧轮通过；新节奏 12 项、布料 12 项在本轮完整运行中均通过。
- 本轮 26 套全量模板回归完成，全部 0 FAIL，xargs 总退出 0，26 组均有真实成功结果。
  cutout_demo 原 pixel7 / HD8 WARN 保留；基线比较 0 regressions、116 changed、
  102 drifted，未更新基线。开始时 JOBS=2，单测及浏览器完成后增加到 3/4 个并行任务，
  没有改变测试选择或命令。完整结果、每组 QA 哈希见 `final-verification.json`。
- 代码与五个安装包已推送 `32908eea726334bff6cd79ca8dadbec7ed10a990` 到原草稿 PR #8，
  同步、五包 freshness 和 diff 检查通过；最终验证结果也记录在此分支，未合并 main。
  本地预览服务器在浏览器核对后已停止。当前工作证据：
  `/workspace/work/run-rhythm-repair-20261105`。

## 常用命令

源码都在 `game-animator/` 下，命令在对应模式目录运行，例如 `game-animator/modes/game-sprite-animator/`。

```bash
python scripts/contact_sheet.py --character assets/characters/hero.json --clips attack_3 --size 192 --max-frames 8 --out sheet.png
python scripts/generate.py --character assets/characters/hero.json --preset hd --out out/hero
python scripts/qa_motion.py out/hero
python scripts/visual_review.py out/hero
python scripts/compare_clips.py out/hero --before out/hero_old --clips idle,run --out out/compare
```

全量回归：仓库根目录运行 `bash dev/regress_all.sh`（Windows 用 `dev/regress_all.ps1`，只含横版和射击），
结果在 `$TEMP/spr/all`（默认 `/tmp`），日志在 `$TEMP/spr/logs`。之后 `python dev/baseline.py`、
`python dev/qa_failures.py`、`python dev/qa_flags.py all/hero-hd`。

## `dev/` 里的主要工具

开发用，不进 skill 包。

| 文件 | 作用 |
|---|---|
| `build_standalone.py` | 从 `game-animator/` 生成四个弃用的独立文件夹；`--check` 检查是否过期 |
| `package_skills.py` | 打包五个 `.skill`；`--check` 检查是否过期 |
| `regress_all.sh`、`regress_all.ps1` | 全量回归（跑统一包里的模式脚本） |
| `regress_unified.py` | 解压 `game-animator.skill` 后跑 26 套并和基准比较 |
| `baseline.py`、`baseline.json` | 回归结果和基准比较；`--strict` 像素变化也算失败，`--update` 更新基准 |
| `qa_failures.py`、`qa_flags.py` | 汇总失败项、列出标记帧 |
| `verify_exports_*.py`、`test_*_demo.js`、`css_playback.js`、`godot_smoke.py`、`web_engines.js` | 导出校验和引擎实测 |
| `engines/` | `get_godot.sh` 和固定版本 `package.json`；下载的引擎不进 git |
| `tests/` | `python3 -m unittest discover -s dev/tests -v` |

## 关键决定

- 外观用 AI 生图，我们负责绑定、动作、质检、导出；按运动方式写代码，物种写成配置（`docs/roadmap.md` 第 3 节）。
- 商用产品：只固定输入条件和通用流程，不为单张图手调；修问题改通用规则，用两个不同角色验收。
- 用户看到的画面是最终关口。数值通过、代理视觉复核都不等于用户认可，汇报时分开写。
- 射击类用上下半身分层；约束是软的；修问题改根因，不放宽阈值。
- AI 视觉质检不调用 API，由运行 skill 的 Claude 自己看图。

## 环境坑

- **中文 Windows 默认 GBK。** skill 自己的脚本和 `dev/` 下的新脚本都显式用 UTF-8。旧的 skill-creator 打包脚本没有，要先设 `PYTHONUTF8=1`；现在用 `dev/package_skills.py`，不需要。
- Windows 那台机器没有 `gh`、`dotnet`、Godot、Unity、Cocos。Godot、Phaser、PixiJS 第五轮在 Linux 容器里测过，Unity、Cocos 没有，`references` 里写了每项的验证程度。
- 会话文件夹路径很长，Windows 上 `../..` 这类相对路径可能超 260 字符，要先规范化。
- 预览窗格隐藏时浏览器的 `requestAnimationFrame` 会暂停，自动化测试用 Node 脚本。
- 全量回归超过 10 分钟，要放后台。
- 仓库本地配置的提交邮箱是 GitHub 匿名邮箱，不要用机器的全局身份，全局是公司邮箱，而这个仓库是公开的。
