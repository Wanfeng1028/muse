package com.dramafactory.metrics;

import com.dramafactory.model.RunStatus;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.RunRepository;
import com.dramafactory.repository.VideoTaskRepository;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.EnumMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * DramaFactory 业务指标采集组件（v2.4 生产级补强第 3 轮：指标与告警）。
 *
 * <p>设计原则：
 * <ul>
 *   <li>Counter / Timer 在业务调用点同步记录（见 {@link #recordScriptLlm}、{@link #recordFinalCutBuild}）。</li>
 *   <li>Gauge 只读进程内 {@link AtomicLong} 快照，<b>绝不在 Prometheus 抓取时访问数据库</b>，
 *       避免抓取拖慢 DB；快照由 {@link #refresh()} 定时任务刷新。</li>
 *   <li>刷新过程对 DB 异常完全隔离：只打 warn 日志，不中断调度。</li>
 * </ul>
 *
 * <p>指标一览（Prometheus 命名规范：小写下划线）：
 * <ul>
 *   <li>dramafactory_video_tasks_queued —— 视频任务队列长度 = PENDING + PROCESSING，单位：个</li>
 *   <li>dramafactory_runs_by_status{status} —— 按 RunStatus 拆分的 Run 数量，单位：个</li>
 *   <li>dramafactory_runs_waiting_approval —— 等待审批的 Run 数量，单位：个（供告警使用）</li>
 *   <li>dramafactory_script_llm_calls_total{model,result} —— 脚本生成 LLM 调用总次数，单位：次</li>
 *   <li>dramafactory_script_llm_duration_seconds{model} —— 脚本生成 LLM 调用耗时，单位：秒</li>
 *   <li>dramafactory_finalcut_builds_total{result} —— 成片构建总次数，单位：次</li>
 *   <li>dramafactory_finalcut_build_duration_seconds —— 成片构建耗时，单位：秒</li>
 * </ul>
 */
@Component
public class DramaMetrics {

    private static final Logger log = LoggerFactory.getLogger(DramaMetrics.class);

    private final MeterRegistry registry;
    private final RunRepository runRepository;
    private final VideoTaskRepository videoTaskRepository;

    /** 视频任务队列长度快照 = PENDING + PROCESSING。单位：个。 */
    private final AtomicLong videoTasksQueued = new AtomicLong(0L);

    /** 按 RunStatus 拆分的 Run 数量快照，每个枚举值一个槽位。单位：个。 */
    private final Map<RunStatus, AtomicLong> runsByStatus = new EnumMap<>(RunStatus.class);

    /** 等待审批的 Run 数量快照。单位：个。 */
    private final AtomicLong runsWaitingApproval = new AtomicLong(0L);

    public DramaMetrics(MeterRegistry registry,
                        RunRepository runRepository,
                        VideoTaskRepository videoTaskRepository) {
        this.registry = registry;
        this.runRepository = runRepository;
        this.videoTaskRepository = videoTaskRepository;

        // Gauge 注册：抓取时只读内存快照，不访问 DB。
        Gauge.builder("dramafactory_video_tasks_queued", videoTasksQueued, AtomicLong::get)
                .description("视频任务队列长度 = PENDING + PROCESSING，单位：个")
                .register(registry);

        // 为每个 RunStatus 预注册一个带 status 标签的 Gauge，标签值统一小写枚举名。
        for (RunStatus status : RunStatus.values()) {
            AtomicLong holder = new AtomicLong(0L);
            runsByStatus.put(status, holder);
            Gauge.builder("dramafactory_runs_by_status", holder, AtomicLong::get)
                    .description("按状态拆分的 Run 数量，单位：个")
                    .tag("status", status.name().toLowerCase())
                    .register(registry);
        }

        Gauge.builder("dramafactory_runs_waiting_approval", runsWaitingApproval, AtomicLong::get)
                .description("等待审批的 Run 数量（WAITING_APPROVAL），单位：个")
                .register(registry);

        // 启动时立即刷新一次，避免上线初期指标全零。
        refresh();
    }

    /**
     * 记录一次脚本生成 LLM 调用。
     *
     * @param model     模型名，null 或空串归一化为 "unknown"（Micrometer 不接受空标签值）
     * @param latencyMs 调用耗时毫秒，喂给秒级 Timer；负值截断为 0
     * @param ok        是否成功
     */
    public void recordScriptLlm(String model, long latencyMs, boolean ok) {
        String normalizedModel = (model == null || model.isBlank()) ? "unknown" : model;
        long safeLatency = Math.max(0L, latencyMs);
        // registry.counter/timer 对同名同标签返回同一实例，幂等，可直接调用。
        registry.counter("dramafactory_script_llm_calls_total",
                        "model", normalizedModel, "result", ok ? "ok" : "error")
                .increment();
        registry.timer("dramafactory_script_llm_duration", "model", normalizedModel)
                .record(Duration.ofMillis(safeLatency));
    }

    /**
     * 记录一次成片构建。
     *
     * @param latencyMs 构建耗时毫秒，喂给秒级 Timer；负值截断为 0
     * @param ok        是否成功
     */
    public void recordFinalCutBuild(long latencyMs, boolean ok) {
        long safeLatency = Math.max(0L, latencyMs);
        registry.counter("dramafactory_finalcut_builds_total", "result", ok ? "ok" : "error")
                .increment();
        registry.timer("dramafactory_finalcut_build_duration")
                .record(Duration.ofMillis(safeLatency));
    }

    /**
     * 定时刷新内存中的 Gauge 快照（默认每 30 秒）。
     *
     * <p>整个方法被 try/catch 包住：任何 DB 异常只打 warn 日志、不向上抛，
     * 保证一次刷新失败不会打断后续调度周期。
     */
    @Scheduled(fixedDelay = 30000)
    public void refresh() {
        try {
            videoTasksQueued.set(
                    videoTaskRepository.countByStatus(VideoTaskStatus.PENDING)
                            + videoTaskRepository.countByStatus(VideoTaskStatus.PROCESSING));
            for (RunStatus status : RunStatus.values()) {
                runsByStatus.get(status).set(runRepository.countByStatus(status));
            }
            runsWaitingApproval.set(runRepository.countByStatus(RunStatus.WAITING_APPROVAL));
        } catch (Exception e) {
            // 不抛出：调度任务必须活下来，下一周期继续尝试。
            log.warn("刷新 DramaMetrics Gauge 快照失败，已跳过本次刷新", e);
        }
    }
}
