# Drama Factory UI 设计体系（v1）

> 自然中性，不刻意做暖、不做旧、不做深蓝紫。一切页面照此验收，有据可查。
> 竞品（pix6）只借功能与信息架构，**视觉零借用**。

## 1. 色板（Design Tokens）

CSS 变量定义在 `static/app.css`（`:root` = 暗色默认，`[data-bs-theme="light"]` = 亮色）。

| Token | 亮色 | 暗色 | 用途 |
|---|---|---|---|
| `--bg` | `#FFFFFF` 纯白 | `#16161A` 中性灰黑 | 页面底 |
| `--bg-elev` | `#F7F7F8` 极淡灰 | `#1C1C21` | 侧边栏 |
| `--surface` | `#FFFFFF` | `#202027` | 卡片底 |
| `--surface-2` | `#F4F4F5` | `#26262E` | 输入框/条形轨道 |
| `--border` | `rgba(0,0,0,.08)` 发丝 | `rgba(255,255,255,.08)` 发丝 | 边框 |
| `--border-soft` | `rgba(0,0,0,.06)` | `rgba(255,255,255,.06)` | 弱分隔 |
| `--text` | `#111111` | `#EDEDEF` | 主文字 |
| `--text-2` | `#555555` | `#A1A1AA` | 次文字 |
| `--text-3` | `#999999` | `#71717A` | 弱文字/占位 |
| `--ink` | `#111111` | `#FFFFFF` | 主按钮底（随主题反转） |
| `--ink-text` | `#FFFFFF` | `#111111` | 主按钮字 |
| `--green` / `--amber` / `--red` | `#16803C` / `#B45309` / `#DC2626` | `#4ADE80` / `#FBBF24` / `#F87171` | 成功/警告/危险 |

原则：**不偏暖、不偏蓝**。暖黄变量（`#F8F7F4`、`#F1EFEA`、`#2B2620` 等）已全部删除，发现即 bug。

## 2. 字体

- 正文：系统字体栈（`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`）。
- 等宽：`--mono`（`ui-monospace, "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace`）——仅用于时间码、API 地址、Key 掩码、快捷键、数字。

## 3. 间距与圆角

- 页面：`.page` 内边距 24px；卡片 `.card` 内边距 `16px 20px`，圆角 `10px`（`--radius: 8px`，卡片 10px）。
- 按钮 pill：`border-radius: 999px`，主按钮 `padding: 8px 20px`。
- 输入框/下拉：圆角 `8px`，`padding: 8px 12px`。
- 卡片：**实色 + 发丝边框，零阴影**（`box-shadow: none`）。

## 4. 按钮规范（两款）

1. **主按钮** `.btn.btn-primary`：墨色 pill（亮色 `#111` 底白字，暗色反转为白底黑字），`font-weight: 500`。
2. **安静款** `.btn.btn-quiet`：透明底、`--text-2` 字，hover 时 `--surface` 底。

**铁律：每页最多一个 pill 主按钮**，其余操作（取消/编辑/删除/次级）全用安静款。
危险操作可用 `.btn-danger`（文字按钮样式，不做 pill）。

## 5. 图标

- 只用 **Lucide**（`/vendor/lucide.min.js` 本地包），`<i data-lucide="…">` + `lucide.createIcons()`。
- **禁用**：emoji 当图标、字母首字母当 logo/头像。

## 6. Badge 与状态色

- `.badge`：实色淡底（`--accent-soft`），`font-weight: 550`，无辉光。
- 状态：成功 `--green`、警告 `--amber`、危险 `--red`、进行中 `--accent`。
- 空值/未知：一律显示 `—`（em dash），**不许编数字、不许用假数据画图表**。

## 7. 空状态文案风格

- 一句克制陈述，不煽情、不 polished 四字词。例：
  - "还没有接入图片模型"
  - "暂无供应商，点击右上添加"
  - "暂无用量数据，先跑一次运行吧"
- 配一个安静款行动按钮（如"去通道管理添加 API"），不许放装饰性插画。

## 8. 文案红线

禁用：Unleash / Empower / Seamless / Next-generation 及其四字中文 polished 对应词。
禁用"工作台"一词（产品定位是 Harness）。

## 9. 黑名单（出现即 bug）

1. `backdrop-filter` / 玻璃拟态（全站零出现）
2. 渐变紫、深蓝紫调（`#6xxx`/`#7xxx` 蓝紫、`linear-gradient` 彩色）
3. emoji 当图标
4. 字母首字母 logo/头像（默认用几何/插画头像）
5. 暖黄/做旧配色变量
6. 卡片阴影（`box-shadow` 只允许 `none`）
7. 假数据、假成功态（未知显示 `—`；未实现的功能明确告知，不许点出假成功）

## 10. 主题切换

- `document.documentElement` 的 `data-bs-theme`（`light`/`dark`），`localStorage` key `df-theme`。
- 每个 HTML 必须在 `<head>` 顶部内联主题脚本（防闪烁），与其他页一致：
  ```html
  <script>try{var t=localStorage.getItem('df-theme');document.documentElement.setAttribute('data-bs-theme',t==='dark'?'dark':'light');}catch(e){document.documentElement.setAttribute('data-bs-theme','light');}</script>
  ```
- logo 用 `currentColor`，28px 下深浅主题都清晰。
