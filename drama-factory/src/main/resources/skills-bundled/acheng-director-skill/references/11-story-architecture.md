# 11｜多线叙事、知情边界与伏笔工程

## 入口与产物

长篇、群像、悬疑、双时间线或跨集任务必读。采用 `story.contract_version:"3.0"`；JSON 实例见[跨集悬疑](../examples/04-serial.production.json)。它展示可运行的数据颗粒度，不能把样例集数与时长当通用上限。

先锁主题的两种可辩护立场、终局必须成立的事件、主角拥有的因果权、时间与空间范围。产出全局梗概、人物、剧情线网络、伏笔/知情表、分集分场正文；分批交付保留完整范围与未交付清单。分镜时长在剧本确认后分配，不能为了模型窗口压缩故事。

## 任意数量线路

`threads[]` 每项有 id、question、function（external/relationship/world/thematic）、visibility（overt/covert/mixed）。A/B/C只是一种功能解释，实际线路可以是调查、家庭、政治、反派行动等任意数量。暗线不是必须隐藏角色；它可以是观众暂不理解意义的真实行动。每拍只有一条主导线路，其余用 secondary_threads 表明具体作用。

每条线路先回答持续问题，再分配启动、推进、受阻、交汇和结算。切走时留下行动压力，切回时带来新事实或代价。两个地点的故事时钟独立于播放顺序；倒叙另标 story_time，角色获得证据的时间仍须明确。不要把无因并列的场景包装成多线。

`beats[]` 按播放顺序保存 id、episode、story_time、scene_id、characters、primary_thread、secondary_threads、depends_on、goal、obstacle、choice、cost、result。起始拍用 entry_cause 声明事件起因，其余用已发生 beat 的依赖表达因果。存在倒叙时 depends_on 表达本次信息揭示所依赖的前文，故事内因果在 result/故事时钟中说明，不能制造未来信息已被角色掌握的假象。

场景级容量用“一个主要价值变化”判断。旁支每次出现至少改变资源、关系、可行动范围或认知之一。季终拆成规模承担者与胜负条件创造者，避免配角打完、主角只旁观。

## 知识与误解

`facts[]` 保存客观 truth；`initial_knowledge[]` 和 `knowledge_events[]` 保存谁知道什么。holder使用已登记角色ID或AUDIENCE。state为unknown/suspects/believes_false/knows；误信必须另写belief。evidence说明真实取得信息的渠道，不能只写“剧情需要”。

事件包含id、holder、fact_id、before、state、after_beat_id、evidence。获得知识在对应beat完成后生效；同一场内先发现后行动可拆成两个beat。下一拍的requires_knowledge逐项声明行动所需的认知状态。机器重放初始知识与事件，拦截提前知道、错误角色、过期before。认识事实不等于公开证明事实；需要法律、政治或关系证据时，另建一个可证明性fact。

观众与人物认知分开管理：观众可能先知危险、人物仍误解；也可能与人物一起发现。揭示前检查镜头、配乐、表情是否提前泄露答案。对观众隐瞒必须来自受限视点或合理误读，不得删除角色明明看见的决定性信息来作弊。

## 伏笔与兑现

`setups[]`：id、setup_beat、surface_reading、reinforcement_beats、payoff_beat、effect。未到兑现范围时payoff_beat为null并写planned_payoff；不得为使清单全绿而提前揭晓。已兑现项须有中段强化，并在effect写明它如何改变选择、战场条件、关系或旧场景的解释。

铺设顺序：先决定兑现造成的变化 → 找到可信的早期出现理由 → 提供当时合理的表面理解 → 安排一次有新信息的强化 → 选择揭示时机。重看时线索必须仍成立；不能临时增添此前未存在的决定性物证。

## 人物弧光与正文覆盖

`character_arcs[]`记录character_id、kind（positive/tragic/flat/open）、want、need、belief、voice、relationship_debt及evidence[{beat_id,choice}]。允许平弧、反弧和暂不结算；阶段不是按页数机械划分。选择证据应由本人行动造成，不能把配角解释当改变。

`script_scenes[]`每场带beat_ids，场景名称来自登记簿，text必须是完整可拍正文。机器检查beat覆盖与顺序；人工检查每场是否真的完成所标事件。禁改台词写入story.locked_dialogue[{scene_id,text}]，scene_id在这里指正文场次ID。

全生产交付使用delivery_scope:full_production，每个shot填写story_beat_ids；导出前核对剧情没有在分段中遗漏。已有确认剧本的局部提示词工作可用prompt_only，但报告不宣称全剧故事通过。

## 检查边界

运行 `python scripts/post_hooks.py script examples/04-serial.production.json`。它检查引用、顺序、知识与覆盖，不判断故事是否优秀。主导演另读正文，检查因果可信、误导公平、人物声音、情感累积和终局因果权。保留该次内容检查证据，不用结构分数代替创作判断。
