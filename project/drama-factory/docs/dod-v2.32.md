# v2.32 flaky 收尾：ffmpeg 输出竞态 + 中断异常收敛 + 重试逃逸发版对照报告

## 里程碑概述

本轮 v2.32（2026-10-17）关闭 `docs/FLAKY_ROOT_CAUSE.md` §7 残余风险 ③④⑥：

1. 残余风险 ③（`FfmpegService.run()` 的 `reader.join(2000)` 硬等待）。`reader.join(2000)` 为固定上限等待，读取线程未在 2s 内结束即返回，输出可能被截断且无任何标注。本轮改为有上限循环 join + `reader.isAlive()` 守卫：预算耗尽仍未结束时，message 标注"可能不完整"，不再静默丢弃。
2. 残余风险 ④（中断语义丢失）。原先三处中断 throw 点抛出的是通用 `FfmpegException`，调用方无法区分"中断"与"普通失败"，导致中断被当作可重试失败。本轮新增 `FfmpegInterruptedException extends FfmpegException`（构造 `(String, Throwable)` → `super(m, t, false)`），把三处中断 throw 点收敛为专用异常；`FinalCutService.withFfmpegRetry` 新增 `catch (FfmpegInterruptedException)` 直接 throw（终止重试），sleep 中断改抛专用异常（修复 cause=null）。
3. 残余风险 ⑥（`catch (RuntimeException)` 过宽 + 中断后重试逃逸）。`FinalCutService.withFfmpegRetry` 的 `catch (RuntimeException)` 收敛为保守 transient 重试；`VideoTaskService.processDueTasks()` 新增 `catch (FfmpegInterruptedException)`——恢复中断标志 + `failOrRetry(task, msg, true)`，避免中断被吞后继续重试。

诚实根因报告见 `docs/FLAKY_ROOT_CAUSE.md`。残余风险 ⑤（多实例 CAS 单飞）本轮仍未关闭，留待多实例场景再议。

## 交付清单

| 批次 | 内容 | 结果 |
| --- | --- | --- |
| B1 | 残余风险 ③ 分析 | 完成 |
| B2 | 残余风险 ③ 修复 + 测试 | 完成 |
| B3 | 残余风险 ④ 分析 | 完成 |
| B4 | 残余风险 ④ 修复 + 测试 | 完成 |
| B5 | 残余风险 ⑥ 审计 | 完成 |
| B6 | 残余风险 ⑥ 修复 + 测试 | 完成 |
| B7 | 文档（`docs/FLAKY_ROOT_CAUSE.md` §7/§2/§6/§8/§9） | 完成 |
| B8 | 收尾文档批（本批：对照报告 + CHANGELOG） | 完成 |
| B2-FEEDBACK | 回喂：残余风险 ③ 修复 | 2 轮 |
| B4-FEEDBACK | 回喂：残余风险 ④ 修复 | 2 轮 |
| B6-FEEDBACK | 回喂：残余风险 ⑥ 修复 | 2 轮 |
| B7-FEEDBACK | 回喂：文档 | 1 轮 |

## 验证

- 新测试：9/9 全绿（`FfmpegOutputRaceV232Test` 3/3，2.621s；`FfmpegInterruptV232Test` 3/3，12.92s；`FfmpegRetryEscapeV232Test` 3/3，14.12s）。
- 回归：13 类 64/64 全绿，无回归。其中既有 10 类 55/55 基线（`FinalCutServiceTest` 20、`FinalCutFfmpegRetryTest` 3、`FinalCutRealFfmpegRetryTest` 1、`FfmpegServiceTest` 4、`FfmpegExceptionClassificationTest` 5、`VideoTaskFailFastTest` 2、`ProcessDueTasksSingleFlightTest` 1、`FfmpegRetryMetricsTest` 2、`FinalCutRetryBudgetV231Test` 7、`FfmpegLaunchClassifyV231Test` 10），新增 3 类 9 例。
- 全量 `mvn -o verify` 本轮未跑（只跑受影响的 13 类；铁律：不降 JaCoCo 门禁）。v2.31 全量数据（2013 例，14 失败 + 11 错误，Qwen 相关）保持原样，本轮不改写。

## PRODUCTION_CHECKLIST.md 逐条对照

本轮相关条目：

- 1.1 测试金字塔：通过（新测试 9 例 + 回归 13 类 64/64，其中既有 10 类 55/55 基线无回归）。
- 6.2 CHANGELOG：通过（Unreleased 首条插入 v2.32）。
- 6.3 技术债有记录：通过（`docs/FLAKY_ROOT_CAUSE.md` §9）。
- 6.4 代码与文档同步：通过（生产改动 3 文件与 `docs/FLAKY_ROOT_CAUSE.md` §7/§2/§6/§8/§9 同步）。

## 诚实声明

- 门禁：本轮未跑全量 `mvn -o verify`，只跑受影响的 13 类（铁律：不降 JaCoCo 门禁）。v2.31 全量数据（2013 例，14 失败 + 11 错误，Qwen 相关）保持原样，本轮不改写。本轮不宣称全量门禁通过。
- 残余风险 ⑤（多实例 CAS 单飞）本轮仍未关闭，留待多实例场景再议。本轮不宣称 flaky 残余风险已全部关闭。
- 概率性：ffmpeg 输出竞态与中断路径属概率性场景，新测试 9/9 通过是在当前样本量下的观测结果，不能据此推断概率性已彻底消除。
- 措辞：本轮关闭的是 `docs/FLAKY_ROOT_CAUSE.md` §7 残余风险 ③④⑥ 三条，其余风险条目状态见该文档。

## 生成方式说明

本轮由 8 批 dpsk 完成：B1 残余风险 ③ 分析、B2 残余风险 ③ 修复 + 测试、B3 残余风险 ④ 分析、B4 残余风险 ④ 修复 + 测试、B5 残余风险 ⑥ 审计、B6 残余风险 ⑥ 修复 + 测试、B7 文档、B8 收尾文档批（本批）；另有回喂 B2 2 轮、B4 2 轮、B6 2 轮、B7 1 轮。

编排者承担机械性工作：PATCH 应用、构建验证、受影响 13 类回归、基线对照；本轮编排者机械修正 2 处（未改测试语义）。
