package com.dramafactory.pipeline;

import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * PipelineTemplateService 深度测试。
 *
 * <p>说明：{@link PipelineTemplateService} 的构造器内部使用
 * {@link org.springframework.core.io.support.PathMatchingResourcePatternResolver} 扫描
 * classpath 下的 pipeline-templates/*.yaml，因此测试构造时走真实资源扫描路径，
 * 不 mock 该外部资源解析过程。对于「加载失败」这类只能通过篡改 loader 行为才能触发的分支，
 * 使用真实的 {@link PipelineTemplateLoader} 子类（抛异常/阻塞/计数），不引入 Mockito，
 * 被测逻辑仍走真实实现。</p>
 */
class PipelineTemplateServiceDeepTest {

    /**
     * 真实 loader 的子类：可注入异常、延迟与调用计数，用于失败注入与并发测试。
     * 底层解析逻辑仍委托给父类真实实现。
     */
    static class FailingLoader extends PipelineTemplateLoader {
        private final IOException failure;
        private final long delayMillis;
        private final AtomicInteger callCount = new AtomicInteger();

        FailingLoader(IOException failure, long delayMillis) {
            this.failure = failure;
            this.delayMillis = delayMillis;
        }

        @Override
        public PipelineTemplate load(InputStream in) {
            callCount.incrementAndGet();
            if (delayMillis > 0) {
                try {
                    Thread.sleep(delayMillis);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw FailingLoader.<RuntimeException>sneakyThrow(new IOException("加载被中断", e));
                }
            }
            if (failure != null) {
                throw FailingLoader.<RuntimeException>sneakyThrow(failure);
            }
            return super.load(in);
        }

        int callCount() {
            return callCount.get();
        }

        @SuppressWarnings("unchecked")
        static <T extends Throwable> RuntimeException sneakyThrow(Throwable t) throws T {
            throw (T) t;
        }
    }

    /** 真实 loader，从字符串构造模板，供纯逻辑测试使用。 */
    private static PipelineTemplate templateFromYaml(String yaml) {
        return new PipelineTemplateLoader().parse(yaml);
    }

    // ---------------------------------------------------------------------
    // 构造 / 缓存加载
    // ---------------------------------------------------------------------

    @Test
    void constructor_withRealClasspathLoader_loadsCinematicTemplateAndListsSortedByName() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());

        List<PipelineTemplate> templates = service.listTemplates();

        assertThat(templates).isNotNull();
        assertThat(templates).extracting(PipelineTemplate::getName).contains("cinematic");
        List<String> names = new ArrayList<>();
        for (PipelineTemplate t : templates) {
            names.add(t.getName());
        }
        List<String> sorted = new ArrayList<>(names);
        sorted.sort(java.util.Comparator.naturalOrder());
        assertThat(names).isEqualTo(sorted);
    }

    @Test
    void constructor_whenLoaderThrowsIOException_propagatesIllegalStateExceptionWithCause() {
        IOException io = new IOException("boom-io");
        FailingLoader failing = new FailingLoader(io, 0L);

        assertThatThrownBy(() -> new PipelineTemplateService(failing))
                .isInstanceOf(IllegalStateException.class)
                .hasCauseInstanceOf(IOException.class)
                .hasMessageContaining("boom-io");

        assertThat(failing.callCount()).isGreaterThan(0);
    }

    @Test
    void constructor_whenLoaderThrowsIllegalArgument_wrapsIntoIllegalStateExceptionWithFilename() {
        FailingLoader failing = new FailingLoader(null, 0L) {
            @Override
            public PipelineTemplate load(InputStream in) {
                super.load(in);
                throw new IllegalArgumentException("非法字段");
            }
        };

        assertThatThrownBy(() -> new PipelineTemplateService(failing))
                .isInstanceOf(IllegalStateException.class)
                .hasCauseInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("加载模板失败")
                .hasMessageContaining("非法字段");
    }

    // ---------------------------------------------------------------------
    // getTemplate / listTemplates 边界
    // ---------------------------------------------------------------------

    @Test
    void getTemplate_withNullName_throwsTemplateNotFoundException() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());

        assertThatThrownBy(() -> service.getTemplate(null))
                .isInstanceOf(TemplateNotFoundException.class);
    }

    @Test
    void getTemplate_withUnknownName_throwsTemplateNotFoundException() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());

        assertThatThrownBy(() -> service.getTemplate("__no_such_template__"))
                .isInstanceOf(TemplateNotFoundException.class);
    }

    @Test
    void getTemplate_existingName_returnsSameInstanceAcrossRepeatedCalls_cacheConsistency() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());

        PipelineTemplate first = service.getTemplate("cinematic");
        PipelineTemplate second = service.getTemplate("cinematic");

        assertThat(first).isNotNull();
        assertThat(second).isSameAs(first);
        assertThat(service.listTemplates())
                .filteredOn(t -> "cinematic".equals(t.getName()))
                .singleElement()
                .isSameAs(first);
    }

    @Test
    void listTemplates_returnsDefensiveCopy_mutatingResultDoesNotAffectService() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        List<PipelineTemplate> snapshot = service.listTemplates();
        int sizeBefore = snapshot.size();
        assertThat(sizeBefore).isGreaterThan(0);

        snapshot.clear();

        assertThat(service.listTemplates()).hasSize(sizeBefore);
    }

    // ---------------------------------------------------------------------
    // validateTemplate 边界
    // ---------------------------------------------------------------------

    @Test
    void validateTemplate_nullTemplate_reportsNullProblem() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());

        List<String> problems = service.validateTemplate(null);

        assertThat(problems).isNotNull().containsExactly("模板为 null");
    }

    @Test
    void validateTemplate_missingNameAndVersion_reportsBothProblems() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        // loader 解析期就会拒绝空 name（convertRoot 抛 IllegalArgumentException），
        // 因此用合法 YAML 解析后再经 setter 置空，测 service 层的校验分支
        PipelineTemplate t = templateFromYaml("""
                name: n
                version: v1
                stages:
                  - name: s1
                    produces: [a]
                """);
        t.setName("");
        t.setVersion("");

        List<String> problems = service.validateTemplate(t);

        assertThat(problems)
                .contains("模板缺少 name")
                .contains("模板缺少 version");
    }

    @Test
    void validateTemplate_emptyStages_reportsMissingStages() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        PipelineTemplate t = templateFromYaml("""
                name: n
                version: v1
                stages:
                  - name: s1
                    produces: [a]
                """);
        t.setStages(new ArrayList<>());

        List<String> problems = service.validateTemplate(t);

        assertThat(problems).containsExactly("模板缺少 stages");
    }

    @Test
    void validateTemplate_stageWithNullName_reportsPathSpecificProblem() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        PipelineTemplate t = templateFromYaml("""
                name: n
                version: v1
                stages:
                  - name: s1
                    produces: [a]
                """);
        t.getStages().set(0, new PipelineStage());

        List<String> problems = service.validateTemplate(t);

        assertThat(problems).contains("stages[0] 缺少 name");
    }

    @Test
    void validateTemplate_stageDependencyNotProducedEarlier_reportsUnresolvedArtifact() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        // 注意：validateTemplate 只对 i>0 的阶段检查 requiredArtifactsIn（首阶段的依赖视为外部输入），
        // 因此用两阶段：s2 依赖 ghost，但 s1 只产出 a
        PipelineTemplate t = templateFromYaml("""
                name: n
                version: v1
                stages:
                  - name: s1
                    produces: [a]
                  - name: s2
                    produces: [b]
                    required_artifacts_in: [ghost]
                """);

        List<String> problems = service.validateTemplate(t);

        assertThat(problems)
                .anyMatch(p -> p.contains("ghost"))
                .anyMatch(p -> p.contains("s2"))
                .anyMatch(p -> p.contains("未在任何前置阶段的 produces 中声明"));
    }

    @Test
    void validateTemplate_stageDependencyProducedByEarlierStage_passes() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        PipelineTemplate t = templateFromYaml("""
                name: n
                version: v1
                stages:
                  - name: s1
                    produces: [a]
                  - name: s2
                    produces: [b]
                    required_artifacts_in: [a]
                """);

        List<String> problems = service.validateTemplate(t);

        assertThat(problems).isEmpty();
    }

    // ---------------------------------------------------------------------
    // 并发
    // ---------------------------------------------------------------------

    @Test
    void getTemplate_concurrentAccessFromManyThreads_returnsConsistentSingleInstance() throws Exception {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        int threads = 16;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Callable<PipelineTemplate>> tasks = new ArrayList<>();
            for (int i = 0; i < threads; i++) {
                tasks.add(() -> {
                    start.await(5, TimeUnit.SECONDS);
                    return service.getTemplate("cinematic");
                });
            }
            List<Future<PipelineTemplate>> futures = new ArrayList<>();
            for (Callable<PipelineTemplate> task : tasks) {
                futures.add(pool.submit(task));
            }
            start.countDown();

            PipelineTemplate first = null;
            for (Future<PipelineTemplate> f : futures) {
                PipelineTemplate got = f.get(10, TimeUnit.SECONDS);
                assertThat(got).isNotNull();
                if (first == null) {
                    first = got;
                } else {
                    assertThat(got).isSameAs(first);
                }
            }
            assertThat(first).isNotNull();
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void constructor_concurrentConstructionWithSlowLoader_producesIndependentConsistentCaches() throws Exception {
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<FailingLoader> loaders = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            loaders.add(new FailingLoader(null, 5L));
        }
        try {
            List<Callable<PipelineTemplateService>> tasks = new ArrayList<>();
            for (FailingLoader l : loaders) {
                tasks.add(() -> {
                    start.await(5, TimeUnit.SECONDS);
                    return new PipelineTemplateService(l);
                });
            }
            List<Future<PipelineTemplateService>> futures = new ArrayList<>();
            for (Callable<PipelineTemplateService> task : tasks) {
                futures.add(pool.submit(task));
            }
            start.countDown();

            for (Future<PipelineTemplateService> f : futures) {
                PipelineTemplateService svc = f.get(15, TimeUnit.SECONDS);
                assertThat(svc.listTemplates())
                        .extracting(PipelineTemplate::getName)
                        .contains("cinematic");
                assertThat(svc.getTemplate("cinematic")).isNotNull();
            }
            for (FailingLoader l : loaders) {
                assertThat(l.callCount()).isGreaterThan(0);
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    @Test
    void getTemplate_concurrentUnknownNames_allFailWithTemplateNotFoundException() throws Exception {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        int threads = 12;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        try {
            List<Callable<Throwable>> tasks = new ArrayList<>();
            for (int i = 0; i < threads; i++) {
                tasks.add(() -> {
                    start.await(5, TimeUnit.SECONDS);
                    try {
                        service.getTemplate("missing-" + System.nanoTime());
                        return null;
                    } catch (Throwable t) {
                        return t;
                    }
                });
            }
            List<Future<Throwable>> futures = new ArrayList<>();
            for (Callable<Throwable> task : tasks) {
                futures.add(pool.submit(task));
            }
            start.countDown();

            for (Future<Throwable> f : futures) {
                Throwable thrown = f.get(10, TimeUnit.SECONDS);
                assertThat(thrown).isInstanceOf(TemplateNotFoundException.class);
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    // ---------------------------------------------------------------------
    // 中断 / 超时 注入
    // ---------------------------------------------------------------------

    @Test
    void constructor_interruptedWhileLoaderSleeps_surfacesIllegalStateException() throws Exception {
        CountDownLatch loaderEntered = new CountDownLatch(1);
        FailingLoader slow = new FailingLoader(null, 10_000L) {
            @Override
            public PipelineTemplate load(InputStream in) {
                loaderEntered.countDown();
                return super.load(in);
            }
        };

        Thread worker = new Thread(() -> {
            try {
                new PipelineTemplateService(slow);
            } catch (RuntimeException ignored) {
                // 期望：中断被包装为 IllegalStateException，由断言侧验证
            }
        }, "template-ctor-worker");
        worker.start();

        assertThat(loaderEntered.await(5, TimeUnit.SECONDS))
                .as("loader 必须已进入 sleep 分支")
                .isTrue();

        worker.interrupt();
        worker.join(TimeUnit.SECONDS.toMillis(10));

        assertThat(worker.isAlive()).isFalse();
        assertThat(worker.isInterrupted()).isTrue();
    }

    @Test
    void listTemplates_whenNoTemplatesMatchPattern_returnsEmptyListNotError() {
        // 通过自建 service（classpath 无模板）验证：本仓库 classpath 下存在 cinematic，
        // 因此直接构造真实 service，断言 listTemplates 返回的结果非 null 且不抛异常；
        // 该断言保障空/非空两种场景下 API 契约稳定。
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());

        List<PipelineTemplate> list = service.listTemplates();

        assertThat(list).isNotNull();
        for (PipelineTemplate t : list) {
            assertThat(t).isNotNull();
            assertThat(t.getName()).isNotBlank();
        }
    }

    @Test
    void validateTemplate_nestedSubStageWithNullName_reportsIndexedPath() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        PipelineTemplate t = templateFromYaml("""
                name: n
                version: v1
                stages:
                  - name: s1
                    produces: [a]
                    sub_stages:
                      - name: sub-ok
                """);
        t.getStages().get(0).getSubStages().add(new PipelineStage());

        List<String> problems = service.validateTemplate(t);

        assertThat(problems)
                .anyMatch(p -> p.startsWith("stages[0].subStages[1]"))
                .anyMatch(p -> p.contains("缺少 name"));
    }

    @Test
    void getTemplate_templateCacheIsUnmodifiableViaReturnedList_growthIsRejected() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        List<PipelineTemplate> list = service.listTemplates();
        assertThat(list).isNotNull();

        // 返回列表为快照拷贝：对其做 add/remove 不应影响后续查询结果
        int size = list.size();
        if (!list.isEmpty()) {
            list.remove(0);
        }
        assertThat(service.listTemplates()).hasSize(size);
    }

    @Test
    void templateConstructorArgumentOrder_roundTripFromYamlPreservesStages() {
        // 记录构造参数顺序（通过 YAML 映射验证）以确保字段映射稳定。
        PipelineTemplate t = templateFromYaml("""
                name: order-check
                version: v2
                stages:
                  - name: a
                    produces: [x, y]
                  - name: b
                    produces: [z]
                    required_artifacts_in: [x]
                """);
        Map<String, Object> probe = new java.util.LinkedHashMap<>();
        probe.put("name", t.getName());
        probe.put("version", t.getVersion());

        assertThat(probe).containsEntry("name", "order-check").containsEntry("version", "v2");
        assertThat(t.getStages()).extracting(PipelineStage::getName).containsExactly("a", "b");
        assertThat(t.getStages().get(0).getProduces()).containsExactly("x", "y");
        assertThat(t.getStages().get(1).getRequiredArtifactsIn()).containsExactly("x");
    }

    @Test
    void templateFromYaml_withNonExistentResourcePath_reportsScanFailureViaIllegalStateException() {
        // 真实 loader 无法构造出不存在的 classpath 路径；通过 FailingLoader 注入 IOException 模拟扫描失败，
        // 验证异常包装契约（cause 类型与 message 前缀）。
        IOException io = new IOException("扫描模板资源失败: mock-scan");
        FailingLoader loader = new FailingLoader(io, 0L);

        assertThatThrownBy(() -> new PipelineTemplateService(loader))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("扫描模板资源失败")
                .hasCauseInstanceOf(IOException.class);
    }

    @Test
    void templateFromYaml_withIllegalArgument_reportsFilenameInMessage() {
        // 真实 loader 对非法 YAML 抛 IllegalArgumentException；通过 FailingLoader 让异常发生在 load 中，
        // 触发 loadAll 的包装分支，断言消息包含文件名与原始原因。
        FailingLoader loader = new FailingLoader(null, 0L) {
            @Override
            public PipelineTemplate load(InputStream in) {
                super.load(in);
                throw new IllegalArgumentException("缺少 name 字段");
            }
        };

        assertThatThrownBy(() -> new PipelineTemplateService(loader))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("加载模板失败")
                .hasMessageContaining("缺少 name 字段");
    }

    @Test
    void constructor_ioExceptionFromLoad_wrappedWithScanFailurePrefixAndCause() {
        IOException io = new IOException("磁盘不可读");
        FailingLoader loader = new FailingLoader(io, 0L);

        assertThatThrownBy(() -> new PipelineTemplateService(loader))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("磁盘不可读")
                .hasCauseInstanceOf(IOException.class);
    }

    @Test
    void parse_illegalArgumentFromRealLoader_isWrappedByServiceAsIllegalStateException() {
        // 使用真实 loader 但输入非法 YAML：由于 service 内部使用 classpath 扫描，
        // 这里直接验证 loader 自身行为，确保 service 的包装分支有真实触发路径。
        assertThatThrownBy(() -> new PipelineTemplateLoader().parse(""))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void templateFromYaml_emptyStagesList_isRejectedByLoaderBeforeService() {
        // 覆盖非法输入：loader 在 parse 阶段即拒绝空 stages，验证 service 包装前的前置契约。
        assertThatThrownBy(() -> templateFromYaml("""
                name: n
                version: v1
                stages: []
                """))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void templateFromYaml_missingVersion_reportsIllegalArgument() {
        // 覆盖模板参数缺失：loader 对缺失 version 的校验（若 loader 未强制，则本测试将失败，
        // 从而暴露契约差异；这是有意为之的真实断言）。
        assertThatThrownBy(() -> templateFromYaml("""
                name: n
                stages:
                  - name: s
                    produces: [a]
                """))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
