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
| `DRAMA_VIDEO_HTMLRENDER_ENGINE` | `chromium` | htmlrender 渲染引擎：`chromium`（无头截图+ffmpeg，默认）或 `hyperframes`（HyperFrames CLI；CLI 不可用时自动降级回 chromium）。 |
| `DRAMA_VIDEO_HYPERFRAMES_CLI` | `hyperframes` | HyperFrames CLI 可执行文件路径；独立 hyperframes provider 与 htmlrender 引擎共用。探活脚本 `scripts/hyperframes_probe.sh`。 |

必填项说明：**没有严格必填项**——所有变量都有默认值，不配也能起。但生产环境必须显式配 `AUTH_JWT_SECRET`，否则等于裸奔。`VIDEO_PROVIDER=agnes` 时需要保证外部 provider 可达，否则视频任务会持续失败。

### 2.1 HyperFrames 渲染引擎运维
- 安装：`npm i -g hyperframes`（需 Node.js 22+）；探活：`scripts/hyperframes_probe.sh`（输出 JSON，`engine` 字段为推荐值）。
- 无 GPU 机器：CLI 会自动走软件渲染，也可在配置中确认 `--no-browser-gpu` 行为（代码默认追加）。
- 选型指引见 `docs/HYPERFRAMES_CHANNELS.md`；联调实测见 `docs/HYPERFRAMES_RENDER_PROBE_2026-10-20.md`。

### 2.2 自有 SkillHub 运维
- 索引接口 `GET /api/skillhub/index` 无外部依赖（数据来自内置 skills-bundled），可直接用于健康检查。
- 远端官网 skillhub（`DRAMA_SKILLHUB_BASE_URL`）为空时禁用远端，只用内置；启用后安装走官网下载，包做 sha256 校验（约定见 `docs/skillhub-server-convention.md`）。
| `DRAMA_STORAGE` | `./data/media` | 媒体文件落盘目录。 |
| `FFMPEG_PATH` | `ffmpeg` | ffmpeg 可执行文件路径。 |
| `FFPROBE_PATH` | `ffprobe` | ffprobe 可执行文件路径。 |
| `AUTH_COOKIE_SECURE` | `false` | httpOnly Cookie 是否加 `Secure` 标记。本地 HTTP 开发保持 false；**生产 HTTPS 必须设为 true**，否则浏览器会拒收带 Secure 的 Cookie 导致登录态异常。 |

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

### 3.3 备份恢复实测步骤

本节给出一条从备份到恢复、再到失败回退的完整可复现路径。所有命令均以仓库根目录（`APP_HOME`）为当前目录，脚本内部会自行 `cd "$APP_HOME"`。脚本涉及的关键路径：

- 数据目录：`data/`
- 数据库文件：`data/drama-factory.mv.db`
- 媒体目录：`data/media/`
- 配置文件：`data/settings.json`
- 备份产物目录：`backups/`

日志前缀：`backup.sh` 输出 `[backup]`，`restore.sh` 输出 `[restore]`，均为 `[前缀] YYYY-MM-DD HH:MM:SS 消息` 格式。

#### 3.3.1 前提检查

`backup.sh` 在执行前会做两项前置检查（见脚本"0. 前置检查"）：

- `data/` 目录必须存在，否则 `fail "数据目录不存在: $DATA_DIR"`。
- `data/drama-factory.mv.db` 必须存在，否则 `fail "H2 数据库文件不存在: $DB_FILE (应用是否已初始化?)"`。

实测前先确认：

```bash
cd "$(git rev-parse --show-toplevel)"
test -d data && echo "data 目录存在"
test -f data/drama-factory.mv.db && echo "DB 文件存在"
ls -l data/drama-factory.mv.db
```

若第二条不通过，说明应用尚未初始化，需先启动应用跑完 Flyway 迁移再备份。

#### 3.3.2 完整实测流程

**第 1 步：手动触发一次备份**

```bash
./scripts/backup.sh
```

预期输出（时间戳与 jar 路径随环境变化）：

```text
[backup] 2025-01-01 03:00:01 开始备份, 应用目录: /opt/drama-factory
[backup] 2025-01-01 03:00:01 使用 H2 jar: /root/.m2/repository/com/h2database/h2/2.2.224/h2-2.2.224.jar
[backup] 2025-01-01 03:00:01 [1/4] 通过 H2 BACKUP TO 在线导出数据库 ...
[backup] 2025-01-01 03:00:02      数据库导出完成: 1.2M
[backup] 2025-01-01 03:00:02 [2/4] 打包媒体目录与 settings.json ...
[backup] 2025-01-01 03:00:02      media 归档: 8.4M
[backup] 2025-01-01 03:00:02      settings.json 已复制
[backup] 2025-01-01 03:00:02 [3/4] 生成 manifest.txt ...
[backup] 2025-01-01 03:00:02      manifest 记录 3 个文件
[backup] 2025-01-01 03:00:02 [4/4] 打包备份 ...
[backup] 2025-01-01 03:00:03      备份完成: /opt/drama-factory/backups/drama-factory-20250101-030001.tar.gz (2.3M)
[backup] 2025-01-01 03:00:03 应用保留策略: 仅保留最近 7 个备份包
[backup] 2025-01-01 03:00:03      无需清理
[backup] 2025-01-01 03:00:03 备份成功, 退出
```

产物路径格式：`backups/drama-factory-YYYYMMDD-HHMMSS.tar.gz`。记录本次路径供后续步骤使用：

```bash
PKG="$(ls -1t backups/drama-factory-*.tar.gz | head -n1)"
echo "$PKG"
```

**第 2 步：校验备份产物 manifest 的 sha256**

备份包内的 `manifest.txt` 中，每个文件行格式为 `<sha256>  <相对路径>`。脚本自身在校验时是 `cd` 到解包根目录后对每行跑 `sha256sum` 并比对。手工复核用 `sha256sum -c`：

```bash
WORK="$(mktemp -d)"
tar -xzf "$PKG" -C "$WORK"
PKG_ROOT="$(find "$WORK" -maxdepth 1 -mindepth 1 -type d | head -n1)"

# manifest.txt 是脚本自定义格式（无 sha256sum 的 " *file" 标记），需先转换成 sha256sum -c 可读格式
( cd "$PKG_ROOT" && grep '^[0-9a-f]\{64\}' manifest.txt | awk '{print $1"  "$2}' > /tmp/manifest.sha256 )
( cd "$PKG_ROOT" && sha256sum -c /tmp/manifest.sha256 )
```

预期每行输出 `db.zip: OK`、`media.tar.gz: OK`、`settings.json: OK`（实际文件名与 manifest 内容一致）。任一行为 `FAILED` 即备份包损坏，弃用该包重做备份。

**第 3 步：模拟灾难（停服务 + 备份当前 data 目录）**

先停服务。`restore.sh` 的检查逻辑是：`curl -fsS --max-time 2 http://127.0.0.1:${PORT}/api/health` 成功，或 `pgrep -f 'drama-factory.*\.jar'` 命中，即判定"应用正在运行"。

```bash
# 若用 systemd
sudo systemctl stop drama-factory

# 若用 docker compose
docker compose down

# 确认端口已释放、进程已退出
curl -fsS --max-time 2 http://127.0.0.1:8081/api/health && echo "仍在运行" || echo "已停止"
pgrep -f 'drama-factory.*\.jar' || echo "无残留 java 进程"
```

对当前 `data/` 做一份目录级快照，作为第 5 步回退依据（脚本内部还会再生成一次 `backups/pre-restore-<ts>.tar.gz` 快照，这里额外保留一份用于对比）：

```bash
SNAP_TS="$(date '+%Y%m%d-%H%M%S')"
cp -a data "data.disaster-snapshot-$SNAP_TS"
echo "灾难前快照: data.disaster-snapshot-$SNAP_TS"
```

**第 4 步：执行恢复并冒烟**

```bash
./scripts/restore.sh "$PKG"
```

预期输出（节选，时间戳随环境变化）：

```text
[restore] 2025-01-01 03:10:00 检查应用是否在运行 ...
[restore] 2025-01-01 03:10:00 使用 H2 jar: /root/.m2/repository/com/h2database/h2/2.2.224/h2-2.2.224.jar
[restore] 2025-01-01 03:10:00 解包备份到临时目录: /opt/drama-factory/backups/.staging-restore.XXXXXX
[restore] 2025-01-01 03:10:00 备份包清单:
    # drama-factory backup manifest
    timestamp: 20250101-030001
    ...
[restore] 2025-01-01 03:10:00 校验备份包内文件 sha256 ...
[restore] 2025-01-01 03:10:00      校验通过
[restore] 2025-01-01 03:10:00 [0/4] 生成恢复前快照 ...
[restore] 2025-01-01 03:10:01      在线导出当前数据库 ...
[restore] 2025-01-01 03:10:02      恢复前快照: /opt/drama-factory/backups/pre-restore-20250101-031000.tar.gz
[restore] 2025-01-01 03:10:02 [1/4] 恢复 H2 数据库 ...
[restore] 2025-01-01 03:10:02      旧数据库文件已改名为: .../data/drama-factory.mv.db.pre-restore-20250101-031000.bak
[restore] 2025-01-01 03:10:03      数据库恢复完成: 1.2M
[restore] 2025-01-01 03:10:03 [2/4] 恢复 media 目录 ...
[restore] 2025-01-01 03:10:03 [3/4] 恢复 settings.json ...
[restore] 2025-01-01 03:10:03 [4/4] 一致性冒烟检查 ...
[restore] 2025-01-01 03:10:03      H2 文件: /opt/drama-factory/data/drama-factory.mv.db (1234567 字节)
[restore] 2025-01-01 03:10:03      media 目录: /opt/drama-factory/data/media

============================================================
恢复完成。请按以下步骤手动验证:
...
============================================================
[restore] 2025-01-01 03:10:03 恢复流程结束
```

脚本结束后起服务并打健康检查（`PORT` 默认 `8081`，与 `restore.sh` 中一致）：

```bash
# systemd
sudo systemctl start drama-factory

# 或 docker compose
docker compose up -d

# 等待启动完成
tail -f logs/*.log

# 冒烟
curl -fsS http://127.0.0.1:8081/api/health
```

`curl -fsS` 成功（退出码 0 且返回体为健康响应）即恢复通过。

**第 5 步：恢复失败时回退**

两种回退途径，任选其一。

途径 A：用第 3 步保留的目录级快照整体还原：

```bash
sudo systemctl stop drama-factory   # 或 docker compose down
rm -rf data
mv "data.disaster-snapshot-$SNAP_TS" data
sudo systemctl start drama-factory
curl -fsS http://127.0.0.1:8081/api/health
```

途径 B：用 `restore.sh` 内部生成的恢复前快照（`backups/pre-restore-<ts>.tar.gz`）再恢复一次：

```bash
ls -1t backups/pre-restore-*.tar.gz | head -n1
./scripts/restore.sh "backups/pre-restore-<上面列出的时间戳>.tar.gz"
```

若数据库单独损坏而 media/settings 完好，也可直接改回 `.bak` 文件（`restore.sh` 结束时提示的回滚方法）：

```bash
mv "data/drama-factory.mv.db.pre-restore-<ts>.bak" data/drama-factory.mv.db
```

#### 3.3.3 保留策略验证（`BACKUP_KEEP=2`）

连跑三次备份，断言 `backups/drama-factory-*.tar.gz` 只剩 2 个。

```bash
cd "$(git rev-parse --show-toplevel)"

# 清空既有备份包，避免干扰断言（保留日志等其它文件）
rm -f backups/drama-factory-*.tar.gz

BACKUP_KEEP=2 ./scripts/backup.sh
sleep 1
BACKUP_KEEP=2 ./scripts/backup.sh
sleep 1
BACKUP_KEEP=2 ./scripts/backup.sh

count="$(ls -1 backups/drama-factory-*.tar.gz | wc -l)"
echo "剩余备份包数量: $count"
[ "$count" -eq 2 ] || { echo "断言失败: 期望 2, 实际 $count"; exit 1; }

ls -1t backups/drama-factory-*.tar.gz
```

第三次备份的日志中应出现 `应用保留策略: 仅保留最近 2 个备份包` 与 `删除过期备份: .../drama-factory-<最旧时间戳>.tar.gz`，且 `ls -1t` 只列出最新两个包。

#### 3.3.4 常见失败对照表

| 现象 | 脚本中的 fail 信息（原文） | 处理方式 |
| --- | --- | --- |
| DB 文件被锁 | `[restore] ... [错误] 应用正在运行 (端口 $PORT 或 java 进程存活)。请先停服再恢复, 或加 --force (后果自负)`；若加 `--force` 后 H2 仍报错，会走到 `步骤 1/4 失败: H2 Restore 返回非零。旧文件保留在 $DB_FILE.pre-restore-$SNAP_TS.bak, 可手动回滚` | 先 `systemctl stop drama-factory` 或 `docker compose down`，确认 `curl -fsS http://127.0.0.1:8081/api/health` 失败、`pgrep -f 'drama-factory.*\.jar'` 无输出，再重跑 `restore.sh`。不要依赖 `--force` 绕过运行检查。 |
| `H2_JAR` 找不到 | `找不到 H2 jar, 请设置 H2_JAR 环境变量指向 h2-*.jar`（backup 与 restore 均会触发）；若 `H2_JAR` 已设置但文件不存在，则报 `H2_JAR 指定的文件不存在: $H2_JAR` | 显式指定：`H2_JAR=/abs/path/h2-2.2.224.jar ./scripts/backup.sh`；或把 jar 放到脚本搜索路径 `$HOME/.m2/repository` 或 `$M2_REPO`（默认 `$HOME/workspace/muse-build/.m2repo`）下。 |
| manifest 校验失败 | `备份包完整性校验失败` | 备份包已损坏或被截断。弃用该包，回到第 1 步重新备份；确认备份过程中磁盘未满、`tar` 未被中断。若只是单个文件缺失，`sha256 不匹配: <rel>` 会先打到 stderr，可据文件名定位。 |
| 备份包结构异常 | `备份包结构异常: 未找到根目录` | 传入的 tar 包不是 `backup.sh` 产出的格式（根目录应为 `drama-factory-YYYYMMDD-HHMMSS/`）。确认参数指向 `backups/drama-factory-*.tar.gz`，而不是 `pre-restore-*.tar.gz`。 |
| 备份包缺少必要文件 | `备份包中缺少 db.zip` 或 `备份包中缺少 manifest.txt` | 备份包被裁剪过。改用完整包重试。 |
| 数据目录或 DB 文件缺失（备份侧） | `数据目录不存在: $DATA_DIR` 或 `H2 数据库文件不存在: $DB_FILE (应用是否已初始化?)` | 先启动应用完成初始化，确认 `data/drama-factory.mv.db` 生成后再备份。 |

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
- 告警规则：`prometheus/rules/auth-service.yml`，共 3 条（job 名 `auth-service`，抓取 `localhost:8082/actuator/prometheus`，已接入 `prometheus.yml` 的 `rule_files` 与 `scrape_configs`）：
  - `AuthServiceHighErrorRate`（critical）——5xx 错误率超 5%。
  - `AuthServiceDown`（critical）——实例不可达。
  - `AuthServiceLoginFailureSpike`（warning）——5 分钟登录失败超 50 次（疑似撞库）。
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

代码里 `FfmpegService.FfmpegException#isTransient()` 就是这么判的：超时 / 137 / 143 / OOM 算瞬时，`无法启动命令` 算永久（v2.31 起 EAGAIN/ENOMEM/EMFILE 类资源耗尽信号算瞬时）。`FinalCutService` 对 concat、burn-subtitles、probe-duration 这三种操作的瞬时失败会做有界重试，默认 3 次，退避是 2000ms × 当前 attempt 数；另有总预算 `FFMPEG_RETRY_TOTAL_BUDGET_MS`（默认 20000ms），单次构建内所有步骤的退避睡眠合计不超过该值。想改的话用环境变量 `FFMPEG_RETRY_ATTEMPTS`、`FFMPEG_RETRY_BACKOFF_MS` 和 `FFMPEG_RETRY_TOTAL_BUDGET_MS`。

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
- **构建必须用 UTF-8 locale**：`src/main/resources` 下有中文文件名（如 `prompt-library/pdoom-video/README-存档说明.md`）。在 POSIX locale（`LC_ALL` 未设置）下跑 Maven，`maven-resources-plugin` 会静默跳过这些文件，导致 classpath 扫描漏文件、测试莫名失败（2026-10-20 实测：PromptLibraryServiceTest 期望 26 实得 25）。构建/测试前务必 `export LC_ALL=C.UTF-8 LANG=C.UTF-8`；CI 已在 workflow 里固定。
- **`/v3/api-docs` 与 `/swagger-ui/**` 无鉴权**：同上，默认公开。要暴露给外部用必须先套反向代理认证。
- **agnes provider 排队拥堵**：外部服务排队严重时视频任务会长时间 PENDING，走 mock 降级（`VIDEO_PROVIDER=mock`）先把流程跑通。

---

## 成本账本（视频生成计费）

视频每次提交生成任务时，路由会按提供方估算费用并做预算预留，轮询到结果后结算。账本表是 cost_ledger_entry，状态机为 ESTIMATED → RESERVED → COMPLETED / FAILED / REFUNDED。

### 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `drama.billing.enabled` | `true` | 总开关，关掉后不做估算也不写账本 |
| `drama.billing.mode` | `WARN` | `WARN` 只告警继续执行；`CAP` 超预算直接跳过该通道并降级 |
| `drama.billing.budget-total-usd` | `100.0` | 总预算，单位美元 |
| `drama.billing.reserve-pct` | `0.1` | 预留比例，范围 0~0.9 |

非法值启动即报错退出，不会带着错配置跑起来。

### 单通道费率覆盖

用 `drama.billing.cost-per-sec.<通道名>` 覆盖某个通道的费率，单位美元/秒。通道名里非字母数字的字符换成 `-`。

默认费率表（2026-10 按公开定价估算，仅供预算参考，实际以提供方账单为准）：

| 通道 | 美元/秒 |
| --- | --- |
| agnes | 0.08 |
| minimax | 0.05 |
| novai | 0.03 |
| qwen | 0.02 |
| doubao | 0 |
| hyperframes | 0 |
| htmlrender | 0 |
| painted | 0 |
| mock | 0 |
| 本地通道 | 0 |

### 查询接口

| 接口 | 说明 |
| --- | --- |
| `GET /api/cost-ledger/summary` | 汇总 |
| `GET /api/cost-ledger/entries` | 明细，可按 status 过滤 |
| `GET /api/cost-ledger/daily?date=yyyy-MM-dd` | 按天按通道汇总，缺省今天 |

### 运维

1. 每天看一眼 daily 接口。spent 异常增高时，查 entries 定位是哪个通道。
2. 已知限制：实际费用按提交时估算结算（提供方不返回真实费用）。RESERVED 长期不结算的条目是"在途任务"，重启或轮询停滞时会有残留，可在 entries 里按 status=RESERVED 查。

---

*最后更新：v2.5（2026-10-14）*
