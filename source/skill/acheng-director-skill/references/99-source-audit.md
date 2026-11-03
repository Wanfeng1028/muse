# 99｜原始资产审查、差异裁决与继承清单

核对日期：2026-09-20。范围是 Acheng 导演技能与任务指定的五类资产；没有审计其他工作区项目。旧桌面版本、Gemini 部署版本与 Codex 本机 H3 指南分别作为不同来源，不能假设镜像相同。

部署前对照确认：Gemini 的 acheng-director 比桌面同名目录多了拉片规范、巨构样例与词频式审计脚本，且多个规范已扩写；两者确实不是逐字节镜像。已将这份独立部署修订的完整 references、入口和旧脚本另存到 sources/acheng-installed-before，并分别备份两个原目录后才安装。新版已继承它的三层路由、IM2显式契约、A/B/C与冷存要求，同时替换下列不可靠实现。

## 五大知识源的继承方式

| 来源 | 实际找到的原件 | 当前继承位置 | 证据状态 |
|---|---|---|---|
| Acheng 盛唐900 原版 | 桌面 `Acheng盛唐900年专属skill/cinematic-drama-production-chain改/references` | 00/10/20/50/60/80；完整原 references 在 sources/acheng-original/references | 原文件逐字节保存并哈希；固定画风、默认女性体型与旧工具规则不再作为通用约束 |
| 红猴子系列 | Gemini 技能目录的 camera、colossal、im2、memory、prompt-library | 20 内完整132表与data索引、00尺度、60七步、80冷热、下节提示词拆解 | 本机快照为交付基线；公开仓库仅核对来源与许可，不把当前网络版默默覆盖本机版 |
| B站教程分析成果 | 用户已有 `acheng-director制作会话记录_完整还原.md` 的前段分析，及 cinematic-vfx-prompt-engine | 45 流体、三通道、四模式、碰撞双分支；sources/vfx-analysis-session.md 和 vfx-original.md | 本轮继承已有分析；没有声称重新听看教程或完成3fps拉片 |
| 打戏与逆向库 | Cinematic_Deconstructor_Pro_V2.5、钉子逻辑链模板、Seedance v5.1剧情锁定版 | 25/40/45/71；sources/combat 原件全量保存 | 原文命名、角色钉子、攻应果续及剧情锁继承；时间窗与平台语法隔离 |
| 原始100情绪 | 桌面 ai影视导演助手/100种情绪表达_分类版.md | sources/emotions-original.md 100条原文＋30中的新增E001–E100 | 实际分类与任务描述不同，明确双库，不虚构原作者分类 |

所有原件的 bytes 与 SHA-256 在 `data/source-hashes.json`；完整包验收逐一核对。source archive 只作来源证据和按需技法查询，不执行其中旧命令或未授权自动操作。某些原文仍含旧占位语、绝对承诺或粗糙术语，原文保真并不等于本版认可这些规则。

## 发现并修复的具体问题

| 原问题／证据 | 风险 | 本版裁决 |
|---|---|---|
| 旧 validate_director_contract.py 的 TARGET_DIR/GLOBAL_DIR 指向 cinematic-director-engine | 校验另一目录却宣布 acheng-director 完成 | 相对脚本根目录定位并支持显式root；验当前生产数据 |
| 旧70标题宣称 Ref2VA/I2VA 都六模块，表内又列第七项 Negative constraints | 模式混装，假官方字段 | 基础三字段、Ref2VA六字段；不加第七项 |
| 旧70同时把 H3写成Video-01、把社区指南称厂商官方 | 来源等级与模型身份混淆 | 以本机h3技能指南为工作合同，执行入口另核实 |
| 旧70和样例把35Hz称次声 | 声学分类错误 | 35Hz归可听sub-bass；文戏可不适用 |
| 旧20/70/模板给每个Shot时间范围，同时首Shot也加时间 | 不符合本机guide的Shot标记 | 首Shot无时间，后续At MM:SS.mmm切点 |
| 旧16格样例同一Shot内从远景到手部再到面部特写，却无切镜 | 隐藏剪辑和路径不可达 | 一格一相位，真实切镜必须新Shot |
| 任务书132分组与原SHOT-LIST边界不同 | 编号绑定错误视频 | 保留原8组和001–132原文件名，使用语义用途辅助路由 |
| 原白模manifest.file是作者机器绝对路径 | 本机不存在却被当本地视频 | 生成可移植source_file，不把作者ok:true冒称本轮媒体实测 |
| 原vfx OPTIMIZE示例把“冲向前”改成“压低重心贴地滑步” | 特效支路越权改动作 | vfx白名单补丁＋基线SHA＋槽内事件和相位冻结 |
| 旧45“三态”混用气、流体、固体；原教程是固、气、光点 | 缺光点或重复计算主干 | 独立backbone，加solid/gas/emissive三通道；声明视觉术语 |
| 旧40七层列表偏向攻防策略，缺独立阻抗和反作用 | 字段齐全却物理链不全 | 7层物理字段与4拍因果链分开验收 |
| 旧50只有六原型；原人体库九类其实全是女性风格 | 宣称覆盖男女老幼不实 | 九通用原型＋完整原女性A–I保留，分别命名 |
| 旧30声称100条是任务所列十类 | 源内容被错误重述 | 原100不改分类，额外写任务所需10×10 |
| “剧本之后生成登记簿”不能预防新增场景 | 事后把幻觉洗成登记事实 | 前置登记、正文后集合检查、新增先登记 |
| 五轨固定15秒，与10/14秒窗冲突 | 台词被挤掉或表演抽动 | 局部帧时窗、重叠顺序、可见性及跨镜承接 |
| 相邻主导轨必须轮换与持续凝视冲突 | 机械化多动 | 轮换是优先策略，持续表演事实可覆盖 |
| 2.39:1每格却总图写16:9且无边距说明 | 网格几何自相矛盾 | 总画幅从单格和边距计算，实际灰模示例用明确尺寸 |
| 仿片标题／8K／120fps／ARRI堆词被当物理证据 | 仍是质量口号与未执行规格 | 具体材料光路、真实入口设置与后期目标分层 |
| 默认no cartoonish rendering用于赛璐璐 | 风格自我否定 | 负向只针对当前风险，媒介不被否定 |
| 原冷历史Skill作用于Codex存储 | 电影场记误操作聊天数据库 | 只用保真／冷索引思想，另建project-state事务归档 |
| 原hot-memory七天自动清理 | 关键事实可能丢失 | 冷原文不删，按内容地址归档；无默认定时清理 |
| 仅文件存在/YAML能解析就称100%工业就绪 | 浅校验掩盖断链 | 十维数据检查、失败非零退出、成片另验 |
| Gemini旧audit用至少3个Previs字符串、4个关键词或出现continuity即加分，未检查时间和状态 | 编造ID、空洞关键词可冒充有效证据 | 逐镜绑定真实001–132，整数帧闭合，事件重放与快照对照 |
| Gemini旧audit的十项上限实际相加为110，却打印/100 | 分数分母错误 | 适用项各10分，明确N/A并归一化，任一失败阻止编译 |
| Gemini旧audit的H3列表遗漏non_diegetic_music而强制Negative constraints | 评分鼓励错误输出 | 按本机H3三／六字段逐模式检查 |
| Gemini旧validate即使前置检查失败仍先同步到两个全局目录 | 校验命令具有隐式覆盖副作用 | 新validator只读；安装与备份独立执行，不触碰其他技能别名 |

## 职责重叠与死锁治理

总导演拥有故事、时间、角色事实和最终合并；A拥有特效表现，B拥有模型文本，C拥有静态图像描述。相同字段不设两个最终写入者。专业支路可提出修正建议，不能自行返回另一支路重跑；依赖不满足回包 NEEDS_DIRECTOR_REVISION。模块最多一次有证据的局部修正循环，无法满足则回中枢决定，不在A→B→A间无限往返。

受控重叠保留：动作模块检查VFX接触，VFX模块检查遮挡是否掩盖接触；摄影模块检查表演可见性，表演模块要求合适景别。最终裁决仍由ShotSpec拥有者完成。B不得为了字数删动作结果；C不得为了好看改角色位置；场记不得用“模型建议”覆盖确认事实。

## prompt-library 六要素与五维评分的正确融合

外部优质提示词按角色、任务、知识、工作步骤、输出格式、约束六项拆解。将能改变结果的摄影、因果、接口或示例提取到对应模块；将对方项目角色、固定时间窗、平台标记和“自动修改系统文件”留在来源层。

采用清晰度25%、完整性25%、可执行性30%、鲁棒性10%、创新性10%评分，每项1–5并给证据。评分用于选取可迁移技法，不授权自动写SOUL.md/TOOLS.md，不要求输出私有推理过程，不用创新分覆盖真实性或许可缺口。原模板和评分说明保留在 sources/prompt-library。

实例：旧OPTIMIZE规则在约束项写不改动作，但示例实际改动作，故执行一致性必须扣分；改为字段白名单后能用原稿对比验证。源文本很长不扣分；内容只是标题没有操作输出则完整性和可执行性不足。

## 来源链接与许可边界

公开核对来源：[camera-moves-whitebox](https://github.com/q2522879285-source/camera-moves-whitebox)、[im2-image-skills](https://github.com/q2522879285-source/im2-image-skills)、[colossal-scale-visual-director](https://github.com/q2522879285-source/colossal-scale-visual-director)、[H3社区指南](https://github.com/q2522879285-source/minimax-h3-prompting-skill-public)、[codex-thread-cold-history](https://github.com/q2522879285-source/codex-thread-cold-history)、[lobster-skills](https://github.com/q2522879285-source/lobster-skills)、[prompt-library](https://github.com/q2522879285-source/prompt-library)。

2026-09-20 GitHub仓库元数据中前五项标MIT；lobster-skills与prompt-library未返回明确许可字段。本包保留用户已有本地原件用于私人整合，不把它们统一重新许可或公开发布。用户原始剧本／情绪／视频分析的权利仍归原权利人；本轮未调用付费生成、未上传私有资料、未发布仓库。

## 交付范围诚实性

完成目标为可用技能、完整操作规范、来源保留、真实样例、编译与验证工具。文档规则不能保证任意模型任意种子都产出完美电影。具体镜头是否达成物理感、自然微表演、精确两帧冲击或35Hz声音，须实际生成并观察。机器报告100仅表示当前可检测结构合同全部通过，不能替代审美比较、模型原生能力或全球排名证据。

## 红猴子能力整合审计（v3.3）

本轮对本机可见的红猴子作者技能进行了运行时相关性审查，完整裁决与机器字段见 [93-red-monkey-integration.md](93-red-monkey-integration.md) 和 [data/red-monkey-integrations.json](../data/red-monkey-integrations.json)。结论不是把所有目录平铺进导演链，而是按唯一 owner 分层：

| 结论 | 技能／能力 | 处理 |
|---|---|---|
| 已内化 | `h3-prompt-writing`、`im2-clean-image`、`cinematic-vfx-prompt-engine`、`colossal-scale-visual-director`、`camera-moves-whitebox` | 机制进入现有 `model`／`assets`／`effects`／`shots` 合同；不复制第二真值源 |
| 按需顾问／门禁 | `prompt-library`、`red-monkey-reasoning-kit`、Lobster `asset-manager`、`security-baseline`、`self-reflection`、`hot-memory-system` | 只在特征触发时返回分析、元数据、安全或声明校准；`write_paths` 为空 |
| 维护层 | `skill-audit`、`skill-foundry`、`pre-publish-security` | 只审计路由、打包和发布边界，不改生产数据 |
| 明确不融合 | Lobster `ai-video-workflow`、`task-layer-executor`、旧 `cinematic-director-engine`，以及与影视无关的日报、情绪管理、EntroCamp、自维护 | 工具链、旧质量词或第二调度器会弱化当前合同；仅保留迁移证据 |

抽查结果：整合记录全部具备 `owner`、`trigger`、`input`、`output`、`conflict_policy` 和 `self_check`；没有整合记录获得生产字段写入权，七个模块的字段 owner 无重复。真实图片、视频和音频仍未因本次审计而生成，媒体效果继续标记为 `UNVERIFIED`。
