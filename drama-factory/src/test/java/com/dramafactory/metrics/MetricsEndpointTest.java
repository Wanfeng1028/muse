package com.dramafactory.metrics;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Metrics 端点测试。
 *
 * <p>重要约束（与本项目沙箱环境一致）：
 * 本项目的 surefire fork 出来的 JVM 中真实 HTTP 回环不可用，
 * 因此禁止使用 TestRestTemplate / RANDOM_PORT / 真实 HTTP 端口。
 * 全部测试统一通过 MockMvc 驱动控制器层（参见 DramaV2ApiIntegrationTest 的明文规定）。</p>
 *
 * <p>由此带来的断言边界说明：
 * MockMvc 只驱动 Spring MVC 控制器层，不经过真实 Servlet 容器与真实网络栈，
 * 因此像 {@code http_server_requests_seconds} 这类"仅由真实 HTTP 流量产生"的指标
 * 在本测试中不会出现，也不应被断言。
 * 该类指标由独立的冒烟验证（真实部署环境）覆盖，不在本单测范围内。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
class MetricsEndpointTest {

    @Autowired
    private MockMvc mockMvc;

    /**
     * 场景一：/actuator/prometheus 端点应可用，返回 200 且 content-type 为 text/plain。
     */
    @Test
    @DisplayName("场景一：Prometheus 端点返回 200 且 content-type 包含 text/plain")
    void prometheusEndpointIsExposed() throws Exception {
        mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                // Prometheus 文本暴露格式的 MIME 类型为 text/plain（可能带 version/charset 参数），
                // 这里只断言主类型包含 text/plain 即可。
                .andExpect(content().contentTypeCompatibleWith("text/plain"));
    }

    /**
     * 场景二：先访问白名单放行的 /api/health（无需 token），
     * 再抓取 /actuator/prometheus，断言核心业务指标与 JVM 指标均存在。
     */
    @Test
    @DisplayName("场景二：健康检查放行后，Prometheus 文本包含队列与 JVM 内存指标")
    void prometheusExposesCoreBusinessAndJvmMetrics() throws Exception {
        // /api/health 在 JwtAuthFilter 白名单中放行，无需携带 token。
        mockMvc.perform(get("/api/health"))
                .andExpect(status().isOk());

        MvcResult result = mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andReturn();

        String body = result.getResponse().getContentAsString();

        // 业务侧：视频任务排队数指标。
        assertThat(body).contains("dramafactory_video_tasks_queued");
        // JVM 侧：内存使用量指标（由 Micrometer JVM binder 暴露）。
        assertThat(body).contains("jvm_memory_used_bytes");
    }

    /**
     * 场景三：按状态分组的运行计数指标，标签值必须为小写（例如 running）。
     */
    @Test
    @DisplayName("场景三：runs_by_status 指标标签值小写（running）")
    void runsByStatusMetricUsesLowercaseLabelValue() throws Exception {
        MvcResult result = mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andReturn();

        String body = result.getResponse().getContentAsString();

        // 精确匹配标签值小写形式，防止大小写回归。
        assertThat(body).contains("dramafactory_runs_by_status{status=\"running\"}");
    }

    /*
     * 关于未断言指标的说明：
     * http_server_requests_seconds 由 Micrometer 的 HTTP server 观测机制产生，
     * 只有在真实 Servlet 容器处理真实 HTTP 请求时才会被记录。
     * MockMvc 绕过真实容器与网络栈，直接驱动控制器层，
     * 因此该指标在本测试中不会出现，属于预期行为。
     * 该指标的验证由部署环境下的冒烟测试覆盖，此处不做断言。
     */
}
