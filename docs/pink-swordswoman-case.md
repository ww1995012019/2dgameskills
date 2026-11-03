# 樱璃女侠：第二个实际八部件图集案例

## 粉色古装女侠待机/走路已发布（2026-11-03）

用户认可粉色可爱系立绘后要求按此制作，沿用实验八部件图集适配器和正式known-joint绑定。
案例 `/workspace/2dgameskills-output/pink-swordswoman-v1`，最终 `rig-v2` / `build-v2`，
512px、24FPS，idle58帧、walk20帧，共78帧。数值QA 0 FAIL/0 WARN，4张视觉审查图检查并登记通过，
浏览器播放、暂停、逐帧、翻转、键盘移动通过，0页面错误。用户仅认可立绘，动态仍pending。
本角色动画阶段图集1次、修复图1次；此前身份生成历史是青色初稿1次、粉色重设1次。
首版数值动作通过但素材软糊检查失败（近腿3/62、近臂1/23 tiles），保留build-v1及日志。
一次图集修复仅导入近臂/近腿，另外六部件原始字节不变，最终9层全部0软糊tile；未放宽QA。
继续使用既有领口前景副本规则。发饰/衣摆/流苏随部件运动，无独立布料模拟，剑柄流苏简化去掉。
本轮未改Skill、适配器或runtime，仅新案例、网页和文档；此例不能代表任意美术都能自动分层。

原私有Site已成功发布：https://skeleton-animation-preview-1103.ww1995012019.chatgpt.site 。
默认粉色女侠，`pink.html`也是独立入口；`swordsman-full.html`保留男角色27动作，浏览器检查通过。
Site源提交 `8ea46758155f02b9478f70caf09fedccd69d344b`，部署
`appgdep_6ae94ce2b0a48191ad863c895ea504c6`。没有改变访问权限，未声明Unity/Godot实际运行。
详情 `docs/pink-swordswoman-case.md`。

## 复现

在仓库根目录用项目虚拟环境运行：

```sh
/workspace/2dgameskills-venv/bin/python game-sprite-animator/scripts/generate.py \
  --character /workspace/2dgameskills-output/pink-swordswoman-v1/rig-v2/character.json \
  --preset hd512 --clips idle,walk --fps 24 --no-fx \
  --out /workspace/2dgameskills-output/pink-swordswoman-v1/NEW_BUILD
```

原始立绘、两次图集、提取部件、测量manifest、组装图、rig、两版render与QA日志均保留在案例目录。
`parts-v2`只替换近侧手臂和腿，其他六部件严格保留初版。
`job.json`记录用户立绘认可、真实生成计数、失败与修复、最终验证和发布，动态认可仍pending。
视觉报告覆盖完整动作、关节极限、肩根与完整手臂四张图；只验证idle/walk，未生成其余25动作。
实际脚滑0.006px、脚底最大偏离0.286px，数值不能代替用户对动态的观感判断。

网页产物位于 `/workspace/sites/skeleton-preview/dist`，外置atlas加载，约5.4MB下载包包含完整rig、
图集、动画配置、引擎导出和离线HTML。浏览器证据及截图在 `build-v2`。
这次只运行新产物QA与浏览器检查，没有改核心代码，因此没有重跑无关的旧26套回归。
