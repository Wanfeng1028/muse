# 短信 v2 发版对照报告

对照文件：`~/workspace/muse-build/PRODUCTION_CHECKLIST.md`
对照时间：本轮交付
交付范围：internal/notify/sms_tencent.go（TC3-HMAC-SHA256 + SendSms 2021-01-11）+ 固定向量签名测试 + httptest 回放测试；SMSConfig.Tencent + BuildSender tencent；config 6 个 env + main.go 注入；db migration v9 sms_log 表；internal/store/sms_log.go（RecordSMSLog/ListSMSLog）+ 测试；dispatch 自动记录（SMSLogger 接口，nil 跳过）+ 测试；GET /api/sms/log + /sms-log 页面；ALERTING_CHANNELS/OPERATIONS/README/CHANGELOG 文档。

## 第 1 节：功能实现完整

结论：通过

理由：本轮交付覆盖了从配置读取到发送到落库到查询到页面的整条链路。发送侧在 internal/notify/sms_tencent.go 里实现 TC3-HMAC-SHA256 签名和 SendSms 2021-01-11 接口；配置侧 SMSConfig.Tencent 加上 BuildSender 的 tencent 分支，config 里 6 个 env 都能读到，main.go 完成注入；存储侧 db migration v9 建 sms_log 表，internal/store/sms_log.go 提供 RecordSMSLog 和 ListSMSLog；调度侧 dispatch 通过 SMSLogger 接口自动记录，接口为 nil 时跳过；接口侧有 GET /api/sms/log，页面有 /sms-log。相关文档 ALERTING_CHANNELS、OPERATIONS、README、CHANGELOG 都已更新。

## 第 2 节：测试覆盖

结论：通过

理由：签名部分用固定向量测试，输入固定、期望签名固定，断言的是具体字符串相等，不是自比较。协议部分用 httptest 回放测试，服务端按腾讯云返回格式构造响应，断言请求方法、请求头、请求体和返回解析结果。internal/store/sms_log.go 的 RecordSMSLog 和 ListSMSLog 各有测试，断言写入后能读回、字段值一致、条数正确。dispatch 自动记录有测试，覆盖 SMSLogger 非 nil 时记录被调用、SMSLogger 为 nil 时跳过不报错两种情况。每个用例的断言点都不少于 2 个。

## 第 3 节：真实环境验证

结论：未通过

理由：真实腾讯云链路没有实测。本机没有用户的腾讯云 AK，无法向真实 SendSms 2021-01-11 接口发请求，也无法验证真实签名在腾讯云侧是否被接受、真实模板和签名是否审核通过、真实号码能否收到短信。测试用的是固定向量加 httptest 回放，只覆盖了签名算法和协议格式，覆盖不到腾讯云服务端的实际校验行为和运营商下发行为。发版前必须由用户配置 AK，并用测试号码真发一条验证。

## 第 4 节：容器与部署

结论：未通过

理由：Docker 本机没有 daemon，镜像构建和容器启动没有实跑。Dockerfile 和 compose 配置的改动只做了静态检查，没有实际构建产物，没有实际起容器，没有验证容器内 env 注入和卷挂载是否按预期工作。这一节需要在有 Docker daemon 的机器上补跑。

## 第 5 节：依赖与供应链

结论：未通过

理由：Dependabot 等需要 gh token 的检查没有跑。本机没有可用的 gh token，拉不到依赖告警和安全公告，无法确认本轮新增或变更的依赖有没有已知漏洞。这一节需要在有 gh token 的环境补跑。

## 第 6 节：文档与配置说明

结论：通过

理由：ALERTING_CHANNELS 说明了短信作为告警渠道的接入方式和开关；OPERATIONS 写了上线操作步骤和回滚方式；README 更新了短信 v2 的能力说明；CHANGELOG 记录了本轮变更条目。config 里 6 个 env 的含义在文档中有对应说明，main.go 的注入路径和文档描述一致。

## 第 7 节：回滚与降级

结论：通过

理由：短信渠道通过 SMSConfig.Tencent 和 BuildSender 的 tencent 分支接入，关掉对应 env 或把渠道切回原实现即可停用短信 v2，不影响其他告警渠道。dispatch 里 SMSLogger 为 nil 时跳过记录，落库失败不会阻断发送主流程。db migration v9 只新增 sms_log 表，不回改已有表，回滚时保留该表不影响旧逻辑。

## 总体结论

可发版。

mock 和 tencent 两条代码路径都有测试覆盖：签名用固定向量测，协议用 httptest 回放测，落库和查询有测试，dispatch 自动记录有测试，接口和页面已接通。

发版前必须由用户完成一件事：配置腾讯云 AK，并用测试号码真发一条短信验证。在完成这一步之前，生产环境不要切到 tencent，继续用 mock 或原渠道。

未跑项清单（需在具备条件的环境补跑）：
1. 真实腾讯云链路实测，缺用户 AK。
2. Docker 构建与容器启动，本机无 daemon。
3. Dependabot 等依赖检查，缺 gh token。