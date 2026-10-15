
# 幕间 Interlude 运维手册

本文写给要在这台机器上跑起来、验证、排查问题的人。内容都是实际做过的步骤，没有别的假设。

## 安装与运行

### 正常机器（有 GUI、Gradle 可用）

```
./gradlew run
```

启动 Compose 桌面应用。

跑测试：

```
./gradlew test
```

### 本机（沙箱）直编

本机 Gradle daemon 起不来（IPC 故障），所以不用 Gradle，改用 kotlinc 直编 + JUnit Platform Console 来验证。

主代码编译：

```
kotlinc src/main/kotlin/com/interlude/dsl/*.kt \
        src/main/kotlin/com/interlude/lint/*.kt \
        src/main/kotlin/com/interlude/i18n/*.kt \
        src/main/kotlin/com/interlude/log/*.kt \
        src/main/kotlin/com/interlude/LintCli.kt \
        src/main/kotlin/com/interlude/Smoke.kt \
        src/main/kotlin/com/interlude/ui/GraphLayout.kt \
        -d build/v11-main
```

注意：`src/main/kotlin/com/interlude/ui/App.kt` 是 Compose 代码，本机编不过（Compose 编译器插件后端崩溃），所以不在直编范围里，上面这行也没带它。GraphLayout.kt 是纯算法，可以编。

测试编译：

```
kotlinc $(find src/test/kotlin -name "*.kt") \
        -cp "build/v11-main:kotlin-test.jar:kotlin-test-junit5.jar:junit-jupiter-api.jar" \
        -d build/v11-test
```

`kotlin-test-junit5` 里的 `kotlin.test.Test` 是个 typealias，指向 junit-jupiter 的注解。junit-jupiter-api.jar 必须也在编译 classpath 上，否则报 unresolved reference。

运行测试：

```
java -jar junit-platform-console-standalone-1.11.4.jar execute \
     --class-path "build/v11-main:build/v11-test:src/main/resources:..." \
     --scan-class-path
```

`src/main/resources` 一定要在 classpath 上，端到端测试会从里面读示例剧本 `sample.interlude`。

当前测试 28 例全过：ParserTest / ValidatorTest / ExtractorTest / GraphLayoutTest 共 24 例，EndToEndTest 4 例。

## CLI 参考

入口类是 `com.interlude.LintCliKt`。用 kotlinc 直编之后这样跑：

```
java -cp <classes>:<kotlin-stdlib.jar> com.interlude.LintCliKt lint <剧本文件> [选项]
```

用法：

```
interlude-lint lint <剧本文件> [--log-level LEVEL] [--log-json] [--format text|json]
```

参数：

- `--log-level`：trace / debug / info / warn / error，默认 info。非法值会打印用法并以退出码 2 退出。
- `--log-json`：日志以 JSON 行写到 stderr。不加就是人读格式。
- `--format`：text（默认）或 json，决定 stdout 上校验报告的格式。

退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 无 ERROR 问题 |
| 1 | 命中至少一条 ERROR |
| 2 | 参数错误 / 文件不存在 / 解析失败 |

日志走 stderr，报告走 stdout，两者分开，方便脚本里管道处理。

## 日志说明

日志通过 `com.interlude.log` 这个统一门面输出，op 字段固定是四个之一：startup / parse / validate / report。

- parse：记录文件路径、场景数、耗时。
- validate：记录问题总数、ERROR 数、WARNING 数、耗时。
- debug 级别：逐条记录命中的规则，含 code / scene / line。

日志内容只包含路径、scene id、行号、code、计数、耗时。不含剧本正文内容。

人读格式示例（`[INFO ]` 为 5 宽左对齐，fields 按 key 排序）：

```
2026-10-15T07:30:00.123+08:00 [INFO ] op=parse durationMs=12 file=src/main/resources/scripts/sample.interlude scenes=9 解析完成
```

JSON 行示例（level 为大写，fields 按 key 排序）：

```
{"timestamp":"2026-10-15T07:30:00.123+08:00","level":"INFO","op":"validate","message":"校验完成","durationMs":4,"errors":1,"issues":5,"scenes":9,"warnings":4}
```

想看逐条命中规则，把 `--log-level` 设成 debug：

```
interlude-lint lint src/main/resources/scripts/sample.interlude --log-level debug
```

## 测试说明

测试分两层：

- 单元层：ParserTest（DSL 解析与行号）、ValidatorTest（5 条校验规则）、ExtractorTest（本地化抽取）、GraphLayoutTest（分支图布局算法），共 24 例。
- 端到端层：EndToEndTest 4 例，从 `src/main/resources` 读示例剧本跑全链路。

示例剧本 `src/main/resources/scripts/sample.interlude` 有 9 个场景，里面埋了 5 个已知问题，端到端测试就是围绕它写的。

本机跑测试按上面「本机直编」那节的三条命令来。

## 常见报错排查

**`第 N 行: ...`**

DSL 解析失败。N 是剧本文件的真实行号，按提示信息去改第 N 行。

**`文件不存在: <路径>`，退出码 2**

检查剧本路径。相对路径是相对当前工作目录的。

**UNREACHABLE 警告**

场景从入口 `scene start:` 走不到。可能是真的孤立场景，也可能是某个 choice 的条件写错，把通往这个场景的分支挡掉了。先顺着入口往下看 choice 条件。

**DEAD_END**

场景没有任何出边，也没有 end。补一个 end 或者接一条出边。

**桌面 UI 本机跑不起来**

Compose 编译器插件在本机后端崩溃，UI 编不过，也截不了图。去有 GUI 的正常机器上 `./gradlew run`。本机只用直编流程验证非 UI 部分。

## 已知环境限制

- 桌面 UI 的截图验收还没做，要等正常 GUI 环境。
- Gradle daemon 在本沙箱不可用（IPC 故障），所以本机验证一律走直编。
- UI 相关的代码（`ui/App.kt`）不在本机直编范围内。
