# profile：擦白之后写回去的那一层

清完之后文件是「无名」的——没有 tag，没有 handler 名，没有时间。
profile 决定往回写什么。

**隐私强度排序：`bare` > 其余三档。** 理由很简单：`bare` 不写任何可被证伪的声明。
其余三档写的是工具类信息（什么软件封装的、什么 handler），**不编造拍摄设备、不编造位置**。

---

## 录屏的元数据长什么样

先说一个事实，它决定了这几档为什么都这么简单：

**录屏的元数据特征九成是「没有」。**

GPS 是拍摄设备的定位服务写进去的——iPhone 相机写 `com.apple.quicktime.location.ISO6709`，
安卓相机写 `location`。录屏抓的是显示缓冲区，QuickTime、ScreenCaptureKit、OBS、
Windows Game Bar、iOS 控制中心录屏，**压根没有定位这条管线，也没有相应权限**。

所以一条录屏文件里不会有：GPS、相机型号、镜头光圈快门、旋转矩阵、拍摄参数。
剩下的只有封装工具的痕迹。

---

## 四档

### `obs`（默认）—— OBS Studio 录制

```
encoder      = Lavf<ffmpeg 的真版本号>
handler_name = VideoHandler / SoundHandler
creation_time = <当前时间或 --date>
```

**这档不是伪造。** OBS 本来就是用 ffmpeg 封装输出的，所以它产出的文件带 `Lavf` 版本号、
带标准 handler 名。我们的输出也是 ffmpeg 封的，长相同类。

版本号**不伪造**——做不到（见 `residue-map.md` 第 1 条），也没必要。
这一档靠**不加** `-fflags +bitexact` 来保住 ffmpeg 自己写的版本号。

### `quicktime` —— macOS QuickTime 录屏

```
handler_name = Core Media Video / Core Media Audio
creation_time = <当前时间或 --date>
（无 encoder 字段）
```

`Core Media *` 是 Apple 的 AVFoundation 写的 handler 名，QuickTime 录屏、
iOS 录屏产出的文件都长这样。

### `screencapture` —— macOS ScreenCaptureKit

和 `quicktime` 同款。分成两档是因为语义不同（一个是 App 录的，一个是系统 API 录的），
元数据层面当前不做区分。

### `bare` —— 什么都不写

```
handler_name = "（单空格）"
（无 encoder、无 creation_time）
```

**隐私强度最高的一档。** 不留任何可被证伪的声明，也不留时间。

handler 用单空格是有原因的：置空会退回 ffmpeg 的默认值 `VideoHandler`，等于没清。
见 `residue-map.md` 第 5 条。

---

## 选哪一档

| 场景 | 建议 |
| --- | --- |
| 发布前清掉自己的隐私信息 | `obs`（默认），够了 |
| 交付给客户、不想带自己的工具痕迹 | `bare` |
| 素材库归档，想要一致的元数据 | 任意一档，固定住就行 |
| 不确定 | `bare`——不写就不会错 |

---

## profile 不做的事

- **不写设备型号。** 不会往输出里填 `iPhone 15 Pro` 或任何相机型号。
- **不写 GPS。** 位置那道门判的是「必须不存在」，不是「伪造一个合理的坐标」。
- **不写作者、版权、账号。** 这些字段只会被清，不会被填。

profile 只碰三样东西：封装工具的痕迹、handler 名、创建时间。
