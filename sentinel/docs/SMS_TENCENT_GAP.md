# 腾讯云短信通道：文档与代码不一致现状记录

本文只记录当前代码和文档对不上的地方，不改代码、不改口径。

## 一、SENTINEL_SMS_MODE=tencent 从环境变量进不来

现状：

- `internal/config/config.go` 里读 `SENTINEL_SMS_MODE` 的那段逻辑，先做 `strings.ToLower(strings.TrimSpace(...))`，空的话默认 `"mock"`，然后判断 `if smsMode != "mock" && smsMode != "aliyun"` 就直接 `return Config{}, fmt.Errorf("环境变量 SENTINEL_SMS_MODE 取值 %q 非法：仅支持 mock/aliyun", smsMode)`。
- 也就是说从环境变量设 `tencent` 会在 `Load()` 里直接报错退出，`cfg.SMSMode` 根本不会被赋成 `"tencent"`。
- 但是 `internal/notify/sms.go` 里的 `SMSConfig.BuildSender` 明确有 `case "tencent": return NewTencentSMSSender(c.Tencent)` 分支。
- `internal/config/config.go` 里 `SMSMode` 字段的注释写的是“mock（默认，内存记录不真发）、aliyun（阿里云短信）或 tencent（腾讯云短信）”，和上面 Load 的实际校验对不上。

影响：

- 走正常启动路径（main.go 里 `smsCfg := notify.SMSConfig{Mode: cfg.SMSMode, ...}` 再 `BuildSender`）时，`tencent` 模式永远进不来，`BuildSender` 里的 tencent 分支是死代码。
- 想用腾讯云通道，只能绕过 `config.Load()`，在别处手工把 `SMSConfig.Mode` 设成 `"tencent"` 并填好 `Tencent` 字段，实际部署没有这个入口。

## 二、腾讯云变量“填空就报错”的说法与实际不符

现状：

- `docs/OPERATIONS_SMS.md` 写的是 7 个 `SENTINEL_SMS_TENCENT_` 变量“填空时 NewTencentSMSSender 会返回 error”。
- `internal/notify/sms_tencent.go` 里 `NewTencentSMSSender` 实际只检查两个：`cfg.SecretId == ""` 和 `cfg.SecretKey == ""`，对应报错文案分别是“腾讯云短信 SecretId 为空，请配置 SENTINEL_SMS_TENCENT_SECRET_ID”和“腾讯云短信 SecretKey 为空，请配置 SENTINEL_SMS_TENCENT_SECRET_KEY”。
- `SmsSdkAppId`、`SignName`、`TemplateId` 这三个字段在 `NewTencentSMSSender` 里完全没有校验，为空也会返回 `nil` error，构造出一个各字段为空的发送器。`Region` 为空会回退到 `"ap-guangzhou"`，`Endpoint` 为空会回退到 `"sms.tencentcloudapi.com"`，`HTTPClient` 为空会回退到 `&http.Client{Timeout: 10 * time.Second}`。

影响：

- 按文档填了 SecretId/SecretKey 但漏了 SmsSdkAppId/SignName/TemplateId，程序启动阶段不会报错，只会在真正发短信的时候由腾讯云接口返回错误。
- 文档让人以为这 7 个都必填校验，实际只有 2 个。

## 三、文档里的变量名和 config.go 实际读的名字对不上

现状：

- `docs/OPERATIONS_SMS.md` 里写的变量名是 `SENTINEL_SMS_TENCENT_SECRETID`、`SENTINEL_SMS_TENCENT_SECRETKEY`、`SENTINEL_SMS_TENCENT_SMSSDKAPPID`、`SENTINEL_SMS_TENCENT_SIGNNAME`、`SENTINEL_SMS_TENCENT_TEMPLATEID`、`SENTINEL_SMS_TENCENT_REGION`、`SENTINEL_SMS_TENCENT_ENDPOINT`，词之间没有下划线分隔。
- `internal/config/config.go` 实际读的是 `SENTINEL_SMS_TENCENT_SECRET_ID`、`SENTINEL_SMS_TENCENT_SECRET_KEY`、`SENTINEL_SMS_TENCENT_SDK_APP_ID`、`SENTINEL_SMS_TENCENT_SIGN_NAME`、`SENTINEL_SMS_TENCENT_TEMPLATE_ID`、`SENTINEL_SMS_TENCENT_REGION`，分别赋给 `SMSTencentSecretID`、`SMSTencentSecretKey`、`SMSTencentSdkAppID`、`SMSTencentSignName`、`SMSTencentTemplateID`、`SMSTencentRegion`。
- `SENTINEL_SMS_TENCENT_ENDPOINT` 这个变量 `config.go` 根本没有读，`Config` 结构体里也没有对应的字段；`TencentConfig.Endpoint` 只有通过 `NewTencentSMSSender` 的入参才能设置，从环境变量进不来。
- `main.go` 装配 `notify.TencentConfig` 时 `Endpoint` 没有赋值，所以走正常启动路径时 `Endpoint` 永远是空串，`NewTencentSMSSender` 会把它填成 `"sms.tencentcloudapi.com"`。

影响：

- 按 `docs/OPERATIONS_SMS.md` 里的变量名设环境变量，`config.go` 一个都读不到，`SMSTencentSecretID` 等字段全是空串，`NewTencentSMSSender` 会报 SecretId 为空。
- 想改 Endpoint（比如指向自建代理或者测试环境）从环境变量这条路走不通，只能改代码。
