# 资产交付总览

这是给人阅读的导航页；模型只接收各资产 `.image.txt` 或 `.draft.txt` 的完整正文。

## 总控台

资产数量：1
可提交提示词：1
待参考图草案：0
状态：已编译但未调用图像模型。真实身份一致性、画面质量和文字伪影仍需生图后人工检查。

## 资产目录

| 资产 | 类型 | 状态 | 参考图 | 用途 |
|---|---|---|---|---|
| 红伞误会·工作坊 · v1.0 | asset | ready-to-submit-not-generated | 无需参考图 | Create one opening keyframe before the exchange. |

## 逐项交付

### 红伞误会·工作坊 · v1.0

用途：Create one opening keyframe before the exchange.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：无需参考图；这是单项独立资产，按完整正文生成。

参考图上传助手：无需上传参考图；可直接复制完整提示词生成。

#### 复制：红伞误会·工作坊 · v1.0（完整正文）

完整文件：[下载/打开 ASSET_COMEDY_UMBRELLA.image.txt](ASSET_COMEDY_UMBRELLA.image.txt)

```text
Create a live-action wide keyframe in a cramped prop workshop. Pei Jun, a slim adult stage manager in a mustard vest, points at an empty red umbrella hook beside a tilted worktable while Tao Lin, an adult performer in a cobalt rehearsal jacket and loose red scarf, raises both empty gloved hands in exaggerated innocence. A rolling ladder, costume racks and one warm ceiling lamp establish the space. Keep the empty hook visibly readable, leave a clear floor path behind the ladder for the later red umbrella reveal, and preserve grounded feet and contact shadows. Avoid captions, extra umbrellas, duplicated hands and frozen theatrical smiles.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

