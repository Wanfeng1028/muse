# PROMPT PACK: NEON JUMP（Opus 5.5）

来源：Google Drive 分享的 PDF《Prompt Neon Jump Opus 5.5》（Clawd Motion Lab 出品，5 页）；原 PDF 同目录存档 `neon-jump-prompt-pack.pdf`。
内容：一支 14 秒无缝循环角色短片的完整提示词包——体素吉祥物开红色跑车穿霓虹隧道、冲出峡谷、墨镜翻下、飞跃断桥，空中时间慢到 6%，落地砸在节拍上火花四溅，然后回到第一帧。每一帧都是 Claude Opus 5.5 按提示词写出的 Blender 场景。

规格：14.0s / 30fps / 1920x1080 / 无缝循环 420 帧 / 137.14 BPM，8 小节 = 14 秒。

## 公式（第 1 页）

1. **一个世界，反复用**：隧道、高速、断桥、塔楼是同一段场景实例化重复，所以循环不需要剪。
2. **节拍决定物理**：先选速度让 8 小节填满 14 秒；起跳唇和落地点精确落在第 12 拍和第 20 拍。
3. **慢动作慢的是空间不是时间**：空中时间重映射的是距离、不是重力，抛物线形状不变，时钟慢到 6%。
4. **吉祥物从 logo 来**：HERO 的每个体素都来自终端 logo 网格：12x8 身体、 slit 眼、短臂、四条腿。
5. **填满脸，别填城市**：车里装一盏小灯对着 HERO；霓虹只用来画反射。
6. **用测的，别用猜的**：接缝用帧差检查，声音用频谱图 + ffmpeg ebur128 测响度。

分段：0.63s 隧道 / 2.47s 冲出 / 4.97s 斜坡 / 6.47s 慢镜 / 8.83s 落地 / 13.30s 回环。

---

## 主提示词（第 2 页，copy-ready，320 词）

使用方式：原样粘进运行 Opus 5.5 的 Claude Code（effort high），本机装好 Blender 5 与 ffmpeg。它会把场景写成 Python，无头 GPU 渲染，并自查静帧。

**BRAND**
HERO: voxel mascot 18x10, body 12x8 at (3,0), arms 2x2 at (1,4) (15,4), legs 1x2 at x 4 6 11 13 row 8, eye slits 0F0F0F 1x2 at (5,2) (12,2), 6 deep, beveled, orange D97757
RIDE: open roadster, low wedge nose, full-width tail light, candy red 6B0A0F clearcoat, three hidden rear thrusters, orange underglow
PROP: pixel "deal with it" shades, white glints, parked on HERO's head
SET: neon tunnel through a megastructure, then a highway in a night canyon of towers, kicker ramp, missing bridge span, wet asphalt
SIGNS: "CLAUDE CODE" on the tunnel wall, giant pixel-HERO billboard, ROAD CLOSED gantry
PALETTE: cyan 14B4FF, magenta FF1A78, ring FF6124, sodium FFB873, sky 0D0612

**FORMAT:** Blender 5 Python, Cycles GPU, 1920x1080, 30 fps, 14.0 s seamless loop: the world repeats every period P so frame 420 hands off to frame 1. One timeline.py drives picture and sound; 137.14 BPM, 8 bars = 14 s.

**BEATS (s):** 0 HERO drives at the lens through the tunnel, shades up, rings rushing past / 2.1 bursts out into the canyon / 4.75 hits the ramp; 4.95 shades flip down / 5.25 launch on the beat: thrusters fire, speed ramps to 6% slow-mo / 6.0 arc over the gap, arms up, slight roll, billboard behind / 8.75 slam on the beat: suspension dips, sparks, camera shake / 12.1 shades flip back up; 12.57 into the next tunnel = frame 1

**CAMERA:** one take locked to the car: front low 3/4, swing wide at the exit, chase on the ramp, orbit over the canyon, front low for the slam, settle on the opening offset.

**LOOK:** puddles mirror the neon, mist fog, bloom, slight dispersion, shallow DOF on HERO, 0.5 shutter blur; a soft fill rides with the car so the face reads D97757.

**CHECKS:** preview 9 beat stills at half res before the full render; eyes readable in every front shot; frame 420 to 1 no bigger a jump than any neighbour.

块的读法：BRAND 是唯一要换的块（HERO/RIDE/PROP/SET/SIGNS/PALETTE），其余部分只引用这些名字。FORMAT = Blender 脚本而非手工文件：时间轴的纯函数，每次改动从零重建。CHECKS 让 Opus 在烧一小时 GPU 之前先看图——大部分精修来自这一行。

---

## 4 条跟进提示词（第 3 页，逐字、按顺序）

第一版仅靠主提示词就已经有了隧道、跳跃和循环。以下每条都是看完静帧/渲染日志/成片后写的反馈原文。

**FOLLOW-UP 1（看完首批 9 张预览静帧后）**
HERO reads as a pile of bricks on the back seat: at 0.08 per voxel it is a third of the car. Make the voxel 0.105, sit HERO in the middle of one bench seat and bring the opening camera to 5.4 m, aimed at its eyes, not the bonnet. The neon pixel-HERO billboard blows out the whole top of every jump frame: drop it to a third of the brightness, shrink it and set it 6 m back on its tower. The windows are 5 m tall, so the towers read as toys next to the car: make them about 1.6 by 2.7 m. At the slam the sparks are invisible: 240 of them, thicker and twice as bright.
结果：每个正面镜头里 HERO 占画面三分之一；城市读起来像塔楼了。

**FOLLOW-UP 2（看完 HERO 的全分辨率裁切后）**
The steering wheel and the blue dash screen read as a white disc floating over HERO's face. Take both out, a speedster does not need them on camera. HERO sits so low the cowl hides its eyes: lift it 10 cm on a thicker seat and drop the windscreen to a low wraparound so both eye slits clear it in the front shots.
结果：接缝跳变 23.4，落在相邻帧范围（20.5–26.1）之内；成片 29 MB。

**FOLLOW-UP 3（给首批全质量帧计时后）**
Each 1080p frame takes 2.5 to 3.5 minutes: that is the CPU, because the GPU choice lives in the user preferences, not in the .blend. Write a gpu.py that switches Cycles to OptiX and pass it on every render. Then time one frame again before you start all 420.
结果：OptiX 7.3 秒/帧，420 帧 54 分钟（否则约 20 小时）。

**FOLLOW-UP 4（最终编码后）**
The loop is clean, but the MP4 is 118 MB at 67 Mb/s: the per-frame grain is noise the encoder cannot share between frames. Drop the grain, keep the vignette, CRF 18.

### 改成自己的（BRAND 块示例）

只换 BRAND 块：吉祥物换成自己的 logo 像素网格、座驾换成白色悬浮机车、场景换成黎明雪山、招牌换成自己的 logo 刻在冰川墙上。任何"我们上线了"的发版帖都适用。

### 渲染流程

1. `blender -b --factory-startup -P scene.py` 建 .blend
2. 先渲染 9 张节拍静帧（50% 分辨率、48 采样），拼成 contact sheet 先看
3. 每次渲染都加 `-P gpu.py`（OptiX 是用户偏好设置，不在文件里）
4. 全量 1920x1080、128 采样自适应、OptiX 降噪、0.5 快门、persistent data（RTX 4070 SUPER 约 7 秒/帧）
5. H.264 High CRF 18、30fps、柔和暗角；WAV 以 AAC 320k 混入，+faststart

### 每帧卡节拍（137.14 BPM 下每拍都落在 16 分音符上）

0.00–2.10s（f1–f64）：HERO 迎面开，环每秒擦过四次 | 引擎轰鸣、环的呼啸、隧道混响
2.14s（f65）：冲出隧道进峡谷 | 大 whoosh，混响打开
3.00/4.35s（f91/f131）：相机摆宽再从背后追 | 两次 whoosh、军鼓滚、riser
4.75s（f143）：前轮上斜坡 | 钢铁撞击
4.95–5.25s（f149–f158）：墨镜翻下 | 清脆 shing
5.25s（f158）：起跳：推进器点火，时间压到 6% | BRAAAM、喷气轰鸣、音乐低通
5.70–7.40s（f172–f223）：顶点 6% 慢镜，举手，广告牌在后 | 挤出的 wheee、引擎下沉、心跳底鼓
8.75s（f263）：落地砸拍：悬挂下沉、火花、相机抖 | 低频轰、金属碎、火花噼啪、轮胎尖叫、撞击
12.12s（f364）：墨镜翻回 | 小 click
12.57–14.0s（f378–f420）：进下一条隧道 = 第一帧 | whoosh、混响收起、第一小节回来

3 个要点：① 世界要复用——一段路实例化，帧 1 和帧 421 是同一位置，循环免费；② 跳跃卡节拍——先定速度让循环时长整数小节，再把唇和落地点放拍上；③ 慢动作慢的是距离不是重力——重映射飞行距离，保持抛物线。

---

## 配音提示词（第 4–5 页，copy-ready，210 词）

画面是 Blender 场景，声音来自另一段提示词：全部用 numpy 合成，按同一 timeline.py 走。要求：48kHz 立体声 WAV，14.0 秒，从 timeline.py 读每个事件并落在对应帧；渲染三遍取中间一遍，让所有尾音包进开头。

Music: dark action trap cue at 137.14 BPM in D minor, 8 bars loop. 808 on the root with glides, hard kick, clap snare on 3, hats with rolls into bar ends, 16th-note pluck ostinato in a 3-3-2 accent. Bar 3 builds: snare roll, filter sweep, riser into the lip. On the launch a low BRAAAM, then slow-mo: everything low-passed, a pad, heartbeat kicks, a reverse cymbal into the landing. The beat drops back on the slam.
Car: engine pitch follows speed and dives in slow-mo, thin electric whine, whup for each tunnel ring and tunnel reverb only inside, whooshes on camera swings, clunk on the ramp, shing for the shades, jet roar for the thrusters, squeaky wheee from HERO, then the slam: sub boom, metal crunch, spark crackle, short tyre screech.
Master loud like a trailer: glue compressor and limiter at -1 dBFS.

### 2 条配音跟进（看完频谱图后）

**SOUND FOLLOW-UP 1**
Everything from 20 to 200 Hz is one solid wall for all 14 s and the loudness is flat at -9 dBFS RMS: the engine and the 808 bury the kick and there is no dip in the slow-mo. Halve the engine, high-pass it at 70 Hz, drop it 80% while airborne, duck the bed under the launch and the slam, and keep the slam and the BRAAAM on their own bus. The seam also jumps 0.2 between the last and first sample: the engine's half-speed firing term and its 3.02x partial do not complete whole cycles in 14 s. Round the engine to an even cycle count and use 3.0x.
结果：接缝跳变降到 0.05，在正常采样步进（0.056）之内。

**SOUND FOLLOW-UP 2**
Still too much below 60 Hz under the slow-mo: take the D1 out of the BRAAAM and start it at D2, high-pass the 808 at 38 Hz and bring it down a third, and high-pass the master at 32 Hz.
结果：集成响度 -9.2 LUFS、动态 2.6 LU、峰值 -0.6 dBFS，无削波。刻意做得预告片级响；平台按 -14 LUFS 播的话 master 降 5 dB 就行。

**进 MP4**：WAV 用 ffmpeg 以 AAC 320k 混成视频音轨，自己的片子照搬这一步。

---

## 适用与启示

- 适合：任何"we shipped it"发版日、产品上线帖（换 BRAND 块就行）
- Loop 的核心：世界复用 + 接缝跳变量化检查（画面用帧差、声音用采样步进）
- "先渲染 9 张节拍静帧拼 contact sheet 再全量"——和我们的审片拼图一个思路，可并入剧坊质量门
- Follow-up 逐条保留原文记录：这种"看完→反馈→再渲"的迭代记录本身就是最好的教程格式
