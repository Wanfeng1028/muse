# Pipeline 模板体系

## 1. 这个模板解决什么问题

把「一条短剧从立项到交付」的流程写成 YAML，让每一步产出什么、进来要带什么、哪里必须停下来让人看一眼，都变成可读、可改、可测的配置文件，而不是散落在代码和口头约定里。

## 2. 文件位置与加载机制

模板文件放在：

```
src/main/resources/pipeline-templates/*.yaml
```

启动或按需加载时，由 `PipelineTemplateLoader` 负责读取。它使用 SnakeYAML 的 `SafeConstructor`，只认白名单里的键，碰到不认识的键直接报错，不会悄悄忽略。解析结果落到两个 POJO：

- `PipelineTemplate`：整条流水线的骨架。
- `PipelineStage`：单个阶段，其中可以再嵌 `subStages`。

加载失败的常见原因有三类：键名拼错、缩进不对（本体系统一 2 空格）、必填项缺失。报错信息会带上文件名和出问题的键，照提示改即可。

## 3. 顶层字段表

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 模板名，与文件名保持一致，用小写加连字符，例如 `talking-head`。 |
| `version` | 是 | 版本号，字符串形式，例如 `"1.0"`。改动阶段结构时记得往上加。 |
| `description` | 是 | 一句话说清这条流水线是干什么的、大致分几段。 |
| `category` | 是 | 归类标签，方便按用途筛模板，例如 `cinematic`、`explainer`。 |
| `stages` | 是 | 阶段列表，顺序即执行顺序，数量控制在 6 到 10 之间。 |

## 4. stage 字段表

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 阶段名，小写下划线，例如 `scene_plan`。 |
| `produces` | 是 | 本阶段产出的产物名列表，用方括号写，例如 `[script]`。 |
| `requiredArtifactsIn` | 是 | 进本阶段前必须已经存在的产物列表；第一个阶段写 `[]`。 |
| `checkpointRequired` | 是 | 本阶段结束时是否要落一个检查点，通常为 `true`。 |
| `humanApprovalDefault` | 是 | 默认是否需要人工点头才能往下走。 |
| `reviewFocus` | 是 | 审阅时要盯的几个点，至少 3 条。 |
| `successCriteria` | 是 | 判定本阶段算不算过关的标准，至少 2 条。 |
| `subStages` | 否 | 条件触发的子阶段，没有就不写这个键。 |

## 5. subStage 字段表

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 子阶段名，小写下划线。 |
| `description` | 是 | 一句话说明这个子阶段干什么、什么时候值得做。 |
| `condition` | 是 | 触发条件，用大白话写清楚，例如「存在参考视频」。 |
| `humanApprovalDefault` | 是 | 子阶段默认是否需要人工确认。 |
| `reviewFocus` | 是 | 审阅要点，至少 3 条。 |

## 6. 编写规范

**阶段数量**：一条流水线的 `stages` 不少于 6 个、不多于 10 个。少于 6 个说明拆得不够细，审阅点会挤在一起；多于 10 个说明拆过头了，维护成本上去了，实际执行时也会来回跳。

**条目数量**：每个 stage 的 `reviewFocus` 至少 3 条，`successCriteria` 至少 2 条。子阶段的 `reviewFocus` 同样至少 3 条。写不满就说明这个阶段还没想清楚要盯什么，先想清楚再写。

**文案要求**：

- 用大白话写，像跟同事交代事情那样写。能说「这条素材有没有授权」就不要写「知识产权合规性评估」。
- 每条只讲一件事，不要一句话里塞三个要求。
- 能落到具体数字、具体文件、具体动作的就落下去，别停在形容词上。
- 不要写空话套话，不要为了凑条数把一句话拆成三条。

**禁用词表**（出现即打回）：

- 英文宣传腔：`Unleash`、`Empower`、`Seamless`、`Next-generation`。
- 中文四字空话：极致体验、赋能未来，以及同类为了好听而写的四字短语。
- 任何 emoji、图标、装饰性符号。
- 任何照搬外部项目英文原文的整句。

**格式要求**：缩进统一 2 空格。顶层键只允许 `name`、`version`、`description`、`category`、`stages`；stage 键只允许 `name`、`produces`、`requiredArtifactsIn`、`checkpointRequired`、`humanApprovalDefault`、`reviewFocus`、`successCriteria`、`subStages`；subStage 键只允许 `name`、`description`、`condition`、`humanApprovalDefault`、`reviewFocus`。多一个键 Loader 就会报错。

## 7. 新增模板流程

1. 从 `src/main/resources/pipeline-templates/` 里挑一个最接近的现有模板，整份复制一份。
2. 把文件名改成新模板名，同时改文件里的 `name` 字段，两者保持一致。
3. 改 `description` 和 `category`，一句话说清这条流水线服务什么场景。
4. 逐个调 stage：该删的删、该加的加、该换顺序的换顺序，把 `produces` 和 `requiredArtifactsIn` 前后对齐，别出现「进来要的东西上游没产出」这种情况。
5. 重写每个 stage 的 `reviewFocus` 和 `successCriteria`，别直接沿用旧模板的措辞，要贴着新场景写。
6. 需要条件子阶段的，在对应 stage 下加 `subStages`。
7. 跑 `PipelineTemplateLoaderTest`，确认能正常加载、字段没写错、条目数量达标。测试不过就照着报错改，改完再跑一遍。

## 8. 与 OpenMontage 方案的差异说明

我们借的是它的思路——按阶段切流程、设检查点、留人工审批门、审阅要点和过关标准分成两份清单、用条件子阶段处理分支情况，以及给编排留预算约束的意识；格式、字段命名和全部中文文案都是我们自己定的，没有搬运它的任何原文。

## 9. 许可证合规声明

OpenMontage 采用 AGPL-3.0 许可。本项目只借鉴其设计思想，不复制、不翻译、不改编其代码与文档文本。所有 YAML 结构、字段命名、中文说明均为独立创作。若后续需要引入其任何具体实现，须先经过许可证评审并履行 AGPL-3.0 相应义务。