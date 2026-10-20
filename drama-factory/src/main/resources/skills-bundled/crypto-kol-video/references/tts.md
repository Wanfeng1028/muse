# 配音

## 默认：MiniMax speech-2.8-hd（用户本机的 mmx CLI）
- `kol.py voicekit <proj> <dir>` 生成 `text/<scene_id>.txt`、`gen_fill.sh` 和 `双击生成配音.command`。
- 参数：`--model speech-2.8-hd --voice male-qn-jingying --speed 1.15 --language Chinese --format wav --sample-rate 32000`，读音修正来自 video.json 的 `pronunciations`（格式 `词/(拼音1)(拼音2)`，轻声写 5，如 `拿得久/(na2)(de5)(jiu3)`）。
- mmx 从 `~/.mmx/config.json` 或环境变量 `MINIMAX_API_KEY` 读 Key。**API Key 只在用户自己的机器上用**，不要让用户把 Key 发进对话。
- 换声线或语速：`VOICE=presenter_male SPEED=1.1 bash gen_fill.sh`。
- 云端沙盒通常连不上 MiniMax，所以让用户在本机运行脚本，再把 `out/<voice>/` 里的 wav 取回。
- 1.15 倍速约每秒 5 个汉字（含停顿）。`kol.py check` 会按这个估算时长。

## 其他来源
任何 TTS 或真人录音都可以：每个场景一个音频文件，命名为 `<scene_id>.wav`（也支持 mp3、m4a、flac），然后 `kol.py timeline <proj> <dir>`。
对齐靠 ASR 加拼音匹配，所以口播内容必须和 `tts` 一致。即兴发挥会降低匹配率，字幕时间会不准。

## 重配某一段
把旧 wav 挪进 `_old/`（不要删），改 `text/<id>.txt` 和 video.json 里对应的 `tts`、`chunks`，再运行 `gen_fill.sh`。它只会生成缺失的段落。
