# 依赖管理策略

本文档说明本仓库依赖怎么升级、怎么扫、出了漏洞怎么办、高危依赖怎么盯。所有写死的版本号、工具名称、流程步骤都以本文档为准，改动要同步更新这里。

## 一、依赖更新节奏

### 1.1 自动扫描

仓库接入了 Dependabot，配置文件在 `.github/dependabot.yml`，覆盖三类生态：

- `maven`
- `github-actions`
- `docker`

扫描节奏：每周一（时区 Asia/Shanghai）跑一次。同一时间最多开 5 个 PR，PR 带 `dependencies` 标签，commit message 前缀 `chore(deps)`。

### 1.2 合并前必须做的事

任何一个 Dependabot PR，合入前必须本地跑：

```
mvn -o test
```

全绿才能合。红的话先查是不是依赖本身带来的行为变化，不要为了合 PR 去改测试断言凑绿。

### 1.3 版本从哪来

分两类：

- **BOM 管的**：除下面三个之外的所有直接依赖，版本都由 `spring-boot-starter-parent` 3.3.5 的 BOM 统一决定。升级就跟 Spring Boot 走，Spring Boot 升大版本时再一起评估。
- **显式写死的**：`springdoc-openapi-starter-webmvc-ui`、`resilience4j-spring-boot3`、`logstash-logback-encoder`。这三个升级前必须先查官方兼容矩阵（见附录 B 关于 springdoc 的说明），确认和当前 Spring Boot / Spring 版本对得上再动。

## 二、扫描与抽查

### 2.1 自动 + 人工两条腿

- 自动：Dependabot 每周一开 PR，见 1.1。
- 人工：每月一次，用下面这条命令核对直接依赖的实际版本，和本文档附录 A 对一遍：

```
mvn dependency:list
```

对不上的，要么改代码要么改附录 A，不许放着不管。

### 2.2 CI 现状

本仓库 CI 暂时放在各个项目自己的 `.github` 目录下，没放仓库根。原因是当前 gh token 缺 workflow 权限，推不到仓库根的 workflow 目录。`dependabot.yml` 同理，也先放项目级。

等权限补齐后，CI 和 `dependabot.yml` 一起迁到仓库根。在迁之前，别假设仓库根有 CI 配置。

## 三、紧急漏洞响应流程

发现漏洞或收到漏洞通报后，按下面走：

1. **评估，两步**：
   - 第一步看影响范围：这个依赖在本项目里用没用、用在哪个模块、暴露面多大。
   - 第二步看有没有公开利用：有没有公开的 PoC / 在野利用。有公开利用的优先级直接拉满。
2. **处置**：能升版本就升版本；升不了（比如被兼容矩阵卡住）就打补丁，或者在调用层做隔离。
3. **本地全量测试**：处置完本地跑全量测试，全绿再往下走。
4. **发版 + 记录**：发一个版本，并在 CHANGELOG 里记一笔：漏洞编号、影响依赖、处置方式、版本号。

**时间要求：高危漏洞 24 小时内出修复分支。** 不是 24 小时发版，是 24 小时内得有分支开始动。

## 四、高危依赖清单维护

### 4.1 哪些算高危

按攻击面分类，落在下面三类里的算高危：

- **网络暴露面**：tomcat、spring-web、httpclient5。这些直接对外收请求或发请求，被打了就是入口。
- **反序列化面**：jackson。反序列化出问题通常是直接能执行代码。
- **执行面**：ffmpeg 调用链。走到系统命令执行，出错就是命令注入。

### 4.2 怎么维护

高危清单就放在本文档附录里（见附录 A 的标注）。每季度复核一次，有增有减就改本文档，改完同步给团队。

## 五、附录 A：当前直接依赖清单

下表是 2026-10-16 用 `mvn -o dependency:list` 实际跑出的直接依赖，版本来源一列标 BOM 或显式。

| 构件 | 版本 | scope | 版本来源 |
| --- | --- | --- | --- |
| org.apache.httpcomponents.client5:httpclient5 | 5.3.1 | compile | BOM |
| org.springframework.boot:spring-boot-starter-web | 3.3.5 | compile | BOM |
| org.springframework.boot:spring-boot-starter-data-jpa | 3.3.5 | compile | BOM |
| org.springframework.boot:spring-boot-starter-validation | 3.3.5 | compile | BOM |
| org.flywaydb:flyway-core | 10.10.0 | compile | BOM |
| com.h2database:h2 | 2.2.224 | runtime | BOM |
| net.logstash.logback:logstash-logback-encoder | 8.0 | compile | 显式 |
| io.github.resilience4j:resilience4j-spring-boot3 | 2.4.0 | compile | 显式 |
| org.springframework.boot:spring-boot-starter-actuator | 3.3.5 | compile | BOM |
| io.micrometer:micrometer-registry-prometheus | 1.13.6 | compile | BOM |
| org.springframework.boot:spring-boot-starter-aop | 3.3.5 | compile | BOM |
| org.springdoc:springdoc-openapi-starter-webmvc-ui | 2.6.0 | compile | 显式 |
| org.springframework.boot:spring-boot-starter-test | 3.3.5 | test | BOM |

## 六、附录 B：springdoc 版本选择说明

`springdoc-openapi-starter-webmvc-ui` 钉死在 2.6.0，这是人工决策，不是随手写的。

原因：当前 Spring Boot 是 3.3.5，对应 Spring 6.1.x。springdoc 2.6.x 和 Spring 6.1.x 对得上。springdoc 2.7+ 要求 Spring 6.2 起，在当前 Spring Boot 版本下起不来。

所以：

- 2.6.0 写死，不跟着 BOM 走（本来也不在 BOM 里）。
- **不允许 Dependabot 给它升大版本。** 要动这个版本，先确认 Spring Boot 升到对应版本、Spring 到 6.2+，再人工改，改完同步更新本节和附录 A。
