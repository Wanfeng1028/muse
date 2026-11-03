package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.springframework.stereotype.Component;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 离线演示与测试用的视频服务商实现。
 * 不调用任何外部 API，仅在内存中模拟任务提交与轮询。
 */
@Component("mockVideoProvider")
public class MockVideoProvider implements VideoProvider {

    /** 任务记录：创建时间与视频时长 */
    private static final class MockJob {
        private final long createdAtMs;
        private final int seconds;

        private MockJob(long createdAtMs, int seconds) {
            this.createdAtMs = createdAtMs;
            this.seconds = seconds;
        }
    }

    /** 内存任务表：任务 ID -> 任务记录 */
    private final ConcurrentHashMap<String, MockJob> jobs = new ConcurrentHashMap<>();

    /** 就绪耗时（毫秒），默认为 3000，可通过 setter 调整供测试使用 */
    private volatile long readyAfterMs = 3000L;

    /** 是否让下一次 poll 返回失败，供测试失败路径使用 */
    private volatile boolean failNext = false;

    /**
     * 提交模拟任务。
     *
     * @param shot    分镜实体（此处不使用其内部字段，仅用于接口兼容）
     * @param seconds 期望视频时长（秒）
     * @return 生成的模拟任务 ID，前缀为 "mock-"
     */
    @Override
    public String submit(Shot shot, int seconds) {
        String id = "mock-" + UUID.randomUUID();
        jobs.put(id, new MockJob(System.currentTimeMillis(), seconds));
        return id;
    }

    /**
     * 轮询模拟任务状态。
     *
     * @param providerTaskId 提交时返回的任务 ID
     * @return 探测结果；任务不存在时抛出 IllegalArgumentException
     */
    @Override
    public ProbeResult poll(String providerTaskId) {
        MockJob job = jobs.get(providerTaskId);
        if (job == null) {
            throw new IllegalArgumentException("未知的 mock 任务 ID: " + providerTaskId);
        }

        // 优先处理测试用失败路径
        if (failNext) {
            failNext = false;
            return new ProbeResult(RemoteStatus.FAILED, null, "mock 模拟失败", 0);
        }

        long elapsed = System.currentTimeMillis() - job.createdAtMs;
        if (elapsed >= readyAfterMs) {
            return new ProbeResult(RemoteStatus.COMPLETED, "mock://clip?seconds=" + job.seconds, null, 100);
        }
        return new ProbeResult(RemoteStatus.PROCESSING, null, null, 50);
    }

    /**
     * 服务商名称。
     */
    @Override
    public String name() {
        return "mock";
    }

    @Override
    public ConnectivityResult probeConnectivity() {
        return new ConnectivityResult(ConnectivityStatus.OK, "演示用提供方，无需真实连接");
    }

    /**
     * 设置任务就绪所需耗时（毫秒），供测试使用。
     */
    public void setReadyAfterMs(long readyAfterMs) {
        this.readyAfterMs = readyAfterMs;
    }

    /**
     * 标记下一次 poll 返回失败，供测试失败路径使用；调用后自动重置。
     */
    public void setFailNext(boolean failNext) {
        this.failNext = failNext;
    }
}
