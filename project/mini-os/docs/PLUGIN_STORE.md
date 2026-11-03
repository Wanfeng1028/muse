# mini-os 插件开发规范

本文档说明 mini-os 应用商店第 2 批（插件安装包解析与沙箱安装）里插件的打包格式、`plugin.json` 字段、入口 JS 约定、权限语义，以及安装时的硬性限制。

## 1. 安装包格式

插件安装包是一个标准的 zip 文件（`.zip`）。压缩包里必须包含一个顶层文件 `plugin.json`，以及 `entry` 字段指向的 JS 文件。

目录结构示例：

```
plugin.json
main.js
assets/
  logo.txt
```

注意：

- 文件必须直接放在 zip 根目录下，不允许再套一层父目录。
- 文件路径不允许出现 `..`，不允许以 `/` 或 `\` 开头，不允许 `C:\` 这种盘符。
- 压缩包里不允许放符号链接（mini-os 安装时按普通文件处理，遇到异常条目会拒绝）。

## 2. plugin.json 字段说明

`plugin.json` 是一个 UTF-8 编码的 JSON 对象，字段如下：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | string | 是 | 插件唯一标识。只能包含字母、数字、`-`、`_`、`.`，不允许 `/`、`\`、`..`。安装后目录名即为此 id。 |
| `name` | string | 是 | 插件显示名，用于应用商店和任务栏。不能为空。 |
| `version` | string | 是 | 语义化版本，例如 `1.0.0`。不能为空。 |
| `entry` | string | 是 | 入口 JS 文件相对路径，必须以 `.js` 结尾。 |
| `description` | string | 否 | 一句话描述，显示在应用列表里。默认空字符串。 |
| `icon` | string | 否 | 图标名，走 mini-os 的 Lucide 图标体系。不要用插件名首字母当图标。默认空字符串。 |
| `permissions` | string[] | 否 | 权限列表，见第 4 节。默认空数组。 |

示例：

```json
{
  "id": "hello",
  "name": "Hello",
  "version": "1.0.0",
  "entry": "main.js",
  "description": "一个示例插件",
  "icon": "sparkles",
  "permissions": ["fs.read", "settings.read"]
}
```

安装时校验规则：

- `id` 非空，且不含 `/`、`\`、`..`。
- `id` 必须与安装目录名一致（安装器按 `id` 生成目录，因此天然一致）。
- `name`、`version`、`entry` 非空。
- `entry` 必须通过路径校验，并以 `.js` 结尾。
- 若 `data_dir/plugins/<id>/` 已存在，安装直接失败，返回“已安装”。

## 3. 入口 JS 约定

`entry` 指向的 JS 文件是插件启动时加载的脚本。约定：

- 必须是 UTF-8 文本。
- 顶层不能有裸的 `await`（用 `async function main()` 包裹）。
- 脚本通过全局对象 `muse` 访问宿主能力，例如：

```js
async function main() {
  muse.log("hello from plugin");
  const data = await muse.fs.read("assets/logo.txt");
  muse.ui.mount(document.getElementById("root"), data);
}
main();
```

- `muse` 提供的 API 与 `permissions` 字段一一对应。没有声明权限就调用对应 API，宿主会抛错。
- 插件不得直接访问 `window`、`document.cookie`、`localStorage` 等浏览器全局，宿主沙箱会拦截。

## 4. permissions 语义

`permissions` 是一个字符串数组，每一项代表一项宿主能力。当前支持：

| 权限 | 风险 | 说明 |
| --- | --- | --- |
| `fs.read` | 中 | 能读你的全部文件 |
| `fs.write` | 高 | 能修改或删除你的文件 |
| `settings.read` | 低 | 能读你的偏好设置 |

规则：

- 权限必须落在白名单内，申请未知权限会被拒绝安装。
- 同一权限不允许重复声明。
- 未声明的权限调用对应 API 会立即失败，错误信息写明缺失的权限名。
- 权限不会跨插件继承，每个插件独立声明。
- 权限校验发生在宿主侧，插件无法绕过。

## 5. 硬性限制

安装器在解析 zip 时执行以下检查，任一不通过即拒绝安装，返回 400 和中文错误信息：

| 限制 | 值 |
| --- | --- |
| 解压后总大小上限 | 10 MB（10485760 字节） |
| zip 内文件数上限 | 200 |
| 路径穿越 | 拒绝，检测到 `..`、绝对路径、盘符即失败 |
| 缺失 `plugin.json` | 拒绝 |
| `plugin.json` 不是合法 JSON | 拒绝 |
| 目标插件目录已存在 | 拒绝，提示已安装 |

10MB 限制按解压后字节数计算，不看压缩包本身大小。压缩包可以很小，但只要解压后超过 10MB 就拒绝。这样做是为了防 zip 炸弹。

## 6. 安装接口

后端提供三个插件管理接口：

- `GET /api/plugins`：列出已安装插件，返回 `PluginManifest` 数组 JSON。
- `POST /api/plugins/preview`：只解析校验上传的 zip，不写盘，成功返回 `PluginManifest` JSON。
- `POST /api/plugins/install`：解析校验并安装上传的 zip。
- `DELETE /api/plugins/:id`：卸载插件，成功返回 204。

`preview` 与 `install` 请求体均为 `multipart/form-data`，文件字段名为 `file`。

- 成功：`preview`/`install` 返回 200 和 `PluginManifest` 的 JSON；`uninstall` 返回 204。
- 失败：返回 400（卸载未安装的插件返回 404），响应体是纯文本中文错误信息，例如 `压缩包为空`、`缺少 plugin.json`、`解压后总大小超过 10MB 上限（实际 12345678 字节）`。

示例：

```
curl -X POST http://127.0.0.1:3000/api/plugins/install \
  -F "file=@hello.zip"
```

插件数据目录由 `MINIOS_DATA_DIR` 决定：设置该环境变量时使用其值，否则取 `DATABASE_PATH` 的父目录，再否则回退到 `data`。插件安装到 `<data_dir>/plugins/<id>/`。

安装成功后的目录结构：

```
<data_dir>/plugins/hello/
  plugin.json
  main.js
  assets/
    logo.txt
```

## 7. 卸载

已安装插件通过 `uninstall(id, data_dir)` 卸载，对应目录会被整体删除。若目录不存在，返回“插件 <id> 未安装”。