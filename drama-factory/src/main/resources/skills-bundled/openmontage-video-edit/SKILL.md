---
name: openmontage-video-edit
description: 面向视频剪辑日常任务的 ffmpeg 命令速查手册，覆盖裁剪、转码、缩放、变速、音视频处理、拼接、水印、画中画、滤镜、字幕、防抖、调色、压缩、幻灯片、章节标记、响度归一化等常见操作。
version: "1.0.0"
author: playhouse
license: MIT
---

# ffmpeg 视频编辑速查

本手册按任务类型组织常用 ffmpeg 命令，每条给出可直接运行的示例和一句话说明。示例参数只是演示值，实际使用时按需替换输入输出文件名与参数。

约定：`in.mp4` 表示输入文件，`out.mp4` 表示输出文件；滤镜链用 `-vf`（视频）和 `-af`（音频）。

---

## 一、裁剪与切片

### 1. 快速裁剪（不重编码）
```bash
ffmpeg -ss 00:00:10 -i in.mp4 -t 15 -c copy out.mp4
```
从第 10 秒起截取 15 秒，直接复制流不重编码，速度快但切点可能落在关键帧上。

### 2. 精确裁剪（重编码）
```bash
ffmpeg -i in.mp4 -ss 00:00:10.500 -t 15 -c:v libx264 -c:a aac out.mp4
```
把 `-ss` 放在 `-i` 之后做逐帧定位，切点精确，代价是重新编码。

### 3. 按时间段切分多个片段
```bash
ffmpeg -i in.mp4 -ss 0 -t 30 -c copy part1.mp4
ffmpeg -i in.mp4 -ss 30 -t 30 -c copy part2.mp4
```
同一条命令重复执行、每次换起止时间即可得到多段。

### 4. 按比例裁剪画面区域（crop）
```bash
ffmpeg -i in.mp4 -vf "crop=iw*0.8:ih*0.8" out.mp4
```
裁掉四周各 10%，输出画面为原尺寸的 80%。

### 5. 切掉画面边缘固定像素
```bash
ffmpeg -i in.mp4 -vf "crop=iw-40:ih-40:20:20" out.mp4
```
四边各裁 20 像素，常用于去黑边。

---

## 二、格式与编码

### 6. 格式转换
```bash
ffmpeg -i in.mp4 out.mkv
```
换封装格式，ffmpeg 会自动选择合适的编码器。

### 7. 指定编码器转码
```bash
ffmpeg -i in.mp4 -c:v libx265 -crf 24 -c:a aac -b:a 160k out.mp4
```
用 H.265 视频编码、AAC 音频编码输出。

### 8. Web 压缩（CRF 控制画质）
```bash
ffmpeg -i in.mp4 -c:v libx264 -crf 28 -preset medium -c:a aac -b:a 128k -movflags +faststart out.mp4
```
CRF 越大画质越低、体积越小；`faststart` 让 moov 前置，便于网页边下边播。

### 9. 改帧率
```bash
ffmpeg -i in.mp4 -r 30 out.mp4
```
把输出帧率改为 30 fps，会丢帧或复制帧来匹配。

### 10. 改分辨率（缩放）
```bash
ffmpeg -i in.mp4 -vf "scale=1280:720" out.mp4
```
缩放到 720p。

### 11. 保持宽高比缩放到指定宽度
```bash
ffmpeg -i in.mp4 -vf "scale=1280:-2" out.mp4
```
宽度 1280，高度按比例自动计算并取偶数。

---

## 三、时间与速度

### 12. 变速（视频 setpts + 音频 atempo）
```bash
ffmpeg -i in.mp4 -filter_complex "[0:v]setpts=0.5*PTS[v];[0:a]atempo=2.0[a]" -map "[v]" -map "[a]" out.mp4
```
视频加速 2 倍（0.5×PTS），音频同步加速 2 倍。atempo 单次支持 0.5–2.0，超出需串联。

### 13. 慢放
```bash
ffmpeg -i in.mp4 -filter_complex "[0:v]setpts=2.0*PTS[v];[0:a]atempo=0.5[a]" -map "[v]" -map "[a]" out.mp4
```
视频放慢 2 倍，音频同步放慢。

### 14. 倒放
```bash
ffmpeg -i in.mp4 -vf reverse -af areverse out.mp4
```
视频和音频同时倒放。

### 15. 只倒放视频
```bash
ffmpeg -i in.mp4 -vf reverse -an out.mp4
```
只倒放画面，丢弃音频。

---

## 四、循环

### 16. 循环视频到指定时长
```bash
ffmpeg -stream_loop 2 -i in.mp4 -c copy out.mp4
```
把输入重复播放 3 次（2 次循环 + 原始 1 次）。

### 17. 无限循环并限制总时长
```bash
ffmpeg -stream_loop -1 -i in.mp4 -t 60 -c copy out.mp4
```
无限循环，但只输出前 60 秒。

---

## 五、音频处理

### 18. 提取音频
```bash
ffmpeg -i in.mp4 -vn -c:a copy out.m4a
```
只保留音频流，直接复制不重编码。

### 19. 提取音频并转为 mp3
```bash
ffmpeg -i in.mp4 -vn -c:a libmp3lame -q:a 2 out.mp3
```
抽出音频并转成高质量 mp3。

### 20. 静音（去掉音频）
```bash
ffmpeg -i in.mp4 -an out.mp4
```
移除所有音频流。

### 21. 音频叠加到视频（替换音轨）
```bash
ffmpeg -i in.mp4 -i bgm.mp3 -map 0:v -map 1:a -c:v copy -shortest out.mp4
```
用 bgm.mp3 替换视频原音轨，视频流不重编码。

### 22. 合并音轨（原音 + 背景音）
```bash
ffmpeg -i in.mp4 -i bgm.mp3 -filter_complex "[0:a][1:a]amix=inputs=2:duration=first[a]" -map 0:v -map "[a]" out.mp4
```
把两路音频混在一起，时长以第一路为准。

### 23. 响度归一化（loudnorm）
```bash
ffmpeg -i in.mp4 -af "loudnorm=I=-16:TP=-1.5:LRA=11" -c:v copy out.mp4
```
把整体响度标准化到 -16 LUFS，适合流媒体发布。

---

## 六、画面合成

### 24. 文字水印（drawtext）
```bash
ffmpeg -i in.mp4 -vf "drawtext=text='Playhouse':fontsize=36:fontcolor=white:x=20:y=20" out.mp4
```
左上角叠加文字水印。

### 25. 图片水印（overlay）
```bash
ffmpeg -i in.mp4 -i logo.png -filter_complex "[0:v][1:v]overlay=W-w-20:H-h-20" out.mp4
```
把 logo 叠到右下角，留 20 像素边距。

### 26. 画中画（overlay）
```bash
ffmpeg -i in.mp4 -i pip.mp4 -filter_complex "[1:v]scale=480:-2[p];[0:v][p]overlay=20:20" out.mp4
```
把小画面缩放后叠到主画面左上角。

### 27. 左右并排堆叠（hstack）
```bash
ffmpeg -i left.mp4 -i right.mp4 -filter_complex "[0:v]scale=640:360[a];[1:v]scale=640:360[b];[a][b]hstack" out.mp4
```
两路视频缩放到同高后左右拼接。

### 28. 上下堆叠（vstack）
```bash
ffmpeg -i top.mp4 -i bottom.mp4 -filter_complex "[0:v]scale=640:360[a];[1:v]scale=640:360[b];[a][b]vstack" out.mp4
```
两路视频缩放到同宽后上下拼接。

---

## 七、竖屏适配与模糊背景

### 29. 模糊背景竖屏适配
```bash
ffmpeg -i in.mp4 -filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20[bg];[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2" out.mp4
```
横屏视频放大模糊铺底，前景等比缩放居中，得到竖屏 9:16 画面。

### 30. 旋转
```bash
ffmpeg -i in.mp4 -vf "transpose=1" out.mp4
```
顺时针旋转 90°。`transpose=2` 为逆时针，`transpose=0`/`3` 为翻转。

---

## 八、过渡与效果

### 31. 淡入淡出（视频）
```bash
ffmpeg -i in.mp4 -vf "fade=t=in:st=0:d=1,fade=t=out:st=9:d=1" out.mp4
```
第 0 秒起淡入 1 秒，第 9 秒起淡出 1 秒。

### 32. 淡入淡出（音频）
```bash
ffmpeg -i in.mp4 -af "afade=t=in:st=0:d=1,afade=t=out:st=9:d=1" out.mp4
```
音频同步做 1 秒淡入淡出。

### 33. 色彩校正（eq）
```bash
ffmpeg -i in.mp4 -vf "eq=brightness=0.05:contrast=1.15:saturation=1.2" out.mp4
```
微调亮度、对比度、饱和度。

### 34. 防抖（vidstab 两遍）
```bash
ffmpeg -i in.mp4 -vf "vidstabdetect=shakiness=6:result=transforms.trf" -f null -
ffmpeg -i in.mp4 -vf "vidstabtransform=input=transforms.trf:smoothing=15" -c:a copy out.mp4
```
第一遍分析抖动轨迹，第二遍据此稳定画面。

---

## 九、拼接

### 35. 拼接（concat demuxer）
```bash
printf "file 'a.mp4'\nfile 'b.mp4'\n" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4
```
把同编码参数的多个文件按列表顺序拼接。

### 36. 拼接前统一转码
```bash
ffmpeg -i a.mp4 -c:v libx264 -crf 23 -c:a aac a_norm.mp4
ffmpeg -i b.mp4 -c:v libx264 -crf 23 -c:a aac b_norm.mp4
```
若源文件参数不一致，先各自转成相同参数再走 concat。

---

## 十、抽帧与缩略图

### 37. 抽帧
```bash
ffmpeg -i in.mp4 -vf "fps=1" frame_%04d.png
```
每秒抽 1 帧保存为 PNG 序列。

### 38. 生成单张缩略图
```bash
ffmpeg -i in.mp4 -ss 00:00:05 -vframes 1 thumb.jpg
```
取第 5 秒画面存为缩略图。

### 39. 生成缩略图网格
```bash
ffmpeg -i in.mp4 -vf "fps=1/5,scale=320:-1,tile=4x3" grid.jpg
```
每 5 秒取一帧，缩放后排成 4×3 网格。

### 40. 波形图
```bash
ffmpeg -i in.mp4 -filter_complex "[0:a]showwavespic=s=1280x360:colors=white" -frames:v 1 wave.png
```
把音频波形渲染成一张 PNG。

---

## 十一、字幕

### 41. 烧录字幕
```bash
ffmpeg -i in.mp4 -vf "subtitles=subs.srt" out.mp4
```
把外挂字幕硬编码进画面。

### 42. 指定字幕样式
```bash
ffmpeg -i in.mp4 -vf "subtitles=subs.srt:force_style='FontSize=28,PrimaryColour=&H00FFFFFF'" out.mp4
```
通过 force_style 控制字号与颜色。

---

## 十二、图片与幻灯片

### 43. 图片幻灯片
```bash
ffmpeg -framerate 1 -i img_%03d.jpg -c:v libx264 -pix_fmt yuv420p -r 30 slides.mp4
```
每张图停留 1 秒，输出 30 fps 视频。

### 44. 延时摄影（图片序列）
```bash
ffmpeg -framerate 24 -i shot_%05d.jpg -c:v libx264 -crf 20 -pix_fmt yuv420p timelapse.mp4
```
把按序编号的图片以 24 fps 合成为延时视频。

### 45. 单图生成视频（带时长）
```bash
ffmpeg -loop 1 -i cover.jpg -t 10 -vf "scale=1280:720" -c:v libx264 -pix_fmt yuv420p cover.mp4
```
让一张图循环成 10 秒视频。

---

## 十三、章节与元数据

### 46. 章节标记
```bash
ffmpeg -i in.mp4 -i chapters.txt -map_metadata 1 -c copy out.mp4
```
chapters.txt 使用 ffmetadata 格式，写入章节信息。

### 47. 写入元数据
```bash
ffmpeg -i in.mp4 -metadata title="My Video" -metadata artist="Playhouse" -c copy out.mp4
```
给输出文件写标题和作者信息。

---

## 十四、诊断与检查

### 48. 查看媒体信息
```bash
ffprobe -v error -show_format -show_streams in.mp4
```
列出容器与各流的详细参数，排查编码问题常用。

---

## 来源说明

本手册的操作清单参考自 https://github.com/calesthio/OpenMontage ，本文为独立重写，分类、标题、示例参数与说明文字均为自有表达。ffmpeg 命令本身属于事实性知识。
