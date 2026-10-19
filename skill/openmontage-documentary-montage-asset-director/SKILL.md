---
name: openmontage-documentary-montage-asset-director
version: "1.0.0"
description: 为纪录片蒙太奇分镜逐个槽位采集匹配素材并生成 asset_manifest，支持直接多源搜索快速路径与 CLIP 语料库检索标准路径，适用于成片前的素材装配阶段。
metadata:
  license: AGPL-3.0
---

# 素材总监 · 纪录片蒙太奇流水线

## 适用时机

分镜表已经就绪，接下来要把每个槽位填上真实的视频片段。有两条路可走。

### 快速路径：直接搜索（按幕制作时推荐）

1. 调用 `direct_clip_search`，把查询广播到所有可用素材源，每个查询下载 2-3 条片段。无需 CLIP 嵌入、无需语料索引、无需 .npy 文件。
2. 查看自动抽出的缩略图（可交给子代理读图），核对画面与槽位描述是否吻合。
3. 人工把最合适的片段指派给对应槽位。

适合场景：逐幕推进、幕间需要用户确认、单幕槽位数少于 30、需要快速迭代。

### 标准路径：语料库 + CLIP 检索

1. 把分镜导演给出的查询广播到所有素材源（Pexels、Pixabay Video、Coverr、Mixkit、Archive.org、NARA、国会图书馆、Pond5 PD、Videvo、NASA、ESA、JAXA、NOAA、Dareful、Wikimedia、Unsplash），下载并建立嵌入索引。
2. 对每个槽位，用其描述在语料库上跑 CLIP 检索，选出最佳一条。

适合场景：50 个槽位以上的大型制作、需要自动化多样性、需要按 CLIP 相似度排序填充。

### 跨幕复用

按幕制作时，前几幕已下载的片段往往能填后续幕的槽位。把代理指向既有目录，优先复用与新槽位描述相符的片段。实测可节省 40-50% 的下载耗时。

### 并行作业

`direct_clip_search` 在后台跑的同时，可以并行生成旁白 TTS、搭建混音、制作字幕、搜索音乐。整体制作时间会明显缩短。

### 回退策略

快速路径下某些槽位画面不匹配时，只对这些槽位改用 `corpus_builder` + `clip_search`。两种方式可以混用。

最终产出是一份 `asset_manifest`：每个槽位恰好对应一条片段，并附带完整来源信息。

## 前置依赖

| 层 | 资源 | 用途 |
|----|------|------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | 产物校验 |
| 前置产物 | `state.artifacts["scene_plan"]["scene_plan"]` | 槽位描述、查询、偏好素材源 |
| 前置产物 | `state.artifacts["idea"]["brief"]` | `era_mix`、`sources_allowed`、`music_plan` |
| 工具（快速路径） | `direct_clip_search` | 轻量级多源搜索与下载 |
| 工具（标准路径） | `corpus_builder` | 建立带 CLIP 嵌入的检索索引 |
| 工具（标准路径） | `clip_search` | 按槽位描述排序候选片段 |
| 工具（可选） | `music_gen`、用户的 `music_library/` | 配乐床 |

## 心智模型

语料库不是素材库，而是代理按需构建的检索索引。你不去翻它，而是去查询它。由此得出三条规则：

1. **先建库再挑选。** 若语料库中没有该槽位查询族对应的候选，就不要调 `clip_search.rank_for_slot`，否则排序结果是垃圾，槽位白白浪费。
2. **只增不换。** 语料库是追加式的。某槽位检索效果差，就补查询再扩充，不要推倒重来。
3. **按槽位挑，不按片段挑。** 一条片段在成片中只属于一个槽位。用 `exclude_ids` 防止重复使用。

## 儿童/童话类内容：素材源覆盖规则

当分镜计划的 `metadata.tone` 或 `metadata.target_audience` 显示是儿童内容（童话、睡前故事、少儿科普、动画故事）时，**覆盖常规素材源路由**，只从 Pixabay Video 获取。

### 为什么只用 Pixabay Video

Pixabay 社区里有大量由 Midjourney / Stable Diffusion 视频工作流产出的 AI 奇幻动画素材——发光森林、魔法景观、奇幻生物。在吸引儿童方面，这类素材远超实拍画面，其他免费源在这个风格上没有同等深度。

### 采集规则

1. **源锁定。** 所有查询的 `sources` 一律设为 `["pixabay_video"]`。不要把实拍源（Pexels、Dareful 等）与奇幻片段混用，风格冲突会破坏儿童的沉浸感。
2. **查询改写。** 分镜导演通常已把槽位描述改写成奇幻风格。若需要自写兜底查询，前置奇幻关键词：`fairy tale`、`fantasy`、`enchanted`、`magical`、`glowing`、`dreamy`、`mystical`、`fairy`、`enchanted forest`、`magical world`。示例：槽位需要"叶子上的毛毛虫"，查询写成 `"fairy tale caterpillar magical forest glowing"`。
3. **视觉一致性检查。** 下载后逐一确认所有片段都是 AI 奇幻美学。哪怕是 CLIP 分数更高的实拍片段，也必须拒收。一条实拍片段就能打破整段魔法氛围。
4. **兜底。** Pixabay 返回空结果时，换奇幻关键词再试，每个槽位最多重写两次。仍为空则上报用户，不要悄悄换成实拍素材。

## 流程 · 快速路径（直接搜索）

适用于逐幕推进、幕间需人工确认，或总槽位数不超过约 30 的情况。

### F1. 后台启动 `direct_clip_search`

边搜边并行处理旁白、音频、字幕：

```python
direct_clip_search.execute({
    "output_dir": "projects/<name>/assets/video/raw_act2",
    "queries": [
        {"query": "cesium atomic clock laboratory", "slot_id": "slot_01"},
        {"query": "laser beam laboratory optics",   "slot_id": "slot_02"},
        {"query": "satellite dish night sky",        "slot_id": "slot_03"},
        # ... 每个槽位一条
    ],
    "sources": ["pexels", "pixabay_video", "coverr", "mixkit", "archive_org"],  # 省略则搜索所有可用源
    "clips_per_query": 3,
    "filters": {
        "min_duration": 3,
        "max_duration": 40,
        "orientation": "landscape",
        "min_width": 1280,
    },
})
```
上例为第二幕每个槽位发起一条查询、每查询下载 3 条候选；`filters` 用于过滤时长、朝向与分辨率。

关键参数：

- `clips_per_query=3` 是最佳平衡点，既有选择余地又下载够快。
- 省略 `sources` 会自动搜索所有可用源。
- `skip_existing=true`（默认）在重试时避免重复下载。

### F2. 查看缩略图

浏览 `<output_dir>/thumbnails/` 逐一核对；必要时用子代理读图确认。每个槽位从下载集合中挑出最匹配的一条。

### F3. 跨幕复用

处理第 2-5 幕时，先检查前几幕的片段再决定是否新下载。常见的主题重叠包括：实验室镜头（显微镜、激光、科研人员）、科技镜头（服务器、卫星、电路）、自然/抽象镜头（山脉、太空、延时）。

把代理指向先前各幕的目录，先把已有片段映射到新槽位，再考虑新搜索。

### F4. 定点补缺

初次搜索后仍无合适匹配的槽位，按顺序处理：

1. 重写查询（换成更具体的名词、不同措辞）。
2. 只针对这些查询再跑一次 `direct_clip_search`。
3. 仍无匹配，就仅对这些槽位回退到 `corpus_builder` + `clip_search`。

### F5. 记录 asset_manifest

格式与标准路径第 9 步相同，只是 `source_tool` 填 `"direct_clip_search"`。

---

## 流程 · 标准路径（语料库 + CLIP 检索）

适用于 50 槽位以上的大型制作、需要自动 CLIP 排序、或快速路径匹配不佳的情况。

### 1. 确定语料库目录

约定放在 `projects/<project-name>/corpus/`。所有 `corpus_builder` 与 `clip_search` 调用共用同一个 `corpus_dir`。语料库可跨次运行复用——分镜导演后续加槽位时，扩充既有库即可，不必重建。

### 2. 把查询广播给 `corpus_builder`

读取 `scene_plan.metadata.slots[]`，收集所有槽位的 `queries[]`，去重，并按 `preferred_sources` 分组。按素材源集合分别调用：

```python
corpus_builder.execute({
    "corpus_dir": "projects/<name>/corpus",
    "queries": [
        {"query": "raindrop on asphalt slow motion", "kind": "video", "per_source": 8},
        {"query": "wet city street night neon",       "kind": "video", "per_source": 8},
        {"query": "taxi heavy rain yellow",           "kind": "video", "per_source": 6},
        # ... 每条唯一槽位查询一条
    ],
    "sources": ["pexels", "archive_org", "wikimedia"],   # 取自 preferred_sources 并集
    "filters": {
        "min_duration": 3,
        "max_duration": 40,
        "orientation": "landscape",
        "min_width": 1280,
    },
    "max_new_clips": 150,
    "thumbs_per_video": 5,
})
```
该调用把一组去重查询广播到指定源，每个查询每源取若干候选，并限制新增片段总量与抽帧数量。

广播规则：

- 若 brief 指定了某素材源而 `corpus_builder.source_provider_menu` 显示该源不可用，立刻停下并上报，不要悄悄降级到其余源。
- 语料库规模按槽位数的 8-12 倍预算。15 槽位的蒙太奇应有约 150 条候选，检索才有真正的选择空间。
- 每查询每源 `per_source` 取 4-8 通常够用，推到 20+ 主要增加噪声。
- `era_mix = "vintage"` 时，单独跑一批限制在 `["archive_org"]` 且查询符合年代的广播。Prelinger 搜索慢，不要与现代 Pexels 批次交错。
- 任一槽位的 `preferred_sources` 含 `nasa`，就跑一小批 nasa 专用批次。NASA 慢且结果冷门。
- `unsplash` 只有图片，只能作辅助源，不能当运动为主的纪录片剪接主干。

### 3. 检索前先做语料库体检

在花 token 排序前，先调 `clip_search` 的 `operation=stats`：

```python
clip_search.execute({
    "operation": "stats",
    "corpus_dir": "projects/<name>/corpus",
})
```
该调用读取语料库统计信息，用于判断规模、来源分布与运动强度是否健康。

看 `rows`、`per_source`、`per_kind`、`mean_motion_score`，排查三种失败模式：

- `rows < 50`：库太小，扩充。
- `per_source` 严重偏斜（如 98% pexels、2% archive_org）而 brief 是复古题材：补一批 archive_org。
- `mean_motion_score < 1.0`：库里全是静态片段，成片会像幻灯片。换查询重跑，或在排序时加 `motion_min`。

### 4. 逐槽位排序候选

对 `scene_plan.metadata.slots[]` 中每个槽位调用 `operation=rank_for_slot`：

```python
clip_search.execute({
    "operation": "rank_for_slot",
    "corpus_dir": "projects/<name>/corpus",
    "query_text": slot["description"],      # 用 description，不要用 queries
    "k": 30 if slot.get("hero") else 12,
    "tag_weight": 0.3,
    "motion_min": 1.5,
    "kind": "video",
    "exclude_ids": already_picked_ids,
})
```
该调用用槽位描述作为文本查询，在语料库中排序候选，同时排除已锁定片段并过滤低运动素材。

要点：

- 用槽位的 **description**，不是 queries。描述是分镜导演写的富含名词与形容词的语义文本，CLIP 排序效果更好。
- `tag_weight=0.3` 是视觉嵌入（70%）与源标签嵌入（30%）的混合。Pexels URL 标签强而视觉通道噪声大时提到 0.5；Prelinger 这种长散文式标签降到 0.15。
- 每次都要传 `exclude_ids`，把已锁定片段全带上，避免同一把"钥匙开门"的镜头赢下两个槽位。

### 5. 用判断挑选，不要只看分数

排名第一未必是对的。看前 3-5 条，逐一评估：

- **年代匹配。** 2022 年的 4K Pexels 镜头放进关于家的挽歌式清单蒙太奇里合适吗？也许，也许不。
- **运动匹配。** 分镜导演给出的调性表会决定镜头保持时长。若目标保持 4.0 秒而片段只有 2 秒且带快速甩镜，就撑不住。
- **构图衔接。** 这条片段与相邻槽位已选的片段放一起是否成立？如果 slot_02 是雨中屋顶远景，slot_03 的首选也是雨中屋顶远景，那就选第二顺位。
- **情绪调性。** CLIP 会把"夜晚空荡人行道"匹配到明亮的拉斯维加斯霓虹剪辑。挽歌式 brief 下霓虹镜头是错的。0.42 的分数压不过调性。

CLIP ViT-B/32 余弦分数的经验阈值：

- `>= 0.30`：强匹配，通常可用。
- `0.22-0.30`：可能可用，需要人工判断。
- `< 0.22`：语料库里没有你需要的东西。扩充，不要硬挑。

### 6. 检索效果弱时扩充语料库

若某槽位最高分低于 0.22，不要从烂中挑最不烂的。按顺序：

1. 重写该槽位的查询——可能过于抽象，或词汇与年代不符。
2. 只针对这一个槽位的新查询再跑一次 `corpus_builder.execute(...)`。构建器会跳过已入索引的片段，代价很低。
3. 重新排序。

每个槽位最多扩充两轮。三轮后仍拿不到 0.22 以上，就告知创意总监：该槽位在开放素材源中不可实现，建议弃用或让用户自备素材。

### 7. 相邻片段去重

每个槽位有一条候选后，按时间线顺序得到一串 clip_id。相邻画面重复会毁掉剪辑。对整个列表跑 `clip_search.diversify`：

```python
clip_search.execute({
    "operation": "diversify",
    "corpus_dir": "projects/<name>/corpus",
    "candidate_ids": picked_ids_in_timeline_order,
    "n": len(picked_ids_in_timeline_order),
    "diversity": 0.5,
})
```
该调用按时间线顺序检查候选列表的视觉多样性，必要时剔除冗余片段。

若 `diversify` 丢掉了某条片段，说明你的两个选择视觉上几乎一致。对片段被丢掉的槽位重新排序，把幸存的"孪生兄弟"放进 `exclude_ids`。

### 8. 处理音乐计划

读 `brief.music_plan`，严格照创意总监记录的计划执行，不要自创来源：

- **`source=library`**：确认 `music_plan.path` 文件存在，在 manifest 中记为 `type=music`、`subtype=library`。
- **`source=user`**：同上，`subtype=provided`。
- **`source=generated`**：用 brief 中的种子提示词调用指定的音乐工具。先试听单条，确认情绪后再批量。记录提供方与成本。
- **`source=none`**：不要生成静音，也不要因为剪辑显得单薄就塞一条曲目。用户批准了"无音乐"，就无音乐运行。

**此阶段绝不切换音乐来源。** 这属于决策沟通契约违规——更换音乐模式是重大制作变更，必须在提案阶段获得用户批准。

### 9. 记录 asset_manifest

每个槽位产出一条 asset，按规范 schema 输出。纪录片蒙太奇特有字段放在 `metadata` 下：

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "asset_slot_01",
      "type": "video",
      "path": "projects/<name>/corpus/clips/pexels_12345/video.mp4",
      "source_tool": "corpus_builder",
      "scene_id": "slot_01",
      "duration_seconds": 7.2,
      "resolution": "1920x1080",
      "format": "mp4",
      "provider": "pexels",
      "license": "Pexels License (free, no attribution required)",
      "original_url": "https://www.pexels.com/video/12345",
      "subtype": "stock",
      "generation_summary": "Retrieved via CLIP rank for slot 'raindrop on asphalt slow motion...'. Score 0.38."
    },
    {
      "id": "asset_music_bed",
      "type": "music",
      "path": "music_library/dawn_04.mp3",
      "source_tool": "music_library",
      "scene_id": "global",
      "subtype": "library",
      "license": "user-provided"
    }
  ],
  "metadata": {
    "pipeline": "documentary-montage",
    "corpus_dir": "projects/<name>/corpus",
    "corpus_stats": { "rows": 157, "per_source": {"pexels": 98, "archive_org": 52, "nasa": 7} },
    "rejected_picks": [
      {
        "slot_id": "slot_03",
        "clip_id": "pexels_99921",
        "score": 0.41,
        "reason": "wrong era — 2022 4K kitchen, brief is vintage"
      }
    ]
  }
}
```
上例给出每条视频素材的完整溯源字段（路径、来源工具、时长、分辨率、提供方、许可证、原始 URL），以及 music 条目和 metadata 中的语料库统计与拒收记录。

`rejected_picks` 日志很关键。剪辑总监觉得某条选择不对时，会读它去找第二顺位。

### 10. 质量门

- 分镜计划中每个槽位恰好映射到一条 asset。
- 每条被选片段的 `score >= 0.22`（记录在 rejected-picks 日志中），或有"用户批准覆盖"的备注。
- 没有任何 clip_id 同时作为两个槽位的首选。
- 最终列表跑 `diversify` 无残留（无丢片，或丢片已全部补位）。
- `corpus_stats` 的行数至少是槽位数的 8 倍。
- 音乐 asset 存在，或 `music_plan.source = "none"` 且有显式确认。
- 复古 brief 下，至少 60% 的选择来自 `archive_org`。
- 所有文件路径可解析。

## 常见坑

- **对空语料库跑 `clip_search.rank_for_slot`。** 会拿到空 `results` 或奇怪的形状报错。建库后先 `stats` 再排序。
- **只看分数挑选。** 分数是判断的输入，不是判断本身。挽歌式作品塞满高分的 Pexels 高清阳光镜头，无论分数多高都会不对味。
- **忘记 `exclude_ids`。** 没有它，同一个绝佳片段会赢下所有槽位，蒙太奇变成一张图的幻灯片。
- **悄悄替换音乐。** 用户说了"不要音乐"，代理觉得"剪辑太单薄"还是生成了。这是重大变更，需要批准——参见 `skills/pipelines/documentary-montage/executive-producer.md` 的跨阶段规则。
- **无限扩充语料库。** 每个弱槽位最多两轮扩充。再多说明开放素材源里大概确实没有，槽位本身需要改。
- **把槽位查询当排序文本用。** queries 是给素材 API 的搜索短语，descriptions 是给 CLIP 的语义文本。两者不同，排序要用 descriptions。
- **丢失溯源信息。** 每条片段都必须在 manifest 里带 `provider`、`original_url`、`license`。这是下游任何发布环节的硬要求。

## 检索配方

几个常用检索动作：

### "找到我喜欢这条片段的 N 个变体"

```python
clip_search.execute({
    "operation": "find_similar_set",
    "corpus_dir": "projects/<name>/corpus",
    "seed_clip_id": "pexels_12345",
    "n": 5,
    "diversity": 0.4,
    "candidate_pool": 40,
})
```
该调用以一条种子片段为基准，在语料库中找若干风格相近但不重复的候选。

用于某槽位需要"再找五条类似的镜头"，比如一组同调性的门口镜头。

### "我有 20 条候选，裁到 8 条不重复的"

```python
clip_search.execute({
    "operation": "diversify",
    "corpus_dir": "projects/<name>/corpus",
    "candidate_ids": [...],
    "n": 8,
    "diversity": 0.5,
})
```
该调用在候选集合中去重，输出指定数量的多样片段。

### "查一条片段的完整元数据"

```python
clip_search.execute({
    "operation": "get",
    "corpus_dir": "projects/<name>/corpus",
    "clip_id": "archive_org_Prelinger_HomeMovies_0042",
})
```
该调用按 clip_id 读取片段在语料库中的全部元数据。

用于剪辑总监锁定成片前确认提供方与 URL。

---

## 门禁提醒（强制）

本阶段以人工批准为门（`human_approval_default: true`）。评审通过后：以 `status="awaiting_human"` 打检查点，呈现摘要（Backlot 面板会渲染产物），然后**结束本轮**。不要在同一响应里启动下一阶段。批准按门生效——先前的"继续"不覆盖本门。
