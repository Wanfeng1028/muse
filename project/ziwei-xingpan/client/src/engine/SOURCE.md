# 引擎来源说明

排盘引擎移植自 Renhuai123/ziwei-doushu 的 lib/ziwei 模块（MIT License，复印件见本目录 LICENSE）。

- 来源：https://github.com/Renhuai123/ziwei-doushu
- 许可证：MIT License，Copyright (c) 2026 紫微研究
- 移植改动（仅适配小程序运行环境，计算逻辑未改）：
  - 删除 Next.js 专属导入（patterns.ts 的 `server-only`）。
  - 删除对 UI 组件的导入依赖（源项目 history.ts / share.ts 依赖 `@/components/BirthForm`，本期未移植，见下方剔除清单）。
  - patterns.ts 中 5 处格局描述删除了引用他人原话的短句，改写为中性表述；格局判定条件（名称、等级、涉及宫位）未变。
  - algorithm.ts 注释中 1 处古籍引文改为转述；school-config.ts 中流派标签的中性化改写。
  - 顶部加移植说明注释。

## 移植清单（15 个模块）

algorithm、cities、clock-adjust、constants、dst-cn、patterns、school-config、school-data、
school-tables.generated、shier-shen、sihua、true-solar-time、types、yunxian-context、lunar-solar，
另附 lunar-javascript.d.ts 类型声明（源项目同名文件）。

## 剔除清单（明确未移植）

- lib/ziwei/history.ts：依赖 React hooks 与 `@/components/BirthForm`，属 Web 端状态逻辑，小程序用 Taro storage 自行实现。
- lib/ziwei/share.ts：依赖 `@/components/BirthForm` 类型，属分享链接逻辑，一期不做分享。
- lib/ziwei/db-analysis.ts：依赖数据库分析口径，一期纯本地排盘不需要。
- lib/ziwei/famous.ts：含 `server-only` 与名人案例数据，一期不需要。
- lib/ziwei/heming-knowledge.ts：许可红线，绝不移植。
- lib/nihai/*、docs/tianji-ziwei、lib/seo/knowledge 原文：许可红线，绝不移植、不抄录。
- 区县级数据（源项目 counties.generated 等）：源项目 lib/ziwei 目录内无此文件，一期只用 cities.ts 的省市经度库。

## 依赖

iztro@2.5.8、lunar-javascript@1.7.3，均为纯 JS，可在小程序内运行。
