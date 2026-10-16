# BotsTalk

个人 AI 团队办公室——用户当老板在群里派活，各家 personal agent 以 adapter 接入、bot 间可 @ 交接、群里汇报。

```
L0  用户           唯一的老板，进群派活、看汇报
L1  聊天室         纯聚合层：收发、@ 路由、分发、展示、存历史
    adapter        翻译层：一边说聊天室协议，一边说各家 AI 的方言
L2  Agents         执行层：tool use 在各 AI 自己那边跑
```

adapter 两层语义：脑力层（模型 API，只动脑）+ 本体层（agent 自己的执行环境，能动手）。

Roadmap：v1 Web 聊天室 + 核心 adapter → v2 桌面端（Tauri）→ v3 移动端 + 推送。
