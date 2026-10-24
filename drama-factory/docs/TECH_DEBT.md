# 技术债登记（drama-factory）

## 登记规则

发现即记，每条写清"现象/影响/偿还计划/优先级"四列，做完后从存量挪到"已偿还"，不删记录。

## 存量技术债

| 编号 | 现象 | 影响 | 偿还计划 | 优先级 | 登记日期 |
| --- | --- | --- | --- | --- | --- |
| TD-001 | toonflow-canvas / toonflow-workflow / toonflow-v118workflow 三个 skill 说好独立重写，实际只是改了改，跟上游原文用 difflib 比相似度还有 0.911–0.982；`_index.json` 里一度把 `rewritten` 标成 true，已经改回 false，并补上了上游 MIT LICENSE。详见 docs/TOONFLOW_SKILLS_REVIEW_2026-10-20.md | 对外说"重写"但拿不出独立成果，跟上游授权关系也没讲清楚，属于合规和交付两头都站不住；但功能上能跑，不挡当前流程 | 让 dpsk 按"抄了 95%"的思路重写 workflow 的 PART A 规则表述和 canvas 操作手册，重测相似度掉到 0.5 以下，再把 `rewritten` 改回 true；没排期 | P1 | 2026-10-20 |
| TD-002 | `composition.html` 直接复用 scene.html 模板，是 kinetic typography 那套风格，没做 HyperFrames 原生的可寻址动画模板（data-composition-id / 时间线那套） | 动画风格只有一种，做不出按时间线定位的原生效果 | 补一份 HyperFrames 原生可寻址动画的 composition 模板 | P2 | 2026-10-20 |
| TD-004 | 4 个 Toonflow provider 描述符里，models 的 id 命名风格不统一 | 同一模型在不同通道叫法不一样，跨通道匹配会踩坑 | ~~定一套 models id 命名规则统一改 id~~（方案已修正：id 是上游 API 模型名，DescriptorVideoProvider 直接拿去发请求，统一改会改坏上游调用；改为新增 `canonical` 归一化字段做匹配，id 保持不动） | P2 | 2026-10-20 |
| TD-005 | 4 个 Toonflow provider 描述符的真实接口还没联调过，没有 Key，只能判为未验证 | 描述符写得再对，没打过真接口就不知道通不通，上线有翻车风险 | 等用户提供各通道 Key 后逐个联调，跑通再把状态改成已验证；当前卡在 Key 上 | P1 | 2026-10-20 |

## 已偿还

- toonflow skills 标注失实纠正 + LICENSE 补齐：`_index.json` 里 `rewritten` 从 true 改回 false，并补上上游 MIT LICENSE，跟上游的授权关系写清楚了。
- skillhub 自有索引落地：`/api/skillhub/index` 已经能出 227 条索引数据，自有索引这条通了。
- TD-003 已偿还（2026-10-24，SkillHub 索引默认分页）：GET /api/skillhub/index 始终分页，无参默认第 0 页、每页 50 条；updatedAt 取 SkillRegistry 构造时记录的 bundledLoadedAt，即索引构建时刻；远端官网未上线仍属约定文档范围，不在本条。
- TD-002（workers 半句）：经核查不成立——`drama.video.hyperframes.workers` 配置键自 468ad37 起即存在并透传 `--workers`，已有 HyperFramesWorkersConfigTest 锁定；存量债仅剩原生可寻址动画模板一项。
- TD-004：`ProviderDescriptor.DescriptorModel` 新增 `canonical` 字段；4 个描述符 9 个 model 全部补上归一化名（规则：全小写 kebab，版本号点保留）；`id` 保持为上游 API 模型名不动。验证：seedance-2.5 在 apimart/tfrouter 两通道 canonical 一致，跨通道匹配打通。
- hyperframes 引擎接入 + 真实联调：内嵌引擎已经接进来并跑过真实联调（`-w` 配置和原生动画模板另记 TD-002）。

## 与 DoD 的关系

发版前对照 PRODUCTION_CHECKLIST 里"技术债记录与偿还计划"那一条，本文件就是该条目的载体。
