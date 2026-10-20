# 电影级作画与视效引擎 (Cinematic Sakuga & VFX Engine)

当分镜或打戏中出现超自然能量、刀光剑气、机甲装甲尾焰、爆炸激波、元素魔法或好莱坞级破坏光效时读取本文件。
本引擎严格基于计算机图形学物理解算（流体动力学、三态粒子、材料破坏）与日式顶级作画（Sakuga 顿挫、冲击帧）双重法则构建，并作为**多 Skill 调度总线中与 `cinematic-vfx-prompt-engine`（视效总监支路 Skill）对接的核心枢纽**。

---

## 1. 视效六大底层公理 (The 6 VFX Axioms)

1. **流体骨架律 (Fluid-Skeleton Law)**：
   - 任何宏观能量大招（如龙形气劲、巨刃切线、等离子射流、暗影触手）**必须定性为【流体】作为动势主干**。
   - 严禁以粒子为主体，单纯散碎粒子会导致画面失去动势凝聚力；粒子只能作为流体边缘的剥离微观修饰。
2. **防生物实体化铁律 (Anti-Entity Syntax Rule)**：
   - 严禁在提示词中独立使用具体生物名词作为能量主体（例如：不能写“空中出现一条巨大的金龙咆哮冲向敌人”）。
   - **合规写法**：必须以形态修饰语修饰流体：“`金龙形态的纯阳剑气高能流体大招呼啸穿刺`”，防止 AI 扩散模型误生成带肉身毛皮的真实动物实体。
3. **碰撞破坏双分支机制 (Dual Collision Taxonomy)**：
   - **撞击型 (Impact)**：瞬态刚体碰撞，产生放射状地表深坑、高对比几何立方碎块高速飞旋、环形激波涟漪与超重打击顿挫。
   - **接触/侵染型 (Contact & Erosion)**：体积流体笼罩，接触面碳化发黑剥落、高温红热拉丝熔穿、微孔酸蚀与挥发气雾。
4. **暗部主导分层光色矩阵 (Low-Key Lighting Law)**：
   - 严禁全屏死亮高光或刺眼的纯色荧光污染（如荧光绿/高光白瞎眼）。
   - **矩阵配比**：核心极薄超亮切线（高饱和主色）占 10% + 柔和半透明边缘弥散辉光占 30% + **深邃通透的对比暗部（占 60%）**。唯有暗部扎实，特效才具备电影级景深立体感。
5. **作画时序四段论 (4-Phase Sakuga Timing)**：
   - 拒绝匀速运动，严格嵌入非线性速度坡度：
     `蓄力微缩 (Anticipation) ──▶ 瞬发极限拉伸 (Smear) ──▶ 1-3帧冲击定格 (Impact Hold) ──▶ 激波扩散余韵 (Decay)`。
6. **动量耦合与后坐力反噬 (Kinetic Recoil Law)**：
   - 特效不得凭空在空中生成，其根部必须紧密锚定在角色发力末梢（枪口、剑脊、掌心、机甲喷口），施法者必须承担地面反震、衣发倒卷与机械避震器冲压。

---

## 2. 三态微观粒子协同解算 (Tri-State Particle Physics)

在描述高级视效时，必须同时调用以下三种物理形态的粒子，构成丰满的层次感：

```text
[气态粒子 (Gaseous Particles)]
- 锥状音爆凝结激波环 (Prandtl-Glauert Condensation Vapor)
- 接触面受高温瞬间升腾的白炽水汽或臭氧薄烟
- 贴地翻滚扩散的环形气浪爆压圈 (Toroidal Shock Ring)
       +
[液态/流体主干 (Fluid Backbone)]
- 极高密度等离子光刃射流 / 高温红热熔化金属拉丝
- 水墨洇散流转的太极真气流动体
       +
[固态碎片粒子 (Solid Geometry Particles)]
- 剧烈震碎的高对比几何岩石立方块 (Nakamura Cubes)
- 装甲受挫剥落的碳纤维与耐热陶瓷残片
- 摩擦激爆出的千百道向外飞溅的金属火星束
```

---

## 3. 四大主流流派工业级视效矩阵 (Genre VFX Matrices)

### 3.1 好莱坞重装机甲与空爆科技 (Hollywood Mecha & Blast - Style 01 适配)
- **流体主干**：三道清晰马赫环的亮蓝白等离子尾焰流体射流、重型破甲穿透激波空气锥。
- **固态破坏**：震飞的黄铜弹壳、受冲击波震脱的六角钛合金螺栓、沥青地面铲出的粗大焦黑碎块。
- **气态与光学**：贴地扩散的甜甜圈状爆轰尘环、重度空气热浪畸变 (Thermal Mirage)、镜头被强光吞噬后的瞬时自动曝光下潜（呈现极高反差英雄逆光黑剪影）。
- **色彩矩阵**：超温极透冰白蓝核心 + 工业炽橙色边缘焰 + 铸铁哑光黑背景。

### 3.2 玄幻仙侠与道门真元 (Eastern Fantasy Qi - Style 02/04 适配)
- **流体主干**：百米极薄冷翠剑气流体、水墨洇散交织的八卦罡风流体、游龙形态的纯阳紫金剑罡。
- **固态破坏**：被剑锋平整镜面削切的花岗岩滑脱切口、震碎的古玉符晶屑、金芒铁屑。
- **气态与光学**：破空音锥白汽、伞状水雾爆散圈、淡青色清冷灵气残烟。
- **色彩矩阵**：纯白锋刃切线 + 琉璃深青/沉香古金主色 + 玄青深空暗底。

### 3.3 赛博脉冲与高频高压电离 (Cyberpunk High-Frequency Arc)
- **流体主干**：超导等离子锯齿脉冲电弧流体、单分子热熔光刃拖尾、六边形高频振荡偏折护盾。
- **固态破坏**：钢化玻璃蜂窝状碎粒、烧焦断裂的硅芯片与铜丝残渣、碳纤维发黑剥落。
- **气态与光学**：高压击穿空气的微毒臭氧青烟、液氮冷却管爆裂喷射的极寒冷凝白汽。
- **色彩矩阵**：电离极冷青蓝核心 + 受力过载处脉冲赛博洋红 + 湿润沥青黑地表反光。

### 3.4 暗黑深渊与虚空诅咒 (Dark Fantasy & Abyssal Necromancy - Style 05 适配)
- **流体主干**：活体粘稠深渊黑雾流体、千百条尖啸怨煞汇聚而成的阴影巨爪流体。
- **固态破坏**：生机抽离后瞬间粉化的惨白骨粉、受诅咒脆性断裂的碳化黑石。
- **气态与光学**：贴地爬行的惨冷白雾、微孔挥发的暗绿酸蚀毒气、阴森幽光。
- **色彩矩阵**：至黑深渊核心 + 边缘幽绿/惨紫微弱发光 + 枯萎死灰背景。

---

## 4. 与支路 Skill `cinematic-vfx-prompt-engine` 协同调度协议

在总导演引擎 (`cinematic-director-engine`) 运作时，涉及高阶特效时自动激活与外部专业支路 Skill `cinematic-vfx-prompt-engine` 的双向通信：

```text
【总导演分镜/打戏】 ──▶ 提取动作与特效插槽 [Action / Dynamics]
                         │
                         ▼
【支路 Skill: cinematic-vfx-prompt-engine】
  ├── 模式 1 (CREATE): 从零装配九维工业级大招提示词
  ├── 模式 2 (OPTIMIZE): 非侵入原位手术注水 (时间线与动作逻辑绝对冻结)
  ├── 模式 3 (REINFORCE): 注入 4 阶段作画顿挫、冲击帧与光学失真
  └── 模式 4 (PERSONALIZE): 装配四大主流流派光色矩阵与专属印记
                         │
                         ▼
【回传总导演】 ──▶ 填回 ShotSpec / 分镜行 / MiniMax H3 编译块
```

### 调度指令与数据载荷契约 (Dispatch Payload Contract)
```yaml
vfx_dispatch_request:
  caller: "cinematic-director-engine"
  target_skill: "cinematic-vfx-prompt-engine"
  mode: "OPTIMIZE" # CREATE | OPTIMIZE | REINFORCE | PERSONALIZE
  genre: "hollywood_mecha" # eastern_fantasy | cyberpunk | hollywood_mecha | dark_fantasy
  input_slot:
    shot_id: "EP01-S01-SH004"
    time_window: "10.5s - 14.0s"
    original_action_text: "双手机甲同时开火互轰，发生剧烈爆炸"
  physics_constraints:
    fluid_backbone_required: true
    prevent_entity: true
    low_key_lighting: true
```
支路 Skill 返回高精度物理语言后，由总导演直接装配入 MiniMax H3 的 `detailed_description` 字段。
