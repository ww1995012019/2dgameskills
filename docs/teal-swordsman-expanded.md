# 青岚剑客完整动作扩展

用户认可 idle/walk 后要求查看其他动作，复用同一 `rig-v7` 和原部件。无新增AI图像调用，
身份图1次、八部件图集1次、修复图0次的累计次数不变。此前用户认可的两动作存于
`idle-walk-user-approval.json`；新25动作只记录代理审查通过，不替代用户观感验收。

案例根目录：`/workspace/2dgameskills-output/teal-swordsman-v1`。
生成命令（仓库根目录，使用项目虚拟环境）：

```sh
/workspace/2dgameskills-venv/bin/python game-sprite-animator/scripts/generate.py \
  --character /workspace/2dgameskills-output/teal-swordsman-v1/rig-v7/character.json \
  --preset hd512 --clips all --fps 24 \
  --out /workspace/2dgameskills-output/teal-swordsman-v1/expanded-v1
```

生成27动作共494帧，图集去重后483帧，含剑光特效。数值QA与动作衔接均通过，0 FAIL/0 WARN。
16张审查图（完整动作5、关节1、肩5、手臂5）均已逐张查看并登记通过，visual_review --check
通过。检查覆盖翻转翻滚、落地、三连击、受击和死亡等极端姿态，未发现明显断肢、重剑或领口缺口。
此处属于代理视觉判断。`expanded-render-v1.log`、`expanded-qa-v1.log` 保留完整过程。

`expanded-v1/browser-validation.json` 记录27动作选择、10个快捷按钮、播放/暂停/逐帧，以及
游戏中奔跑、二段跳、三连击、冲刺、翻滚、施法、格挡受击、受击和死亡/复活触发。
页面错误和失败请求均为0，保留桌面及移动端截图。没有宣称Unity/Godot实际运行。
旧 `build-v7` 的idle/walk帧与新导出逐帧SHA256相同。

本轮没有修改runtime、绑定器或图集适配器，只新增实际角色完整动作输出和预览。
发布页面保留同一私有Site，默认奔跑；顶部提供快捷入口，动作库可选全部动作。
媒体外置为PNG，避免把17MB图集塞入HTML阻塞首屏；下载包包含rig、图集、引擎导出和可离线打开的HTML。

已确认成功发布：https://skeleton-animation-preview-1103.ww1995012019.chatgpt.site

Site源提交 `c7fdcbffc1b91a69a4f30908ea27e23888e05f03`，部署
`appgdep_6ae94796b36c81919c3285bb01477004`。保留原owner-private权限。
