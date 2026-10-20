# Acheng Director 4.3.6｜升级与验收说明

本版基于 4.3.3，在独立目录开发；没有安装、公开发布或调用付费媒体生成。

本目录是 4.3.6 的完整性修订构建：它纠正了上一份 4.3.6-final 说明与实际代码之间的差异，不能把旧包的 PASS 报告当成本目录的验证依据。

## 判断与原则

原架构不是无效堆砌：七个模块已有字段权属、按需调度、相邻复核、创作合同及可恢复提交机制。实际缺陷是引用需求、真实文件、H3 和用户操作说明之间缺少共同的可执行合同，部分旧规则还互相矛盾。4.3.6 修复这条连接，不建立第二个导演、第二个编译器或第二份生产真值。

合理的职责重叠是「可读相邻事实并指出冲突」，不是多个模块同时改同一字段。shots 规划引用需求，assets 管批准文件和版本，model 分配请求局部标签，continuity 检查时序与状态；主导演唯一合并并接受最终证据。技能加载不等于启动子代理，也不等于执行了媒体生成。

## 已实现

- Shot 参考策略 → 批准素材解析 → 同源 H3/manifest/逐段上传卡 → 联合回读 → 原子提交与恢复。
- 待生成、真实本地绑定、平台上传证据分开；本地导出一律 NOT_UPLOADED。READY_TO_UPLOAD 只表示本地准备完成。
- 缺图保留完整草案、模式锁与逐段计划，禁止显示「无需参考」或静默切 T2VA。
- Subject 是内容身份，不是上传槽位；媒体可供多个 Subject 使用。开场帧构图和跨镜身份范围分开，镜头内状态按账本事件及帧窗检查。
- 自动模式显示逐段操作卡，长正文留文件；交互模式保持单段及 partial 游标。
- `CHAT_DELIVERY.md` 现在按「总控台 → 创作摘要 → 资产目录与可复制提示词 → 段落地图 → 每段上传参考助手 → H3 文件链接 → 执行顺序与阻塞项」输出；自动模式不展开长 H3 正文，交互模式在当前 Segment 卡后展开完整正文并保留继续门。
- H3 编译包额外导出 `asset_prompts/`：这些是可直接交给画布 Agent 的生成指令，明确标注 `PROMPT_READY`/`PLANNED`，绝不冒充已生成媒体。
- H3 资产提示词导出与资产编译器现在共用 `resolve_card()`；`asset_id` 依赖会展开为真实批准文件/版本，渲染失败会显式成为 DRAFT，不再回退成无参考原文。
- 多资产任务默认要求显式 `style_policy=required` 与 `STYLE_MOTHER`；单项独立资产仍可不启用跨资产风格锁。历史 04-serial 夹具明确标记 `legacy_unlocked`，不伪装成风格一致已保证。
- 编排选中的动画术语只有在 Segment 提供 `animation_term_evidence`（时间窗、可见事实、镜头/布局、声音或 QA）后才会进入 H3；缺展开不会因术语名存在而通过。
- `archive/restore` 同步重写已批准 `style_lock.approved_file`，避免归档后 STYLE_MOTHER 路径断裂。
- 主文、卡片、快照或媒体改变后旧回执失效；H3 complete 提交必须携带完整联合 bundle。

详见[绑定合同](references/114-reference-binding-delivery-v4.3.6.md)和[使用指南](使用指南.md)。宿主把 CHAT_DELIVERY.md 呈现在聊天时，应将包内相对链接解析成该导出目录下可点击的绝对文件链接；不能只链接 CHAT_DELIVERY.md 或 UPLOAD.md。

## 保留与验证边界

动态词数、完整创作正文、工程参数、动作七层受力、微表演、场景设计、STYLE_MOTHER、连续性、132 运镜及白模、九类 88 个术语、H3 格式门和 archive/restore 仍在原体系内。机器验收证明实现连接和结构合同，不证明未来生成的影片必然更好。

八套历史示例重编为 23 个 H3 bundle：21 个本地准备完成，2 个明确的待素材草案。动画电话和悬疑档案室的旧引用实际是「纸人过桥」图，不能提供其声称的身份/场景/首帧。本版保留完整创作稿并移除错误绑定，附可制作的资产提示词；未生成和批准正确媒体前不得提交。其草案验收通过表示「正确阻断」，不表示生产就绪。历史示例的 legacy_fixture 兼容标记不允许新项目绕过密度或内容批准门。

示例入口：[机甲上传卡](examples/compiled/mecha/MECHA_SEG01.upload.md)、[电话戏待素材卡](examples/compiled/animated-phone/ANIME_PHONE_SEG01.upload.md)、[悬疑待素材卡](examples/compiled/suspense-whisper/SUSPENSE_SEG01.upload.md)。

当前包级证据见 reports/package-acceptance-v4.3.6.json、reports/package-acceptance-current.json 和 reports/previs-media-acceptance-v4.3.6.json。其他旧版报告是历史追溯，不是 4.3.6 的通过依据。旧重复导出不随新包分发；4.3.3 基线和 ZIP 原样保留。

visual_status=UNVERIFIED；未实际上传平台、未生成影片，音画质量仍需后续真实媒体验收。不宣称「完美」或通用宿主一定自动执行所有规范。
