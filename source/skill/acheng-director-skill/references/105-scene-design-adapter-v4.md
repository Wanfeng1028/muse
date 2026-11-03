# 105｜场景设计专业支路与 Acheng 适配合同

## 定位

`scene-concept-art-director` 是场景设计专业支路，不是 Acheng 的第二套导演、调度器、资产真值或提示词总编译器。它把 brief、已确认的 `moodboard-alignment/data.json`、现有场景参考和生产事实转换为 `scene_art_direction.json`、独立图像提示词、参考上传清单和 QA 回执。

它可以作为 assets 之前的设计节点，也可以在已有场景资产上执行 repair、multi_view 或 critique。默认只做 plan/prompt；不调用付费图像、视频或音频模型，不声称真实媒体已经生成。

## 触发条件

只在请求明确包含以下任一条件时追加 `scene-design` 节点：

- `intent` 为 `scene`、`scene-design`、`environment`、`concept-art` 或 `moodboard-to-scene`；
- `features` 包含 `scene`、`scene-design`、`environment`、`concept-art` 或 `moodboard`；
- 用户明确要求场景概念图、场景美术、环境设定、背景板、场景修复或多视图场景包。

没有这些条件时，不强制读取场景支路，不把每个项目变成场景概念图任务。

## 输入与输出

输入按优先级读取：当前用户修订 → 已确认剧本/场景登记 → 已确认 moodboard → 当前资产与镜头需求 → 视觉默认。moodboard 只提供已确认的摘要、色板、构图、风格和节点方向；它的图像不是自动的 STYLE_MOTHER。

回包至少包含：

```json
{
  "request_id": "...",
  "input_revision": "sha256",
  "module": "scene-design",
  "owner": "assets",
  "status": "READY|NEEDS_DIRECTOR_REVISION|EXECUTION_BLOCKED",
  "attempt": 1,
  "artifact": {
    "path": "scene_art_direction.json",
    "sha256": "...",
    "prompt_status": "DRAFT|DRAFT_MISSING_REFERENCES|READY_TO_SUBMIT|BLOCKED",
    "visual_status": "UNVERIFIED"
  },
  "advisory_patch": [],
  "evidence": [],
  "unresolved": []
}
```

`advisory_patch` 的 `write_paths` 必须为空。场景支路不直接替换 `production.json`、`scene_registry`、`shots`、`segments` 或 `ledger`。

## 权属与相邻协作

| 生产事实 | 场景支路 | 最终写入者 |
|---|---|---|
| 场景 thesis、空间语法、入口/出口、地标、材质、使用痕迹、场景参考关系 | 提议并附来源、保留/排除、未知项 | `assets` / 主导演合并到 `scene_registry` 与 `asset_cards` |
| 镜头景别、机位、运动、帧区间、切镜 | 只给构图意图和不可破坏的空间约束 | `shots` |
| VFX、破坏、巨构尺度证据 | 只给材料/空气/遮挡后果 | `effects` |
| H3 独立正文 | 提供完整场景描述输入 | `model` |
| 破坏等级、天气状态、跨场景继承 | 提供可见状态假设和 unresolved | `continuity` |

冲突必须记录 `adopted/rejected/reason/source`。已确认生产事实优先于场景支路审美建议。

## 长输出与交付门

长输出提交 partial artifact 并保存 `current_cursor`；partial 不能 accepted。`READY_TO_SUBMIT` 只代表独立提示词和必需输入齐全，`visual_status` 仍保持 `UNVERIFIED`。真实图像的身份一致性、空间可信度、文化准确性、材质、光线和艺术质量必须单独人工验收。

## 读取路径

- 外部专业 skill：`scene-concept-art-director/SKILL.md` 与其 `references/scene-contract-v1.md`、`model-adapters.md`、`multi-view-continuity.md`、`acheng-handoff.md`。
- Acheng 资产合同：`references/61-asset-dependency-production.md`、`references/72-standalone-prompt-delivery.md`、`references/62-style-anchor.md`。
- 协作合同：`references/91-module-orchestration.md`、`data/module-registry.json`、`data/red-monkey-integrations.json`。
