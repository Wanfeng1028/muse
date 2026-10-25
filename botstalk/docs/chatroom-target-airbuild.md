# BotsTalk 聊天室目标参考：AirBuild 式多智能体房间

来源：用户 2026-10-25 发来的照片，Akring 介绍 AirBuild 的视频截图。
原图存档：docs/screenshots/airbuild-chatroom-reference.jpg
用户原话要点：这就是他最初想相信的聊天室的样子；想象中的他最终就是这个样子。
即：用户不亲手写代码，只在聊天室里当老板指挥、验收。

## 图里看到的房间结构

- 一个房间，不是 1 对 1 对话框。
- 用户坐中间发号施令，用 @ 点名派活，例如 @developer。
- 右侧（或侧栏）是一排 Agent 名单，各有分工，例如 Ato 管产品、Pluto 管开发，另有 Coin、Camo 等角色。
- Agent 在房间里直接回进度、交东西，例如 Save for Later 卡片。
- 底部挂着服务模块，例如 AirFeedback、AirPayment、AirRouter、AirKnowledge、AirTraffic。
- 宣传语要点：AirBuild 直接把“不会开发 iOS 应用”这个门槛拆了。

## 对应到 BotsTalk 的目标

- 工作坊就是这个房间：老板派活、Agent 汇报、Agent 之间交接。
- 路由：工作坊默认定向，只有被 @ 或被回复的成员接活，没被点名的只看不接（见 SOUL-rooms.md）。
- 房间里要有：成员名单（分工可见）、@ 派活、任务状态可见、交付物直接出现在房间里、服务模块入口。
- 用户的最终姿态：说话、验收、拍板，不写代码，不替 Agent 干活。

## 用户新口径（2026-10-25 20:18，覆盖旧口径）

- 用户亲定：BotsTalk 的前端**可以参考或者完全抄 AirBuild 的项目来做**。
- 旧口径“只借结构、不照抄素材品牌”就此作废，但落地前先问用户定设计细节（见下），不擅自替他定。
- 待用户决策的设计点：①布局是否照图三栏（中间聊天＋右侧 Agent 名单＋底部服务模块）；②配色/风格是沿用 BotsTalk 现有 design-v1/v2“值班室台账”，还是换成图里那种浅底卡片风；③底部模块用 BotsTalk 自己的模块名（任务/交付物/审批等），还是照抄图里的 AirFeedback/AirPayment/AirRouter/AirKnowledge/AirTraffic；④右侧名单是否照图用 Ato/Pluto/Coin/Camo 等分工，还是用 BotsTalk 现有角色。

## 不做的事

- 不把“老板只指挥”变成“老板看不见”：任务状态、交付物、失败原因必须在房间里可见、可追溯。
- 不把“老板只指挥”变成“老板看不见”：任务状态、交付物、失败原因必须在房间里可见、可追溯。
- 娱乐厅仍按 SOUL-rooms.md 的广播、抢话规则走，不套用工作坊的定向规则。
