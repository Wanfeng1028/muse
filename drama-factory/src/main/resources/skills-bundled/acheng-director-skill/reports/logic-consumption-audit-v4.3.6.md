# Acheng Director 4.3.6 Integrity｜功能消费审计

本审计检查的不是“字段是否存在”，而是每项能力是否有明确输入、下游消费者、可见产出和门禁证据。

| 能力 | 作用 | 输入 | 实际消费者 | 验收证据 | 结论 |
|---|---|---|---|---|---|
| STYLE_MOTHER | 锁定跨资产媒介、线条、阴影、色板和材质语言 | `style_policy`、`style_lock`、style asset node/card | `resolve_card`、`render_asset_prompt`、assets post-hook、archive/restore | required 缺失阻塞；approved 文件/哈希；归档路径回写 | 已接通；单项独立资产可不启用，历史夹具必须显式 waiver |
| 资产依赖 | 把角色/场景/道具/关键帧依赖转成真实参考图 | `asset_id`、版本、approved node、reference role/preserve/exclude | `compile_assets` 与 H3 的 `export_asset_prompt_bundle` | 每个 Reference image 均有用途和保留/排除；`.image.txt` 不可过媒体门 | 已接通；两套编译器共用 `resolve_card` |
| Segment 绑定 | 让 Shot 需求、真实本地文件、H3 标签、上传卡和 manifest 使用同一快照 | `references`、`subjects`、Shot requirement、文件/哈希 | `resolve_bindings` → `compile_segment` → `h3_delivery` | `binding_sha256`、正文/卡/manifest 联合回读、平台状态独立 | 已接通；缺图保留草案，不静默变 T2VA |
| 交付视图 | 让用户先看懂再复制执行 | index、asset prompt entries、per-Segment snapshot | `CHAT_DELIVERY.md` / `DELIVERY_VIEW.md` | 总控台→摘要→资产提示词→段落地图→逐段卡→H3链接→阻塞项 | 已接通；长正文留文件，自动模式仍有逐段卡 |
| 动画术语库 | 把术语转成可见时间、动作、镜头、声音或 QA 事实 | `animation_term_ids`、`animation_term_evidence` | `compile_segment`、H3 schema gate、orchestrator required artifacts | 缺展开/未知术语/正文未消费均失败 | 已接通；术语名本身不能冒充证据 |
| 表演/动作/VFX/132 运镜 | 保留动作因果、微表演、受力链、效果阶段和镜头路径 | ShotSpec 专属字段 | `shot_text`、`compile_segment`、对应质量门 | 受影响合同门与 H3 正文消费检查 | 已保留并通过包级合同；真实画面仍需人工验收 |
| 场景设计支路 | 提供 advisory 场景合同，不制造第二份生产真值 | `scene_art_direction.json`、moodboard/brief 来源 | assets 主导演合并到 `scene_registry`/asset_cards | `write_paths=[]`、来源/保留/排除/未决项 | 逻辑正确但合并仍是宿主执行边界，不冒充自动视觉批准 |

## 本次纠正的真实断连

1. H3 资产提示词导出曾直接读取原始 card，绕过 `resolve_card()`；已改为先解析依赖，渲染失败显式写 DRAFT。
2. 多资产任务缺 `style_policy` 曾可在非严格 hook 下通过；新任务默认要求 `style_policy=required`，历史 04-serial 夹具显式 `legacy_unlocked`。
3. `archive/restore` 曾漏写 `style_lock.approved_file`；现与其他批准资产路径一并通过 manifest 重定位。
4. 动画术语选择曾停留在 plan node；现在必须提交 `animation_term_evidence` 并由 H3 正文实际消费。

## 尚不能由本地门禁证明的事项

- 未调用付费媒体模型，未进行平台实际上传，`visual_status=UNVERIFIED` 保持不变。
- 本地文件签名/哈希通过不等于内容真伪、身份一致、表演自然、口齿清晰或最终艺术质量通过。
- scene-design 的 advisory 事实需要 assets/主导演在宿主中批准合并；本包不会把 advisory 自动升级成 production truth。
