# 80｜连续性账本与冷热隔离

## 四域状态与版本

角色伤势、弹药／能量、道具所有权、场景破坏进入同一时间顺序的事实流。人物关系、认知、天气、服装版本和空间尾态保存在角色／场景快照，并由带来源的事件更改。心理关系不强制永远不可逆，和解也必须有戏剧事件支撑。

初始 snapshot 不是“全部默认完好”。读取上游已确认事实，受伤者用真实当前 phase；未受伤用 null，与 Phase 0 区分。

| 伤势阶段 | 含义 | 可见状态 | 转移条件 |
|---|---|---|---|
| null | 无本条伤势 | 无该伤口 | injury 事件才能建立 Phase 0 |
| Phase 0 | 急性期 | 新损伤、避痛、出血或机械失效 | 稳定／处理事件转 1；恶化仍留 0 并更新症状 |
| Phase 1 | 稳定／处理期 | 包扎、固定、功能仍受限 | 足够故事时间与恢复事件转 2；再伤可回 0 |
| Phase 2 | 恢复／残留期 | 疤痕、代偿或已说明恢复程度 | 不自动清除；治疗或修复事件另记 |

这是叙事状态机，不是医学时间表。没有依据不强制“活动度减少30%”，改写具体不能完成的动作。伤势有 location、origin_shot、functional_limit；不同部位各自记录，不用新伤覆盖旧伤。

场景 Level 0 完好／既定基线；Level 1 表层损伤；Level 2 局部重损且主要承重仍可用；Level 3 结构破坏影响路线和荷载。降级需要明确 repair 事件；更换场景不能重置旧场景。玻璃碎片、烟气、照明中断按各自时间和物理条件衰减，不与破坏等级一起一键清零。

## 事件与守恒

每事件有唯一 ID、发生 frame、source_shot、kind、target、before、after、reason。弹药 `after = before + delta`，不允许负数；增弹需要 reload/resupply 理由及相应资源来源，不能凭“下一镜”增弹。道具转移 before.owner 必须为当前持有者，after.owner 只能是已登记角色或场所；落地也要位置。伤势、破坏或所有权的镜头结果必须通过 `outcome_events` 连接到事件。

机器审查从 initial 逐事件重放，核对 before、frame 所属镜头及最终 snapshot；每个镜头的 `state_in/state_out` 必须与重放结果对应，跨 Segment 同样检查。任一“上镜掉枪、下镜又持枪”要么补真实拾取事件，要么修镜头。

## 冷热数据分工

hot 只包含当前 revision、最新状态快照、当前场景地图、活跃人物的外观锚点、未兑现伏笔及下一场入口。cold 保存完整剧本、ShotSpec、原始提示词、资产版本、事件和质量报告。不能把原始信息“摘要后删除”；摘要是索引，原文保持完整可查。

`lobster-skills/hot-memory-system` 提供冷热分层思想，但其“七天清理”不适用于生产事实。`codex-thread-cold-history` 针对 Codex 会话存储，本系统只借鉴原文保真、检索定位、恢复核验，不执行它的数据库迁移流程。导演的场记归档绝不触碰聊天记录或全局 AGENTS。

## 不可变归档事务

`director_pipeline.py archive` 在指定 project-state 下建立 `revisions/<内容SHA>/`，保存 production.json、ledger.json、hot.json 与 manifest.json。先写临时同级目录，完成哈希核验后 rename 为正式内容地址目录。已有同内容目录时复核后返回幂等成功，不重写。失败的临时目录保留可诊断信息，不把未完成目录当最新版本。

hot.json 包含 `cold_production` 和摘要状态，并有完整 production 哈希；不把长正文复制进 hot。读取时先验证哈希，再按 scene_id/shot_id/event_id 定位 cold。档案以显式 revision ID 接续，避免并行写入“latest”指针产生丢失更新；当前工作生产文件记录 base_revision 供调用者比较。

`director_pipeline.py restore` 接收 archive 返回的 revision 目录，校验manifest列出的每个文件、原production摘要、ledger与hot一致性，再把参考素材复制进新的恢复目录并改写引用为该目录下的相对路径。恢复稿增加base_revision，其他叙事与状态保持相同；恢复后可以直接再次运行H3编译，不依赖原工程素材路径仍存在。原冷档案保持不变。

## 恢复与冲突

断电／失败：正式 revision 不存在则此次未提交，原稿仍在；正式目录存在但哈希不匹配则报错，不能重新造一个“通过”标记。过期 vfx 补丁或状态基线不符时报 stale_revision，保留两版差异，由主导演读真实变更后重放。不同分支不自动合并事实。

跨集继续时读初始基线＋之前事件的已验快照，不把 Phase 1 自动升级 2。长文本需要旧台词或伏笔时按索引精确读取，保留来源位置和版本。未找到事实标 unknown；角色能力、隐藏武器、未登记通道不得靠“合理推测”补入已确认世界。
