# 外置提示词示例

本目录下的 `<name>.md` 是外置提示词示例。把它们复制到运行目录的 `data/prompts/` 下即被热加载：

- 每次读取前按文件 mtime 检查是否需要重新加载，改提示词无需改代码、无需重启。
- 目录不存在时跳过；只扫描一级目录下的 `*.md`，不递归，跳过以 `.` 开头的文件。
- 文件名必须匹配 `^[a-zA-Z0-9][a-zA-Z0-9._-]*\.md$`。

## frontmatter 格式

文件必须以 `---\n` 开头，到下一个 `\n---\n` 之间的行为头：

```
---
name: shot-splitter
version: 1.0.0
description: 分镜拆分系统提示词
---

正文……
```

- 头内每行按第一个 `:` 切分 key/value，只识别 `name`/`version`/`description`，均 trim。
- `version`、`description` 可缺省（缺省为空串）。
- `name` 为空或文件缺少 frontmatter，该文件被跳过并打 warn 日志。
- 正文（body）为分隔线之后全文，去掉开头的空行。

## 占位符

正文中支持 `{{key}}` 占位符，通过 `PromptFileService.render(name, vars)` 替换；缺失的 key 替换为空串。

## 已接入

- `ScriptSplitterService` 已接入 `shot-splitter`：优先读 `data/prompts/shot-splitter.md`，文件缺失或读取失败时回退内置常量。
- `chapter-events.md` 为示例提示词，尚未接入任何服务。

修改：
