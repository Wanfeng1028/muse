# 电影级分镜编译器 (Storyboard Compiler)

当已有确认版剧本，需要将其拆解为 **作品/集 → 场次 (Scene) → 生成切片 (Segment) → 分镜镜头 (Shot)**，并建立全局不可变 ID 与摄影机空间语法时读取本文件。

---

## 1. 双重时长合同 (Dual-Duration Contract)

- `production_total_duration`：原样继承上游剧本声明的作品或单集总时长（如 90 秒、3 分钟、15 分钟）。本编译器绝不擅自重写总时长。
- `generation_clip_duration`：当前下游目标视频生成引擎（如 **MiniMax H3** 默认 5s 或 10s 单次生成窗口）的单次片段上限。
- **装箱切片机制**：当 `production_total_duration` 大于单次切片上限时，按戏剧动作因果、对白停顿与场景转换自然划分为连续切片（Segment 01, Segment 02...）。所有片段在时间轴上**首尾相连、严丝合缝**，绝对时间从 `00:00` 累加至全片结束。

---

## 2. 镜头命名与全局唯一标识符规范

- **单集剧集项目**：`EPxx-Sxx-SHxxx`（例如：`EP01-S03-SH004` 表示第 1 集第 3 场第 4 个分镜）。
- **单部电影/独立短片**：`FILM-Sxx-SHxxx`（例如：`FILM-S01-SH001`）。
- **绝对不可变性**：镜头 ID 一经确定并在上下游流转，**严禁中途重新编号**。即使删改中间镜头，仅作标记或跳号，防止资产图与表演映射出现 404 断链。

---

## 3. 电影级视听语言与摄影机语法规范

在编写分镜时，必须使用严谨的工业级景别、视角、机位运动与空间轴线定义：

### 3.1 景别体系 (Shot Scales)
| 术语代号 | 中文名称 | 取景范围 | 核心功能与情绪指向 |
|---|---|---|---|
| **ECU** | 大特写 (Extreme Close-Up) | 人物眼睛/嘴唇/机械咬合微结构 | 放大极致情绪泄露、机械微观伺服运动、致命危机 |
| **CU** | 特写 (Close-Up) | 头肩部或关键道具手部交互 | 捕捉面部微表情、视线转折、心理距离最近 |
| **MCU** | 中近景 (Medium Close-Up) | 胸部以上 | 兼顾表情与肩颈、手部轻微动作，核心对话镜头 |
| **MS** | 中景 (Medium Shot) | 腰部以上 | 展现双人对峙互动、肢体语言交锋、空间关系交代 |
| **FS** | 全景 (Full Shot) | 完整全身及周围局部环境 | 交代完整武戏攻防姿态、位移步态与近身碰撞 |
| **WS** | 远景 (Wide Shot) | 人物在画面中占比约 1/4 至 1/3 | 强化人物与废墟/机库/建筑的空间对抗，建立环境氛围 |
| **EWS** | 大远景 (Extreme Wide Shot) | 人物微小如点，宏大环境为主 | 史诗感开场、好莱坞战争浩劫落点、废土孤寂 |

### 3.2 空间轴线原则 (180° Rule)
- **绝对禁忌**：同一场对话或打斗中，摄像机严禁在无过渡镜头的情况下跳过两角色连接的“虚拟动作轴线”（Action Axis）。
- **视线匹配 (Eyeline Match)**：若角色 A 位于画面左侧望向右侧，则对手角色 B 的反打镜头必须位于画面右侧望向左侧，维持正确的空间凝视因果。
- **好莱坞越轴解法**：如需越轴，必须在中间插入主观 POV 移动镜头、中性轴上正面镜头或强烈的 360° 环绕运镜带过。

### 3.3 导演级高阶机位调度与全量 132 段白模 Previs 工业映射总库 (132 Camera Moves Whitebox Taxonomy)
为彻底杜绝分镜中“镜头不知道怎么动、空间位移缺乏视差、AI 生成发飘抽搐”的致命缺陷，主系统**全盘深度吸收红猴子（hong hou zi）开源的 `camera-moves-whitebox` 全量 132 段带 2m 棋盘格与视差参考柱的标准运镜代码库**。
每个 Previs 均基于 1920×1080 / 24fps / 96帧（4.0秒标准窗口）带 2m 棋盘格地面与视差参考柱。在编写专业分镜时，**必须从以下八大门类、132 种标准运镜中选取精确标号**：

#### 一、基础运镜基准（001–008：场次覆盖的基础）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 光学视差与空间特征 |
|---|---|---|---|---|
| 001 | `Previs: [001_dolly_in]` | 推 | Dolly In | 沿 Z 轴匀速直线向前推进，前景参考柱视差向外扩张 |
| 002 | `Previs: [002_dolly_out]` | 拉 | Dolly Out | 沿 Z 轴匀速直线向后拉远，空间视野逐步扩大 |
| 003 | `Previs: [003_pan]` | 横摇 | Pan | 机位固定，镜头沿水平轴平滑左右旋转扫描 |
| 004 | `Previs: [004_tilt]` | 竖摇 | Tilt | 机位固定，镜头沿垂直轴平滑上下俯仰扫描 |
| 005 | `Previs: [005_truck]` | 横移 | Truck | 摄像机沿 X 轴水平平行滑动，产生强烈的横向移动视差 |
| 006 | `Previs: [006_crane_up]` | 升降 | Crane Up | 摄像机沿 Y 轴垂直垂直平稳抬升，视角由平视转为俯瞰 |
| 007 | `Previs: [007_orbit]` | 环绕 | Orbit | 摄像机以主体为圆心做 360° 正圆周环绕，空间背景高速流转 |
| 008 | `Previs: [008_follow]` | 跟随 | Follow | 摄像机锁定主体距离，伴随主体运动同步位移 |

#### 二、经典影视运镜（009–020：标志性镜头语言）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 光学视差与空间特征 |
|---|---|---|---|---|
| 009 | `Previs: [009_vertigo_pull]` | 眩晕变焦·拉 | Dolly Zoom (Pull) | 机位向前推进同时镜头光学拉焦变广，主体大小不变而背景纵深剧烈拉伸 |
| 010 | `Previs: [010_vertigo_push]` | 眩晕变焦·推 | Dolly Zoom (Push) | 机位向后拉远同时镜头光学推焦变窄，主体大小不变而背景空间剧烈压迫压缩 |
| 011 | `Previs: [011_zoom_in]` | 变焦推 | Zoom In | 机位不动，焦段由广角变长焦，纯光学放大无物理视差 |
| 012 | `Previs: [012_zoom_out]` | 变焦拉 | Zoom Out | 机位不动，焦段由长焦变广角，纯光学缩小无物理视差 |
| 013 | `Previs: [013_crash_zoom]` | 急推 | Crash Zoom | 极高加速度瞬间急推向角色瞳孔或接触点，制造剧烈顿挫冲击 |
| 014 | `Previs: [014_whip_pan]` | 甩摇 | Whip Pan | 极高角速度瞬间水平甩镜，中段画面产生严重运动模糊转场 |
| 015 | `Previs: [015_dutch_angle]` | 荷兰角 | Dutch Angle | 地平线倾斜 15°-30°，制造心理失衡、危机四伏与疯狂感 |
| 016 | `Previs: [016_barrel_roll]` | 滚转 | Barrel Roll | 镜头沿光轴做 360° 旋转，产生天地翻转的失重或战机翻滚感 |
| 017 | `Previs: [017_spiral_up]` | 螺旋上升 | Spiral Up | 摄像机一边环绕主体一边垂直拔高，螺旋轨迹升空 |
| 018 | `Previs: [018_high_descend]` | 俯瞰下降 | High Descend | 自高空云层/天花板垂直降落至角色头顶平视 |
| 019 | `Previs: [019_low_push]` | 仰拍推进 | Low Angle Push | 贴近地面仰角推进，赋予主体极其强烈的威严与压迫感 |
| 020 | `Previs: [020_handheld]` | 手持呼吸 | Handheld | 模拟摄影师肩扛手持的自然微幅呼吸晃动，强化真实纪实感 |

#### 三、进阶运镜（人物固定）（021–036：摇臂与复合空间轨迹）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 典型实战场景 |
|---|---|---|---|---|
| 021 | `Previs: [021_jib_advance_rise]` | 摇臂推进升起 | Jib Advance Rise | 推进同时大臂抬升，展现角色面前广袤的战场全貌 |
| 022 | `Previs: [022_crane_down]` | 升降下降 | Crane Down | 垂直下落至角色眼前，打断宏观视角进入微观对峙 |
| 023 | `Previs: [023_boom_over]` | 高位越过 | Boom Over | 摇臂从角色头顶正上方水平扫过，俯视地面阴影与受力点 |
| 024 | `Previs: [024_arc_inward]` | 内弧横移 | Arc Inward | 沿凹形弧线切向滑过主体，产生由远及近再及远的动态视差 |
| 025 | `Previs: [025_arc_outward]` | 外弧横移 | Arc Outward | 沿凸形弧线绕过主体，揭示侧后方潜在敌人 |
| 026 | `Previs: [026_bullet_time]` | 子弹时间 | Bullet Time | 时间极度冻结，摄像机高速环绕悬浮碎片或刀刃交击点 |
| 027 | `Previs: [027_fpv_dive]` | 穿越机俯冲 | FPV Dive | 极速无死角向下俯冲擦地拉起，机甲坠落或空中突袭 |
| 028 | `Previs: [028_fpv_reveal]` | 穿越机退掠 | FPV Reveal | 贴背倒飞掠过战壕，瞬间拉出宏大破败全景 |
| 029 | `Previs: [029_dolly_in_tilt]` | 推进上摇 | Dolly In + Tilt | 向前推行同时镜头缓慢上扬，展现仰望百米神明巨像 |
| 030 | `Previs: [030_dolly_in_dutch]` | 推进倾斜 | Dolly In + Dutch | 推进同时地平线渐进扭曲倾斜，精神崩溃或异化觉醒 |
| 031 | `Previs: [031_push_pull]` | 推拉往返 | Push-Pull | 短促推入后立即反向回拉，模拟肉体受创震荡弹回 |
| 032 | `Previs: [032_impact_shake]` | 撞击震动 | Impact Shake | 画面在重击接触瞬间产生 2-3 帧垂直方向强震与阻尼衰减 |
| 033 | `Previs: [033_handheld_lateral]`| 手持横移 | Handheld Lateral | 战火中奔跑跟拍，剧烈横向颠簸与地面扬尘干扰 |
| 034 | `Previs: [034_rack_focus]` | 焦点转移 | Rack Focus | 焦平面从前景枪口/水滴锐利平滑过渡至背景角色眼睛 |
| 035 | `Previs: [035_zoom_snap_out]` | 急拉变焦 | Snap Zoom Out | 瞬间从微距暴退至全景，揭露被包围的悬殊绝境 |
| 036 | `Previs: [036_vertigo_roll]` | 眩晕滚转 | Vertigo + Roll | 眩晕推拉叠加光轴 180° 翻滚，极度混乱的失重梦境 |

#### 四、带主体位移（037–048：人动相机动真实行进）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 典型实战场景 |
|---|---|---|---|---|
| 037 | `Previs: [037_walk_follow]` | 背跟步态 | Walk Follow | 摄像机居于角色正后方跟随行进，展现行进方向未知危险 |
| 038 | `Previs: [038_walk_lead]` | 前导退步 | Walk Lead | 摄像机居于角色正前方倒退滑行，观察角色前进步态与面部 |
| 039 | `Previs: [039_walk_side]` | 侧移跟拍 | Walk Side Track | 侧面平行平稳滑轨跟拍，呈现全身轮廓与环境向后流移 |
| 040 | `Previs: [040_walk_orbit]` | 环绕跟拍 | Walk Orbit | 在角色行进的同时围绕其身体螺旋环绕，动感极强 |
| 041 | `Previs: [041_walk_rise]` | 跟拍升高 | Walk Follow Rise | 跟随行进中机位逐渐拔高至俯瞰，展现前路断崖 |
| 042 | `Previs: [042_walk_past]` | 走过镜头 | Walk Past | 机位固定，角色由远及近跨过镜头前景离场 |
| 043 | `Previs: [043_walk_reveal]` | 拉开揭示 | Walk Reveal | 角色前行撞开前景遮挡，镜头横向拉开呈现新世界 |
| 044 | `Previs: [044_run_chase]` | 追跑跟击 | Run Chase | 高速剧烈奔跑追击，贴地尘土与近距脚步扬起 |
| 045 | `Previs: [045_run_fpv]` | 穿越机跟跑 | Run FPV Chase | 极低底盘贴地极速穿越障碍跟随跑动 |
| 046 | `Previs: [046_run_side]` | 侧面跟跑 | Run Side Track | 宽银幕高速侧移，双腿肌肉爆发力与冲刺惯性 |
| 047 | `Previs: [047_walk_approach]` | 迎面走近 | Walk Approach | 摄像机固定，角色迎面坚定逼近，直至填满画框 |
| 048 | `Previs: [048_diag_follow]` | 斜后跟拍 | Diagonal Follow | 处于角色左后方或右后方 45° 伴随突进 |

#### 五、经典电影大师镜头（049–072：大师级视听签名）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 艺术大师签名与情绪功能 |
|---|---|---|---|---|
| 049 | `Previs: [049_kubrick_push]` | 库布里克凝视 | Kubrick Push | 绝对中心对称、极度克制的一点透视冷酷慢推 |
| 050 | `Previs: [050_spielberg_push]`| 斯皮尔伯格惊叹 | Spielberg Push | 镜头推向仰视角色面孔，眼神光闪烁，目睹不可思议之物 |
| 051 | `Previs: [051_pull_out_reveal]`| 拉开揭示 | Pull Out Reveal | 从一个紧凑微观物体向外拉出，揭示庞大而残酷的整体局势 |
| 052 | `Previs: [052_slow_creep]` | 缓慢逼近 | Slow Creep | 几乎不可察觉的超慢爬行推进，制造无法呼吸的恐怖悬疑 |
| 053 | `Previs: [053_snap_push_hold]`| 急推定住 | Snap Push & Hold | 极速突进在眼眸前 0.1 秒死死咬住定格，断然决绝 |
| 054 | `Previs: [054_gods_eye]` | 上帝视角 | God's Eye | 90° 垂直正俯瞰，众生如蝼蚁棋盘，命运宿命感 |
| 055 | `Previs: [055_worms_eye]` | 虫视贴地 | Worm's Eye | 贴地向上极限大仰视，巨型机甲脚掌踏碎地面 |
| 056 | `Previs: [056_high_angle]` | 高角度俯拍 | High Angle | 角色处于画面低位，强化弱小、被审判与孤立无援 |
| 057 | `Previs: [057_low_angle_hero]`| 低角度英雄 | Low Angle Hero | 广角仰拍战立废墟之巅，肩甲披风迎风飞舞，英雄降临 |
| 058 | `Previs: [058_overhead_rotate]`| 顶视旋转 | Overhead Rotate | 垂直正俯瞰镜头伴随顺时针旋转，天地旋转迷乱感 |
| 059 | `Previs: [059_fisheye]` | 鱼眼畸变 | Fisheye | 极端桶形畸变超广角，空间被压弯，噩梦与精神异化 |
| 060 | `Previs: [060_telephoto]` | 长焦压缩 | Telephoto | 200mm 超长焦压缩热浪空气，千米外敌人与前景重叠 |
| 061 | `Previs: [061_deep_focus]` | 维伦纽瓦深焦 | Deep Focus | f/16 全景深，前景角色与五公里外巨构同样清晰平实 |
| 062 | `Previs: [062_wide_low]` | 广角低机位 | Wide Low | 24mm 贴地大透视，前冲拳风撕裂地表碎石 |
| 063 | `Previs: [063_macro_close]` | 微距特写 | Macro Close | 100mm 机械阀门齿轮、瞳孔血丝与汗滴蒸发 |
| 064 | `Previs: [064_push_through]` | 穿框推进 | Push Through Frame | 穿过断壁残垣的窗框、铁丝网孔隙滑入室内 |
| 065 | `Previs: [065_twist_around]` | 绕柱揭示 | Twist Around | 镜头绕过粗大混凝土承重柱，突兀撞见潜伏暗杀者 |
| 066 | `Previs: [066_corridor_advance]`| 长廊推进 | Corridor Advance | 狭长幽暗合金回廊单向直推，两旁故障灯光规律爆闪 |
| 067 | `Previs: [067_rise_reveal]` | 升起揭示 | Rise Reveal | 镜头从地面死者残骸垂直抬升，显露远方整座城市的毁灭 |
| 068 | `Previs: [068_reverse_angle]` | 正反打对镜 | Reverse Angle | 180° 轴线标准正反打对切，对话交锋核心支柱 |
| 069 | `Previs: [069_trunk_shot]` | 昆汀低位视角 | Trunk Shot | 自被开启的箱体/车尾箱/地窖内部仰视外界角色 |
| 070 | `Previs: [070_jump_cut]` | 跳切突变 | Jump Cut | 同机位抽帧跳切，表现时间飞逝、毒发痉挛或记忆碎裂 |
| 071 | `Previs: [071_face_close_low]`| 贴面仰拍 | Face Close Low | 贴身极近距离下颌仰拍，威严压迫与残暴审视 |
| 072 | `Previs: [072_pull_back_up]` | 诺兰撤离拉升 | Pull Back & Up | 斜向后方拉远并同时升高，角色独对苍凉浩劫世界 |

#### 六、经典电影大师镜头·续（073–084：时空与纵深奇观）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 艺术大师签名与情绪功能 |
|---|---|---|---|---|
| 073 | `Previs: [073_hitchcock_zoom]`| 希区柯克变焦 | Hitchcock Zoom | 经典眩晕空间扭曲，恐惧在视网膜上炸开 |
| 074 | `Previs: [074_piro_rotate]` | 皮洛横掠 | Piro Reveal | 水平高速掠过掩体转折点，瞬间拉出埋伏圈 |
| 075 | `Previs: [075_time_slice]` | 时间切片 | Time Slice | 动态切片停顿，光线与爆炸烟尘悬停在刀尖 |
| 076 | `Previs: [076_proscenium]` | 韦斯安德森舞台 | Proscenium | 严格正交几何平面视角，人物严谨置于对称轴心 |
| 077 | `Previs: [077_flat_symmetric]`| 平面对称 | Flat Symmetric | 消除透视感的扁平画卷，古朴工整或仪式肃穆 |
| 078 | `Previs: [078_vertigo_spin]` | 眩晕旋转 | Vertigo Spin | 变焦与 180° 自转复合，思维受精神控制或坠入深渊 |
| 079 | `Previs: [079_dolly_spin]` | 推轨旋进 | Dolly Spin | 推进同时机头以螺旋姿态旋转突入风暴中心 |
| 080 | `Previs: [080_peek_over]` | 越肩窥视 | Over-Shoulder | 极深景深越肩镜头，前景肩胛形成深邃暗影相框 |
| 081 | `Previs: [081_through_pillars]`| 柱间窥视 | Through Pillars | 摄像机在密集的立柱、栅栏间横移滑过，造成断续视线遮挡 |
| 082 | `Previs: [082_reveal_tilt_up]` | 上摇揭示 | Tilt Up Reveal | 镜头自血迹斑斑的靴子缓慢上摇至持刀者冷酷眼眸 |
| 083 | `Previs: [083_pull_focus_deep]`| 深焦游移 | Deep Rack Focus | 焦点在 1m、10m、100m 三重景深层级之间自如调动 |
| 084 | `Previs: [084_scale_reveal]` | 尺度揭示 | Scale Reveal | 从人类近景滑出，沿建筑立面无尽滑向百米泰坦头颅 |

#### 七、快速镜头（085–100：高动态速度与冲击）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 高动态打戏与追逐应用 |
|---|---|---|---|---|
| 085 | `Previs: [085_fast_truck]` | 快速横移 | Fast Truck | 极速滑轨伴随两台战车齐头并进对轰 |
| 086 | `Previs: [086_whip_snap]` | 急速甩镜 | Whip Snap | 毫秒级猛烈甩头，瞬间锁定突如其来的狙击弹道 |
| 087 | `Previs: [087_snap_zoom_in]` | 急速推焦 | Snap Zoom In | 光学急变焦暴推，锁定远方敌人扣动扳机的食指 |
| 088 | `Previs: [088_snap_zoom_out]` | 急速拉焦 | Snap Zoom Out | 光学急变焦暴拉，展现爆炸在眼前掀起的宏大冲击波 |
| 089 | `Previs: [089_fast_pass]` | 快速掠过 | Fast Pass | 机甲以数倍音速自镜头前 0.5 米呼啸擦过，气浪吹翻镜头 |
| 090 | `Previs: [090_crash_zoom_fast]`| 急推撞击 | Crash Zoom Fast | 拳锋重击下颌刹那镜头急暴推，引爆视觉冲击核心 |
| 091 | `Previs: [091_whip_double]` | 连环甩镜 | Double Whip | 连续两次高速换向甩镜，交代三人三角互殴 |
| 092 | `Previs: [092_rapid_dolly]` | 急速推轨 | Rapid Dolly | 贴地滑车以百公里时速向前猛冲突入敌阵 |
| 093 | `Previs: [093_dive_bomb]` | 俯冲轰炸 | Dive Bomb | 自千米高空垂直俯冲，在贴近地表 2 米瞬间改平拉起 |
| 094 | `Previs: [094_rocket_rise]` | 火箭升空 | Rocket Rise | 伴随导弹发射垂直拔地而起，镜头穿透多层烟雾 |
| 095 | `Previs: [095_side_wipe]` | 横向擦除 | Side Wipe | 高速行进的前景列车或车体横向完全遮挡画面的瞬间切镜 |
| 096 | `Previs: [096_hyperspeed]` | 超速穿越 | Hyperspeed | 镜头穿过激光弹雨与高频等离子能量走廊 |
| 097 | `Previs: [097_slingshot]` | 弹射拉扯 | Slingshot | 类似弹弓轨迹，先蓄力滞后随即超高速弹射反超 |
| 098 | `Previs: [098_barrel_burst]` | 崩解甩出 | Barrel Burst | 被重拳击中时镜头伴随受力方一同崩解旋转甩飞 |
| 099 | `Previs: [099_zip_lateral]` | 瞬时横掠 | Zip Lateral | 毫秒级横向瞬移位移，展现刺客鬼魅身法 |
| 100 | `Previs: [100_strobe_run]` | 频闪奔行 | Strobe Run | 在强光爆炸或防空警报频闪交替中高速冲锋 |

#### 八、实用工业镜头语法（101–132：长篇叙事必备工具箱）
| 标号 | Previs 代码 | 中文名称 | 英文名称 | 导演讲戏与工程落地功能 |
|---|---|---|---|---|
| 101 | `Previs: [101_establishing_pull]`| 定场拉远 | Establishing Pull | 从室内局部缓慢拉出至整座废弃工业基地的全貌，交代时空 |
| 102 | `Previs: [102_master_wide]` | 全景主镜 | Master Wide | 涵盖整场戏所有人物空间相对位置的基石主镜头 |
| 103 | `Previs: [103_medium_push]` | 中景推进 | Medium Push | 对峙双方开始言语试探，镜头平稳入戏 |
| 104 | `Previs: [104_close_up_push]` | 特写推进 | Close-Up Push | 逼问至核心秘密时推向角色额头冷汗与动摇眼神 |
| 105 | `Previs: [105_insert_detail]` | 插入细节 | Insert Detail | 插入战术手势、引信拔出、怀表滴答声特写 |
| 106 | `Previs: [106_reaction_drift]` | 反应漂移 | Reaction Drift | 主讲人对白时，摄像机缓慢平移捕捉旁观者的微妙表情变化 |
| 107 | `Previs: [107_eyeline_look]` | 视线匹配 | Eyeline Match | 严谨的视线高低角匹配，仰视者与俯视者严密对准 |
| 108 | `Previs: [108_reverse_pair]` | 反打对镜 | Reverse Pair | 构图比例与焦段完全对称的双人对白正反打 |
| 109 | `Previs: [109_ots_clean]` | 过肩·净 | OTS Clean | 前景肩膀虚化干净，视觉重量 100% 聚焦于说话者面孔 |
| 110 | `Previs: [110_ots_reverse]` | 过肩反打 | OTS Reverse | 翻转至对手过肩位，保持焦段、光比与轴线连续 |
| 111 | `Previs: [111_dirty_two]` | 双人脏镜 | Dirty Two-Shot | 前景故意保留另一角色的后脑勺与头发遮挡，增强压抑偷窥感 |
| 112 | `Previs: [112_conversation_arc]`| 对话弧线 | Conversation Arc | 摄像机沿圆弧在两人之间流畅滑移，平滑切换说话主导权 |
| 113 | `Previs: [113_reaction_pan]` | 反应摇 | Reaction Pan | 从发话者迅速摇向受惊吓者的脸部特写 |
| 114 | `Previs: [114_group_scan]` | 群体扫视 | Group Scan | 慢速横摇依次扫过谈判桌前各个阵营代表的冷峻面孔 |
| 115 | `Previs: [115_match_cut_push]` | 匹配推进 | Match Cut Push | 前一镜推向瞳孔，后一镜自太阳火球拉出，跨时空形状匹配 |
| 116 | `Previs: [116_invisible_cut]` | 无缝接续 | Invisible Cut | 利用角色背影完全填满黑屏的瞬间完成隐形剪辑 |
| 117 | `Previs: [117_swish_clean]` | 干净甩镜 | Clean Swish | 借由快速横扫动作干净利落地切换至完全不同的第二场景 |
| 118 | `Previs: [118_wipe_reveal]` | 遮挡擦除 | Wipe Reveal | 移动的战术装甲车身划过画框，带出隐藏在车后的战友 |
| 119 | `Previs: [119_whip_out]` | 甩出模糊 | Whip Out | 战斗终结瞬间猛烈甩离现场，留给观众想象空间 |
| 120 | `Previs: [120_hold_dissolve]` | 叠化定住 | Hold for Dissolve | 镜头完全静止保持 2 秒，等待与下一场戏叠化融合 |
| 121 | `Previs: [121_pov_walk]` | 主观行进 | POV Walk | 晃动的主观脚步视线，枪口微动，身临其境搜查废弃大楼 |
| 122 | `Previs: [122_pov_look]` | 主观环视 | POV Look Around | 濒死或昏迷醒来时，视线模糊且艰难转动打量四周 |
| 123 | `Previs: [123_blind_reveal]` | 遮挡揭开 | Blind Reveal | 缓缓拉开百叶窗，阳光透过缝隙投射在满布伤痕的脸上 |
| 124 | `Previs: [124_door_crack]` | 门缝窥视 | Door Crack | 自虚掩的门缝向外窥视，两边形成厚重黑色遮幅 |
| 125 | `Previs: [125_negative_space]`| 负空间留白 | Negative Space | 角色孤零零缩在画面右下角 1/9 处，大面积留白压迫 |
| 126 | `Previs: [126_diagonal_frame]`| 对角线构图 | Diagonal Frame | 倒塌的钢梁横贯画框对角线，分割生死两界 |
| 127 | `Previs: [127_breathing_push]`| 呼吸推进 | Breathing Push | 推进速度伴随人物沉重粗粝的呼吸节奏微幅起伏 |
| 128 | `Previs: [128_tremor_hold]` | 颤抖定镜 | Tremor Hold | 机位静止但在剧烈爆炸冲击下产生极高频微颤抖动 |
| 129 | `Previs: [129_heartbeat_zoom]`| 心跳脉冲 | Heartbeat Zoom | 伴随心跳重音以微小振幅做有节奏的轻微推拉 |
| 130 | `Previs: [130_slow_ramp]` | 慢动作暗示 | Slow Ramp | 速度悄然放慢至 1/2 倍速，强调致命暗杀前夕的死寂 |
| 131 | `Previs: [131_speed_ramp]` | 速度渐增 | Speed Ramp | 自极慢起手瞬间加速至超音速，完成出鞘斩杀 |
| 132 | `Previs: [132_freeze_push]` | 定格推进 | Freeze Push | 物理时间彻底定格，摄像机在凝固的弹雨中持续前推 |

### 3.4 主客观视角调度法则 (POV & Objective Rules)
- **POV 格式规范**：必须显明标注角色身份，例如 `[角色名 POV 第一人称视角]`。
- **画面要素界定**：POV 镜头严禁出现该角色完整正脸；画面前景必须包含该角色眼睛高度所见的视线焦距，可包含手部、手持武器边缘、战损机甲 HUD 面罩投影。
- **主客交替因果**：主观 POV 用于制造沉浸式压迫与危险逼近，随即硬切回第三人称中远景交代攻击结果与物理受力击飞。

---

## 4. 镜头节拍与时长密度速查表 (Rhythm & Density)

| 镜头节奏分类 | 单镜头推荐时长 | 典型适用场景 | 戏剧张力特征 |
|---|---|---|---|
| **极限快剪 (Blitz Cut)** | **1.0 - 1.8 秒** | 战车追逐碰撞、连续格挡拆招、爆炸冲击波逃生 | 肾上腺素飙升、高频信息灌注 |
| **戏剧对抗 (Dramatic Pace)** | **2.0 - 3.5 秒** | 逼问对话、枪口对峙、关键道具交接、战术指令 | 紧迫感、蓄势待发、交锋张力 |
| **沉淀凝视 (Breathing Shot)** | **4.0 - 6.0 秒** | 战后废墟回望、战友牺牲沉默、眼神心理挣扎、环境空镜 | 留白深邃、心理共鸣、余韵悠长 |
| **史诗长调度 (Epic Tracking)** | **6.0 秒以上** | 军队集结横移、单人深入敌阵连续推进长镜头 | 空间压迫感、沉浸式世界观展现 |

---

## 5. 标准分镜输出排版协议 (The Storyboard Blueprint)

每一个生成的镜头必须严格遵循以下单行语法结构输出（**强制带 Previs 白模代码与微表情/武指锚点**）：

```markdown
- **[镜头ID]｜绝对 [mm:ss-mm:ss]｜切片内 [0.0s-X.Xs]｜Previs: [[Previs代码]]｜EX: [[EX编号]]**：[景别｜视角类型｜机位状态｜拍摄角度与朝向] 视觉画面描述（主体起始状态、动作轨迹、物理受力反馈、环境粒子交互）... {台词} 『旁白VO』 <音效> (音乐) 【字幕】 [转场方式]
```

### 真实生产范例：

```markdown
### 第一幕：集结的钢铁（总时长：00:00 - 01:00）

#### 切片 SEG01：00:00 - 00:10（MiniMax H3 10秒片段）
- **FILM-S01-SH001｜绝对 00:00-00:03｜切片内 0.0s-3.0s｜Previs: [018_high_descend]｜EX: []**：[EWS大远景｜第三人称客观视角｜俯瞰下降长镜头｜俯视转平视] 浓烟滚滚的末日地平线，镜头自高空阴云裂缝穿透下降。夕阳投射下血红色耶稣光，三台百米级残破重型机甲静静矗立在燃烧的废墟之上，金属表面覆盖着厚重烟灰与焦黑灼痕。 (低沉深邃的大提琴长音与管风琴和弦缓缓升起) [硬切]
- **FILM-S01-SH002｜绝对 00:03-00:07｜切片内 3.0s-7.0s｜Previs: [007_orbit]｜EX: [EX-S01-B01]**：[MCU中近景｜第三人称客观视角｜低角度弧形环绕｜仰拍] 镜头自下而上低角度高速环绕林远。林远身披战损外骨骼装甲立于悬崖边缘，右脸颊带有渗血划痕，逆光勾勒出冷峻下颌线条，强风吹卷着碎发。他缓缓抬起沉重的机械右臂，五指握紧成拳。 [EX-S01-B01: 林远下颌紧绷，喉结微弱滑动，冷冽的瞳孔中映出远方天际线的火光。] <狂风呼啸声夹杂着远处断续的防空警报低鸣> [硬切]
- **FILM-S01-SH003｜绝对 00:07-00:10｜切片内 7.0s-10.0s｜EX: []**：[ECU大特写｜第三人称客观视角｜固定镜头｜平视] 外骨骼装甲右肘关节微米级伺服电机瞬间加压，液压油管剧烈膨胀颤动，排气阀喷射出一道高温白炽气流，合金齿轮严密咬合锁死。 <重型液压阀门高压泄气刺鸣声与金属沉闷咬合喀嚓声> [硬切]
```

---

## 6. 下游交接检查门禁 (Validation Checklist)

在分镜表交付给下游（资产设计、表演适配器与 H3 编译器）前，必须确认：
1. **时间戳严格守恒**：切片内时间戳必须首尾闭合（例如 `0.0s-3.0s` 接 `3.0s-7.0s`），总时长严格等于切片声明时长。
2. **角色与道具专有名词统一**：严禁中途将“林远”写成“那个男人/军官”，全程保持不可变专名。
3. **镜头内声音五元组齐全**：精确使用 `{台词}`、`『旁白』`、`<音效>`、`(音乐)`、`【字幕】` 语义符号，为 MiniMax H3 双轨声场编译提供纯净原料。
4. **EX 节拍映射挂载**：凡涉及微表情的镜头，必须显式标注关联的 `EX-Sxx-Bxx`；若纯动作或风景，明确标记 `EX: []`。
