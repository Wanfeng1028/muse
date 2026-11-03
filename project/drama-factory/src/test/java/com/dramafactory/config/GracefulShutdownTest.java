package com.dramafactory.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.yaml.snakeyaml.Yaml;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ScheduledExecutorService;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 优雅停机相关配置的测试。
 *
 * <p>注意：本测试<strong>不能</strong>通过 Spring 的 {@code Environment} 来断言
 * {@code server.shutdown} 与 {@code spring.task.scheduling.shutdown.*}。
 * 原因在于本项目的 surefire 测试 classpath 中，{@code target/test-classes/application.yml}
 * 排在 {@code target/classes/application.yml} 之前，而 {@code classpath:/application.yml}
 * 由类加载器按“首次命中”解析，于是测试用的 application.yml 会把主配置完全遮蔽，
 * 导致 {@code environment.getProperty("server.shutdown")} 返回 null。
 * 这是项目既有特性，不应通过改构建或重命名测试 yml 来绕过。
 *
 * <p>因此这里改为直接解析生产配置文件 {@code src/main/resources/application.yml}
 * （surefire 的工作目录即模块根目录，相对路径可用），
 * 使用 Spring Boot 自带的 SnakeYAML 读取 YAML 内容并做断言。
 */
@SpringBootTest
class GracefulShutdownTest {
    @Autowired private TaskScheduler taskScheduler;

    /**
     * 读取并解析生产配置文件 {@code src/main/resources/application.yml}。
     *
     * <p>直接读文件而不是走 {@code Environment}，是为了避开测试 classpath 中
     * 测试用 application.yml 对主配置的遮蔽问题。
     *
     * @return 解析后的 YAML 顶层映射
     * @throws Exception 当文件不存在或读取失败时抛出
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> loadMainApplicationYaml() throws Exception {
        Path yamlPath = Path.of("src", "main", "resources", "application.yml");
        assertThat(Files.exists(yamlPath))
                .as("生产配置文件应存在: %s", yamlPath.toAbsolutePath())
                .isTrue();
        try (InputStream in = Files.newInputStream(yamlPath)) {
            Object loaded = new Yaml().load(in);
            assertThat(loaded).isInstanceOf(Map.class);
            return (Map<String, Object>) loaded;
        }
    }

    /**
     * 从嵌套 Map 中按路径逐层取值。
     *
     * @param root 顶层映射
     * @param keys 逐层键名
     * @return 命中的值，任一层缺失时返回 null
     */
    @SuppressWarnings("unchecked")
    private Object getNested(Map<String, Object> root, String... keys) {
        Object current = root;
        for (String key : keys) {
            if (!(current instanceof Map<?, ?> map)) {
                return null;
            }
            current = ((Map<String, Object>) map).get(key);
        }
        return current;
    }

    /**
     * 生产配置中 {@code server.shutdown} 应为 {@code graceful}。
     *
     * <p>不使用 {@code Environment}，因为测试 classpath 中的 application.yml
     * 会遮蔽主配置，使其读不到该属性。
     *
     * @throws Exception 读取生产 yml 失败时抛出
     */
    @Test
    void serverShutdownShouldBeGraceful() throws Exception {
        Map<String, Object> yaml = loadMainApplicationYaml();
        Object shutdown = getNested(yaml, "server", "shutdown");
        assertThat(shutdown).isEqualTo("graceful");
    }

    /**
     * 生产配置中 {@code spring.task.scheduling.shutdown.await-termination} 应为 {@code true}，
     * 且 {@code await-termination-period} 应为 {@code 30s}。
     *
     * <p>同样直接解析生产 yml，避免测试 classpath 遮蔽导致 {@code Environment} 读不到值。
     * SnakeYAML 会将不带引号的 {@code true} 解析为 {@link Boolean}，
     * 而 {@code 30s} 保持为字符串。
     *
     * @throws Exception 读取生产 yml 失败时抛出
     */
    @Test
    void schedulingAwaitTerminationShouldBeTrue() throws Exception {
        Map<String, Object> yaml = loadMainApplicationYaml();
        Object awaitTermination = getNested(
                yaml, "spring", "task", "scheduling", "shutdown", "await-termination");
        assertThat(awaitTermination).isEqualTo(Boolean.TRUE);

        Object awaitTerminationPeriod = getNested(
                yaml, "spring", "task", "scheduling", "shutdown", "await-termination-period");
        assertThat(awaitTerminationPeriod).isEqualTo("30s");
    }

    /**
     * 校验 {@link TaskScheduler} bean 为可用的 {@link ThreadPoolTaskScheduler}，
     * 且其底层执行器尚未关闭（这部分不依赖被遮蔽的配置，原样保留）。
     */
    @Test
    void taskSchedulerShouldBeThreadPoolTaskSchedulerWithExecutor() {
        assertThat(taskScheduler).isInstanceOf(ThreadPoolTaskScheduler.class);
        ThreadPoolTaskScheduler pool = (ThreadPoolTaskScheduler) taskScheduler;
        ScheduledExecutorService executor = pool.getScheduledExecutor();
        assertThat(executor).isNotNull();
        assertThat(executor.isShutdown()).isFalse();
    }

    /**
     * 默认 profile 下 server.address 为 0.0.0.0（未限定回环），Docker/生产部署路径
     * （compose.yml / docker-compose.yml 中 nginx 容器通过服务名连主服务）不受影响；
     * POC 本地限定回环走独立的 application-poc-local.yml（--spring.profiles.active=poc-local 启用），
     * 与默认配置解耦。
     */
    @Test
    void defaultProfileBindsAllInterfaces() throws Exception {
        Map<String, Object> yaml = loadMainApplicationYaml();
        Object address = getNested(yaml, "server", "address");
        assertThat(address).isEqualTo("0.0.0.0");
    }
}
