# agent-canvas POC 评审补改（Hark 第 1+2 轮）交付报告

- 日期：2026-10-16
- 基线：commit 2cce087（五项必改项落地）
- 范围：Hark 第 1 轮评审意见 4 项 + 第 2 轮补充 3 项
- 生成方式：微信 ChatAPI DeepSeek-V4-Flash 生成（三批 PATCH），编排侧应用 + 验收

## 改动清单

| # | 评审意见 | 落实 |
|---|---|---|
| 1 | 并发用例防假绿 | `concurrentSave_sameBaseVersion_onlyOneWins` 改写：20 轮循环，每轮新子目录隔离；双栅栏（起跑门+完成门）；每轮严格三元组断言（恰好 1 成功 / 恰好 7 个 CanvasConflictException / 0 其他异常 / revision=base+1） |
| 2 | poc-local profile 确认 | `application-poc-local.yml` 独立文件绑 127.0.0.1；`GracefulShutdownTest.defaultProfileBindsAllInterfaces` 断言默认 profile 下 `server.address=0.0.0.0`；README 含 `--spring.profiles.active=poc-local` 用法 |
| 3 | revision null 前端 | `src/store.test.ts` 新增：revision 为 null 时 save() 不发 PUT（fetch 调用 0 次）且提示"请先加载画布后再保存"；`test:logic` 脚本纳入 store 测试 |

## 红测证据（注释掉 synchronized 后变红）

实测命令：临时将 `CanvasProjectService.save` 内 `synchronized (writeLock)` 改为普通块，运行
`CanvasProjectVersionConflictTest#concurrentSave_sameBaseVersion_onlyOneWins`。

失败输出（第 0 轮即变红）：
```
[ERROR] CanvasProjectVersionConflictTest.concurrentSave_sameBaseVersion_onlyOneWins:158
  ==> expected: <0> but was: <7>
[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
```

解读：无锁时 8 线程同时写同一文件，7 个线程抛出非 `CanvasConflictException` 的异常
（文件写入竞态：多线程共用同一 `project.json.tmp` 路径互相覆盖 + 非原子 move），
严格三元组的第一元组（0 其他异常）即被触发。恢复 `synchronized` 后 20 轮全绿。
这证明该用例验证的是**锁的原子性**，而非仅版本比对逻辑。

## 测试结果

- 后端全量：1871 通过 / 0 失败 / 0 错误（2 skipped 为既有）
- `CanvasProjectVersionConflictTest`：7/7（含 20 轮并发用例）
- `GracefulShutdownTest`：4/4（含新增默认 profile 断言）
- 前端 `tsc --noEmit`：0 错误；`vite build`：成功
- 前端 `test:logic`：conflict 8/8 + store save guard 2/2
