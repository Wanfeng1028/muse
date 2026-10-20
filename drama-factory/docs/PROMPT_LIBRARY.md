# 提示词库（PROMPT_LIBRARY）

## 一句话定位

收集的实测提示词与教程拆解（抖音/X/GitHub 等渠道），配合剧坊与 skill 库使用。

## 数据模型

后端返回两个 DTO：`PromptSummary` 和 `PromptDetail`。`PromptDetail` 在 `PromptSummary` 基础上多一个 `content` 字段。

### PromptSummary

| 字段名 | 含义 | 取值规则 |
|---|---|---|
| `id` | 提示词唯一标识 | 相对路径去掉末尾 `.md`，把 `/` 全部换成 `__`。例如 `opus-video-prompts/prompts/01-inference-startup-launch.md` 的 id 是 `opus-video-prompts__prompts__01-inference-startup-launch`。 |
| `title` | 标题 | 取文件内容第一行以 `# ` 开头的标题；没有这种标题行就用文件名（去掉 `.md`）。 |
| `source` | 来源目录 | 相对路径中第一个 `/` 之前的目录名；文件直接在 `prompt-library/` 根下时值为 `根目录`。 |
| `path` | 相对路径 | 文件在 `prompt-library/` 下的相对路径。 |
| `summary` | 摘要 | 标题行之后的第一段正文，空白折叠成单空格，超过 200 字截断。 |

### PromptDetail

| 字段名 | 含义 | 取值规则 |
|---|---|---|
| `id` | 提示词唯一标识 | 同 `PromptSummary.id`。 |
| `title` | 标题 | 同 `PromptSummary.title`。 |
| `source` | 来源目录 | 同 `PromptSummary.source`。 |
| `path` | 相对路径 | 同 `PromptSummary.path`。 |
| `summary` | 摘要 | 同 `PromptSummary.summary`。 |
| `content` | 全文 | 文件完整内容。 |

## REST API

当前只有两个 GET 端点，没有写操作。

| 方法 | 路径 | 参数 | 返回体 | 状态码 |
|---|---|---|---|---|
| GET | `/api/prompts` | `q`（可选，query 参数，字符串） | `List<PromptSummaryDto>` | 200 |
| GET | `/api/prompts/{id}` | `id`（path 参数，字符串） | `PromptDetailDto` | 200 / 404 |

### 行为说明

- `GET /api/prompts`：`q` 为空时返回全部；非空时转小写后做子串匹配，只匹配 `title` 和 `summary`，不匹配全文 `content`。
- `GET /api/prompts/{id}`：按 `id` 精确查，查不到返回 404。

### curl 示例

```bash
# 获取全部提示词
curl http://localhost:8080/api/prompts

# 搜索（q 需 URL 编码）
curl "http://localhost:8080/api/prompts?q=video"

# 查看详情
curl http://localhost:8080/api/prompts/opus-video-prompts__prompts__01-inference-startup-launch
```

## 前端页面 prompts.html

页面标题为“提示词库 · AI 短剧工坊”，副标题为“收集的实测提示词与教程拆解：浏览、搜索、查看全文。”

- **搜索**：输入框输入后 300ms 防抖，调 `GET /api/prompts?q=<url 编码后的输入>`；输入框为空时调 `GET /api/prompts`。
- **列表**：结果渲染为卡片网格。每张卡片显示 `title`（无标题则显示 `id`）、`summary`、`来源：source · path`；卡片右下角有“查看全文”按钮。
- **详情**：点“查看全文”调 `GET /api/prompts/<url 编码后的 id>`，页面下方展开详情卡，显示标题、`来源：source · 路径：path`，并用 `pre` 标签原样展示 `content` 全文。详情卡有“返回列表”按钮，点击后收起详情卡。
- **空态**：无匹配结果时显示“没有找到匹配的提示词”。
- **报错**：加载失败时显示红色提示条“加载失败：<错误信息>”。
- **中英双语**：通过 `i18n.js`（`DFI18N`）切换，文案 key 前缀为 `prm.`。

## 新增提示词流程

1. 把 `.md` 文件拷入 `src/main/resources/prompt-library/` 下对应目录。可以放根目录，也可以新建子目录。
2. 同目录写一份 `_SOURCE.md`，记录以下内容：
   - 目录名
   - 拷入日期
   - muse 仓库 `prompt/` 下的原件路径
   - 原作者/链接
   - 许可证声明
   - “原件直拷，未改写——与 muse 仓库对应文件逐字节一致”
3. 重启应用。启动时会扫描 `classpath*:/prompt-library/**/*.md`，一次性加载进内存，自动收录新文件。

## source 字段说明

`source` 等于文件相对路径的第一级目录名。例如文件位于 `opus-video-prompts/` 下，`source` 就是 `opus-video-prompts`。如果文件直接放在 `prompt-library/` 根下，`source` 显示为 `根目录`。

## 待补充

以下功能由另一 worker（W-CTRL）并行开发中，尚未合入当前工作区，合入后补全：

- 分页（page/size）
- 按来源筛选
- 收藏功能

---

# 补充分册：收藏、分页、运维与 FAQ

## 1. 收藏功能

待补充（功能合入中，具体参数以合入后代码为准）

当前收藏功能由 W-CTRL 并行开发，尚未合入主工作区。以下为规划中的行为说明，实际接口以合入后的代码为准。

### 幂等语义
重复收藏同一个 prompt id，结果不变，不会重复计数。取消收藏后可以再次收藏，行为一致。

### 持久化文件
收藏数据保存在单机文件：
`${user.home}/.drama-factory/prompt-favorites.json`

### 单机限制
当前采用单机文件持久化，多实例或多机部署之间不共享收藏数据。换机器部署时，需要手动迁移该文件。

### 接口占位
收藏相关的 HTTP 接口形态待合入后补全，本册不预先定义路径、方法或参数。

## 2. 分页参数规范

待补充（功能合入中，具体参数以合入后代码为准）

### 现状
当前 `GET /api/prompts` 不支持分页，一次返回全量数组。可选 query 参数 `q` 按标题和摘要搜索。

### 规划中的分页语义
计划引入 `page`（第几页）和 `size`（每页条数）参数。默认值、上限、越界行为（如页码超出范围时返回空数组还是报错）一律以合入后实现为准，本册不预设具体数字。

## 3. 运维

### 收藏文件备份与迁移
收藏文件位于 `${user.home}/.drama-factory/prompt-favorites.json`。备份时直接拷贝该文件即可。恢复时放回同一路径，并重启应用。

### 坏文件排查
应用启动时会扫描 prompt-library 目录。坏文件（路径无法解析、id 为空、读取失败、id 冲突）会被跳过，并在日志中打 warn。日志 logger 名为 `com.dramafactory.service.prompt.PromptLibraryService`，warn 行会写明被跳过的文件与原因。排查时先看应用启动日志中该 logger 的 warn 输出。

## 4. FAQ

### 中文文件名的 id 是怎么算的？
相对路径去掉末尾 `.md` 后，把 `/` 全部换成 `__`，中文字符原样保留。例如相对路径 `教程/入门.md` 的 id 是 `教程__入门`。请求详情接口时，对 id 做 URL 编码。

### 某个 md 文件没出现在列表里，去哪查原因？
看应用启动日志，找 logger 名为 `com.dramafactory.service.prompt.PromptLibraryService` 的 warn 日志。路径无法解析、id 为空、读取失败、id 冲突这四种情况会 warn 并跳过该文件。

### 为什么搜正文里的词搜不到？
`q` 参数只匹配 title 和 summary，不匹配 content 全文。想搜全文请打开详情页用浏览器查找。

### source 显示"根目录"是什么意思？
表示文件直接放在 `prompt-library/` 根目录下，没有子目录。

### 新增 md 后为什么没生效？
扫描在应用启动时一次性完成，新增文件后需要重启应用。