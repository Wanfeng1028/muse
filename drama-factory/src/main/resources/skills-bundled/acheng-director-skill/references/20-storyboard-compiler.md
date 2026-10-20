# 20｜分镜编译、132 运镜与双时长装箱

## 时间模型

`production_total_duration` 是作品总秒数；`generation_clip_duration` 是每一 Segment 的实际秒数；`generation_clip_limit` 是本次目标入口的计划上限。全部精确计算用 `fps_num/fps_den` 与整数 `start_frame/end_frame`，区间左闭右开。秒数是帧数乘 fps_den/fps_num 的显示值，不能用四舍五入后的字符串累加。

全局镜头 ID 不因装箱改变；H3 `[Shot 1]` 是切片局部编号，在每段重置。帧号不重置。一个镜头跨生成窗必须导演明确拆成两个有承接的镜头或连续片段，并登记父镜头，不由 pack 偷切动作。

本制作合同默认generation_clip_min=4、generation_clip_limit=15；可缩小范围但不得突破4–15秒。装箱在已批准镜头边界搜索覆盖全部镜头的合法分区，优先较少片段；贪心留下不足4秒尾段时回退重排。任一镜头超窗或不存在合法分区时报错；由导演调整动作安全边界，或明确设计生成把手及剪辑采用区间，不能悄悄拖长故事。实际入口支持的范围另核实。

例如 24 fps、90 秒共 2160 帧；最大窗 14 秒为 336 帧。先按事件切出镜头后打包，而不是机械拿 6×14+6 秒决定故事。声音跨切片保存 event_id、全局音频区间及后期接点，避免重复词或吞字。

## 每镜必须回答的摄影问题

1. 新信息是什么，观众本镜结束必须读懂什么？
2. 相机在哪个世界位置、朝哪里、与角色距离多大？
3. 镜头走哪条路径，幅度和速度如何变化，何时稳定？
4. 前景参照／主体／远景的视差如何区分推轨与变焦？
5. 接触、面部或道具哪一个优先保持清楚？
6. 本镜尾态如何进入下一镜，是否越轴，过渡证据在哪？

`camera` 保存 `previs_id/movement/lens_mm/sensor_basis/height_m/path/target/easing/focus/shutter_angle`。其中路径为本项目改编参数，不能冒称原库真实测量。白模编号只提供动作家族；模型通常不理解“用 052”，因此最终提示词必须展开可见运动。

## 焦段、景别、动作可见性矩阵

| 全画幅等效焦段 | 建议观察距离与景别 | 叙事功能 | 避错 |
|---|---|---|---|
| 12–16 mm | 大空间 EWS/WS，距离按地标决定 | 强纵深与前景掠过 | 脸靠边会拉伸；不能为巨物把相机贴玩具 |
| 18–24 mm | WS/FS，保留脚与地面 | 冲刺、落地、巨物接触环境 | 保留地平线，避免每拍旋转 |
| 28–35 mm | FS/MS，显示两人完整接触链 | 格挡、入身、道具交接 | 对手与接触点不能被前景肩膀盖住 |
| 40–55 mm | MS/MCU，自然观看关系 | 对话与中距离动作 | 透视由机位决定，不自动“真实” |
| 65–85 mm | MCU/CU，明确焦点距离 | 眼睑、吞咽、手指控制 | 不把前后人物都写成同一浅景深锐面 |
| 90–100 mm | CU/ECU 或真正微距镜 | 接触纹理、机械锁扣 | 100 mm 不自动等于微距；注明放大率意图 |

景别是取景范围，不由焦距单独确定。画面关键线索小于像素可读尺寸时换镜头，不靠“微米级细节”。动作镜头默认保持一条主要相机运动和一个追踪锚点；复合运动必须有分相位路径。

## 180° 轴线、角色钉子与复杂环绕

动作轴线由双方世界位置定义。每个角色记录屏幕归一化中心 `[x,y]`（左上 0,0）、可见占比、深度层、身体方向、视线目标、持械手与刃口方向。镜头跨轴后屏幕左右可能合法交换，须有连续移动或轴上中性镜头解释；单纯烟雾遮住画面不是自动满足空间解释。

360° 低机位环绕的本项目示例：中心为角色骨盆地面投影，半径 4 m，高 0.6 m，28 mm；0–1 s 加速至 90°/s，1–3 s 匀速，3–4 s 减速落在 270°方向。实际上只走 270°，不能名为 360°完整一周；若要完整一周必须重新分配路程。相机对角色上胸，地平线锁滚转 0°，近柱与远桁架形成视差，衣摆运动来自人物／环境而非相机。选 007 作为参照但明确改编角度和速度，不能把 4 秒源片拉伸后仍称原速。

Crash zoom 只改变焦距；rapid dolly 移动机身；dolly zoom 同时反向变焦和移动，以主体近似等大为目标。Rack focus 改变焦点，不自动改变机位。子弹时间、冻结和速度坡度是时间表现方案，不能同时要求所有对象真实匀速。

## Previs 绑定与来源限制

原库是 132 段 4 秒白模参照，2 m 棋盘格和参考柱用于读视差。其目录混合运镜、构图、焦点、剪辑及节拍，不能谎称全是独立可执行轨迹代码。静态镜可绑定构图参照 102 并显式写 `movement: static`、`adaptation: composition-only`；不得为了命中率强行推镜。

目录和 data/camera-moves.json 双向校验。`previs_id` 必须是三位字符串 001–132；记录 source_file 与改编说明。源片是否存在由媒体清单单独证明；目录命中率不等于已经观看全部视频。官方原组边界是 001–008、009–020、021–036、037–048、049–072、073–084、085–100、101–132。任务书所列分组与源库不符，编号以源库为准。

## 16 格与 Shot 的关系

格子是时刻／相位，不自动是一次切镜。一镜四格可以是同一镜位下的预备、发力、接触和尾态。若格子从远景突然跳大特写，则应建立新 Shot，或明确物理可达的推进路径。每格有 `panel/shot_id/frame/phase/description`；frame 必须位于对应镜头半开区间，末格取最后一帧而不是镜头外边界。

先验证时间闭合，再绑定格子和素材版本，最后编译提示词。不要固定“16 格=14 秒=4 次切镜”。本包样例完整演示不同总时长与切片数。

## 全量 132 条原作者索引

下列保留 hong hou zi 原编号、文件名与名称。不是对其视频质量结论的代验；媒体验证见独立报告。各镜头的工程执行参数由本项目 ShotSpec 给出。

| ID | 原文件 | 中文 | 英文 |
|---|---|---|---|
| 001 | `01_dolly_in.mp4` | 推 | Dolly In |
| 002 | `02_dolly_out.mp4` | 拉 | Dolly Out |
| 003 | `03_pan.mp4` | 横摇 | Pan |
| 004 | `04_tilt.mp4` | 竖摇 | Tilt |
| 005 | `05_truck.mp4` | 横移 | Truck |
| 006 | `06_crane_up.mp4` | 升降 | Crane Up |
| 007 | `07_orbit.mp4` | 环绕 | Orbit |
| 008 | `08_follow.mp4` | 跟随 | Follow |
| 009 | `09_vertigo_pull.mp4` | 眩晕变焦·拉 | Dolly Zoom (Pull) |
| 010 | `10_vertigo_push.mp4` | 眩晕变焦·推 | Dolly Zoom (Push) |
| 011 | `11_zoom_in.mp4` | 变焦推 | Zoom In |
| 012 | `12_zoom_out.mp4` | 变焦拉 | Zoom Out |
| 013 | `13_crash_zoom.mp4` | 急推 | Crash Zoom |
| 014 | `14_whip_pan.mp4` | 甩摇 | Whip Pan |
| 015 | `15_dutch_angle.mp4` | 荷兰角 | Dutch Angle |
| 016 | `16_barrel_roll.mp4` | 滚转 | Barrel Roll |
| 017 | `17_spiral_up.mp4` | 螺旋上升 | Spiral Up |
| 018 | `18_high_descend.mp4` | 俯瞰下降 | High Descend |
| 019 | `19_low_push.mp4` | 仰拍推进 | Low Angle Push |
| 020 | `20_handheld.mp4` | 手持 | Handheld |
| 021 | `21_jib_advance_rise.mp4` | 摇臂推进升起 | Jib Advance Rise |
| 022 | `22_crane_down.mp4` | 升降下降 | Crane Down |
| 023 | `23_boom_over.mp4` | 高位越过 | Boom Over |
| 024 | `24_arc_inward.mp4` | 内弧横移 | Arc Inward |
| 025 | `25_arc_outward.mp4` | 外弧横移 | Arc Outward |
| 026 | `26_bullet_time.mp4` | 子弹时间 | Bullet Time |
| 027 | `27_fpv_dive.mp4` | 穿越机俯冲 | FPV Dive |
| 028 | `28_fpv_reveal.mp4` | 穿越机退掠 | FPV Reveal |
| 029 | `29_dolly_in_tilt.mp4` | 推进上摇 | Dolly In + Tilt |
| 030 | `30_dolly_in_dutch.mp4` | 推进倾斜 | Dolly In + Dutch |
| 031 | `31_push_pull.mp4` | 推拉往返 | Push-Pull |
| 032 | `32_impact_shake.mp4` | 撞击震动 | Impact Shake |
| 033 | `33_handheld_lateral.mp4` | 手持横移 | Handheld Lateral |
| 034 | `34_rack_focus.mp4` | 焦点转移 | Rack Focus |
| 035 | `35_zoom_snap_out.mp4` | 急拉变焦 | Snap Zoom Out |
| 036 | `36_vertigo_roll.mp4` | 眩晕滚转 | Vertigo + Roll |
| 037 | `37_walk_follow.mp4` | 背跟 | Walk Follow |
| 038 | `38_walk_lead.mp4` | 前导 | Walk Lead |
| 039 | `39_walk_side.mp4` | 侧移跟拍 | Walk Side Track |
| 040 | `40_walk_orbit.mp4` | 环绕跟拍 | Walk Orbit |
| 041 | `41_walk_rise.mp4` | 跟拍升高 | Walk Follow Rise |
| 042 | `42_walk_past.mp4` | 走过镜头 | Walk Past |
| 043 | `43_walk_reveal.mp4` | 拉开揭示 | Walk Reveal |
| 044 | `44_run_chase.mp4` | 追跑 | Run Chase |
| 045 | `45_run_fpv.mp4` | 穿越机跟拍 | Run FPV Chase |
| 046 | `46_run_side.mp4` | 侧面跟跑 | Run Side Track |
| 047 | `47_walk_approach.mp4` | 迎面走近 | Walk Approach |
| 048 | `48_diag_follow.mp4` | 斜后跟拍 | Diagonal Follow |
| 049 | `49_kubrick_push.mp4` | 库布里克凝视 | Kubrick Push |
| 050 | `50_spielberg_push.mp4` | 斯皮尔伯格惊叹 | Spielberg Push |
| 051 | `51_pull_out_reveal.mp4` | 拉开揭示 | Pull Out Reveal |
| 052 | `52_slow_creep.mp4` | 缓慢逼近 | Slow Creep |
| 053 | `53_snap_push_hold.mp4` | 急推定住 | Snap Push & Hold |
| 054 | `54_gods_eye.mp4` | 上帝视角 | God's Eye |
| 055 | `55_worms_eye.mp4` | 虫视贴地 | Worm's Eye |
| 056 | `56_high_angle.mp4` | 高角度俯拍 | High Angle |
| 057 | `57_low_angle_hero.mp4` | 低角度英雄 | Low Angle Hero |
| 058 | `58_overhead_rotate.mp4` | 顶视旋转 | Overhead Rotate |
| 059 | `59_fisheye.mp4` | 鱼眼畸变 | Fisheye |
| 060 | `60_telephoto.mp4` | 长焦压缩 | Telephoto |
| 061 | `61_deep_focus.mp4` | 深焦 | Deep Focus |
| 062 | `62_wide_low.mp4` | 广角低机位 | Wide Low |
| 063 | `63_macro_close.mp4` | 微距特写 | Macro Close |
| 064 | `64_push_through.mp4` | 穿框推进 | Push Through Frame |
| 065 | `65_twist_around.mp4` | 绕过遮挡揭示 | Twist Around |
| 066 | `66_corridor_advance.mp4` | 长廊推进 | Corridor Advance |
| 067 | `67_rise_reveal.mp4` | 升起揭示 | Rise Reveal |
| 068 | `68_reverse_angle.mp4` | 反打镜头 | Reverse Angle |
| 069 | `69_trunk_shot.mp4` | 后备箱视角 | Trunk Shot |
| 070 | `70_jump_cut.mp4` | 跳切 | Jump Cut |
| 071 | `71_face_close_low.mp4` | 面部近距仰拍 | Face Close Low |
| 072 | `72_pull_back_up.mp4` | 拉远升高 | Pull Back & Up |
| 073 | `73_hitchcock_zoom.mp4` | 希区柯克变焦 | Hitchcock Zoom |
| 074 | `74_piro_rotate.mp4` | 皮洛横掠 | Piro Reveal |
| 075 | `75_time_slice.mp4` | 时间切片 | Time Slice |
| 076 | `76_proscenium.mp4` | 舞台正视 | Proscenium |
| 077 | `77_flat_symmetric.mp4` | 平面化对称 | Flat Symmetric |
| 078 | `78_vertigo_spin.mp4` | 眩晕旋转 | Vertigo Spin |
| 079 | `79_dolly_spin.mp4` | 推轨旋进 | Dolly Spin |
| 080 | `80_peek_over.mp4` | 越肩窥视 | Over-Shoulder |
| 081 | `81_through_pillars.mp4` | 柱间窥视 | Through Pillars |
| 082 | `82_reveal_tilt_up.mp4` | 上摇揭示 | Tilt Up Reveal |
| 083 | `83_pull_focus_deep.mp4` | 深焦焦点游移 | Deep Rack Focus |
| 084 | `84_scale_reveal.mp4` | 尺度揭示 | Scale Reveal |
| 085 | `85_fast_truck.mp4` | 快速横移 | Fast Truck |
| 086 | `86_whip_snap.mp4` | 急速甩镜 | Whip Snap |
| 087 | `87_snap_zoom_in.mp4` | 急速推焦 | Snap Zoom In |
| 088 | `88_snap_zoom_out.mp4` | 急速拉焦 | Snap Zoom Out |
| 089 | `89_fast_pass.mp4` | 快速掠过 | Fast Pass |
| 090 | `90_crash_zoom_fast.mp4` | 急推撞击 | Crash Zoom Fast |
| 091 | `91_whip_double.mp4` | 连环甩镜 | Double Whip |
| 092 | `92_rapid_dolly.mp4` | 急速推轨 | Rapid Dolly |
| 093 | `93_dive_bomb.mp4` | 俯冲轰炸 | Dive Bomb |
| 094 | `94_rocket_rise.mp4` | 火箭升空 | Rocket Rise |
| 095 | `95_side_wipe.mp4` | 横向擦除 | Side Wipe |
| 096 | `96_hyperspeed.mp4` | 超速穿越 | Hyperspeed |
| 097 | `97_slingshot.mp4` | 弹射 | Slingshot |
| 098 | `98_barrel_burst.mp4` | 崩解甩出 | Barrel Burst |
| 099 | `99_zip_lateral.mp4` | 瞬时横掠 | Zip Lateral |
| 100 | `100_strobe_run.mp4` | 频闪奔行 | Strobe Run |
| 101 | `101_establishing_pull.mp4` | 定场拉远 | Establishing Pull |
| 102 | `102_master_wide.mp4` | 全景主镜 | Master Wide |
| 103 | `103_medium_push.mp4` | 中景推进 | Medium Push |
| 104 | `104_close_up_push.mp4` | 特写推进 | Close-Up Push |
| 105 | `105_insert_detail.mp4` | 插入细节 | Insert Detail |
| 106 | `106_reaction_drift.mp4` | 反应镜头 | Reaction Drift |
| 107 | `107_eyeline_look.mp4` | 视线匹配 | Eyeline Match |
| 108 | `108_reverse_pair.mp4` | 反打对镜 | Reverse Pair |
| 109 | `109_ots_clean.mp4` | 过肩·净 | OTS Clean |
| 110 | `110_ots_reverse.mp4` | 过肩反打 | OTS Reverse |
| 111 | `111_dirty_two.mp4` | 双人脏镜 | Dirty Two-Shot |
| 112 | `112_conversation_arc.mp4` | 对话弧线 | Conversation Arc |
| 113 | `113_reaction_pan.mp4` | 反应摇 | Reaction Pan |
| 114 | `114_group_scan.mp4` | 群体扫视 | Group Scan |
| 115 | `115_match_cut_push.mp4` | 匹配推进 | Match Cut Push |
| 116 | `116_invisible_cut.mp4` | 无缝接续 | Invisible Cut |
| 117 | `117_swish_clean.mp4` | 干净甩镜 | Clean Swish |
| 118 | `118_wipe_reveal.mp4` | 遮挡擦除 | Wipe Reveal |
| 119 | `119_whip_out.mp4` | 甩出模糊 | Whip Out |
| 120 | `120_hold_dissolve.mp4` | 叠化定住 | Hold for Dissolve |
| 121 | `121_pov_walk.mp4` | 主观行进 | POV Walk |
| 122 | `122_pov_look.mp4` | 主观环视 | POV Look Around |
| 123 | `123_blind_reveal.mp4` | 遮挡揭开 | Blind Reveal |
| 124 | `124_door_crack.mp4` | 门缝窥视 | Door Crack |
| 125 | `125_negative_space.mp4` | 负空间留白 | Negative Space |
| 126 | `126_diagonal_frame.mp4` | 对角线构图 | Diagonal Frame |
| 127 | `127_breathing_push.mp4` | 呼吸推进 | Breathing Push |
| 128 | `128_tremor_hold.mp4` | 颤抖定镜 | Tremor Hold |
| 129 | `129_heartbeat_zoom.mp4` | 心跳脉冲 | Heartbeat Zoom |
| 130 | `130_slow_ramp.mp4` | 慢动作暗示 | Slow Ramp |
| 131 | `131_speed_ramp.mp4` | 速度渐增 | Speed Ramp |
| 132 | `132_freeze_push.mp4` | 定格推进 | Freeze Push |
