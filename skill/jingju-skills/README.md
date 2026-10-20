# 鲸剧 Skills

这是一个用于 AI 漫剧全流程创作的 Codex Skill，名称为 **鲸剧 Skills**。

它的定位不是一键出片工具，而是一个 **AI 编剧 + AI 美术指导 + 生产流程导演**。核心目标是让漫剧创作从随机抽卡，变成可确认、可复用、可批量推进的生产流程。

## 核心能力

- 剧本大纲生成
- 背景设定和人物关系设计
- 人物设定和角色一致性提示词
- 角色多视角参考图提示词
- 分集剧本生成
- 分镜脚本设计
- 每镜头图片提示词
- Codex 内置 image2 预览图生成
- ComfyUI 可选参数包和批量出图流程
- 图生视频提示词
- 本地视频模型/API 可选成片生成
- 每个阶段的用户确认和版本选择

## 关键规则

开工前必须先确认：

```text
故事的大体环境是什么？
小说/漫剧类型是什么？
```

每个关键产物都必须用户确认后才能进入下一步：

```text
大纲确认
角色确认
角色参考图确认
剧本确认
分镜确认
图片版本确认
图生视频提示词确认
视频版本确认
```

图片生成后必须选择版本：

```text
未确认角色图 → 不生成分镜图
未确认分镜图 → 不生成图生视频提示词
未确认图生视频提示词 → 不生成成品视频
```

## 可选生成能力

### image2

Codex 内置 image2 可直接使用，不需要额外接 API。

用于：

- 角色参考图
- 场景预览图
- 分镜预览图

生成后必须等待用户选择版本。

### ComfyUI

ComfyUI 是可选高级生产能力，不是必需依赖。

默认检测地址：

```text
http://127.0.0.1:8188
```

如果 ComfyUI 在线：

- 读取模型和节点
- 注入 workflow 参数
- 批量生成角色图或分镜图

如果 ComfyUI 不在线：

- 不报错
- 不强行生成
- 输出提示词和 ComfyUI 参数包

### 本地视频模型/API

图生视频生成也是可选能力。

只有在以下条件都满足时才生成成品视频：

```text
源图片已确认
图生视频提示词已确认
用户明确要求生成视频
本地视频模型或 API 可用
```

否则只输出图生视频提示词和建议参数。

## 常用命令

```text
/start              开始新项目
/characters         生成角色设定和角色参考图提示词
/outline            生成故事大纲
/episode N          生成第 N 集剧本
/storyboard N       生成第 N 集分镜脚本
/prompts N          生成第 N 集图片提示词
/generate N         使用 image2 生成预览图
/comfy-check        检测 ComfyUI
/comfy-batch N      使用 ComfyUI 批量生成分镜图
/video-check        检测本地视频模型/API
/video-prompts N    生成图生视频提示词
/video-generate ID  生成指定镜头视频
/status             查看待确认项
/approve NAME       确认阶段
/revise NAME        修改阶段
/select ID VERSION  选择图片/视频版本
/lock ID            锁定资产
/next               进入下一阶段
```

## 目录结构

```text
jingju-skills/
├── SKILL.md
├── README.md
├── references/
│   └── stage-output-contracts.md
├── templates/
│   ├── project-state.json
│   ├── character-card.json
│   ├── shot-card.json
│   └── comfy-params.json
└── workflows/
    └── README.md
```

## 推荐工作流

```text
1. /start
2. 确认故事环境和小说类型
3. /outline
4. 用户确认大纲
5. /characters
6. 用户确认角色卡和角色图提示词
7. 使用 image2 或 ComfyUI 生成角色参考图
8. 用户选择并锁定角色图
9. /episode 1
10. 用户确认剧本
11. /storyboard 1
12. 用户确认分镜
13. /prompts 1
14. 生成分镜图
15. 用户选择分镜图
16. /video-prompts 1
17. 用户确认图生视频提示词
18. 有本地视频模型/API则生成成片，没有则交付提示词
```

## 核心卖点

```text
少抽卡
保角色
可确认
可批量
可复用
```
