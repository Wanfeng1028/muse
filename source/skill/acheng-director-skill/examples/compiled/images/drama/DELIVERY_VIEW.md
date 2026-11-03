# 资产交付总览

这是给人阅读的导航页；模型只接收各资产 `.image.txt` 或 `.draft.txt` 的完整正文。

## 总控台

资产数量：1
可提交提示词：1
待参考图草案：0
状态：已编译但未调用图像模型。真实身份一致性、画面质量和文字伪影仍需生图后人工检查。

## 资产目录

| 资产 | 类型 | 状态 | 参考图 | 用途 |
|---|---|---|---|---|
| 受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手 | asset | ready-to-submit-not-generated | 无需参考图 | Create one opening keyframe before the exchange. |

## 逐项交付

### 受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手

用途：Create one opening keyframe before the exchange.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：无需参考图；这是单项独立资产，按完整正文生成。

参考图上传助手：无需上传参考图；可直接复制完整提示词生成。

#### 复制：受伤的陆川一开始仍攥着钥匙；岑禾没有抢夺，只留出接收的手（完整正文）

完整文件：[下载/打开 ASSET_02_DRAMA.image.txt](ASSET_02_DRAMA.image.txt)

```text
Lu Chuan is a 34-year-old man, 1.80 meters tall, with balanced adult proportions, naturally broad shoulders, a square jaw, short dark hair and a short scar above his right eyebrow. He wears a gray woven work jacket over a gray shirt and a functional waist belt. Cen He is a 32-year-old woman, 1.70 meters tall, with a lean adult build, oval face, dark almond-shaped eyes and dark hair tied low behind her head. She wears an olive canvas coat over a cream work shirt and dark straight trousers. Create one live-action medium-close two-person keyframe in the maintenance room. Lu Chuan, an adult man with a short scar above his right eyebrow and a gray woven work jacket, sits on the left; his bandaged right wrist rests on the desk, and his left hand holds one brass key. Cen He, an adult woman with tied dark hair and an olive coat, sits on the right with an empty palm held between them. Capture the single moment before Lu releases the key. Use a 65 mm equivalent lens from the south side, showing eyes, shoulders and both hands together. One east window casts soft directional light across their cheek planes; a weak wall reflection leaves the shadow side readable. Skin has broad soft highlights, cloth folds retain fibrous edges only near the hands, and the brass key catches a narrow highlight. The rear wall and key hook remain quiet low-frequency shapes. Preserve identity, hand ownership, the bandage and the room geometry. Avoid waxy faces, extra hands and ghost texture.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

