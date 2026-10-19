# 技术债登记（drama-factory）

## 登记规则

发现即记，每条写清"现象/影响/偿还计划/优先级"四列，做完后从存量挪到"已偿还"，不删记录。

## 存量技术债

| 编号 | 现象 | 影响 | 偿还计划 | 优先级 | 登记日期 |
| --- | --- | --- | --- | --- | --- |
| TD-001 | toonflow-canvas / toonflow-workflow / toonflow-v118workflow 三个 skill 说好独立重写，实际只是改了改，跟上游原文用 difflib 比相似度还有 0.911–0.982；`_index.json` 里一度把 `rewritten` 标成 true，已经改回 false，并补上了上游 MIT LICENSE。详见 docs/TOONFLOW_SKILLS_REVIEW_2026-10-20.md | 对外说"重写"但拿不出独立成果，跟上游授权关系也没讲清楚，属于合规和交付两头都站不住；但功能上能跑，不挡当前流程 | 让 dpsk 按"抄了 95%"的思路重写 workflow 的 PART A 规则表述和 canvas 操作手册，重测相似度掉到 0.5 以下，再把 `rewritten` 改回 true；没排期 | P1 | 2026-10-20 |
| TD-002 | HyperFrames 内嵌引擎接进来了，但 `-w`（workers）没做成可配，只能吃 CLI 默认的 auto，独立 provider 那边默认写死 2；`composition.html` 直接复用 scene.html 模板，是 kinetic typography 那套风格，没做 HyperFrames 原生的可寻址动画模板（data-composition-id / 时间线那套） | 多机跑的时候 workers 调不动，量上不去；动画风格只有一种，做不出按时间线定位的原生效果 | 把 `-w` 接到配置层暴露出来，并补一份 HyperFrames 原生可寻址动画的 composition 模板 | P2 | 2026-10-20 |
| TD-003 | SkillHub 远端官网还没上线，目前只有约定文档 docs/skillhub-server-convention.md；`/api/skillhub/index` 返回的 `updatedAt` 取的是请求那一刻的时间，不是索引真正构建的时间；也没有分页，227 条一次全吐出来 | 客户端拿 `updatedAt` 判断不了索引新旧；条数再涨下去（上千条）一次返回会拖慢也容易打爆 | skills 数量超过 500 条时启动分页，并把 `updatedAt` 改成索引构建时刻 | P2 | 2026-10-20 |
| TD-004 | 4 个 Toonflow provider 描述符里，models 的 id 命名风格不统一，比如 apimart 用 `seedance-2.5`，tfrouter 用 `"Seedance 2.5"` | 同一模型在不同通道叫法不一样，按 id 查/匹配会踩坑，前端展示也乱 | 定一套 models id 命名规则，把 4 个描述符统一改过来 | P2 | 2026-10-20 |
| TD-005 | 4 个 Toonflow provider 描述符的真实接口还没联调过，没有 Key，只能判为未验证 | 描述符写得再对，没打过真接口就不知道通不通，上线有翻车风险 | 等用户提供各通道 Key 后逐个联调，跑通再把状态改成已验证；当前卡在 Key 上 | P1 | 2026-10-20 |

## 已偿还

- toonflow skills 标注失实纠正 + LICENSE 补齐：`_index.json` 里 `rewritten` 从 true 改回 false，并补上上游 MIT LICENSE，跟上游的授权关系写清楚了。
- skillhub 自有索引落地：`/api/skillhub/index` 已经能出 227 条索引数据，自有索引这条通了（分页和 `updatedAt` 语义另记 TD-003）。
- hyperframes 引擎接入 + 真实联调：内嵌引擎已经接进来并跑过真实联调（`-w` 配置和原生动画模板另记 TD-002）。

## 与 DoD 的关系

发版前对照 PRODUCTION_CHECKLIST 里"技术债记录与偿还计划"那一条，本文件就是该条目的载体。
