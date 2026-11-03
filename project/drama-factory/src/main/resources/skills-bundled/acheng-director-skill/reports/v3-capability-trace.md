# v3 能力迁移、执行路径与证据边界

本表对应用户要求的完整导演体系。来源原文继续保留，活动规范和可运行数据负责日常生产；归档文件的存在不单独算作能力已接通。

| 能力/来源 | 活动规则与生产实现 | 可复核交付 |
|---|---|---|
| 盛唐八线、误导与知情方法的泛化 | [多线叙事](../references/11-story-architecture.md)、story_contract.py；任意线路、知识重放、伏笔先后、关系变化、正文/镜头覆盖 | [原创跨集悬疑](../examples/04-serial.production.md)，不移植盛唐角色或固定政治命题 |
| 原版小传、人物弧光与润色 | [人物与对白](../references/12-character-dialogue-revision.md)；角色want/need/belief/voice、选择证据、锁定对白 | 跨集例两种人物弧与关系变化 |
| 原版12项表演交接 | [来源与适配](../references/31-performance-handoff.md)、production_extensions.py；来源锁、可见性、events、排除项、完整消费 | [文戏数据](../examples/02-drama.production.json)及实际H3正文 |
| 灵动/个性化表演机制 | [灵动表演](../references/32-liveliness-performance-framework.md)、performance_liveliness.py；目标→策略→触发→动作单元→运动弧→语气节拍→切点承接 | 文戏样例的 acting_design、motion_profile 与逐段编译正文 |
| 红猴子132参考与原版摄影 | [分镜](../references/20-storyboard-compiler.md)、[题材与容量](../references/21-genre-camera-capacity.md)；原132媒体与来源不变 | 五例的静态、侧移、推拉和不同媒介 |
| 每段4–15秒与总时长保护 | h3_contract.clip_bounds、director_pipeline.pack；合法边界分区，不可行拒绝 | 新测试复现14+3拒绝、7+7+3重排为7+10 |
| H3五模式及独立请求 | 已安装H3指南；h3_contract.py与编译器，合法任务类型、段内speaker、跨切镜对白、实际图像锚点消费；v3.2每镜重复主体／场景／初态并强制写明触发、因果、摄影机、声音和尾态 | 八例覆盖T2VA、Ref2VA、I2VA、FL2VA、L2VA，另有动画电话、喜剧误会和悬疑低声样例 |
| 全资产与IM2清洁 | [全资产依赖](../references/61-asset-dependency-production.md)、asset_plan.py/compile_assets.py；需求、版本、图号、缺图状态 | 跨集例角色、场景、道具与关键帧；[上传与制作顺序](../examples/compiled/images/serial/UPLOAD.md) |
| 特效广度与原位优化 | [六家族](../references/46-effect-families.md)，能量仅对能量启用；其他家族事件合同，冻结优化 | 原机甲/巨构能量例；非流体光学效果的合同与优化回归 |
| 巨构尺度 | 00视觉宪法、45/46效果规范与原巨构field-guide；保留独立尺度证据、媒介翻译 | [巨构卡](../examples/03-colossal-scale-combat-h3.md) |
| 主子模块协作 | [模块合同](../references/91-module-orchestration.md)、七个modules入口、module-registry.json与director_dispatch.py | [调度请求](../templates/dispatch-request.json)、跨集例调度清单；回包越权与过期阻断 |
| 冷热接续 | director_pipeline.archive/restore；原文、知识/关系/伏笔摘要、资产文件和哈希 | 新测试覆盖含全资产计划的归档恢复与再次导出 |

## 验收方法

新增一份测试文件、五个测试方法，分别保护叙事、表演/调度、分段/H3、条件特效、资产与恢复五组公共合同；现有资产交付测试还检查名称纯净出口。既有测试保留，必要断言随独立speaker与表演输入合同升级。实际运行结果见当前[包验收](package-acceptance-v3.2.json)和本次交付说明，不以本表代替执行证据。

最终包验收检查实际导出的正文、上传文件哈希、草案状态、全部五模式、来源完整性、七模块依赖和至少八套数据；图像目录另检查`ASSET_NAMES.txt`只有名称及可选版本。独立阅读实际提示词与样例剧情，修正发现的语义问题后重新检查受影响项。

## 仍然明确的边界

- 技能支持创作与提示词生产，不保证任意题材、任意模型、任意种子的最佳结果；没有排名比较证据。
- 机器能验证被声明的知识、资产需求和依赖；正文中的隐含遗漏、动机可信度、真正视觉可见性需要内容复核。
- 程序绘制参考图证明输入可绑定，不能证明生成模型能精确复现动作。未调用付费图像或视频生成，真实影像与声学状态保持未验证。
- 当前表演镜头绑定一个主要来源beat，支持该beat跨镜；多人同时具有独立决定性反应时应合理拆镜，不能宣称任意多beat自动融合。
- 模块是可加载的专业入口与确定性回包合同，不是后台自主代理服务。单模型的分阶段自检不等于独立评审。
- 生成能力、参考数量、分辨率与接口设置须在实际入口核对；没有把社区提示词指南冒充厂商API schema。
