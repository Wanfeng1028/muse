# drama-factory 运维手册

本文写给真上手操作的人。命令直接复制能跑，别脑补。

---

## 1. 部署方式

### 1.1 jar 直跑

前置条件：

- JDK 21 或以上（`java -version` 确认）。
- ffmpeg 与 ffprobe 已装好，且在 PATH 里能找到；不在 PATH 就用 `FFMPEG_PATH` / `FFPROBE_PATH` 指定绝对路径。
- Maven（构建阶段用；运行阶段不需要）。

构建（离线模式，需要你自己准备的 settings.xml）：

```bash
mvn -s /path/to/settings.xml -o package -DskipTests
```

产物：`target/drama-factory-1.0.0.jar`。

启动：

```bash
java -jar target/drama-factory-1.0.0.jar
```

常用环境变量在启动时一起给：

```bash
PORT=8081 \
DB_URL='jdbc:h2:file:./data/drama-factory' \
AUTH_JWT_SECRET='换成你们自己的密钥' \
java -jar target/drama-factory-1.0.0.jar
```

启动后浏览器打开 `http://localhost:8081/api/health`，能返回 JSON 就说明起来了。

### 1.2 docker compose

仓库根目录有 `compose.yml`，一键起：

```bash
docker compose up -d --build
```

要点：

- 数据卷映射到宿主机 `./data`（H2 文件库和媒体文件都在里面，删容器不丢数据，删目录就丢）。
- 日志轮转：单文件 10m，保留 3 个。
- 资源限制：2 核 CPU / 1G 内存。
- 端口映射走 `${PORT:-8081}:8081`，宿主机端口想换直接改环境变量。

停掉：

```bash
docker compose down
```

看日志：

```bash
docker compose logs -f drama-factory
```

---

## 2. 配置

主要靠环境变量。默认值写在 `application.yml` 里，环境变量非空时覆盖默认值。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8081` | HTTP 监听端口。 |
| `DB_URL` | `jdbc:h2:file:./data/drama-factory` | H2 文件库地址。换机器/换目录时改这里。 |
| `AUTH_JWT_SECRET` | 空 | JWT 验签密钥，与 auth-service 共用。**为空 = 开放模式**，`/api/**` 不鉴权。生产必须配。 |
| `DRAMA_SCRIPT_LLM_ENABLED` | `true` | 是否启用 LLM 剧本生成。 |
| `DRAMA_SCRIPT_LLM_MODEL` | `Deepseek-v4-flash` | 剧本模型名。 |
| `DRAMA_SCRIPT_LLM_MAX_TOKENS` | `3000` | 单次生成最大 token 数。 |
| `DRAMA_SCRIPT_LLM_TIMEOUT_SECONDS` | `120` | 单次调用超时秒数。 |
| `DRAMA_SCRIPT_LLM_MAX_RETRIES` | `2` | HTTP 调用失败重试次数。 |
| `DRAMA_SCRIPT_LLM_CLI_PATH` | 空 | 受限环境下走 CLI 回退的 `chat.py` 路径；为空则自动探测，探测不到就没有回退。 |
| `VIDEO_PROVIDER` | `mock` | 视频生成 provider。`agnes` 走真实外部服务，`mock` 本地造。 |
| `VIDEO_POLL_MS` | `10000` | 视频任务状态轮询间隔（毫秒）。 |
| `VIDEO_MAX_ATTEMPTS` | `8` | 单个视频任务最大轮询次数，超了判失败。 |
| `DRAMA_STORAGE` | `./data/media` | 媒体文件落盘目录。 |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 可执行文件路径。 |
| `FFPROBE_PATH` | `ffprobe` | ffprobe 可执行文件路径。 |

必填项说明：**没有严格必填项**——所有变量都有默认值，不配也能起。但生产环境必须显式配 `AUTH_JWT_SECRET`，否则等于裸奔。`VIDEO_PROVIDER=agnes` 时需要保证外部 provider 可达，否则视频任务会持续失败。

---

## 3. 备份与恢复

### 3.1 备份

脚本：`scripts/backup.sh`。

用法：

```bash
./scripts/backup.sh
```

行为：

- 用 H2 的 `BACKUP TO` 做在线备份（服务运行中也能跑，不会锁死写）。
- 把 `media/`、`settings/` 目录一起归档。
- 生成 manifest 记录各文件的 sha256，供恢复时校验。
- 产物落在 `backups/` 目录，文件名带时间戳。
- 保留数量由环境变量 `BACKUP_KEEP` 控制，默认 7 个，超出的最旧文件自动删。

建议 cron 每天凌晨跑一次：

```cron
0 3 * * * cd /opt/drama-factory && BACKUP_KEEP=7 ./scripts/backup.sh >> ./backups/backup.log 2>&1
```

### 3.2 恢复

脚本：`scripts/restore.sh`。

流程（脚本内部按顺序执行）：

1. 检查服务是否在跑，在跑会提示先停掉（避免 H2 文件被占用）。
2. 校验备份包 manifest 里的 sha256，不一致直接退出。
3. 把当前数据做一次快照（万一恢复错了还能回退）。
4. 用 H2 的 `Restore` 把数据库文件恢复回来。
5. 恢复 `media/`、`settings/`。
6. 跑一次冒烟（起服务后打 `/api/health`）。

用法：

```bash
./scripts/restore.sh backups/drama-factory-YYYYMMDD-HHMMSS
```

参数是备份目录路径。恢复完成后按提示重启服务。

---

## 4. 升级

标准动作，照做：

1. **先备份**：`./scripts/backup.sh`。这一步没做就别往下走。
2. **停服务**：`docker compose down` 或 `kill` 掉 java 进程。
3. **换 jar**：把新的 `drama-factory-1.0.0.jar` 放到启动路径。用 docker 的就 `docker compose build && docker compose up -d`。
4. **启动**：Flyway 会在启动时自动跑未执行的迁移脚本（`src/main/resources/db/migration/` 下按版本号顺序）。
5. **验证**：

   ```bash
   curl -s http://localhost:8081/api/health
   ```

   返回 200 且 JSON 里状态正常就 OK。

6. **回滚指引**：新版起不来或者起来后行为异常，回到第 1 步备份的目录，执行 `./scripts/restore.sh backups/<那个目录>`，然后把旧 jar 换回去重启。数据是 Flyway 迁移过的，如果新版加了新表新列，回滚到旧版之后这些结构旧版不认识，但 Hibernate `ddl-auto: validate` 只校验不改，多出来的列/表不会导致启动失败——不过再往上升之前建议先跑一遍备份。

---

## 5. 日志

- 日志配置在 `logback-spring.xml`。
- 默认输出到 `./logs/` 目录（按天切）。
- 想切 JSON 结构化输出（含 `request_id`，方便按 ID 检索），加环境变量：

  ```bash
  SPRING_PROFILES_ACTIVE=json java -jar target/drama-factory-1.0.0.jar
  ```

- Docker Compose 场景下日志轮转由 compose 层控制：单文件 10m，保留 3 个。`docker compose logs -f` 实时看。
- 日志级别：`com.dramafactory` 默认 INFO，`org.hibernate.SQL` 压到 WARN，`org.flywaydb` INFO。要临时调 SQL 日志就把 `org.hibernate.SQL` 提到 DEBUG。

---

## 6. 监控告警

- Prometheus 抓取端点：`GET /actuator/prometheus`（无鉴权，`JwtAuthFilter` 只拦 `/api/**`）。
- 抓取配置示例：`prometheus/prometheus.yml`（job 名 `drama-factory`，15s 间隔，目标 `localhost:8081/actuator/prometheus`）。
- 告警规则：`prometheus/rules/drama-factory.yml`，共 4 条：
  - `DramaFactoryHighErrorRate`（critical）——错误率过高。
  - `DramaFactoryVideoQueueBacklog`（warning）——视频任务队列积压。
  - `DramaFactoryApprovalStuck`（warning）——审批卡住。
  - `DramaFactoryRunFailures`（warning）——Run 失败数超标。
- 告警对接：Prometheus 里配 `alerting.alertmanagers` 指向你们的 Alertmanager，规则文件路径写进 `rule_files`。

业务指标说明（v2.4 起）：

- `dramafactory_video_tasks_queued`：排队中的视频任务数。
- `dramafactory_runs_by_status{status}`：各状态 Run 数量（8 个状态小写标签）。
- `dramafactory_runs_waiting_approval`：等待审批的 Run 数。
- `dramafactory_script_llm_calls_total{model,result}`：剧本 LLM 调用次数。
- `dramafactory_script_llm_duration_seconds{model}`：剧本 LLM 调用耗时。
- `dramafactory_finalcut_builds_total{result}`：成片构建次数。
- `dramafactory_finalcut_build_duration_seconds`：成片构建耗时。

Gauge 类指标由 `@Scheduled(30s)` 刷内存快照，抓取时不打 DB。

---

## 7. API 文档

- Swagger UI：`http://<host>:<port>/swagger-ui.html`。
- OpenAPI JSON：`http://<host>:<port>/v3/api-docs`（YAML 把后缀换成 `.yaml`）。
- 用 `AUTH_JWT_SECRET` 部署时，Swagger UI 右上角点 **Authorize**，把 Bearer token（不带 `Bearer ` 前缀）填进去，之后 `/api/**` 的接口都能在页面上直接试。
- **重要**：这两个端点默认无鉴权（不在 `/api/**` 前缀下）。生产环境不要把服务直接暴露到公网，否则任何人都能看到完整接口清单和字段定义。要么走内网访问，要么在反向代理层给这两个路径加白名单/认证。

---

## 8. 故障排查

### 8.1 端口被占

**现象**：启动日志里报 `Port 8081 was already in use`，进程直接退出。

**排查**：

```bash
# Linux/macOS
lsof -i :8081
# 或
ss -ltnp | grep 8081
```

**解决**：kill 掉占用的进程，或者换端口 `PORT=8082 java -jar ...`。

### 8.2 H2 文件被锁

**现象**：启动报 `Database may be already in use` 或 `Locked by another process`。

**排查**：

```bash
ps aux | grep drama-factory
ls -la ./data/
```

看 `./data/drama-factory.mv.db.lock` 之类的锁文件在不在。

**解决**：确认没有另一个 java 进程在跑同一个数据目录。真有僵尸进程就 kill 掉。确认全部停了之后锁文件还在，手动删掉再起（**注意**：删锁文件前一定要确认没有进程在写，否则数据损坏）。

### 8.3 Flyway checksum 失败

**现象**：启动报 `Migration checksum mismatch for migration version x.y`。

**排查**：看日志里报的是哪个版本。一般是有人改了已经执行过的迁移脚本。

**解决**：

- 正确做法：把改过的脚本改回去，改动写进新的迁移文件（`V{n+1}__xxx.sql`）。
- 应急做法（**只在你确定这个改动是修 bug 不是改结构时用**）：在 `flyway_schema_history` 表里 `UPDATE` 对应版本的 `checksum` 列。改之前先备份。

### 8.4 ffmpeg 不在 PATH

**现象**：成片构建失败，日志里报 `Cannot run program "ffmpeg"` 或 `No such file or directory`。

**排查**：

```bash
which ffmpeg
which ffprobe
ffmpeg -version
```

**解决**：装上 ffmpeg（`apt install ffmpeg` / `brew install ffmpeg`），或者显式指定路径：

```bash
FFMPEG_PATH=/usr/local/bin/ffmpeg FFPROBE_PATH=/usr/local/bin/ffprobe java -jar ...
```

### 8.5 视频任务长期 PENDING

**现象**：`/api/runs` 里视频任务一直卡在 PENDING，`dramafactory_video_tasks_queued` 指标一直不降。

**排查**：

```bash
# 看 provider 是什么
echo $VIDEO_PROVIDER
# 看外部 provider 是否可达
curl -s -o /dev/null -w '%{http_code}\n' https://<provider-endpoint>/health
```

看日志里有没有 `agnes` 相关超时/熔断信息。

**解决**：

- provider 是 `mock`：说明调度线程卡了，重启服务试试。
- provider 是 `agnes` 且外部服务排队拥堵：切 `VIDEO_PROVIDER=mock` 先跑通流程，等外部恢复再切回来。
- 熔断打开了：等 `wait-duration-in-open-state`（60s）过去，半开放状态会放 2 个请求探路。

### 8.6 内存不足

**现象**：日志里出现 `OutOfMemoryError` 或容器被杀（exit code 137）。

**排查**：

```bash
# 容器
docker stats
# 裸机
free -h
jstat -gc <pid>
```

**解决**：

- 临时：调大 JVM 堆 `java -Xmx1g -jar ...`，或调大 compose 里的内存限制。
- 长期：看是哪个环节吃内存。视频/成片处理是主要占用方，大文件要避免一次性读进内存。H2 单机内存占用也会随数据量增长。

### 8.7 ffmpeg 瞬时失败（v2.29 flaky 根因歼灭）

**现象**

成片构建偶尔报 500，日志里能看到 `ffmpeg 瞬时失败，…ms 后第 x/3 次重试`。视频任务偶尔 attempts 次数涨上去，过一会儿又好了。

**先分清是哪一类**

看错误日志里的关键字：

- 含 `无法启动命令` → 这是永久失败，ffmpeg 二进制没装或路径不对。跳到 8.4 去装 ffmpeg。
- 含 `命令超时`，或退出码是 137 / 143 → 这是瞬时抖动。137 一般是进程被 SIGKILL（常见是 OOM），143 是 SIGTERM。

代码里 `FfmpegService.FfmpegException#isTransient()` 就是这么判的：超时 / 137 / 143 / OOM 算瞬时，`无法启动命令` 算永久。`FinalCutService` 对 concat、burn-subtitles、probe-duration 这三种操作的瞬时失败会做有界重试，默认 3 次，退避是 2000ms × 当前 attempt 数。想改的话用环境变量 `FFMPEG_RETRY_ATTEMPTS` 和 `FFMPEG_RETRY_BACKOFF_MS`。

**排查步骤**

1. 先确认二进制在不在、版本对不对：

   ```bash
   which ffmpeg
   ffmpeg -version
   ```

2. 看重试指标有没有突增。Prometheus 里查：

   ```bash
   curl -sG 'http://localhost:9090/api/v1/query' \
     --data-urlencode 'query=rate(dramafactory_ffmpeg_retries_total{kind="transient"}[5m])'
   ```

   返回里 `result` 数组非空、值明显大于 0，说明瞬时重试在涨。

3. 翻日志找慢命令 warn。ffmpeg 单次执行超过 30s 会打 warn，能看到是哪个操作慢。

4. 查是不是被 OOM kill 了：

   ```bash
   dmesg | grep -i "killed process"
   ```

5. 看磁盘满没满：

   ```bash
   df -h
   ```

**怎么处理**

- 抖动频繁：加内存、降并发，或者把 `FFMPEG_RETRY_ATTEMPTS` 调到 5 多给几次机会。
- 137 反复出现：去查容器的内存 limit，多半是压得太紧。
- 永久失败（`无法启动命令`）：按 8.4 装 ffmpeg，别在这浪费时间调重试。

### 8.8 轮询单飞跳过（v2.29）

**这是什么**

`VideoTaskService.processDueTasks` 加了单飞保护。定时线程和手动调用如果撞到一起，后到的那个直接跳过，只打一条 debug 日志，同时 `dramafactory_video_poll_skipped_total` 指标加一。这是正常的保护行为，不是 bug，别当故障查。

**什么时候要警惕**

如果 `dramafactory_video_poll_skipped_total` 一直在涨，同时任务积压不降，那可能是定时线程卡死了。用 jstack 看 poll 线程在干嘛：

```bash
jstack <pid> | grep -A 20 'video-poll'
```

（线程名按实际配置替换，重点是找到跑 `processDueTasks` 的那个线程，看它是不是卡在某个 ffmpeg 调用或锁上。）

**Prometheus 告警示例**

finalcut 构建失败率，只要有 error 就报：

```yaml
- alert: FinalCutBuildError
  expr: rate(dramafactory_finalcut_builds_total{result="error"}[5m]) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "finalcut 构建出现失败"
    description: "过去 5 分钟有 finalcut 构建以 error 结束，查日志和 dramafactory_ffmpeg_retries_total。"
```

ffmpeg 瞬时重试突增：

```yaml
- alert: FfmpegTransientRetrySpike
  expr: rate(dramafactory_ffmpeg_retries_total{kind="transient"}[5m]) > 0.1
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "ffmpeg 瞬时重试在涨"
    description: "瞬时重试速率超过 0.1/s 持续 10 分钟，按 8.7 排查内存、并发和磁盘。"
```

轮询跳过持续增长（配合积压判断，这里只给指标表达式，积压得看你们自己的队列指标）：

```yaml
- alert: VideoPollSkippedGrowing
  expr: rate(dramafactory_video_poll_skipped_total[5m]) > 0
  for: 15m
  labels:
    severity: info
  annotations:
    summary: "轮询单飞跳过持续发生"
    description: "结合任务积压一起看，如果积压不降，用 jstack 查 poll 线程是否卡死。"
---

## 9. 已知限制

- **单实例部署**：熔断、限流都是 Resilience4j 内存级实现，多实例各自为政。要真正集群化得换 Redis 版或网关层做。
- **H2 单机**：数据文件就在本机磁盘上，不支持多节点共享。想上集群得换 PostgreSQL / MySQL，Flyway 脚本要过一遍方言。
- **`/actuator/prometheus` 无鉴权**：不在 `/api/**` 前缀下，`JwtAuthFilter` 不管。生产别直接暴露公网。
- **`/v3/api-docs` 与 `/swagger-ui/**` 无鉴权**：同上，默认公开。要暴露给外部用必须先套反向代理认证。
- **agnes provider 排队拥堵**：外部服务排队严重时视频任务会长时间 PENDING，走 mock 降级（`VIDEO_PROVIDER=mock`）先把流程跑通。

---

*最后更新：v2.5（2026-10-14）*
