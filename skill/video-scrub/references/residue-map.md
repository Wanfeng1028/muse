# 五个藏身处

清视频元数据不是一行 `-map_metadata -1` 的事。工具会把身份写进**五个地方**，
其中三处 `ffprobe` 根本看不见——所以「我清干净了」这个判断本身可能是假的。

以下全部在 ffmpeg 8.1.2 / macOS 上实测，包括几个**看着该管用其实没用**的坑。

---

## 1. 容器 tag 的 `encoder`

最显眼的一处，`ffprobe -show_format` 就能看见。

```
encoder = Lavf58.45.100
```

**堵法：** `-fflags +bitexact`

**注意：** 这个字段由 muxer 自己占着，改不动也清不掉：

| 试过 | 结果 |
| --- | --- |
| `-metadata encoder=Lavf60.16.100` | ✗ 盖不过去，输出仍是 ffmpeg 的真版本号 |
| `-metadata encoder=`（置空） | ✗ 清不掉 |
| `-fflags +bitexact` | ✓ 整个字段消失 |

**推论：** 想让输出「看起来像某个特定版本的工具产出」是做不到的。
所以 `obs` 档不伪造版本号——它不加 bitexact，让 ffmpeg 写自己的真版本号。

**另一条实测：** `-fflags +bitexact` 会清掉自动生成的 `creation_time`，
但**不影响显式写的那个**。`-fflags +bitexact -metadata creation_time=...` 两者可以并存。

---

## 2. `avc1` 的 compressorname

藏在 `moov` 的 sample description 里，是 `VisualSampleEntry` 的一个 32 字节 Pascal 串。

```
...\x01\x0cLavc libx264\x00\x00...
```

`ffprobe -show_format` 看不见它，`ffprobe -show_entries stream_tags` 能看见一个对应的
`encoder` 流 tag。

**堵法：** `-metadata:s:v:0 encoder=`

mov muxer 从**流的 `encoder` tag** 取这个字段，置空即清。
注意和第 1 条的区别：容器级的 `encoder` 置空没用，流级的置空有用。

---

## 3. AAC 码流里的 DSE

ffmpeg 的 AAC 编码器把自己的版本号写进 **Data Stream Element**，在音频码流内部。

```
Lavc62.28.102
```

一条 53 秒的片子里出现 8 处。`ffprobe` 完全看不见。

**堵法：** `-flags:a +bitexact`

**关键推论：** 这是**码流内部**的东西，`-c:a copy` 抹不掉它。
所以即使走 copy 模式，**音频也必须重编一遍**。代价很小（53 秒的片子约 1 秒），
换来音轨干净。

---

## 4. H.264 的 SEI —— 最刁的一处

x264 把**完整编码参数**写成 SEI 塞在码流里：

```
x264 - core 165 r3222 b35605a - H.264/MPEG-4 AVC codec - Copyleft 2003-2025 -
http://www.videolan.org/x264.html - options: cabac=1 ref=3 deblock=1:0:0
analyse=0x3:0x113 me=hex subme=7 psy=1 psy_rd=1.00:0.00 mixed_ref=1 me_range=16
... crf=23.0 qcomp=0.60 qpmin=0 qpmax=69 ...
```

这串东西信息量极大——编码器版本、全部参数、CRF 值。**任何 `ffprobe` 命令都看不见它。**

### 试错记录

| 试过 | 结果 |
| --- | --- |
| `-flags:v +bitexact` | ✗ 拦不住，SEI 照写 |
| `-x264-params info=0` | ✗ 被 ffmpeg 的封装吃掉了，无效 |
| **`-bsf:v filter_units=remove_types=6`** | ✓ 干净利落 |

**堵法：** `-bsf:v filter_units=remove_types=6`（6 = SEI 的 NAL 类型）

**重要：它在 `-c:v copy` 下照样工作。** 这是 copy 模式能成立的关键——
不重编画面也能摘掉 SEI。实测抽出前后的 H.264 码流 `cmp`，除了被摘掉的 SEI 之外逐字节一致。

### 但这把刀太钝 ⚠

ffmpeg 只给得起 **NAL 级**的粒度：

- `filter_units` 只能按 NAL 类型删，删不了单个 SEI payload
- `h264_metadata` 也没有对应选项（它能 `insert` SEI，不能选择性 `remove`）

所以 `remove_types=6` 是**全部 SEI 一起删**。SEI 里还住着：

- **HDR 静态元数据**——mastering display colour volume / content light level。
  删了 HDR 片子会掉色，tone mapping 直接崩。
- **CEA-608/708 内嵌字幕**——删了字幕没了。
- `pic_timing` / `buffering_period`——个别播放器会挑剔。

**所以策略是有条件动刀**（`seiPlan()`）：

1. 源片是 HDR → **一律不删**，哪怕有身份串，也只出告警
2. 码流里没查到身份串 → 不必动刀
3. 其余情况 → 删

HDR 的判定看 `color_transfer`（`smpte2084` / `arib-std-b67`）、`color_primaries`（`bt2020`）
和像素格式（`10le` / `12le` / `p010`）。

---

## 5. `handler_name`

```
VideoHandler / SoundHandler
```

**堵法：** 显式写值。

**坑：** `-metadata:s:v:0 handler_name=`（置空）**会退回 ffmpeg 的默认值** `VideoHandler`，
等于没清。要真空白得写一个**单空格**：

```
-metadata:s:v:0 handler_name=" "
```

实测：单空格 → 输出的 handler_name 为空，文件里 `VideoHandler` 出现 0 次。

---

## 不在这五处、但同样要命的：独立的元数据轨

**GoPro 和 DJI 的 GPS 不在任何 tag 里**，在一条独立的定时元数据轨上
（GoPro 是 `gpmd` handler，整条 GPMF 遥测流：轨迹、速度、陀螺仪）。

你把 tag 清光了，`ffprobe -show_format` 看着干干净净，**一整条行动轨迹还躺在文件里**。

**堵法：** 白名单选流。

```
-map 0:v:0 -map "0:a:0?"
```

只显式挑视频和音频，其余一概不带过去——data 轨、timecode 轨、附件、字幕轨全掉。
配合 `-map_chapters -1` 把章节也挡住。

这就是「流构成」单独占一道门的原因：**不是形式主义，是这类源片唯一的防线。**

---

## 完整配方

```bash
ffmpeg -v error -y -i <src> \
  -map 0:v:0 -map "0:a:0?" \
  -map_metadata -1 -map_chapters -1 \
  -c:v copy \                                  # 或 -c:v libx264 -crf 18
  -c:a aac -b:a 192k \                         # 音频必须重编，见第 3 条
  -bsf:v "filter_units=remove_types=6" \        # 第 4 条，有条件
  -fflags +bitexact \                           # 第 1 条，bare/quicktime 档
  -flags:a +bitexact \                          # 第 3 条
  -metadata:s:v:0 encoder= \                    # 第 2 条
  -metadata:s:a:0 encoder= \
  -metadata:s:v:0 handler_name="<profile 的值>" \ # 第 5 条
  -metadata:s:a:0 handler_name="<profile 的值>" \
  -movflags +faststart \
  <out>
```

---

## 字节级扫描的两条讲究

验收时把源片的元数据字符串当「针」在输出里扫，有两个实现细节不能省：

**针要 ≥5 字节。** 更短的串会在压缩数据里随机撞出假阳性——踩过：一次扫描报告
`Lavc` 和 `x264` 有残留，查偏移才发现是压缩数据里的巧合。跳过的针要在报告里列出来，
不能默默忽略。

**通用串不当针。** 分界线是**能不能把范围缩小到某个人、某台设备、某次导出**：

| 串 | 当针？ | 为什么 |
| --- | --- | --- |
| `wesley@example.com` | ✓ | 指向一个人 |
| `vid:v1e00fgi0000...` | ✓ | 平台的视频 ID |
| `iPhone 15 Pro` | ✓ | 指向设备型号 |
| `Lavf58.45.100` | ✓ | 钉死了一个版本 |
| `VideoHandler` | ✗ | 满世界都是，信息量为零 |
| `isom` | ✗ | 结构性 tag，输出里必然还有，当针会自己扎自己 |

**还有一类要豁免：profile 自己写回去的值。** 如果源片也是 ffmpeg 封的、版本号还恰好相同，
输出的 `encoder` 会和源片一模一样——但它是 muxer 现写的，不是漏过来的。
这个豁免不开口子：有 `-map_metadata -1` 在，源片的 `encoder` 字段**结构上就到不了**输出。
