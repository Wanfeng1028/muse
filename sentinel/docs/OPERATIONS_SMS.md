# 短信告警运维

这一章讲短信告警（腾讯云 provider）怎么配、怎么排障、怎么控成本、怎么回滚。代码位置：`internal/notify/sms_tencent.go`，发送记录在 `internal/store/sms_log.go` 和 migration v9 的 `sms_log` 表。

## 1. 环境变量清单

7 个变量，前缀都是 `SENTINEL_SMS_TENCENT_`，由 `internal/config/config.go` 的 `Load()` 读取。5 个必填项空值时 `Load()` 在启动阶段直接报错退出，不会带着坏配置跑起来；`NewTencentSMSSender` 另对 SecretId/SecretKey 做二次校验。

| 变量名 | 必填/选填 | 默认值 | 非法值行为 |
| --- | --- | --- | --- |
| `SENTINEL_SMS_TENCENT_SECRET_ID` | 必填 | 无 | 空值时 `config.Load` 启动失败 |
| `SENTINEL_SMS_TENCENT_SECRET_KEY` | 必填 | 无 | 空值时 `config.Load` 启动失败 |
| `SENTINEL_SMS_TENCENT_SDK_APP_ID` | 必填 | 无 | 空值时 `config.Load` 启动失败 |
| `SENTINEL_SMS_TENCENT_SIGN_NAME` | 必填 | 无 | 空值时 `config.Load` 启动失败 |
| `SENTINEL_SMS_TENCENT_TEMPLATE_ID` | 必填 | 无 | 空值时 `config.Load` 启动失败 |
| `SENTINEL_SMS_TENCENT_REGION` | 选填 | `ap-guangzhou` | 填了不支持的 Region，腾讯云接口返回错误，`Send` 报错，记录写进 `sms_log` |
| `SENTINEL_SMS_TENCENT_ENDPOINT` | 选填 | `sms.tencentcloudapi.com` | 填了不可达地址，`Send` 报网络错误，记录写进 `sms_log` |

SecretId、SecretKey 属于敏感信息，别写进仓库、别贴到工单里。轮换密钥后要重启进程才会生效。

## 2. 腾讯云侧前置条件

在腾讯云控制台先把这三件套备齐，缺一个都发不出去：

- 短信签名（SignName）：对应 `SENTINEL_SMS_TENCENT_SIGN_NAME`，控制台审核通过后才能用。
- 短信模板（TemplateId）：对应 `SENTINEL_SMS_TENCENT_TEMPLATE_ID`，模板内容要和实际发送内容对得上。
- 短信应用 ID（SmsSdkAppId）：对应 `SENTINEL_SMS_TENCENT_SDK_APP_ID`，在短信控制台的应用管理里能看到。

Region 目前支持的值：`ap-guangzhou`、`ap-nanjing`、`ap-beijing`、`ap-shanghai`、`ap-hongkong`、`ap-singapore`。填别的地方腾讯云会拒绝，具体以腾讯云短信文档里列出的可用地域为准。

## 3. 排障

### 3.1 查 sms_log 表

发送成功失败都会落库，出问题先查这张表。

按手机号过滤：

```sql
SELECT id, phone, status, error_code, error_message, created_at
FROM sms_log
WHERE phone = '13800000000'
ORDER BY created_at DESC
LIMIT 50;
```

按状态过滤（`status` 是发送结果，具体取值看表定义）：

```sql
SELECT id, phone, status, error_code, error_message, created_at
FROM sms_log
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 50;
```

按时间过滤：

```sql
SELECT id, phone, status, error_code, error_message, created_at
FROM sms_log
WHERE created_at >= NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC
LIMIT 50;
```

页面上也能看：`/sms-log`。接口是 `GET /api/sms/log`，支持带过滤参数，具体参数名看接口实现。

### 3.2 常见错误码

腾讯云短信接口返回的常见错误码，对照排查。下面这些只是常见情况，**以官方文档为准**：

| 错误码 | 含义 | 排查方向 |
| --- | --- | --- |
| `FailedOperation.SignatureIncorrectOrUnapproved` | 签名不正确或未审核通过 | 核对 `SIGNNAME` 和签名审核状态 |
| `FailedOperation.TemplateIncorrectOrUnapproved` | 模板不正确或未审核通过 | 核对 `TEMPLATEID` 和模板审核状态 |
| `FailedOperation.PhoneNumberInBlacklist` | 手机号在黑名单 | 确认号码是否被退订或拉黑 |
| `FailedOperation.InsufficientBalance` | 账户余额不足 | 去腾讯云充值 |
| `LimitExceeded.PhoneNumberDailyLimit` | 单号码当日发送超限 | 降频，或换号 |
| `AuthFailure.SignatureFailure` | 请求签名校验失败 | 核对 SecretId、SecretKey，检查服务器时间 |

完整错误码列表去腾讯云短信 API 文档查，别拿这张表当唯一依据。

### 3.3 签名失败三步自查

签名报错时按这三步走：

1. 打开腾讯云短信控制台，看签名列表里对应签名是不是"已通过"。审核中或被打回都不行。
2. 拿控制台里显示的签名文本，和进程里 `SENTINEL_SMS_TENCENT_SIGN_NAME` 的值逐字对比，前后空格、全半角、大小写都算差异。
3. 确认签名用途和短信内容匹配。腾讯云对签名和模板有配对要求，对不上也会拒。

## 4. 成本与限流

单条短信价格看腾讯云定价页，**以腾讯云定价页为准**，这里不写具体数字。计费按实际提交成功的条数走，长短信按拆分后的条数算。

发送频率建议：

- 告警短信按告警级别分流，只有 P0/P1 才发短信，其余走 webhook。
- 同一个告警项在短时间内重复触发时做合并，比如 5 分钟内只发一条。
- 单号码设置日发送上限，别让一个号码把配额吃光。
- 定期看 `sms_log` 的发送量，量突然涨上来先查是不是告警风暴。

## 5. 回滚：切回 webhook 告警

要把短信告警停掉、切回 webhook，三步：

1. 编辑告警配置，把短信通道关掉，只留 webhook 通道。
2. 清掉或注释掉进程环境里 `SENTINEL_SMS_TENCENT_*` 这 7 个变量，避免启动时再去连腾讯云。
3. 重启服务，然后发一条测试告警，确认 webhook 收到、短信没发出去。

回滚不影响 `sms_log` 表里的历史数据，表先留着，确认不用了再清理。
