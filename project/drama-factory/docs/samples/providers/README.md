# 自定义 Provider 描述符（热加载）

drama-factory 支持不改 Java 代码、不重启服务地新增视频生成通道：把一个 JSON 描述符文件丢进运行目录的 `data/providers/` 即可。

## 使用方式

1. 复制本目录下的示例文件（如 `example-seedance-compat.json`）到 drama-factory 运行目录的 `data/providers/` 下。
2. 按需修改文件内容：`id`、`label`、`submit.url`、`poll.url`、`auth.keyRef` 等。
3. 保存即生效。注册表每次调用前按文件 mtime 检查，改动或新增文件会被自动重载，无需重启服务。

通道名形如 `descriptor:seedance-compat`，即在 `id` 前面加 `descriptor:` 前缀。

## 密钥来源

`auth.keyRef` 支持两种写法，禁止把密钥明文写进 JSON：

- `env:VAR_NAME`：从环境变量读取。
- `settings:some.key`：从应用设置（SettingsService）读取。

`auth.type` 支持：

- `bearer`：自动加 `Authorization: Bearer <key>` 头。
- `header`：用 `headerName` 指定的头名（缺省 `X-Api-Key`）携带密钥明文。
- `none`：不附加鉴权头。

## 文件命名与校验

- 文件名必须匹配 `^[a-zA-Z0-9][a-zA-Z0-9._-]*\.json$`，且不以 `.` 开头。
- 校验不通过的文件会被跳过并记录 warn 日志，不影响其它通道。
- 删除文件后对应通道会在下次重载时消失。
</｜DSML｜ parameter>
</｜DSML｜ invoke>
</｜DSML｜ calls>