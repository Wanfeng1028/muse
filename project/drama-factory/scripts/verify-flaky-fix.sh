#!/usr/bin/env bash
# v2.29 flaky 根因歼灭回归验证：一键运行本轮新增测试 + 原 flaky 测试。
# 用法：在 drama-factory 目录下执行 bash scripts/verify-flaky-fix.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/workspace/toolchains/maven/bin:$HOME/workspace/toolchains/jdk/bin:$PATH"
export JAVA_HOME="$HOME/workspace/toolchains/jdk"

# 本轮新增 8 批测试 + 原 flaky 测试 testFullPipeline 所在的测试类集合：
# - FfmpegExceptionClassificationTest      : 验证 ffmpeg 异常分类逻辑稳定可复现。
# - FinalCutFfmpegRetryTest                : 验证 FinalCut 在 ffmpeg 失败时的重试策略。
# - FinalCutRealFfmpegRetryTest            : 用真实 ffmpeg 验证 FinalCut 重试端到端行为。
# - ProcessDueTasksSingleFlightTest        : 验证到期任务处理具备单飞（single-flight）语义。
# - VideoTaskFailFastTest                  : 验证视频任务失败快速返回，不再无谓重试。
# - FfmpegRetryMetricsTest                 : 验证 ffmpeg 重试相关指标计数正确。
# - FfmpegServiceTest                      : 验证 ffmpeg 服务层基础行为与回归。
# - VideoPipelineResilienceE2eTest         : 视频流水线韧性端到端测试。
# - DramaV2ApiIntegrationTest              : Drama v2 API 集成测试（含原 flaky 的 testFullPipeline）。
TESTS="FfmpegExceptionClassificationTest,FinalCutFfmpegRetryTest,FinalCutRealFfmpegRetryTest,ProcessDueTasksSingleFlightTest,VideoTaskFailFastTest,FfmpegRetryMetricsTest,FfmpegServiceTest,VideoPipelineResilienceE2eTest,DramaV2ApiIntegrationTest"

echo "=== v2.29 回归验证开始 ==="
mvn -o -s /home/hatch/.m2/settings.xml test -Dtest="$TESTS" -DfailIfNoTests=false -Dsurefire.failIfNoSpecifiedTests=false
echo "=== 9 个测试类全部通过：flaky 修复回归验证完成 ==="
