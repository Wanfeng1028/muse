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
| Create a neutral side-view asset in two-dimensional ink-and-paper animation · v1.0 | asset | ready-to-submit-not-generated | 无需参考图 | Create the single still specified in the complete prompt. |

## 逐项交付

### Create a neutral side-view asset in two-dimensional ink-and-paper animation · v1.0

用途：Create the single still specified in the complete prompt.
生成模式：GENERATE
提交状态：ready-to-submit-not-generated
上传：无需参考图；这是单项独立资产，按完整正文生成。

参考图上传助手：无需上传参考图；可直接复制完整提示词生成。

#### 复制：Create a neutral side-view asset in two-dimensional ink-and-paper animation · v1.0（完整正文）

完整文件：[下载/打开 INK_CHARACTER.image.txt](INK_CHARACTER.image.txt)

```text
Create a neutral side-view asset in two-dimensional ink-and-paper animation. A small cream folded-paper crane has a triangular body, a long folded neck, a pointed beak, one black ink eye and two thin black folded legs. Its broad paper surfaces stay quiet, with a few dark fold lines. The crane stands with both feet visible against warm empty paper; its wings remain folded. Use one broad upper-left light with readable shadow planes and localized contact shadows. Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.
```

## 使用顺序

1. 先按 `UPLOAD.md` 生成并批准依赖资产。
2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。
3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。

