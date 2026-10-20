# 拼接 · 混音 · 交付 ★★

> 从「一堆镜头文件」到「可以给人看的成片」。
> 这一段踩的坑最多，而且**错了很难发现**（时长膨胀、旁白错位、漏镜）。

---

## 一、目录约定

一部片子会有几百个文件，**先把目录结构定下来**，否则三天后自己都找不到。

```
projects/<片名>/
├─ 00-剧本/            剧本 + 分镜表（md）
├─ 01-角色/            角色定板图
├─ 02-场景/            场景定板图
├─ 03-道具/            道具基底图
├─ 04-逐镜图/          每个镜头的图（按卷/章分）
├─ 05-逐镜视频/        每个镜头的视频
├─ 06-音频/            对白 + 旁白
├─ 07-成片/            分章成片
├─ 08-三卷/            分卷成片
├─ 09-全片/            最终成片
├─ ★剪辑工作台/        交给剪辑用的（见 09-DELIVERY.md）
└─ _tmp/               中间产物
```

**命名规范（很重要）**：
```
镜头视频：<镜号>-<内容>.mp4            例：A04-街口推进.mp4
镜号体系：A=楔子  B~F=一至五章  G~N=六至十三章  O~S=十四至十八章  T=尾声
```
**镜号是全局唯一的**，所有文件、所有对话、所有问题定位都用它。

---

## 二、★ 拼接三段式（必须按这个顺序）

### 第 1 步 · 逐个规范化

```bash
ffmpeg -y -fflags +genpts -avoid_negative_ts make_zero -i <src> \
  -c:v libx264 -preset veryfast -crf 20 -r 24 -vf "scale=1280:720,setsar=1" \
  -pix_fmt yuv420p -c:a aac -ar 32000 -ac 2 <dst>
```

**为什么必须做**：LingCut 的镜头来自不同批次，帧率/分辨率/音频参数可能不一致。
直接 concat 会导致**时长膨胀**（实测 12 秒变 12.6 秒）和音画不同步。

**统一规格**（按需改）：
```
1280×720 · 24 fps · H.264 · yuv420p · AAC 48kHz/32kHz 立体声
```

### 第 2 步 · concat（无损）

```
# list.txt —— ★ 必须无 BOM 的 UTF-8
file 'C:/path/01-n.mp4'
file 'C:/path/02-n.mp4'
```

```bash
ffmpeg -y -f concat -safe 0 -i list.txt -c copy out.mp4
```

⚠️ **BOM 坑**：PowerShell 5.1 的 `Set-Content -Encoding UTF8` **会加 BOM**，
ffmpeg 报 `Line 1: unknown keyword 'file'`。必须：

```powershell
[System.IO.File]::WriteAllLines($p, $lines, (New-Object System.Text.UTF8Encoding($false)))
```

### 第 3 步 · 混旁白

```bash
ffmpeg -y -i <video.mp4> -i <narration.wav> \
  -filter_complex "[1:a]apad=whole_dur=<视频秒数>[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -ar 32000 -ac 2 -shortest <out.mp4>
```

`apad=whole_dur=` 把旁白补静音到视频长度，避免旁白比画面短导致尾部被切。

---

## 三、★ 时长膨胀的检测

拼完**必须核对**：`成片时长 ≈ 各段时长之和`。

```powershell
function Sec($f) {
  $m=[regex]::Match((& ffmpeg -hide_banner -i $f 2>&1|Out-String), 'Duration: (\d+):(\d+):([\d.]+)')
  [double]$m.Groups[1].Value*3600+[double]$m.Groups[2].Value*60+[double]$m.Groups[3].Value
}
```

**实测数据**（《《示例片名》》最终）：
```
20 章逐镜之和 = 1509.55s
全片实际     = 1509.65s
差 0.10s → ✅ 正常
```

差超过 1 秒 → 规范化没做干净，重做。

---

## 四、★ 漏镜的检测（最容易犯的错）

**症状**：成片比预期短。

**原因**：按文件名收集镜头时漏了（比如某个镜头放在别的目录、或命名不符正则）。

**实测踩坑**：第一次重拼时 **B10（米铺阿婆送米）漏了**，
因为 `08-一章视频-v2/` 里没有它（在别的批次生成）。

**对策**：
1. **从画布全集重下**（见 09-DELIVERY.md 的下载脚本），不要从零散目录收集
2. 收集时**按镜号分组**，然后打印每个单元的镜号清单，**人工核对**
3. 和**旧版成片时长**对比 —— 差异超过一个镜头长度就要查

```
╔═══ 逐单元镜号核对（示例）═══
║ 楔子     11 镜   A01 A02 A03 A04 A05 A06 A07 A08 A09 A10 A11
║ 第一章   11 镜   B01 B02 B03 B04 B05 B06 B07 B08 B09 B10 B11
║ ……
╚═════════════════════════
```

---

## 五、★ 旁白错位（改了镜头时长之后）

**症状**：旁白比画面早了/晚了。

**原因**：某几镜加了时长（比如 5s → 10s），但旁白是按旧时长对齐的。

**对策**：在**变化点插入等长静音**。

```
旧时间线：…… [镜头 X: 12s] [镜头 X+1] ……
新时间线：…… [镜头 X: 20s] [镜头 X+1] ……
                     ↑ 这里多出 8s

处理：把旧旁白在"镜头 X 开始处"切开，插入 8s 静音，再拼回去
```

**位置计算**：`P_old = Σ(旧时长[0..X-1])` —— 因为 X 之前的镜头没变，新旧时间相同。

**如果懒得逐点对齐**（旁白是稀疏的、变化点都在对白镜头上）：
最简单的近似是 `apad` 补到新长度，接受几个镜头的错位。
**但要在交付时告诉用户**。

---

## 六、ffmpeg 常用命令速查

```bash
# 抽帧（2fps = 每 0.5 秒一帧）—— 逐帧 QA 用
ffmpeg -i v.mp4 -vf "fps=2" -q:v 3 frames/f_%03d.jpg

# 抽尾帧（尾帧接续用）
ffmpeg -sseof -0.15 -i a.mp4 -frames:v 1 -update 1 tail.png

# 提取音频（换 wav 便于对齐）
ffmpeg -i v.mp4 -vn -c:a pcm_s16le -ar 48000 -ac 2 out.wav

# 取某一段
ffmpeg -ss 12.0 -i v.mp4 -t 8.0 -c copy seg.mp4

# 看时长（不用 ffprobe）
ffmpeg -hide_banner -i v.mp4 2>&1 | Select-String Duration

# 拼图联系表（Python）
python scripts/contact_sheet.py <图片目录> <输出.jpg> [列数]
```

---

## 七、PowerShell 的坑（在 Windows 上做这些必看）

| 坑 | 现象 | 解法 |
|---|---|---|
| **变量名不区分大小写** | `$TOT` 和 `$tot` 是同一个变量 | 用 `$TOTDUR` / `$SUMDUR` 这类明显不同的名 |
| **`Write-Output`/`return` 污染返回值** | 函数返回数组而不是数字 | 用 `Write-Host` + `$global:LASTDUR` |
| **`$ErrorActionPreference='Stop'` + ffmpeg** | ffmpeg 写 stderr 被当成错误 | 改成 `'Continue'` |
| **`Set-Content -Encoding UTF8` 加 BOM** | ffmpeg concat 报错 | `[System.IO.File]::WriteAllLines(..., UTF8Encoding($false))` |
| **脚本文件本身缺 BOM** | 中文路径变乱码、语法错误 | 写完后加 BOM：`[System.IO.File]::WriteAllText($p, $c, (New-Object System.Text.UTF8Encoding($true)))` |
| **`Get-NetTCPConnection` 卡死** | 命令挂住 | 用 `netstat -ano` |
| **`Invoke-WebRequest` 进度条** | 非交互模式报错 | 先 `$ProgressPreference='SilentlyContinue'` |
| **`-f` 不能用在 `Test-Path` 字符串里** | 解析错误 | 分开写 |
| **ffmpeg `-f image2` 必须在输出路径前** | 报错 | 调整参数顺序 |
| **文件被占用删不掉** | `being used by another process` | 让剪辑指南/脚本**按文件名过滤**跳过它；或改名 |

---

## 八、备份规矩（血的教训）

**覆盖任何成片之前，先复制一份到 `_旧版备份-<日期>\`。**

实测踩坑：编辑在剪映里改完后，我把旧成片全覆盖了，
结果用户问「上一版的视频还在吗」——**旧的 24:18 全片没了**。

**补救**：从**画布快照**里把旧版本的 OSS URL 全拉回来，重建了旧版。
（见 10-TROUBLESHOOTING.md 的「画布快照恢复」）

**规矩**：
1. 覆盖成片前 → `Copy-Item <old> <backup>\<name>`
2. 定期把画布 JSON **存快照**（`_tmp/canvas.json`）—— 这是唯一的"时间机器"
