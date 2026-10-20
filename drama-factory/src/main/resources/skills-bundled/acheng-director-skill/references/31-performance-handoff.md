# 31｜表演交接恢复与模型消费

原生产宿主的十二项接口保留在[原表演规范](sources/acheng-original/references/performance-adapter.md)。本版将其分为来源事实和镜头适配，避免把物理state_in与人物心理state_in混为一处。

## 来源层

根expression_handoff含version:"1.0"、source_locked:true、beats、unresolved。每个beat含id、source_anchor、character、timing、trigger、state_in、displayed_state、leakage、control_action、residual、intensity、visible_cues、visibility、exclusions、continuity_out、prompt_ready_zh、confidence。character引用登记角色；intensity为0–5或null；confidence为0–1。

state_in是进入节拍的心理/表演基线；displayed_state是人物展示给对方的表象；leakage是没有控制住的破绽；control_action是主动掩饰/恢复；residual是控制后仍留下的线索；continuity_out是后续镜头应继承的状态。internal分析不直接进入模型正文。

## 镜头层

shots[].performance可用source_beat_id和source_anchor绑定来源，beat_id与source_beat_id一致。填写selected_phase、visibility_result:"visible"、visibility_evidence、continuity_in、continuity_out、events以及exclusion_controls。events每项phase、start、end、cue；时间为本镜局部帧，cue用具体英文动作。

static关键帧只取selected_phase对应的可见瞬间；视频按events先后编译。exclusion_controls把来源排除项转成英文正向控制，例如“Her mouth remains closed until the supplied line”，不能丢弃排除项或复制内部代号。

一个beat可分配给多个镜头，分别承接不同相位。当前每镜绑定一个主要来源beat；多个角色同时具有决定性独立反应时，先按可读性拆镜或把非主导反应列为来源可追踪的配合动作，不能把多个beat静默合并成同一个ID。存在未绑定、不可见或容量不足的beat写入unresolved，视频就绪验收会阻断，主导演决定调整镜头或修改已授权范围。

## 五轨兼容

旧格式的完整五轨仍可使用。strategy:"selective"允许只保留可见或可听的轨道，dominant_track必须实际存在，轨道起点不强制按眼神→呼吸→肩颈排序。来源events格式不再要求凑五轨。极近景看不到肩手时不要编入画面，远景不能要求观众读到眼睑微颤。

连续性人工核对：上一镜残留与下一镜进入状态相容；新变化有触发；伤势限制仍成立；角色控制情绪的动作不与同时执行的受力动作冲突。机器验证引用和时间，语义内容由主导演独立阅读。示例见[文戏交接生产数据](../examples/02-drama.production.json)。
