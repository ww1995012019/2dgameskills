# 交接文档

只放当前状态、最近几轮和常用信息。更早的过程原样归档在
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
- **柯南新预览已交付，蓝金持枪士兵仍待返修。** 用户 2026-11-06 指出腰胯异常，旧代理视觉通过结论撤销，
  旧数值结果保留。柯南跑步/跳跃已重新生成并增加翻滚，用户随后授权当前源码合并推送；本轮未新增真实角色固定基准。
  士兵仍缺原任务，旧画面未重渲染。
  见下面的“柯南跑步/跳跃重新生成”和“腰胯缺陷复查”。
- 其余等用户动态验收（数值和代理视觉复核已过，不等于用户认可）：
  - CityRunner：idle 72 帧 / run 22 帧（`ordinary_run_v2`，v5 网页）
  - 白绿金剑客的刺剑、重斩；魔角战士的待机/跑步；青岚剑客新增的 25 个动作
- 本轮新增：靴尖着地按实测、像素穿地检查覆盖分层角色全部动作，见下面 11-06 最后一节。
- 已知缺口（`expectedFailure` 共 9 项）：几何相接不证明服装颜色/高度正确，以及历史记录里列出的其他缺口。
- Unity、Cocos 从未实测；飞行生物只有线条占位，没有真实美术验收。

## 2026-11-06 翻滚事件、引擎文档、靴尖着地与全动作穿地检查（用户认可后合并 main）

- **翻滚无敌事件**：`ordinary_roll_v1` 原先没有旧翻滚的 `invincible_on/off`，引擎靠事件做闪避无敌会失效。
  现在收身开始（0.12 s）发 on、转满一圈（0.78 s）发 off，随速度缩放，画面帧不变。
- **引擎文档**：`animation-principles.md` 新增 basic 拟合动作表：新跳跃的 `jump_rise`/`fall` 不循环、固定腾空高度，
  翻滚 1.14 s、从 `idle` 进入。已和实际构建的动作逐项核对。
- **靴尖着地**：basic 绑定原来用通用前脚掌点（踝前 6.5 单位），长靴绕靴底中间转，蹬地时画出来的靴尖扎进地面
  （合成矮个角色走路 3.5 px、跑步 2.5 px，限值 1.19 px），骨骼代理却报 0。现在绑定记录每只靴子的实测靴尖
  （`foot_n_ball`/`foot_f_ball`），靴跟按构造本来就是实测的，不记录；同时记两端会启用 `measured_walk_height`，
  第一版试过：待机变高 2-4 px、走路蹬地时头部突跳，已放弃。`Gait.fit_toe` 让更长的力臂保持原设计的踝抬高度。
  两个合成角色：所有动作穿地不超过 0.5 px，走路/跑步头部起伏不变，待机逐像素不变，QA 0 FAIL。
  **用户看过修改前后对照 GIF 后认可并要求合并推送。** 柯南、士兵等已有真实角色需重新绑定才生效，原任务不在仓库，未重渲染。
- **像素穿地检查**：`painted_floor` 从只查翻滚扩到分层角色的所有动作；程序模板显示 `n/a`。
  故障注入在旧 QA 上 4 项失败；`test_painted_toe_contact.py` 用通用支点复现了扎地。
- **验证**：完整单测 816 项全部通过（9 项原有 expectedFailure，0 失败/错误/跳过），Godot、Phaser、PixiJS 共 6 项引擎测试实际运行。
  中途容器缺 `scipy`，导致上一次全量单测有 15 项导入失败，安装后已重跑。
  26 套回归 0 FAIL，`cutout_demo` 原有 WARN 保留；`baseline.py` 及 `--strict` 均为 0 变化；真实角色检查通过，
  但仍无登记的真实角色。`.skill` 本地重建用于测试，提交前已恢复，未提交。
- **发现的优化点（未做）**：只出一个动作也要先跑约 80 s 的布料预计算，没有布料时这一步是空转，
  hd512 单动作出帧时间里它占一半以上。优化要先证明输出逐像素不变。

## 2026-11-06 合并验证（用户已授权推送 main）

- 用户在线预览后明确要求“合并后推送吧”，本轮将腰胯衣料约束、隐藏髋点登记、普通跳跃/翻滚适配、
  实际图层触地及 QA 缺证据报告一起交付源码。没有重新锁定真实角色帧，也未恢复士兵旧视觉通过结论。
- 完整单测 `python3 -m unittest discover -s dev/tests -v`：808 项，799 pass、9 原有 expectedFailure，
  0 failure/error/skip，实际用时 1541.562 秒。Godot 4.3、Phaser 3.80.1、PixiJS 8.6.6 的 6 项引擎测试
  本轮均实际执行并通过，包括代表性角色的导入/播放及错误设置故障注入。
- 26 套完整回归总退出 0，逐套核对实际 QA 报告均 0 FAIL；`cutout_demo` HD 8 / pixel 7 个原有 WARN 保留。
  普通基准和 `baseline.py --strict` 均为 0 regressions、0 changed、0 drifted，无需更新基准。
- 已从统一源码同步旧目录，并本地重建 5 个 `.skill` 供包一致性及隔离安装测试使用。
  测试完成后恢复仓库内打包文件的原始字节，提交排除全部 `.skill`；验证过的新包保留在仓库外输出目录。
- `real_characters.py check --compare` 返回 0，但当前没有登记的真实角色固定基准，这不构成真实角色回归通过。
  本轮验证日志和逐套统计在 `/workspace/2dgameskills-output/merge-main-20261106/`；两次源码哈希核对确认
  全量检查期间动作/绑定/质检代码没有变化，只有本交接文档追加验证结果。

## 2026-11-06 柯南新增翻滚（预览阶段记录）

- 用户要求“给柯南加一个翻滚看看”。复用 `/workspace/work/conan-run-jump-20261106` 已接受的图层，
  正式重绑只新增 `gait.roll`，生图次数和失败历史未重置；原跑步/跳跃播放器数据及全部嵌入 PNG 保持逐字节一致。
- 旧通用翻滚被现有门禁阻断（239 FAIL / 1 WARN），输出保存在 `build-roll-rejected-legacy/`。
  新增显式 `ordinary_roll_v1`，按实测身材保留大腿根部、折回小腿，前倾收身、完整翻转一周、恢复到待机；
  未选择该 profile 时旧翻滚保持不变。第一个数值通过但收腿不足的姿势也已因观感撤回、保留为历史。
- 又发现骨骼近似轮廓会漏掉发梢/鞋尖穿地：旧数值通过的收腿版本保存在 `build-roll-rejected-ground-contact/`，
  新独立 native RGBA 检查能在该版本报 1 FAIL。最终翻滚在姿势求解阶段使用实际不透明源边界及最终网格约束整体触地，
  不移动完成后的 PNG 或弱化阈值；原骨骼代理测量另存，像素检查独立验证。
- 最终 `build-roll/` 只含 idle 36 帧 @15fps、roll 35 帧 @30fps；动作、衔接、绑定、材料和像素触地检查
  0 FAIL / 0 WARN，导出重建 71/71 帧完全相同。新增地面检查有故障注入；95 项定向测试为 94 pass /
  1 原有 expectedFailure，0 failure/error/skip。standalone 同步检查通过；未跑全量或重打 `.skill`。
- 已看全部 14 张 review 表，包括 71 帧完整腰胯、骨链、关节、隐藏裤边、头颈和双手，及浏览器中的 35 个翻滚姿势。
  浏览器正常 4.3 秒、半速 8.3 秒分别覆盖至少两轮与全部 60 个预览帧；暂停、逐帧、重播、背景切换及桌面/手机布局通过。
  浏览器以镜头跟随和地面标记显示原动作速度积分的前进，源帧未变形；预览附前后待机停顿。
- 成品、透明原生帧和新版分层/绑定/运行源码备份在 `/workspace/2dgameskills-output/conan-roll-20261106/`，
  审查和失败原因在任务的 `roll_motion_history.json` / `roll_preview_review.json`。用户明确要求在线预览，继续更新原
  `/conan-run-jump.html#roll` 和 `/conan.html`，保留原站点及访问权限。此预览不代表用户认可、正式动作库发布、
  士兵修复或代码已经合并；本轮通用代码仍未提交，等待动作观感反馈后再走全量门禁。
- Sites 发布返回 `succeeded`，版本 12，站点源码提交 `77797741e06d7baffb968e9497fefe7b68ca5f7c`；
  `online-publication.json` 保留部署及版本标识。源码含新增翻滚帧与当前源工程下载，旧 v6 下载和其他角色保持不变。

## 2026-11-06 士兵前腰缺口再次被用户指出（视觉失败，画面未重渲染）

- 用户圈出士兵前腰，问“士兵这里还是有问题啊 skill 怎么审核的”。保留的原生
  `run_017.png` / `run_018.png` 可直接复现前腰在抬腿时露出背景的缺口。上一轮只重新生成了柯南，
  网站的士兵仍是旧成品，未应用新绑定/衣料规则；此前士兵视觉通过结论继续撤销。
- 历史记录写了士兵 19 张审查图及浏览器复核，但当前导出 ZIP 没有原 job、图层、rig、trace 或审核报告。
  可以确认旧视觉判断错误，不能倒推出当时哪条数值检查测过此缺口，也不能确定是原分层还是网格求解根因。
  当前 skill 已把背景裂口列为阻断项；规则存在不证明代理实际复核正确。
- 本次审计另复现两处执行漏洞并修正：`qa_motion.py` 原先在缺 trace/part/bind 结果时默认显示 PASS，
  现 CLI 和 JSON 对未执行项标 `n/a`，缺证据产生 WARN，已有缺口/警告不会被缺字段掩掉。
  持枪角色的连接门禁现在也由 profile/实际 source owner 强制触发，移除展示标记不再绕过独立门禁。
- 新增入口级故障注入：旧代码 5 测试有 4 failure / 1 error；修后扩为 7 项，连同遮挡、持枪、
  服装连接共 66 项定向检查为 65 pass / 1 原有 expectedFailure，0 failure/error/skip。
  对旧士兵成品重新测量只能得到像素节奏项通过，骨骼/绑定/材料证据不可用；报告为 0 FAIL / 1 WARN，
  不构成视觉通过。新柯南原生 7 动作重查仍 0 FAIL / 0 WARN。
- 证据在 `/workspace/2dgameskills-output/quality-audit-20261106/`，包括原生帧、前腰近景、
  `qa-evidence-before.log`、`qa-evidence-tests.log` 和本次士兵重新测量报告。
  **本次修的是审核误报/漏调用，未重画或重渲染士兵，不能称该缺口已经修复。** 未提交或合并，也未改 `.skill`。

## 2026-11-06 柯南跑步/跳跃重新生成（待用户动态验收）

- 用户重新附柯南原图，明确要求“你重新生成 跑步 和跳跃的动作”。新任务
  `/workspace/work/conan-run-jump-20261106`；旧 v5 的否决和缺失原任务记录保留。
  原上传只在会话中可见，无本地原文件；`source.png` 明确标为 `generated_identity_proxy`，
  不能用它的哈希证明原上传字节。代理图同时作为第 1 次标准参考生成计数；未重置旧预算。
- 依固定流程生图和复核，保留失败尝试：reference 1，head / hips 各 3，torso / leg_near 各 2，
  其余图层和双手提示各 1。`job.json`、输入、分层、正式绑定、提示词、review、attempts 全保留。
- 通用分层提示词明确隐藏 hips 的全部边界都是内部裁边、不描黑线。绑定新增 `registered_hip_level`：
  原两座点已在骨盆与各自腿的实际不透明交集中时完全保留；否则沿实测骨盆轴找最近共同高度，
  不改横向座点、骨长规则或图片。找不到共同交集仍拒绝。更新真实驱动根点和诊断，不手改角色 rig。
- 旧通用跳跃在这个新角色上被现有检查阻断（76 FAIL / 1 WARN），完整输出留在
  `build-rejected-legacy-jump/`。新增显式 `ordinary_jump_v1`，以实测腿长及接受的手臂携带姿势拟合下蹲、
  收腿和落地；五个阶段都有限时且相接，纵向速度积分回到同一地面。仅新 basic 绑定选择该 profile，
  未选择时旧动作保持原行为。没有放宽 QA 阈值。
- 最终 512px 原生输出：run 22 帧；jump_start 8 / jump_rise 10 / jump_apex 8 / fall 10 / land 10，
  完整跳跃 46 帧；另有衔接用 idle 36 帧 @ 15fps。只检查这 7 个动作，未跑射击或完整 27 动作。
  `qa-final.log` 为 0 FAIL / 0 WARN；11 个后侧手臂遮挡候选逐帧看过全身、近景和真实骨链，
  以当前图集哈希绑定的逐项理由接受，不是自动清除警告或用户认可。
- 定向单测 103 项：102 pass / 1 原有 expectedFailure，0 failure/error/skip；standalone 同步检查通过。
  已查看 29 张 review 表及全部候选原生帧；本地 Chromium 正常/半速播放、暂停/逐帧控件检查通过，
  正常播放覆盖全部 22 个跑步帧及含前后静止停顿的 66 个跳跃预览帧。
- 预览和备份在 `/workspace/2dgameskills-output/conan-run-jump-20261106/`。`preview.html` 为本地独立文件，
  `run.gif` / `jump.gif`、透明完整动画帧、原生分阶段帧与图集一起保留。完整跳跃的整体位移从
  当前动作速度曲线积分，不改变源图、关节或原生帧；`playback.json` 记录每帧来源/位移/哈希。
  新旧跑步对照的美术也已重新生成，不能解读为仅改求解器的等价比较；跳跃对照是本任务旧动作与新 profile。
- **仍待用户看预览。** 未将其锁定为真实角色回归基准，未跑全量/打包 skill、发布网页或提交合并。
  当前代码仍在 `codex/garment-contour-20261106`，下轮应保留此状态和失败历史。
- 用户随后指出本地 HTML 链接会显示源码，并要求恢复原先的在线预览体验。已按这次要求更新原 Sites 站点，
  保留原链接及仅所有者访问权限；这不表示用户认可了动作，也未提交/合并动作库代码。
  在线播放器：`https://cityrunner-motion-preview-20261105.ww1995012019.chatgpt.site/conan-run-jump.html`，
  总览为同站点的 `/conan.html`。桌面/手机布局、全部文件链接、GIF、暂停/慢放/逐帧已在对应本地资源上检查；
  Sites 私有发布返回 succeeded。站点源码提交 `066aa22b514c1823e8a3683003f33ab863d8b64d`，
  发布记录见输出目录的 `online-publication.json`。旧版页面保留为历史并标记验收撤回；7 个页面未引用的旧 ZIP
  移到站点源码的 `history-downloads/`，使发布包降到平台 256 MiB 限制内，所有页面实际引用的资源和下载保留。

## 2026-11-06 腰胯缺陷复查与代码修改（真实角色待重渲染）

- 用户反馈：“你看下 这里都是有问题的 skill没有检测到吗”，并补充士兵和柯南的正面外观原图。
  原图未见截图中同样的异常，但正面原图不能替代当时的侧视参考图、分层和绑定证据。
- 从既有私有预览只读取回版本 10 的源码（`33f9c17454456b8d1c3232cb8ae51868989952d4`），
  检查 `conan-idle-run-v5.zip` 和 `soldier-idle-run.zip` 的实际 PNG：各 22 张跑步帧，以及待机 0 / 36 帧。
  柯南跑步 16–19 帧的短裤前缘随抬腿外翻；士兵待机已可见胯部生硬折边，跑步中也未消除。
  用户截图对应的精确版本/帧尚未确认，不把本次复查帧直接当成截图帧。
- 两个导出包只有动画成品，无 `job.json`、侧视绑定参考、layers、rig、trace 或 QA/视觉报告。
  可确认旧导出仍有观感缺陷，尚不能确定是侧视美术、分层还是绑定网格的具体根因。
  数值检查覆盖局部材料应变和登记的隐藏裁边，不能证明完整可见服装轮廓正确；原视觉通过结论已撤销。
- 复查阶段未改角色数据或求解器，未重新生图、绑定、重开任务/预算、发布网页或重跑全量。
  本地证据在 `/workspace/2dgameskills-output/quality-audit-20261106/`（逐帧腰胯图、待机/跑步对比及 `audit.json`）。

用户随后要求直接修改；分支 `codex/garment-contour-20261106` 已继续实现通用修正：

- `GarmentBand` 的 ARAP 与材料投影限制在骨盆和大腿两个实际所有者的旋转区间内，保留固定裁边、
  远端顶点及源像素。原求解器在合成用例中可把约 46° 的两端运动解成接近 180° 的局部卷曲，原应变检查仍通过。
- 材料检查从“三角形中心是否不透明”改为“不透明像素的覆盖范围碰到哪些三角形”，覆盖细裤边。
  边界三角形独立使用原有应变限值；任一异常都阻断，不按 1% 的内部容许比例平均掉。
  最终网格另测材料偏离两所有者旋转区间的误差，沿网格源边折算到原生输出像素，限值仍为 1 px。
- 连接证据增加边界数量/异常数量与转角误差，旧报告缺字段或旧采样标识不能沿用。
  覆盖缓存只留每层当前 alpha/网格快照；原地换 alpha 或网格会失效，不缓存 QA 结论。
- 定向验证 `test_garment_contour test_garment_rims test_registered_connections test_rifle_carry test_character_workflow`：
  95 项，94 pass、1 原有 expectedFailure，0 failure/error/skip。新增故障注入定位实际的部件、动作与第 2 帧，
  并确认源像素不变、固定点不变、旋转跨 ±π 与缩放不引入异常。
- 两种宽度合成衣料各 20 帧，与 `1e8b663` 的原求解器对照：旧报告全为 0 应变异常，
  新检查重测旧网格的最大转角误差为 18.62411 / 6.52586 px；修改后为 0.0142 / 0.0005 px，
  应变异常及边界异常均为 0。对照与测量在 `/workspace/2dgameskills-output/garment-contour-repair-20261106/`。
  **这是合成复现，不是柯南/士兵的修后验收。** 两者缺原任务图层/rig，已询问其余保存路径；未重建任务绕过预算。
- 源码与生成的旧目录已同步；未改 `.skill`，未提交/合并、发布、重跑全量或将真实角色标为已修复。

## 本轮：工作流优化（2026-11-06）

用户要求优化开发流程，不改角色、动作曲线、阈值或质检规则。分支从 `2303b59`（PR #10 合并后）开始。

- **单一源码**：`dev/build_standalone.py` 取代 `shared/`、`sync_shared.py`、`sync_modes.py`。切换前先用新脚本从
  `game-animator/modes/` 生成四个旧文件夹，除加了弃用说明的 SKILL.md 外与原文件逐字节一致；PR #10 新增的
  `review_support.py` 已加入共用清单。已有代码文件唯一的改动是开头那行“去哪里改”的注释。回归改跑统一包。
- **返修先给用户看**：新增 `scripts/compare_clips.py`（固定地面、同比例、按周期相位对齐的新旧 GIF 和相位图，
  附头顶起伏像素数）与 `references/repair-loop.md`；`CLAUDE.md` 改为用户认可后才跑全量验证和发布。
- **真实角色回归**：新增 `dev/real_characters.py`（add / approve / check --compare），锁定用户认可帧的 RGBA 哈希，
  只用 `cutout_demo` 测过。用户发来的柯南、士兵 zip 只有导出成品，没有 job.json / layers / rig，无法重新渲染，
  用户决定这次先不接入。**目前没有任何真实角色进入回归。**
- **文档**：HANDOVER 旧节、路线图顶部状态日志原样归档到 `docs/handover/history-2026-10-30-to-2026-11-05.md`
  （逐行核对 0 丢失）；横版 SKILL.md 开头 95 行规则原样移到 `references/release-gates.md`，入口留 5 行摘要。
- **验证**（2 核云端容器，无外网）：
  - 完整单测 772 项：首跑 3 项 CSS 播放失败，原因是验证脚本把 TEMP 指向尚不存在的目录、浏览器无法建临时目录；
    正常环境单独重跑 3 项全部通过。其余 0 failure/error，9 项原有 expectedFailure，6 项引擎测试因无法下载
    Godot/npm 包而跳过——Godot、Phaser、PixiJS **本轮未重新实测**。
  - 26 套回归 exit 0，全部 0 FAIL；`cutout_demo` HD 8 / pixel 7 WARN 保留。`baseline.py` 和 `--strict`
    均为 0 regressions、0 changed、0 drifted。
  - `.skill` 在本地重建用于测试，按用户约定未提交。

## 2026-11-05 普通横版生产链路的等价重构

- 用户要求完成六项普通横版代码优化，验证后提交并合并 main，且提交中不包含 `.skill`。
  分支从 `d05957f` 建立。具体设计、缓存边界和等价性证据见
  `docs/side-pipeline-refactor.md`；未扩大 basic 的美术/动作范围或改审核标准。
- 素材准备由 `workflow_assets.JobAssets` 在一次命令内复用，输入数组只读；新命令重新读取。
  参考图提交与复查共用审核规则，失败撤销旧审核及重试预算不变。
  `FrameContext`/`puppet_qa` 复用一个动作的数值检查准备数据，最终网格缓存限 32 MiB/128 条，
  满时重算、结束释放；渲染、独立 QA 和交付哈希检查分别执行，不缓存通过结论。
- `RegistrationScore` 预计算每个搜索尺度的固定数据；`review_support` 统一播放时长、分组、
  姿势覆盖和有界审查图片读取。拆出配准、四肢测量、渲染及导出阶段；不更改动作曲线、阈值、
  搜索候选、浮点运算顺序或报告格式。共享文件与统一模式快照已同步。
- 原合成高/矮两体型的绑定图和配置保持一致；相同路径/哈希种子的待机与走路共 98 帧，
  两组分别 88/87 个生成文件逐字节一致，含图集、引擎文件、QA、审查 PNG/GIF 和审核 ID。
  已对齐夹具使用相同 identity registration；不是新 AI 美术或用户视觉通过。
- 7 帧走路的六项身体检查加遮挡检查：网格生成 39 -> 7 次，全部故障/测量相同，缓存 298816 字节。
  绑定前复查抠图 20 -> 10 次。完整躯干配准仍评估原候选，只准备 4 份尺度数据，全部参数及误差
  与原 20257 次评分的结果逐值一致。不把并发环境下的计时波动宣传为固定倍数的产品提速。
- 完整单测实际 exit 0：765 项，756 pass、9 原有 expectedFailure，0 failure/error/skip。
  新增 10 项覆盖缓存故障定位、低容量回退、尺度/采样隔离、跨命令换图、图片副本隔离及评分等价。
  Godot 4.3、Phaser 3.80.1、PixiJS 8.6.6、Chromium CSS 和统一包隔离安装测试均在此轮运行。
- 优化后 26 套回归 exit 0、全部 0 FAIL，cutout_demo HD8/pixel7 WARN 如实保留。
  首次对旧基准严格比较 exit 1（0 状态回退、116 changed、102 drifted），失败日志保留。
  独立归档 `d05957f` 再跑 26 套，确认改前/改后 1124 动作的完整快照和 QA JSON 全部相同；
  旧版本自身也有相同漂移。以改前输出修复旧基准，独立提交 `d78a1bb`；未掩盖重构差异。
  修复后改前、改后两边严格比较均 exit 0，0 regressions/changed/drifted。
- 五个包已在本地重建，用于 freshness 和隔离安装验证；提交前恢复 `.skill`，源码提交明确排除它们。
  `CLAUDE.md`/README 已说明先本地打包再测试，安装最新版本用目录或本地新包，仓库旧包可能落后。
  主要证据与原失败记录在 `/tmp/side-refactor-proof`、`/tmp/side-refactor-full-tests.log`、
  `/tmp/side-refactor-regression.log`、`/tmp/side-refactor-baseline.log`；优化源码提交/合并号见 Git 历史。

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
