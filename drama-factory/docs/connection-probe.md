# 视频供应商"连接自检"原理

## 为什么做

drama-factory 走 BYOK（Bring Your Own Key）：用户自填 API Key。P0 红线是**不许点出假成功**——
用户配好 Key 后，必须给出一个**真实探测**结论，而不是假装"已连接"。

## 负向探测（零费用）

我们**不提交任何生成任务**，而是用 GET 查询一个**不存在**的探测任务 ID：

- 探测 ID 固定为 `__connectivity_probe__`。

因为该 ID 不存在，提供方不会创建任何计费任务，**零费用**。

## 两家提供方的依据（已核验官方文档）

### Agnes

`GET https://apihub.agnes-ai.com/agnesapi?video_id=__connectivity_probe__&model_name=agnes-video-2.5-flash`

官方错误表：**鉴权先行**。401=Key 无效、404=任务不存在。

- 404 ⟹ 密钥有效、链路畅通
- 401/403 ⟹ 密钥无效

### Qwen / DashScope

`GET https://dashscope.aliyuncs.com/api/v1/tasks/__connectivity_probe__`

Model Studio 任务查询文档：无效 Key 返回 401，不存在的 task_id 返回 404。

- 404 ⟹ 密钥有效
- 401 ⟹ 密钥无效

## 状态映射（铁律）

| HTTP / 情形 | 状态 | 用户文案 | 含义 |
| --- | --- | --- | --- |
| 401 / 403 | `AUTH_FAILED` | 密钥无效 | 密钥被拒 |
| 404 | `OK` | 连接正常 | 密钥有效、链路畅通 |
| 429 | `RATE_LIMITED` | 触发限流 | 稍后重试 |
| 网关抛异常 | `UNREACHABLE` | 网络不可达 | DNS / 超时 / 连接被拒 |
| 其他非 2xx | `PROVIDER_ERROR` | 服务方异常 | 服务方返回意外状态码 |
| 2xx | `OK` | 连接正常 | 理论上不应发生 |

**只有真实 404 或 2xx 才可判 OK。其他任何情况判 OK 就是造假。**

## 诚实保证

- 分类映射严格按上表；`detail` 中除 `OK` 外不出现"成功"二字。
- `UNREACHABLE` 的 detail 使用固定文案，**不拼接异常 message**（可能含敏感信息）。
- `detail`、异常 message、日志中**绝不出现密钥原文或片段**。
- 未配置密钥（resolver 返回 null）→ `AUTH_FAILED`，detail 说明需先在设置中心填写对应 api-key。
- `submit`/`poll` 在密钥为 null 时抛 `IllegalStateException`，不产生 NPE。

## Mock 提供方

`MockVideoProvider` 是演示用提供方，不发起真实网络请求，
`probeConnectivity()` 直接返回 `OK` + "演示用提供方，无需真实连接"。

## UNSUPPORTED

非 `VIDEO` 模块，或 `VIDEO` 模块下名称无法匹配到已接入的提供方（agnes / qwen / mock），
统一返回 `UNSUPPORTED`，**不抛异常、不判 OK**。
