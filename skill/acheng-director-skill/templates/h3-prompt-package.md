# H3 完整生产包模板用法

直接复制 [机甲完整数据](../examples/01-mecha.production.json) 或 [文戏完整数据](../examples/02-drama.production.json)，保持图片相对路径有效。前者演示全参考六字段与16格，后者演示总时长20秒分成两个10秒基础三字段切片。

先按用户项目更新 brief、登记簿、镜头、事件和资产，再运行 audit_storyboard_quality.py。通过后运行 compile_h3.py 获取每个 Segment 的完整 `.h3.txt`。不能仅把示例人物名字替换就交付新剧情。

角色／场景prompt_description和每镜state_description须用完整描述，内部ID只留管理字段。每段必须重新带上独立定义；每个 Segment 显式写 `mode_lock` 与 `mode_selection_reason`。有真实参考资产时优先 Ref2VA，其 `detailed_description` 按时长与复杂度动态计算最低词数（默认 10 秒段为 2,000）和目标词数（默认约 2,400） 个英文词，极限值 2900 词硬性封顶（处于 2200-2900 词区间，剔除无上限输出）；达到宿主上限时按字段／镜头续写。同时交付UPLOAD.md及真实素材。见[独立提示词合同](../references/72-standalone-prompt-delivery.md)。

卡片顺序：作品与本段范围 → 素材路径和职责 → 已确认首尾状态 → 各Shot摄影／表演／动作 → 宫格映射 → 分模式完整提示词 → 场记差量 → 机器及实测验收。负向约束不添加未经指南支持的第七字段。
