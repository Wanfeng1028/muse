# 按实际帧取证

`scripts/sample_frames.py` 读取本地视频的首路视频流，用 FFprobe 枚举实际解码帧的 `best_effort_timestamp_time`，再用 FFmpeg 按帧序号导出最近帧。建议 Python 3.11+、Pillow，以及 PATH 中的 FFmpeg / FFprobe；媒体协议限制为本地 `file,pipe`，不联网、不安装依赖。

```bash
python3 scripts/sample_frames.py --input /path/reference.mp4 --out /path/new-evidence \
  --start 8 --end 10.2 --step 0.1

python3 scripts/sample_frames.py --input /path/reference.mp4 --out /path/new-detail \
  --times 8.25,8.3,8.35,9.1 --frame-width 1280 --per-page 12 --columns 3
```

命令从 skill 目录运行，或把脚本路径写全。`--times` 与完整的 `--start/--end/--step` 互斥；起止点含端点，但末端不在步长网格上时不额外追加。时间以**容器的 `format.start_time` 为零点**；该值缺失时回退到 0，并在 `origin_policy` 标明、`timing.origin_verified=false`，这只是显式假设。清单保留 `timeline_origin_pts_s` 与视频首末帧的原始 PTS；`timing.presentation_start_pts_s` 与音频工具同义。对齐音频时须使用同一容器基准，不能把视频首帧与音频首帧各自归零。

输出目录必须不存在。全部帧和联系表通过检查后才提交整个目录；失败不会留下宣称成功的 `manifest.json`，也不会覆盖媒体源。

输出：`frames/*.jpg`、`contact-*.jpg`、`probe.json`、`manifest.json`。联系表标记目标时间与实际源 PTS。目标过密或可变帧率导致多个目标命中同一帧时，清单保留所有目标并引用同一图片，不虚构额外帧。

清单的 `samples` 字段：

| 字段 | 含义 |
|---|---|
| `target_time_s` / `target_pts_s` | 请求的相对秒数 / 换算后的源 PTS |
| `actual_pts_s` | FFprobe 得到的源帧实际时间戳 |
| `actual_time_s` | 实际 PTS 减去 `timeline_origin_pts_s` |
| `error_s` | 实际相对时间减去目标时间，正值表示晚于目标 |
| `frame_index_0` | FFprobe 解码帧序号，从 0 开始 |
| `image` | 相对输出目录的图片路径，可能被多个采样记录复用 |

默认最多 240 个目标，每页 24 格、4 列，帧宽 960。用 `--max-samples`（上限 5000）、`--per-page`、`--columns`、`--thumb-width`、`--thumb-height` 调整。`--font /path/font.ttf` 可选；未提供时寻找通用字体，找不到便用 Pillow 默认字体，不依赖 macOS 字体或 FFmpeg drawtext。

负数、零/负步长、无视频、不可解码帧、越过最后一帧 PTS 均明确报错。视频容器时长可能比末帧 PTS 稍长，不能直接以容器时长当作最后一个可采样时间。脚本会解码并枚举整段视频，长片先选择适当本地片段。抽样能定位画面状态，不能单凭它判断连续运动或证明作者刻意卡点。
