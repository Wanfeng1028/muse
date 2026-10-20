# 跨集连续性事实账本协议 (Continuity Ledger Protocol)

当影视项目包含多集、多幕、体量巨大或分批生成时，为防止角色战损自动痊愈、道具凭空消失、时空错乱或关键情感断层，必须启用本连续性账本协议。
本文件定义了项目级不可逆状态机、多集状态转移矩阵与已确认事实底座。

---

## 1. 连续性账本四大核心维护域 (The Four Continuity Domains)

在长线叙事中，每个制作批次启动前必须读取本账本，批次完成后必须将最新状态写回：

### 1.1 生理状态与战损磨损域 (Physical & Battle-Worn Domain)
- **伤势三阶段物理状态机 (3-Stage Trauma State Machine)**：
  - **Stage 1: 创伤急性期 (Acute Trauma)**：伤口暴露、鲜血渗溢、衣物破裂、动作伴随避痛性肌肉抽搐。
  - **Stage 2: 应急包扎期 (Bandaged & Clotted)**：简易止血带或绷带包裹、暗色干涸血痂、受损肢体关节活动幅度受限 30%。
  - **Stage 3: 疤痕与功能代偿期 (Scarred & Compensatory)**：缝合线痕迹、暗红结痂、持久性微跛行或依靠支撑物。
  - **铁律**：**严禁任何角色在无特定超自然治疗设定的情况下，在下一场戏或下一集自动痊愈！**
- **机甲与装甲战损累加**：装甲板剥落、外露电缆火星微跳、焦黑弹孔在同一台机甲上必须保持三维坐标恒定。

### 1.2 关键道具与武器所有权流转域 (Prop & Asset Ownership Domain)
- **空间流转因果闭环**：若角色 A 的主武器被击飞掉落在地面积水中，角色 A 在下一镜绝对不可凭空再度拔出该枪，除非有拾取、夺取或拔出备用副武器的明确动作交代。
- **弹药与能量守恒**：弹夹余量、高能电池插槽状态、药剂使用次数严格遵循计数守恒。

### 1.3 场景破坏与物理残留域 (Environmental Destruction Domain)
- **四级环境破坏持久化 (4-Level Environmental Damage Scale)**：
  - **Level 0 (完好)**：原厂或出厂整洁状态。
  - **Level 1 (微损)**：表面弹痕、擦伤刮花、灰尘覆盖。
  - **Level 2 (重度破坏)**：混凝土开裂钢筋外露、燃烧焦黑、玻璃与设备粉碎。
  - **Level 3 (结构性坍塌)**：承重立柱断裂、地表巨型深坑、屋顶塌陷天光下倾。
- **重返场景真值保持**：若剧本从内景打到外景再打回内景，内景必须保持此前战斗留下的 Level 2/3 破坏残骸，绝对禁止场景重置。

### 1.4 人物关系与情感认知跃迁域 (Relationship & Cognitive State Domain)
- **不可逆的情感转折**：背叛揭露、生死同盟建立、不可调和的信任崩塌等情节点一旦跨过，后续对话中的身体站位距离、眼神交汇频率与微动作防备姿态必须彻底重构，严禁打回原形。

---

## 2. 连续性事实账本标准存储结构 (Continuity Ledger Schema)

```yaml
continuity_ledger:
  project_id: "CINEMATIC_PROJECT_01"
  last_confirmed_scene: "EP01-S03"
  timeline_clock: "20:45_heavy_rain_night"
  production_total_duration: "03:00"
  elapsed_duration: "00:42"
  
  characters:
    - character_id: "CHAR_LINYUAN"
      physical_status: "injured_fatigued"
      trauma_stage: "stage_2_bandaged"
      wounds:
        - location: "right_cheek"
          type: "bleeding_laceration"
          origin_shot: "EP01-S01-SH002"
        - location: "left_shoulder"
          type: "blunt_contusion"
          origin_shot: "EP01-S02-SH004"
          mobility_penalty: "left_arm_elevation_limited"
      prop_inventory:
        holding: "tactical_plasma_carbine"
        holstered: "broken_titanium_dagger"
        ammo_count: 14
      emotional_state_out: "cold_distrust_guarded"
      relationship_flags:
        CHAR_RENAUD: "mortal_enemy_irreversible"
        
    - character_id: "CHAR_RENAUD"
      physical_status: "overheated"
      armor_damage:
        - component: "right_mechanical_arm"
          condition: "coolant_line_ruptured_steam_emitting"
      prop_inventory:
        holding: "heavy_anti_materiel_pistol"
        ammo_count: 3
        
  environment_persistence:
    - scene_id: "S01_TITAN_HANGAR"
      destruction_level: "level_2_heavy"
      persistent_damage:
        - "main_support_pillar_shattered_rebar_exposed"
        - "ground_concrete_crater_diameter_2m"
      atmosphere: "indoor_flooded_with_steam_and_burning_oil"
      lighting_condition: "primary_floodlight_flickering_50_percent_intensity"
      
  unresolved_plot_threads:
    - "sub_reactor_circuit_unstable_ticking_down"
    - "encrypted_data_drive_dropped_under_control_desk"
```

---

## 3. 跨批次读写生命周期控制门禁 (Lifecycle Gate)

1. **进入新场次编写前 (Pre-flight Load)**：
   - 强制读取本账本，校验当前场次出场人物的持有物、弹药与伤势阶段，并将最新环境状态注入场景描述。
2. **本批次分镜/提示词完成时 (Post-flight Commit)**：
   - 检查本批次是否发生了状态突变（角色负伤、武器脱手、墙体坍塌、情感破裂）。
   - 将最新突变事实追加写回账本，并输出 3 行以内的简要连续性审计更新日志。

---

## 4. 分场场记冷存与防长文本失忆协议 (Scene Cold Archiving Protocol)

在多集、长篇史诗或多场次剧作中，如果把已完成场次的全量分镜与冗长对白持续留在活跃会话中，会导致大模型注意力严重稀释，出现**“剧本吃设定、伤势凭空消失、前序伏笔遗忘”**的上下文退化现象。
本系统严格执行 `codex-thread-cold-history` 的**冷热状态分离架构**：

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 【冷存储库: Cold Archive】                                             │
│  已锁定场次 (S01, S02...) 的全部原始逐字稿、详细分镜卡、历史报错碎片   │
│  • 默认不随新任务加载；仅在用户显式要求“调阅第X场原话”时按需定点提取    │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ 仅提取最新状态突变 (State Delta)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 【热状态机: Hot State Machine】(随当前场次携带)                        │
│  • 当前活跃角色当前伤势/弹药/道具增量                                   │
│  • 当前场景持久化破坏级别 (Level 0-3)                                   │
│  • 未解决的关键剧情悬念 (Unresolved Plot Threads)                      │
│  • 确保大模型在第 100 场仍然具备如同第 1 场的最高注意力和敏锐记忆力   │
└────────────────────────────────────────────────────────────────────────┘
```

*   **冷存触发阈值**：单项目已定稿分镜超过 3 个切片 (Segment) 或剧本超过 2000 字时，自动封存旧切片全量文本至冷档案。
*   **续写交接铁律**：后续场次生成时，**仅向大模型注入当前热状态机 (Hot State) 与当前场次大纲**，严禁倾倒历史全文本，彻底斩断长上下文失忆根源。

