# mini-os 告警运维手册

本文档描述 mini-os 的 Prometheus 告警规则、阈值调参、Alertmanager 接入方式和排障流程。
告警规则文件位于 `prometheus/rules/mini-os-example.yml`，指标由 mini-os 的 `GET /metrics` 暴露。

mini-os 暴露的指标：

| 指标 | 类型 | 标签 |
| --- | --- | --- |
| `http_requests_total` | counter | `method`、`route`、`status` |
| `http_request_duration_seconds` | histogram | `method`、`route` |
| `auth_ops_total` | counter | `op` |
| `ws_connections` | gauge | 无 |
| `vfs_files_total` | gauge | 无 |
| `vfs_bytes_total` | gauge | 无 |
| `shares_total` | gauge | `type` |

---

## 1. 告警规则一览表

规则文件：`prometheus/rules/mini-os-example.yml`
告警组：`mini-os-alerts`，`interval: 30s`，组标签 `team: mini-os`。

| 告警名 | 触发条件（对应 expr） | for | severity | 含义与可能原因 |
| --- | --- | --- | --- | --- |
| `MiniOSHigh5xxErrorRate` | `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05`（5xx 比例 > 0.05，即 5%） | 5m | warning | 服务端 5xx 错误率过高。常见原因：上游依赖故障、数据库/存储异常、代码缺陷、配置错误、资源耗尽导致请求处理失败。 |
| `MiniOSHighP99Latency` | `histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m]))) > 1`（P99 请求延迟 > 1 秒） | 5m | warning | P99 延迟过高。常见原因：慢查询、下游依赖抖动、锁竞争、GC 停顿、线程池/连接池打满、流量突增。 |
| `MiniOSInstanceDown` | `up{job="mini-os"} == 0`（实例抓取失败） | 5m | critical | 实例不可达。常见原因：进程崩溃、端口未监听、网络不通、Prometheus 抓取路径被防火墙拦截、实例被重启或下线。 |
| `MiniOSShareAccessSurge` | `sum(rate(http_requests_total{route=~"/api/s/:token\|/api/s/:token/download\|/api/share/list"}[5m])) > 10`（分享读三路由合计 QPS > 10） | 3m | warning | 分享读接口访问突增。常见原因：爬虫抓取、分享链接被批量转发、恶意刷量。mini-os 已有分享读限流兜底，需确认限流是否生效并排查来源。 |
| `MiniOSLoginRateLimitedSurge` | `increase(auth_ops_total{op="login_ratelimited"}[5m]) > 50`（5 分钟内 login_ratelimited 增量 > 50） | 5m | warning | 登录被限流次数突增。常见原因：暴力破解、撞库攻击、客户端重试风暴、密码错误导致的用户侧反复重试。 |
| `MiniOSHighWSConnections` | `ws_connections > 500`（当前 WebSocket 连接数 > 500） | 10m | warning | WebSocket 连接数过高。常见原因：客户端异常重连、连接未正确释放、长连接泄漏、突发在线人数增长。 |
| `MiniOSShareNotFoundSurge` | `sum(rate(http_requests_total{route=~"/api/s/:token",status="404"}[5m])) / sum(rate(http_requests_total{route=~"/api/s/:token"}[5m])) > 0.3`（`/api/s/:token` 的 404 占比 > 0.3，即 30%） | 5m | warning | 分享 token 枚举探测。常见原因：攻击者批量遍历 token、失效分享链接被大量访问、客户端持有过期链接反复请求。 |
| `MiniOSShareForbiddenSurge` | `sum(rate(http_requests_total{route=~"/api/s/:token|/api/s/:token/download|/api/share/list",status="403"}[5m])) / sum(rate(http_requests_total{route=~"/api/s/:token|/api/s/:token/download|/api/share/list"}[5m])) > 0.2`（分享读三路由的 403 占比 > 0.2，即 20%） | 5m | warning | 有人在扫路径穿越。常见原因：攻击者构造带 `..` 或非法路径段的请求、扫描器批量试探、客户端拼错路径反复请求。 |
| `MiniOSMetricsScrapeFailed` | `absent(up{job="mini-os"})`（Prometheus 里没有 job=mini-os 的抓取目标） | 2m | critical | 监控自己瞎了。常见原因：job 名写错、抓取配置被改坏、target 下线后被从配置里删掉。和 `MiniOSInstanceDown` 不同，后者是目标还在但实例挂了。 |
--- OLD ---
- 该规则依赖 `/api/s/:token` 有稳定的请求量；若该路由请求量极低，建议先加最小请求量条件（如分母 > 某值）再判断占比，避免低基数误报。

## 3. 接入 Alertmanager
--- NEW ---
- 该规则依赖 `/api/s/:token` 有稳定的请求量；若该路由请求量极低，建议先加最小请求量条件（如分母 > 某值）再判断占比，避免低基数误报。

### 2.8 MiniOSShareForbiddenSurge

- 默认阈值：分享读三路由（`/api/s/:token`、`/api/s/:token/download`、`/api/share/list`）的 403 占比 > 0.2，`for: 5m`，severity 为 warning。
- 该规则用分母是三路由的总请求量，如果只想盯某一个路由，把 `route=~` 里的正则改窄即可。
- 403 占比高不一定是被攻击，先看是不是客户端一直拿错路径；如果确认是扫描，可先在网关层封 IP，再回来调阈值。
- 路由请求量很低时同样会低基数误报，建议给分母加个最小请求量条件（如 > 某值）再判断占比。

### 2.9 MiniOSMetricsScrapeFailed

- 默认阈值：`absent(up{job="mini-os"})`，`for: 2m`，severity 为 critical。
- 这条和 `MiniOSInstanceDown` 的区别：`MiniOSInstanceDown` 用 `up{job="mini-os"} == 0`，表示目标还在抓取列表里、只是抓不到；本规则用 `absent(...)`，表示 Prometheus 里压根没有这个 job 的目标了，连抓都不抓。
- 排查顺序：先打开 Prometheus 的 Targets 页面看有没有 `job="mini-os"`；没有就查 `prometheus.yml` 里的 job 名和 `scrape_configs` 是不是写错或被删；确认配置没问题，再去查 mini-os 实例本身是不是没起来。
- 如果只是临时下线实例、故意从配置里移除，可以把这条规则静音或加白名单，别让它一直报。
- 该规则是 critical，因为它意味着监控对 mini-os 完全失明，后面所有 mini-os 告警都不可信。

## 3. 接入 Alertmanager


> 说明：`keep_firing_for`、`service` 标签等字段在本示例规则文件中未使用，属于可选能力；如需启用请自行在规则或组标签中补充，并同步更新本文档。

## 2. 阈值调参建议

调参总原则：先用示例默认值跑一段时间，观察真实基线与告警噪声，再按“误报多则放宽、漏报多则收紧”的方向小步调整；每次只改一个规则的阈值或 `for`，并在变更后回看一周内的触发次数与处置记录。以下建议中的默认值均以 `prometheus/rules/mini-os-example.yml` 为准。

### 2.1 MiniOSHigh5xxErrorRate

- 默认阈值/for：5xx 比例 > 0.05（5%），for 5m，severity warning。
- 调参建议：
  - 小规模、流量较低时，5% 的比例容易因少量请求波动而触发，可将阈值放宽到 0.08~0.10，或把 `for` 延长到 10m，降低噪声。
  - 流量稍大、对可用性要求较高时，可收紧到 0.02~0.03，并把 `for` 保持 5m 或缩短到 3m，以便更早发现故障。
  - 若 5xx 集中在个别路由，建议先补充分路由的 recording rule，再决定是否对全局阈值做调整。

### 2.2 MiniOSHighP99Latency

- 默认阈值/for：P99 > 1 秒，for 5m，severity warning。
- 调参建议：
  - 小规模或冷启动阶段，P99 抖动较大，可将阈值放宽到 1.5~2 秒，`for` 延长到 10m。
  - 流量稍大、SLA 要求更严时，可收紧到 0.5~0.8 秒，`for` 保持 5m 或缩短到 3m。
  - 建议同时观察 P50/P95，避免只盯 P99 而忽略整体劣化；必要时按路由拆分直方图再设阈值。

### 2.3 MiniOSInstanceDown

- 默认阈值/for：`up{job="mini-os"} == 0`，for 5m，severity critical。
- 调参建议：
  - 该规则直接反映实例存活，阈值本身不建议改动；主要调 `for`。
  - 若实例重启频繁、5m 造成大量短时告警，可延长到 10m；若希望更快感知宕机，可缩短到 2~3m，但要接受重启带来的噪声。
  - 多实例部署时，建议结合 `sum(up{job="mini-os"})` 或按实例数比例设置“多数实例不可达”的补充规则，避免单实例抖动触发 critical。

### 2.4 MiniOSShareAccessSurge

- 默认阈值/for：分享读三路由合计 QPS > 10，for 3m，severity warning。
- 调参建议：
  - 小规模、日常分享访问很少时，10 QPS 可能偏高导致漏报，可下调到 5 左右，`for` 保持 3m。
  - 流量稍大、正常分享访问本身较高时，可上调到 20~30，避免正常推广活动误报。
  - 该规则与分享读限流是配套的：调整阈值前先确认限流阈值，二者不要相互矛盾；触发后优先确认限流是否生效并排查来源。

### 2.5 MiniOSLoginRateLimitedSurge

- 默认阈值/for：5 分钟内 `login_ratelimited` 增量 > 50，for 5m，severity warning。
- 调参建议：
  - 小规模、登录量低时，50 次/5m 可能偏高，可下调到 20~30，`for` 保持 5m，以便更早发现撞库。
  - 用户量稍大、正常限流基数较高时，可上调到 100~200，避免把正常用户误输密码计入攻击。
  - 建议同时观察登录失败率与来源 IP 分布；若确认是攻击，优先在网关/WAF 层处置，而不是单纯放宽告警阈值。

### 2.6 MiniOSHighWSConnections

- 默认阈值/for：`ws_connections > 500`，for 10m，severity warning。
- 调参建议：
  - 小规模部署、单实例容量有限时，500 可能已接近上限，可下调到 200~300，`for` 保持 10m。
  - 容量稍大或已做水平扩展时，可按“单实例上限 × 实例数 × 0.7”估算后再上调，例如 1000~2000。
  - 若连接数长期贴近阈值，应优先排查连接泄漏与重连风暴，而不是持续抬高阈值。

### 2.7 MiniOSShareNotFoundSurge

- 默认阈值/for：`/api/s/:token` 的 404 占比 > 0.3（30%），for 5m，severity warning。
- 调参建议：
  - 小规模、分享链接总量少时，30% 容易受少量请求影响，可放宽到 0.5，或把 `for` 延长到 10m。
  - 流量稍大、枚举探测风险较高时，可收紧到 0.15~0.20，`for` 保持 5m 或缩短到 3m。
  - 该规则依赖 `/api/s/:token` 有稳定的请求量；若该路由请求量极低，建议先加最小请求量条件（如分母 > 某值）再判断占比，避免低基数误报。

## 3. 接入 Alertmanager

### 3.1 Prometheus 配置

编辑 `prometheus.yml`：

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "prometheus/rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - "localhost:9093"

scrape_configs:
  - job_name: "mini-os"
    metrics_path: "/metrics"
    static_configs:
      - targets:
          - "localhost:3000"
```

要点：
- `global.evaluation_interval` 决定告警规则多久评估一次，15s 与抓取间隔一致即可。
- `rule_files` 用通配符加载 `prometheus/rules/*.yml`，新增规则文件不用改配置。
- `alerting.alertmanagers` 指向 Alertmanager 的地址和端口，默认 9093。
- `scrape_configs` 里 job 名必须是 `mini-os`，否则 `up{job="mini-os"}` 无数据，`MiniOSInstanceDown` 永远不触发。

### 3.2 Alertmanager 最小配置

创建 `alertmanager.yml`：

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: "default"
  group_by: ["alertname", "service"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity = "critical"
      receiver: "critical-webhook"
      continue: false
    - matchers:
        - severity = "warning"
      receiver: "warning-webhook"
      continue: false

receivers:
  - name: "default"
    webhook_configs:
      - url: "http://localhost:9095/webhook"
  - name: "critical-webhook"
    webhook_configs:
      - url: "http://localhost:9095/webhook"
  - name: "warning-webhook"
    webhook_configs:
      - url: "http://localhost:9095/webhook"
```

要点：
- `route.routes` 按 `severity` 分流，critical 和 warning 各走一个 webhook。info 没有单独路由，会落到 `default`。
- `group_by` 用 `alertname` 和 `service`，同一类告警聚合成一条通知。
- `repeat_interval: 4h` 避免重复轰炸，故障未恢复时每 4 小时提醒一次。
- 三个 receiver 的 URL 是占位，实际部署时替换成你的接收端地址。

### 3.3 重载配置

Prometheus：

```bash
# 方式一：发送 SIGHUP
kill -HUP $(pidof prometheus)

# 方式二：启用 lifecycle 后调用 reload API
# 启动时加 --web.enable-lifecycle
curl -X POST http://localhost:9090/-/reload
```

Alertmanager：

```bash
# 方式一：发送 SIGHUP
kill -HUP $(pidof alertmanager)

# 方式二：调用 reload API
curl -X POST http://localhost:9093/-/reload
```

校验配置：

```bash
promtool check config prometheus.yml
promtool check rules prometheus/rules/mini-os-example.yml
amtool check-config alertmanager.yml
```

---

## 4. webhook 接收端最小示例

下面脚本只用 Python 标准库，直接保存为 `webhook_receiver.py` 后 `python3 webhook_receiver.py` 运行，监听 9095 端口，收到 Alertmanager 推送时打印每条告警的 `summary` 和 `description`。

```python
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return
        for alert in payload.get("alerts", []):
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            print("alertname=%s status=%s severity=%s" % (
                labels.get("alertname", "?"),
                alert.get("status", "?"),
                labels.get("severity", "?"),
            ))
            print("  summary: %s" % annotations.get("summary", ""))
            print("  description: %s" % annotations.get("description", ""))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 9095), Handler).serve_forever()
```

运行：

```bash
python3 webhook_receiver.py
```

测试：手动触发一条告警后，终端会打印告警名、状态、severity 以及 `summary` 和 `description`。若没打印，检查 Alertmanager 的 `receivers[].webhook_configs[].url` 是否指向 `http://localhost:9095/webhook`。

---

## 5. 排障 FAQ

### 5.1 告警不触发

按以下顺序排查：

1. **rule_files 路径错**：Prometheus 的 `rule_files` 是相对启动目录解析的，不是相对配置文件。如果 Prometheus 从 `/etc/prometheus` 启动，`prometheus/rules/*.yml` 会解析成 `/etc/prometheus/prometheus/rules/*.yml`。启动日志里会有 `Loading rules from file ...` 或 `error loading rules`。用绝对路径最稳：`rule_files: ["/etc/prometheus/rules/*.yml"]`。
2. **expr 标签写错导致无数据**：例如 `up{job="mini-os"}` 写成 `up{job="minios"}`，或 `http_requests_total{status=~"5.."}` 里 status 标签实际不存在。在 Prometheus 查询界面直接粘贴 expr 的指标选择器部分，看是否返回序列。返回空说明标签不匹配。用 `curl -s http://localhost:3000/metrics | grep http_requests_total` 确认实际标签名和值。
3. **for 太长**：`for: 10m` 要求条件连续满足 10 分钟。如果故障只持续几分钟，告警不会触发。临时把 `for` 改成 `1m` 或 `0m` 观察，确认 expr 本身能命中后再调回。注意 `0m` 会让抖动直接触发告警。

### 5.2 校验规则文件

有 promtool：

```bash
promtool check rules prometheus/rules/mini-os-example.yml
```

输出 `SUCCESS` 表示语法正确，会列出加载的规则数量。输出 `FAILED` 会指出行号和错误原因，常见错误是 YAML 缩进、`expr` 里的 PromQL 语法错误、`labels` 里用了非法字符。

没有 promtool：用本仓库的 `scripts/check-alert-rules.py`：

```bash
python3 scripts/check-alert-rules.py prometheus/rules/mini-os-example.yml
```

该脚本会检查 YAML 结构、必需字段（`alert`、`expr`、`labels.severity`、`annotations.summary`）、severity 取值是否为 `critical`/`warning`/`info`，并打印每条规则的校验结果。

### 5.3 告警触发了但收不到通知

1. 在 Prometheus 界面 `Alerts` 页面确认告警状态是 `Firing` 而不是 `Pending`。`Pending` 说明还在 `for` 计时中。
2. 在 Alertmanager 界面 `Alerts` 页面确认告警已到达。没到达说明 Prometheus 的 `alerting.alertmanagers` 地址写错，或 Alertmanager 没启动。
3. 检查 Alertmanager 日志里的 `Notify` 记录，确认路由匹配到了 receiver。没匹配说明 `route.routes[].matchers` 的 severity 值与告警实际 severity 不一致。
4. 检查接收端是否可达。用 `curl -X POST -d '{}' http://localhost:9095/webhook` 测试。
5. 检查 `group_wait`。默认 30s，告警到达后最多等 30s 才发第一条通知。

### 5.4 告警抖动（firing 和 resolved 反复切换）

- 加长 `for`，例如从 `5m` 改到 `15m`。
- 给告警加 `keep_firing_for: 5m`，在恢复后保持 firing 一段时间。
- 检查 expr 是否用了瞬时值而不是 `rate` 或 `avg_over_time`。瞬时值抖动大，建议用窗口函数平滑。
=== END ===
