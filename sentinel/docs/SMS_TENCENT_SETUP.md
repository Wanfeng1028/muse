# 腾讯云短信接入说明

这份文档面向要用 sentinel 发短信的人。跟着走，5 分钟能发出第一条测试短信。

## 1. 五分钟快速开始

### 1.1 在腾讯云控制台申请签名和模板

1. 登录腾讯云控制台，进入「短信」产品。
2. 左侧选「国内短信」→「签名管理」，点「创建签名」。
   - 签名用途选「自用」。
   - 签名内容填你的应用名或网站名，比如 `晚风科技`。
   - 上传对应的证明文件（营业执照、App 备案截图等，按控制台要求来）。
   - 提交后等审核，一般几十分钟到几小时。
3. 左侧选「国内短信」→「正文模板管理」，点「创建正文模板」。
   - 模板名称随便起，比如 `登录验证码`。
   - 模板内容里用占位符写变量，比如 `您的验证码是{1}，5分钟内有效。`。
   - 提交后等审核。
4. 审核通过后，记下两个 ID：
   - **签名 ID**：在签名列表里，形如 `1234567`（纯数字）。注意腾讯云控制台里显示的可能是 `签名内容` 或 `SignId`，我们要的是数字 ID。
   - **模板 ID**：在模板列表里，形如 `7654321`（纯数字）。

### 1.2 填 7 个环境变量

sentinel 用 `TencentConfig` 这 7 个字段读配置，对应的环境变量名是 `SENTINEL_SMS_TENCENT_*`。在你的 `.env` 文件里填：

```
SENTINEL_SMS_TENCENT_SECRET_ID=你的SecretId
SENTINEL_SMS_TENCENT_SECRET_KEY=你的SecretKey
SENTINEL_SMS_TENCENT_REGION=ap-guangzhou
SENTINEL_SMS_TENCENT_SDK_APP_ID=你的短信应用SdkAppId
SENTINEL_SMS_TENCENT_SIGN=你的签名内容
SENTINEL_SMS_TENCENT_TEMPLATE_ID=你的模板ID
SENTINEL_SMS_TENCENT_ENDPOINT=sms.tencentcloudapi.com
```

逐个说明：

- `SENTINEL_SMS_TENCENT_SECRET_ID`：腾讯云 API 密钥的 SecretId，在「访问管理」→「API 密钥管理」里建。
- `SENTINEL_SMS_TENCENT_SECRET_KEY`：上面那条密钥的 SecretKey，只显示一次，建完就存好。
- `SENTINEL_SMS_TENCENT_REGION`：短信服务的地域，国内一般填 `ap-guangzhou`。填错会报地域错误。
- `SENTINEL_SMS_TENCENT_SDK_APP_ID`：短信应用 ID，在「短信」→「应用管理」→「应用列表」里能看到，形如 `1400000000`。
- `SENTINEL_SMS_TENCENT_SIGN`：签名内容，填你在 1.1 里申请通过的签名文字，比如 `晚风科技`。注意这里填的是文字，不是数字 ID。
- `SENTINEL_SMS_TENCENT_TEMPLATE_ID`：模板 ID，填 1.1 里记下的数字，比如 `7654321`。
- `SENTINEL_SMS_TENCENT_ENDPOINT`：API 域名，固定填 `sms.tencentcloudapi.com`。除非你走私有云，否则别改。

### 1.3 重启服务

改完 `.env` 后重启 sentinel 进程，让配置生效。重启方式看你部署方式（systemd、docker、pm2 等），这里不展开。

### 1.4 发一条测试短信

sentinel 里发短信的入口是 `NewTencentSMSSender` 建出来的 sender，调它的 `Send(phone, message)` 方法。你可以在代码里调，也可以通过业务接口触发。

先拿一个能收短信的手机号，调一次：

```go
sender := NewTencentSMSSender(cfg)
err := sender.Send("13800138000", "123456")
if err != nil {
    // 处理错误
}
```

`Send` 的第二个参数 `message` 会填进模板的第一个变量 `{1}`。也就是说，模板是 `您的验证码是{1}，5分钟内有效。`，你传 `"123456"`，用户收到的就是 `您的验证码是123456，5分钟内有效。`。

### 1.5 到 /sms-log 页面验证

打开 sentinel 的 `/sms-log` 页面。这个页面展示短信发送记录。

页面数据来自接口 `GET /api/sms/log`。如果你打不开页面，可以直接请求这个接口看返回：

```
GET /api/sms/log
```

在返回里找刚才那条记录，确认：
- 手机号是你要发的号。
- 发送状态是成功。
- 时间对得上。

如果没记录，说明请求没走到发送逻辑；如果有记录但状态是失败，看失败原因（一般是签名/模板/密钥/欠费问题）。

## 2. 手机号格式：toE164 行为说明

sentinel 发短信前会把手机号转成 E.164 格式再发给腾讯云。转换逻辑在 `toE164` 里，规则很简单：

- **不带区号的号**：默认按 `+86`（中国大陆）补全。
  - 输入 `13800138000` → 输出 `+8613800138000`。
- **已经带区号的号**：原样保持，不再补。
  - 输入 `+8613800138000` → 输出 `+8613800138000`。
  - 输入 `+14155552671` → 输出 `+14155552671`。

实际使用注意：

- 国内号直接写 11 位手机号就行，别自己加 `+86`，加了也不会错，只是没必要。
- 给境外号发，必须自己写完整 E.164，带上国家码，否则会被当成国内号补 `+86`，发错地方。
- 别在号里加空格、横线、括号，只留数字和开头的 `+`。

## 3. 模板变量：TemplateId 与 message 的对应关系

腾讯云的短信模板是审核过的固定文案，变量用 `{1}`、`{2}`、`{3}` 这种占位符。`SENTINEL_SMS_TENCENT_TEMPLATE_ID` 决定用哪个模板，`Send(phone, message)` 的 `message` 决定第一个变量的值。

对应关系：

- 你填的 `SENTINEL_SMS_TENCENT_TEMPLATE_ID` 是模板 ID，指向控制台里某个审核通过的模板。
- `Send` 的 `message` 参数填进模板的 `{1}`。
- 如果模板里只有一个变量 `{1}`（验证码场景基本都是这种），那 `message` 就是验证码本身。
- 如果模板里有多个变量 `{1}` `{2}`，当前 `Send(phone, message)` 只处理 `{1}`，`{2}` 之后的变量没有入口，会发不出去或被腾讯云拒绝。这种情况得改代码或换模板，别硬发。

举个例子：

- 控制台模板：`您的验证码是{1}，5分钟内有效。`，模板 ID 是 `7654321`。
- 环境变量：`SENTINEL_SMS_TENCENT_TEMPLATE_ID=7654321`。
- 调用：`sender.Send("13800138000", "654321")`。
- 用户收到：`您的验证码是654321，5分钟内有效。`。

所以填模板的时候，尽量用单变量模板，和 `Send(phone, message)` 对得上。

## 4. 签名原理：TC3-HMAC-SHA256 三步

腾讯云 API 用 TC3-HMAC-SHA256 签名。sentinel 里已经实现好了，你不用自己写。这里只讲原理，方便你排查问题。

### 4.1 三步

**第一步：拼规范请求串（CanonicalRequest）**

把 HTTP 方法、URI、查询串、请求头、请求体拼成一个固定格式的字符串，然后对整体做 SHA256 哈希。请求体是 JSON，哈希前要先算好。

**第二步：拼待签串（StringToSign）**

把算法名、请求时间戳、凭证范围、第一步算出的哈希拼起来，格式是：

```
TC3-HMAC-SHA256
<timestamp>
<date>/<service>/tc3_request
<第一步的哈希>
```

**第三步：算签名（Signature）**

用 SecretKey 派生出签名密钥，再用它对第二步的待签串做 HMAC-SHA256，得到最终签名。派生过程是：

```
SecretDate = HMAC-SHA256("TC3" + SecretKey, Date)
SecretService = HMAC-SHA256(SecretDate, Service)
SecretSigning = HMAC-SHA256(SecretService, "tc3_request")
Signature = HMAC-SHA256(SecretSigning, StringToSign)
```

最后把签名放进 `Authorization` 请求头发给腾讯云。

### 4.2 用固定测试向量验证

sentinel 里有固定的测试向量。当 `timestamp=1551113065` 时，期望签名是：

```
be8acb9d3ed0a2318cd7f83d178a155bdb2f5fac52a4c0c73ca0b15cb17a692b
```

你可以跑 sentinel 的测试来确认实现没坏：

```
go test ./... -run Tencent
```

如果签名测试通过，说明签名逻辑是对的。如果你自己接的时候报 `AuthFailure.SignatureFailure`，先跑这个测试排除代码问题，再去查 SecretId/SecretKey 有没有填错、系统时间有没有偏。

时间偏是常见坑：签名里带时间戳，服务器时间和腾讯云差太多会被拒。确保机器开了 NTP 同步。

## 5. 安全

### 5.1 SecretId 和 SecretKey 不许进 git

- `.env` 文件要写进 `.gitignore`，别提交。
- 仓库里只放 `.env.example`，里面留空位，不填真值：

```
SENTINEL_SMS_TENCENT_SECRET_ID=
SENTINEL_SMS_TENCENT_SECRET_KEY=
SENTINEL_SMS_TENCENT_REGION=ap-guangzhou
SENTINEL_SMS_TENCENT_SDK_APP_ID=
SENTINEL_SMS_TENCENT_SIGN=
SENTINEL_SMS_TENCENT_TEMPLATE_ID=
SENTINEL_SMS_TENCENT_ENDPOINT=sms.tencentcloudapi.com
```

- 生产环境的密钥走密钥管理或环境变量注入，别硬编码进代码，别写进配置文件提交。
- 万一密钥泄露，马上去腾讯云控制台禁用旧密钥、建新密钥，然后更新 `.env` 重启。

### 5.2 日志脱敏说明

sentinel 打日志时会把敏感信息遮掉：

- `SecretId` 和 `SecretKey` 不出现在日志里。
- `Authorization` 请求头不出现在日志里。
- 手机号做脱敏，中间几位打码。
- 短信内容里的验证码做脱敏。

所以你排查问题时看日志，看不到完整密钥和完整验证码是正常的，这是故意的。需要核对具体值时，用腾讯云控制台的发送记录，别指望日志。

### 5.3 其他注意

- 腾讯云短信有频率限制和日发送量限制，压测或批量发之前先看控制台配额。
- 模板和签名审核通过后才能发，审核没过发了会报错。
- 账户欠费会直接发送失败，看失败原因里有没有欠费提示。
