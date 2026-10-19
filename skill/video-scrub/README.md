[![中文](https://img.shields.io/badge/%E4%B8%AD%E6%96%87-a02128?style=for-the-badge)](README.md)
[![English](https://img.shields.io/badge/English-ece9e7?style=for-the-badge&labelColor=ece9e7&color=8a8785)](README.en.md)

# video-scrub

把一条视频重建成干净文件：**画面和声音带过去，源片的元数据一个字节都不带。**

GPS、设备型号、账号 ID、创建时间、章节、GoPro 的遥测轨——全部留在原地。

## 白名单，不是黑名单

清元数据有两种思路，差别是死活：

| | 怎么做 | 问题 |
| --- | --- | --- |
| 黑名单 | 列出要删的字段逐个删（exiftool 那种） | **删不完你不知道的东西** |
| **白名单** | 不说删什么，只说**带什么过去**：画面一条流、声音一条流，别的一律不要 | —— |

走白名单，源片的元数据**没有任何通道**能进来。它不是「被删掉了」，是从来没被搬运。
隐私保证来自结构，不来自枚举。

## 难的不是 tag，是看不见的那几层

`-map_metadata -1` 之后 `ffprobe` 一片安静。**但文件里还躺着三处身份串：**

| 藏在哪 | 内容 | ffprobe 看得见 |
| --- | --- | --- |
| H.264 的 **SEI** | `x264 - core 165 ... cabac=1 ref=3 ... crf=23.0` | ✗ |
| AAC 码流的 **DSE** | `Lavc62.28.102` | ✗ |
| avc1 的 **compressorname** | `Lavc libx264` | ✗ |

加上容器 tag 和 handler_name，一共**五个藏身处**，少堵一个都不算干净。
每一处的堵法、以及几个「看着该管用其实没用」的坑（`-flags:v +bitexact` 和
`-x264-params info=0` 都拦不住 SEI），全部记在 [`references/residue-map.md`](references/residue-map.md)。

还有一类不在这五处、但同样要命的：**GoPro 和 DJI 的 GPS 不在任何 tag 里**，
在一条独立的 `gpmd` 定时元数据轨上。清 tag 清不掉，只有「只挑视频和音频两条流」挡得住。

## 默认不损画质

```bash
node scripts/video-scrub.mjs run <video> -o out.mp4
```

| 模式 | 画面 | 音频 | 速度 |
| --- | --- | --- | --- |
| **`copy`**（默认） | **逐字节照搬** | 重编 | 53 秒的片子 **1.3 秒** |
| `encode` | 重编码 | 重编 | 慢得多 |

画面在 copy 模式下真的一个比特都没动——抽出前后的 H.264 码流 `cmp` 过，
除了被摘掉的 SEI 之外逐字节一致。

音频**两种模式都重编**：AAC 的版本号写在 DSE 里，那是码流内部，`-c:a copy` 抹不掉它。

**关于水印**：`encode` 比 `copy` 多杀的是码流域水印和脆弱隐写，实际素材里少见。
真正要命的**鲁棒像素水印**（SynthID、影视取证水印）设计目标就是扛住重编码，
**两种模式都杀不掉**。选模式按画质和速度选，别指望重编码能洗掉水印。

## 验收不靠声称

前面全是「我调了正确的参数」，属于声称。验收这一步是「我扫了，真没了」，属于证明。

把源片所有元数据字符串抓出来当**针**——tag 的键和值、handler 名、章节标题——
在输出文件里做**字节级扫描**，扎到一根就红。

```
demo2.mp4 → clean.mp4　copy / obs
扫了 14 根针

  ✓ 字节级残留      ✓ 流构成
  ✓ tag 层残留      ✓ 章节
  ✓ 位置信息        ✓ 码流身份串
  ✓ 设备与软件标识   ✓ profile 相符
  ✓ 源片时间戳      ✓ 时长
  – 旋转矩阵        ✓ 可解码

✅ 12 道门全过——源片的元数据一个字节都没剩下
```

仓库里有一份**真跑出来的对账**：[`demo-scrub/`](../../demo-scrub/)——包含一个
最值得看的反例，教科书做法跑完 `ffprobe` 一片干净，码流身份串那道门照样红。

针的挑选有两条讲究：**≥5 字节**（更短的会在压缩数据里撞出假阳性），
**通用串不当针**（`VideoHandler` 满世界都是；`Lavf58.45.100` 钉死一个版本，是指纹）。

## 四个 profile

擦白之后往回写的那一层。`--profile <名>` 切换：

| profile | 写什么 |
| --- | --- |
| **`obs`**（默认） | OBS Studio 的长相。OBS 本来就是 ffmpeg 封装的，这档不是伪造 |
| `quicktime` | macOS QuickTime 录屏：`Core Media Video` / `Core Media Audio` |
| `screencapture` | ScreenCaptureKit 录屏 |
| `bare` | 什么都不写。**隐私强度最高**——不留任何可被证伪的声明 |

profile 只碰三样东西：封装工具的痕迹、handler 名、创建时间。
**不写设备型号、不写 GPS、不写作者和账号。** 详见 [`references/profiles.md`](references/profiles.md)。

## 命令

```bash
inspect <video>                    # 先看源片带了什么，含码流里那几处看不见的
scrub   <video> -o out.mp4         # 清
verify  <源> <输出>                 # 扫残留，出 12 道门的清单
run     <video> -o out.mp4         # scrub + verify 一条龙，日常用这个
```

常用参数：

```bash
--mode encode                  # 完整重编码
--profile bare                 # 什么都不写
--crf 18                       # 只在 encode 模式有意义
--date 2026-01-01T00:00:00Z    # 指定创建时间
--json                         # inspect / verify 出 JSON
```

## HDR 与内嵌字幕：SEI 这刀什么时候不许动

ffmpeg 只给得起 NAL 级的粒度，`remove_types=6` 是**全部 SEI 一起删**。
而 SEI 里除了 x264 那串垃圾，还住着 **HDR 静态元数据**（删了会掉色）和
**CEA-608/708 内嵌字幕**（删了字幕没了）。

所以策略是有条件动刀：**只在真查到身份串时才删，HDR 源片一律不动**（会明说没动，以及为什么）。

## 边界（不做的事）

不去除水印、不改画面内容（不裁剪不缩放不旋转）、不伪造设备型号和 GPS、
不做批量目录扫描、不处理 mp4/mov 之外的容器。

## 依赖与自测

只要 `node` >= 18 和 `ffmpeg` / `ffprobe`。零 npm 依赖、零 API key。

```bash
node scripts/selftest.mjs
```

117 项断言，不碰 ffmpeg、不碰真文件。**12 道门每道都有击穿用例**——证明它真的会拦。
