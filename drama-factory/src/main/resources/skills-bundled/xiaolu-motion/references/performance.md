# 性能与稳定性

跑这套系统需要同时喂饱 headless Chrome 渲染、ffmpeg 编码和 Apple Vision 探测,三者都吃 CPU/GPU/内存,同一台机器上多个任务/多个 Agent 会话并发很容易把内存挤爆。以下规则是踩过坑之后定下来的:

- **`scripts/with_heavy_lock.py`**:所有重任务(视频编码、Vision 探测、headless Chrome 渲染)一律用它包起来跑:
  ```bash
  python3 scripts/with_heavy_lock.py -- ffmpeg -i in.mp4 ... out.mp4
  python3 scripts/with_heavy_lock.py -- python3 -m qa.pixel_qa video.mp4 --out-dir out/
  ```
  它保证全机同一时间最多两个重任务在跑(两把 `flock` 文件锁),新任务要等系统空闲内存 ≥ 35% 才启动,运行中空闲内存跌破 12% 会先 `SIGTERM` 再 `SIGKILL` 掉子任务,防止一个任务把机器压垮连累其他任务。默认按 `<repo>/.cache/locks` 记锁,想跨多个 checkout 共享同一把锁就设 `XM_LOCK_DIR` 环境变量。
- **每任务 4 线程预算**:并行渲染 worker 数、ffmpeg `-threads` 都按"这台机器的核数 ÷ 4"这类预算规划,不要单个任务就把所有核吃满——同一时间可能有另一个重任务在排队(见上一条的并发上限是 2,不是 1)。
- **产物先写 `.partial` 再改名**:任何耗时的渲染/编码都先写到 `xxx.mp4.partial`,成功后再 `os.rename()`/`mv` 成最终文件名。这样即使中途被 `with_heavy_lock` 的内存告急机制杀掉,也不会有一个看起来完整、实际截断的文件被误当成交付物。
- **`ffmpeg -ss` 连读必须加 `-fps_mode passthrough`**:凡是先 `-ss` 定位再用 `select='eq(n,…)'` 挑帧的场景(逐帧抽样、按帧号取图),必须加 `-fps_mode passthrough`,否则 ffmpeg 为了维持恒定帧率会重新插值/复制时间戳,抽出来的帧号和实际内容对不上。参考本仓库 `qa/pixel_qa.py`/`qa/check.py` 里 `decode_frames()`/`grab_frames()` 的写法。
- **原始帧编码要标 BT.709 tv**:任何用纯色/测试图生成的"底片"或中间态视频,编码时都要显式标 `-color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv`(参考 `qa/alpha_selftest.py` 的 `ffmpeg_composite()`),否则合成器和 QA 探针拿到的色彩空间标记跟实际不一致,颜色对比检查会失真。
- **Apple Vision 探测必须分块处理,防内存泄漏**:一次探测调用不要让 `AVAssetReader` 从头顺序解码一整段长视频——按位置分段(而不是按"想要的帧数量"分段:稀疏采样时后者不能限制实际解码范围),每段用 `--start-frame` 让探针从接近目标的位置起读,每帧处理包在 `autoreleasepool` 里及时释放临时对象,每个子进程只处理一段就退出、由进程退出兜底回收内存。`qa/vision.py` + `qa/vision_probe.swift` 已经是这么实现的(2026-09-27 修过一次真实的内存泄漏:旧版一次探测调用在长视频上把 16GB 内存的机器压垮,新版同等测试峰值内存 <250MB)——新写探测代码照这个模式来,不要退回"一次性把所有想要的帧丢给一个进程"的写法。

## 子帧运动模糊采样次数

`engine/post.js` 的 WebGL 累积管线本身不设采样数上限;实际每帧用多少个子帧由 `engine/runtime.js#renderFrame()` 决定:取当前活跃组件里 `mbSamples()` 返回的最大值,再夹到 `TOK.post.mb_max`(令牌里没写就退回 16)。`styles/base.json` 目前把 `mb_max` 设成 **12**,不是 5——检查过 `engine/post.js`、`engine/runtime.js` 和全部 `styles/*.json`,仓库里没有任何地方把这个上限或某个组件的静止态默认值写成 5。

原理仍然值得记录:子帧数太少时,运动模糊只是几张离散帧的加权平均,快速运动的物体边缘会出现看得出来的"阶梯感"(banding/aliasing),而不是连续的拖影——尤其是运动物体本身还带高对比度描边或文字时更明显。经验规律:静止或慢动作 1-3 帧足够(省渲染时间),中速运动 6-8 帧,画面里出现"甩镜头"级别的快速位移(转场中点、数字冲击、卡片抛掷)时给到 10-12 帧才看不出阶梯——这也是库里各组件 `mbSamples()`(见 `components/*.js`、`library/*/src/*.js`)在快动作区间普遍返回 8-12、只有静止区间才降到 1-3 的原因。如果哪天真的把 `mb_max` 调低到个位数(比如为了赶渲染时间),先看这条经验规律再决定阈值,不要凭感觉砍到 5 以下。
