# 知识卡契约

卡片把资料变成“何时用、怎样做、为什么、到哪里停止”，不是无限缩短的摘要。
类型可以是 method / workflow / interaction_pattern / claim / resource。
仅介绍工具的片段可建 resource；未经验证的营销指标只能建有归属和限制的 claim。

输入示例（segment/frame ID 必须换成当前 job 实际存在的值）：

```json
{
  "cards": [{
    "id": "validate-before-building",
    "title": "实现前验证想法",
    "kind": "workflow",
    "when_to_use": "准备投入实现，但问题与目标尚未明确",
    "retrieval_terms": "开发 想法 验证 需求 方向",
    "steps": ["确认原始问题与目标", "检查关键假设", "对齐后再实现"],
    "rationale": "步骤与理由须来自当前资料；整理者推论须标明",
    "limits": ["示例结构，不是已经验证的真实视频内容"],
    "evidence": {"segment_ids": [1, 2], "frame_ids": ["f-0001"]}
  }]
}
```

脚本自动绑定来源 URL、平台、视频身份、scope、时间、SRT片段、帧时间、证据 hash。
默认 needs_review。阶段通过只证明引用可回查，不表示作者结论在现实情境有效。
没有语音的视觉卡可以只引用帧；文字建议至少引用对应 SRT，涉及视觉参数时同时引用清晰画面。
用 source/frame/segment 证据判断，不能为了通过契约而随意挂无关编号。

写卡前先建立论证：问题 → 作者观察 → 干扰或错误做法 → 判断依据 → 行动 → 结果/限制。
未出现的环节留空缺，不把 Agent 的补充当作者原话。翻译、ASR校正另说明画面或上下文依据。
应用时回答“本情境哪一步适用、哪些约束仍缺证据”，而不复述一整张卡。
