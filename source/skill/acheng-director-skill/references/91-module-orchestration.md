# 91｜主导演与专业子入口的执行合同

## 调度的实际含义

主入口拥有项目真值、对象创建、范围、版本和合并。七个modules下的SKILL.md是随包专业入口，可按路径读取；它们不是自动注册到宿主的七个独立工具。需要单独发现时可以显式按路径调用，当前安装不向全局skills平铺额外同名目录。

`data/module-registry.json`是七个生产模块的字段权属与必读依赖真值源。`director_dispatch.py plan`输出本任务的加载计划；它不启动代理、不调用模型、不消耗生成费用。主代理按计划读取模块，写回指定结构；是否使用其他代理始终遵守宿主和用户授权。

场景设计是 assets 分支下的嵌套专业支路，不计入七个生产模块。`references/105-scene-design-adapter-v4.md`定义它的触发、输入、输出和冲突边界；外部 `scene-concept-art-director` 只生成 scene-art 合同和独立提示词，`write_paths` 必须为空。assets 负责最终采纳，shots、effects、model、continuity 不因场景建议失去字段权属。

红猴子能力另由 `data/red-monkey-integrations.json` 登记，并按[红猴子整合合同](93-red-monkey-integration.md)追加到计划。它们分为生产增强、顾问、门禁和维护四类；默认只有七个模块可以写生产字段，整合记录的 `write_paths` 必须为空。`internalized` 表示机制已进入本地规范，不表示需要再加载一个同名全局 skill。

每个有实际交付物的计划自动追加一次 `lobster-anti-omission-gate` 执行层门禁。它只读取[交付完整性与反省略门](94-delivery-integrity.md)并返回范围、完整性、证据和未决项回执；不拥有任何生产字段，不会压缩正文，也不等同于旧版 `task-layer-executor` 的任务调度。

## 请求与回包

专业决策依 [115](115-directed-decisions.md) 按位置执行；模块 reads 包含其专属指南。plan 的总 required_reads 是依赖清单，不要求一次全部加载；执行当前 step/node 时读取其 required_reads，指南只运行当前命中的小节。结果与简短依据沿原 patch/evidence 回包，不新增 scratchpad、第二账本或门禁循环。

专业问题与视觉资料按指南的局部链接按需读取，不加入全量必读列表。提交前只核对所采纳决定是否进入本模块原字段；evidence 可记录来源 Q/视觉条目、采用结果、字段位置与必要取舍，未采用的题无需交答卷。检索工具只读资料；有跨 owner 影响时交具体建议由主导演合并。原身份、状态、时长、详细度、恢复和哈希门保持优先。

请求含request_id、stage、execution_mode、可选features、completed_modules、shot_ids、frozen_paths。执行模式先由用户选择；1 为自动文件与逐段操作卡，2 为每轮一个完整 Segment。stage为script/storyboard/perform/action/vfx/assets/h3-compile/continue/audit/full。completed_modules 需要实际产物，不能仅凭字符串跳过。引用衔接遵守[114 合同](114-reference-binding-delivery-v4.3.6.md)，相邻互检即使不在生产写入步骤中也可按只读入口加载。

plan回包含input_revision、steps、integration_steps、required_reads、external_reads、shot_ids、frozen_paths、max_corrections。H3步骤要求找到已安装h3-prompt-writing及两个指南，否则BLOCKED并列出路径；不能静默使用泛化格式。普通资产阶段不强制载入H3。整合步骤必须注明触发理由、owner、输出类型和自检项；`superseded` 记录不得进入计划。

专业回包含request_id、input_revision、module、status、attempt、patch、evidence、unresolved。patch是[{path,value}]，path使用JSON指针形式，只支持替换允许字段；禁止删除、越权、重叠写入与离开本次shot_ids。新镜头、角色、场景、片段由主导演建骨架，专业模块不通过替换整个shots数组抢走他人字段。

READY且没有unresolved才可合并。NEEDS_DIRECTOR_REVISION或EXECUTION_BLOCKED交回主导演；attempt最多2，即初次与一次有证据的修正。每次成功合并后SHA改变，下一模块必须基于新版本重新生成请求。独立分支只能返回建议，不能拿过期基线覆盖当前文件。

```text
python scripts/director_dispatch.py plan production.json request.json --out dispatch.json
python scripts/director_dispatch.py accept production.json dispatch.json --response response.json --out production.next.json
```

输出必须新文件；输入不覆盖。接受回包时执行已具备数据的合同检查并保存dispatch_log回执。回执的result_revision描述加入回执前的数据摘要，避免摘要自引用；完整最终文件摘要由下一请求计算。

4.3.8明确阶段边界：story/assets/performance/shots/effects回包只接受当前负责人所管合同，回执列 checked_gates、deferred_gates 和 final_delivery_accepted:false。下游H3尚未写完不能阻止已合格的上游事实回包；model/continuity具备整份数据时执行完整生产合同，最终还必须通过磁盘正文与绑定联合验收。阶段通过不是全片通过。

资产模块负责 style_policy/style_policy_reason/style_lock 的数据回包，仍遵守用户风格批准与冻结字段；shots负责 required_assets/required_prop_ids 和 reference_requirements；model负责所选 animation_term_ids 及展开证据。读取某资料库不自动授予它写真值的权限。

编排计划绑定输入revision；阶段合并改变生产数据后，宿主必须基于新文件生成后续计划/dispatch，不能拿旧revision继续提交。非model的artifact提交器只证明文件完整与接力，不代替专业内容合同；验收该阶段的真实检查回执后才能 accepted。宿主须实际执行读取、推理、回包与提交；本包没有隐藏的模型调用后台。

## 有限责任重叠

只有相邻职责互检：编剧/表演看选择是否成立；摄影/表演动作看关键反应和接触是否可见；动作/特效看效果是否遮挡或改变结果；资产/编译看身份版本与上传是否一致。每次反馈记录具体字段、问题证据、影响与建议；接收方无权直接修改另一方拥有字段。

整合层只在这些相邻复核之后提供一次证据回包：prompt-library 只能分析外部提示词；reasoning-kit 只能给方法和决策证据；IM2 只能给资产清洁／材质建议；巨构支路只能给尺度证据；运镜目录只能给语义化运动参考；security/self-reflection 只能做门禁或声明校准。任何整合步骤都不能绕过模块 owner，不能把建议直接当作事实合并。

主导演解决冲突时按当前用户修订、确认剧本、已批准视觉事实、ShotSpec、视觉默认、模型语法的顺序裁决。模型字数不足不能删决定性事件；应减冗余、分合法片段或报告不可满足。不要要求所有模块彼此审阅，也不要把同一模型换角色复述当作独立审查。

H3 交付增加一条密度门：model 模块负责 Ref2VA 六字段、`mode_lock`、真实参考标签和按 `h3_contract.detail_policy()` 动态计算的 `detailed_description` 词数门；continuity 复核角色、场景、道具、伤势、朝向和尾态是否跨镜闭合；shots/performance/action/effects 只复核自己拥有的摄影、表演、受力和遮挡事实，不改写 H3 正文。任一相邻复核发现缺项，退回主导演定位字段后再编译，不能由门禁把正文改成摘要。

STYLE_MOTHER 只属于资产生成链。model 编译 H3 时可以读取已批准的风格锚定结果，但 H3-only 请求不能因为缺少资产卡而自动启动 style-anchor；这样可以把宿主预算留给逐镜正文，同时保持资产与视频的职责边界。

## 上下文与失效传播

热上下文仅放当前任务、版本、相关角色/场景、当前镜头、即将兑现伏笔和必要参考；完整剧本与原技能存在冷层，按来源锚点取用。不是把全量原文每轮载入，也不能摘要后删除原文。

改台词影响表演、声音与编译；改场景地标影响摄影、场景资产与关键帧；改身份版本影响引用该资产的后续项；仅调特效光色不重写故事。用asset_plan的impact及story_beat_ids定位受影响范围。

任务状态需持久化；skill无法保证宿主的精确上下文token阈值或主动压缩接口。没有可观测计数时不得宣称已在指定阈值执行压缩，按照宿主提供的压缩机制接续。
