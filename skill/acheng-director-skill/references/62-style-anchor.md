# 62｜STYLE MOTHER 风格锚定合同

## 目的与边界

动画资产不应分别猜测画风。任何多资产或完整制作任务默认要求 `style_policy: required`：先制作并人工批准一张受控的 `STYLE_MOTHER` 风格参考图，再制作角色、场景、道具、特效和关键帧。它是视觉渲染语言的锚，不是故事海报、角色设定图或场景母图。只有用户明确声明不要求跨资产风格一致时，才可使用 `style_policy: waived`；历史夹具必须显式使用 `legacy_unlocked` 和理由。

STYLE MOTHER 应包含一个不带剧情身份的通用主体（例如无脸中性模型或抽象人体比例体）、简单环境、一个代表性材料／道具和目标媒介。画面要能验收线条边缘、阴影分层、色板逻辑、材质响应、背景抽象、空气透视、轮廓可读性和动画关节可动性；禁止文字、标志、水印、网格、故事专属角色、复杂叙事构图、可识别脸部、品牌和场景地标。它必须有足够的主体、材质和空间层次来代表目标画风，但不能携带会污染后续身份、构图、动作或故事状态的内容。

必要时可追加两个探针，但不能替代母版：

- `STYLE_CHARACTER_PROBE`：通用头部、躯干和手部，验证脸部线条、皮肤／衣料分离与关节可读性；
- `STYLE_ENVIRONMENT_PROBE`：无角色环境与代表性材质，验证透视、景深、主光和背景细节衰减；
- `STYLE_EFFECT_PROBE`：只有视效占主导的项目才增加，验证粒子、辉光、烟尘和遮挡不吞掉动作轮廓。

不要用主角四视图、英雄海报、复杂分镜、情绪板或单张剧情关键帧作为唯一风格参考。它们会把身份、构图、几何或故事光线误传给所有资产。

## 数据合同

项目根可声明：

```json
{
  "style_lock": {
    "anchor_asset_id": "STYLE_MOTHER",
    "anchor_version": "v1",
    "status": "planned",
    "medium": "2d_cel",
    "preserve_scope": ["clean line weight", "flat cel shadow hierarchy", "warm-cool palette separation", "matte material response"],
    "exclude_scope": ["character identity", "face and body proportions", "scene layout", "pose and action", "exact light direction", "text and logo"],
    "apply_to_kinds": ["character", "costume", "injury", "scene", "prop", "vehicle", "keyframe", "effect"],
    "approved_file": null,
    "approved_sha256": null
  }
}
```

## 低污染 STYLE_MOTHER 提示词模板

```text
Create one clean style reference image for an animation production pipeline, not a story image and not a character design sheet. Show one neutral faceless mannequin-like subject with simple joints on a plain unbranded studio ground, plus one small material sample that represents the project's main surface response. Use the target medium: [2D cel / 3D cinematic / stop-motion / ink / other]. Demonstrate [line edge behavior], [shadow hierarchy], [palette roles], [surface response], [background abstraction], [air perspective] and [silhouette readability] with one broad motivated key light and restrained fill. Keep the composition quiet and centered so the rendering language can be judged clearly. No recognizable face, no named character, no costume identity, no story prop, no location landmark, no text, no logo, no watermark, no grid, no panel labels, no dramatic action, no complex narrative lighting, no branded object, no decorative visual noise.
```

把这张图登记为 `STYLE_MOTHER`。**在纯提示词交付模式下，直接一次性输出全套高保真提示词交付包**：`STYLE_MOTHER.image.txt` 作为所有适用角色、场景、道具、特效和关键帧资产的强制风格参考槽位（通常为 Reference image 1 或最后一个槽位）。所有依赖它的提示词正文必须显式包含风格锚定指令（只继承媒介、线条、阴影、材质响应与色调，排除身份、构图与动作）。智能体不发起模型生图，真实出图由用户在外部完成。

`STYLE_MOTHER` 必须是 `asset_plan` 中 `kind: style` 的节点，拥有同一版本和一个资产卡；锚点卡使用 `recipe: style`。`planned` 只表示风格参考图提示词已经准备好，不能证明图像存在；`approved` 必须有真实文件和匹配 SHA-256。批准后，所有 `apply_to_kinds` 内的资产节点都把该锚点列入 `depends_on`，资产卡以最后一个上传槽位登记 `role: style` 的参考图；角色身份、场景几何和构图参考仍各自保留，不能让风格图取代它们。未批准锚点时，依赖资产只能交草案，不能标 `READY_TO_SUBMIT`。

## 权威优先级

1. 身份参考决定脸、身体、服装和道具事实；
2. 场景参考决定几何、地标、入口和遮挡；
3. 当前 ShotSpec 决定姿态、动作、机位、状态和精确光向；
4. STYLE MOTHER 只决定媒介、线条、阴影、色板、材质、背景抽象和空气深度。

风格锚定不能覆盖角色身份、场景拓扑、相机布局、动作方向、状态损伤、道具所有权或故事中的精确光位。参考清单必须写明保留与排除范围；缺少批准锚点时只能交风格资产草案和缺图依赖，不能把后续资产标记为 ready。

## 接受门

批准前逐项核对：无可见文字／标志／水印／网格；线宽、边缘软硬、阴影级数和高光滚降在主体、环境和代表性材料上稳定；远近细节有明确衰减；轮廓、手脚和关节在动画尺寸下可读；没有剧情身份、场景地标或英雄构图污染。机器门只检查字段、版本、文件和哈希；最终画风是否统一仍需生成图组的并排人工验收。

4.3.8连接校验：required 策略下，apply_to_kinds 必须覆盖当前实际计划/卡片中的适用类型，不能靠漏填 keyframe 或 scene 规避风格参考。style_lock 与锚点节点的批准状态、版本、文件路径和SHA-256必须一致。每个适用资产有且只有一个指定母版/版本的风格引用，位于最后槽位；正文编译也检查该引用，不能只写“使用最后一张风格图”而没有真实槽位。上传助手随后将这同一文件复制到交付包，并把编号、用途、保留/排除范围写入该资产的独立上传卡。
