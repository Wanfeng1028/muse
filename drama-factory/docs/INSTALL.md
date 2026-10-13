# drama-factory 安装与首次配置

drama-factory 是一个 Java 21 + Spring Boot 应用，产物为可执行 jar，使用 H2 文件数据库。
前端由 Spring Boot 直接输出静态资源，**无需 nginx**。

运行时依赖 **ffmpeg + ffprobe**（剪辑成片必需）。

提供两种安装方式：Docker 一键安装，或本机跑 jar。

---

## 一、Docker 一键安装（推荐）

### 前置条件
- Docker 20+（含 `docker compose` 子命令）
- 能访问外网（首次构建需拉取 Maven 依赖与 apt 包）

### 步骤
1. 进入项目目录：
   ```bash
   cd drama-factory
   ```
2. 构建并后台启动：
   ```bash
   docker compose up -d --build
   ```
3. 浏览器打开：
   ```
   http://localhost:8081
   ```
4. 进入「设置」页填写各平台 Key（见下方「首次配置」）。

### 常用运维命令
```bash
# 查看实时日志
docker compose logs -f

# 停止
docker compose down

# 更新（拉代码后重新构建并重启）
docker compose up -d --build
```

### 数据持久化
`docker-compose.yml` 将本机 `./data` 映射到容器内 `/app/data`，包含：
- `data/drama-factory`：H2 数据库文件
- `data/media`：媒体文件
- `data/logs`：日志
- `data/settings.json`：设置

`./data` 已加入 `.gitignore`。

---

## 二、本机运行 jar

### 前置条件
- **Java 21**
- **ffmpeg + ffprobe**，验证：
  ```bash
  ffmpeg --version
  ffprobe --version
  ```
- Maven（用于构建）

### 步骤
1. 构建（跳过测试以加速）：
   ```bash
   mvn package -DskipTests
   ```
   产物为 `target/drama-factory-*.jar`（例如 `target/drama-factory-1.0.0.jar`）。
2. 运行：
   ```bash
   java -jar target/drama-factory-1.0.0.jar
   ```
3. 浏览器打开 `http://localhost:8081`。

### 数据目录说明
默认在**当前工作目录**下创建 `./data`：
- `./data/drama-factory`：H2 文件数据库
- `./data/media`：媒体文件
- `./data/logs`：日志
- `./data/settings.json`：设置

### 修改端口
默认端口 **8081**，用环境变量 `PORT` 覆盖：
```bash
PORT=9090 java -jar target/drama-factory-1.0.0.jar
```

---

## 三、首次配置

### 需要填写的 Key
在「设置」页填写各通道所需的 Key。Key 请**去对应平台控制台申请**（登录各平台后在控制台/API 管理页面获取）。

### 通道选择建议
- **mock**：先跑通完整链路，不产生真实费用。
- **qwen / agnes**：确认链路无误、准备好后再切换，此时会产生真实费用。

建议顺序：**先用 mock 跑通 → 再切真实通道**。

---

## 四、排错

### 端口被占用
现象：启动报错或访问不到。
处理：用 `PORT` 换端口启动：
```bash
PORT=9090 java -jar target/drama-factory-1.0.0.jar
```
Docker 方式则修改 `docker-compose.yml` 的端口映射（如 `"9090:8081"`）。

### ffmpeg 缺失
现象：剪辑/成片相关步骤失败，日志中出现找不到 `ffmpeg` / `ffprobe`。
处理：
- 本机：安装 ffmpeg 后 `ffmpeg --version` 验证。
- Docker：镜像已内置 ffmpeg，请确认用的是本仓库的 Dockerfile 构建。

### data 目录权限
现象：启动或写入失败，日志提示无法创建/写入 `data` 目录。
处理：确认当前用户对工作目录下的 `data` 有读写权限，必要时调整目录属主或权限。

### 健康检查
`GET /api/health` 返回 200 表示服务已就绪：
```bash
curl http://localhost:8081/api/health
```

---

## 五、配置优先级

配置来源优先级（高 → 低）：
1. **环境变量**（如 `VIDEO_PROVIDER`、`PORT`、`DRAMA_STORAGE`）
2. `data/settings.json`

即环境变量会覆盖 settings.json 中的同名配置。
