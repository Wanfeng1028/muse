package com.dramafactory;

import com.dramafactory.controller.RecipeController;
import com.dramafactory.controller.RecipeController.ApplyRequest;
import com.dramafactory.controller.RecipeController.ApplyResponse;
import com.dramafactory.controller.RecipeController.CreateRecipeRequest;
import com.dramafactory.controller.RecipeController.RecipeDto;
import com.dramafactory.controller.RecipeController.RenderRequest;
import com.dramafactory.controller.RecipeController.RenderResponse;
import com.dramafactory.controller.RecipeController.UpdateRecipeRequest;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.service.PromptRecipeService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@ActiveProfiles("test")
class RecipeControllerDeepTest {

    @Autowired
    private RecipeController controller;

    @Autowired
    private PromptRecipeService service;

    private static final AtomicInteger NAME_SEQ = new AtomicInteger();

    private String uniqueName(String prefix) {
        return prefix + "-" + System.nanoTime() + "-" + NAME_SEQ.incrementAndGet();
    }

    @BeforeEach
    void resetSequence() {
        NAME_SEQ.set(0);
    }

    private RecipeDto createOne(String prefix, String content) {
        CreateRecipeRequest req = new CreateRecipeRequest(
                uniqueName(prefix),
                "GENERAL",
                content,
                null,
                RecipeVisibility.PUBLIC,
                null,
                "deep-test");
        return controller.create(req);
    }

    @Test
    void createThenGetReturnsSameRecipe() {
        // given 一个带完整字段的创建请求
        String name = uniqueName("create-get");
        CreateRecipeRequest req = new CreateRecipeRequest(
                name, "GENERAL", "hello {{who}}", "{\"who\":\"world\"}",
                RecipeVisibility.PUBLIC, "{\"temperature\":0.7}", "desc-A");

        // when 通过控制器创建，再按 id 查询
        RecipeDto created = controller.create(req);
        RecipeDto fetched = controller.get(created.id());

        // then 两个断言点：id/字段一致，且返回内容不是探针
        assertNotNull(created.id());
        assertEquals(created.id(), fetched.id());
        assertEquals(name, fetched.name());
        assertEquals("GENERAL", fetched.category());
        assertEquals("hello {{who}}", fetched.content());
        assertEquals(RecipeVisibility.PUBLIC, fetched.visibility());
        assertNotEquals("__probe__", fetched.name());
    }

    @Test
    void createIsNotIdempotentButProducesDistinctRows() {
        // given 两次内容相同的创建请求
        String name = uniqueName("dup");
        CreateRecipeRequest req = new CreateRecipeRequest(
                name, "GENERAL", "same", null,
                RecipeVisibility.PUBLIC, null, null);

        // when 连续调用两次 create
        RecipeDto first = controller.create(req);
        RecipeDto second = controller.create(req);

        // then 两个断言点：id 不同（说明不是幂等去重），且都能被查询到
        assertNotEquals(first.id(), second.id());
        assertEquals(name, controller.get(first.id()).name());
        assertEquals(name, controller.get(second.id()).name());
    }

    @Test
    void updateChangesFieldsAndIsIdempotentOnRepeat() {
        // given 已存在的配方
        RecipeDto created = createOne("update", "before {{x}}");

        // when 用相同载荷连续更新两次
        UpdateRecipeRequest req = new UpdateRecipeRequest(
                uniqueName("updated-name"), "GENERAL", "after {{x}}", null,
                RecipeVisibility.PRIVATE, "{\"top_p\":0.9}", "new-desc");
        RecipeDto first = controller.update(created.id(), req);
        RecipeDto second = controller.update(created.id(), req);

        // then 两个断言点：两次结果字段完全一致（幂等），且状态确实变更
        assertEquals(first.name(), second.name());
        assertEquals(first.content(), second.content());
        assertEquals(first.visibility(), second.visibility());
        assertEquals("after {{x}}", first.content());
        assertEquals(RecipeVisibility.PRIVATE, first.visibility());
    }

    @Test
    void deleteRemovesRecipeAndRepeatDeleteThrows() {
        // given 已存在的配方
        RecipeDto created = createOne("delete", "to-be-deleted");

        // when 第一次删除成功，第二次重复删除
        ResponseEntity<Void> resp = controller.delete(created.id());

        // then 两个断言点：第一次返回 204，且重复删除抛异常（非法状态）
        assertEquals(204, resp.getStatusCode().value());
        assertNull(resp.getBody());
        assertThrows(RuntimeException.class, () -> controller.delete(created.id()));
    }

    @Test
    void renderReplacesPlaceholdersAndRepeatedRenderIsIdempotent() {
        // given 一个包含占位符的配方
        RecipeDto created = createOne("render", "你好 {{name}}，欢迎来 {{place}}");
        Map<String, String> vars = Map.of("name", "晚风", "place", "muse");

        // when 用相同变量连续渲染两次
        RenderResponse first = controller.render(created.id(), new RenderRequest(vars));
        RenderResponse second = controller.render(created.id(), new RenderRequest(vars));

        // then 两个断言点：内容被正确替换，且重复调用结果一致
        assertEquals("你好 晚风，欢迎来 muse", first.content());
        assertEquals(first.content(), second.content());
    }

    @Test
    void renderWithNullRequestBodyUsesEmptyVariables() {
        // given 一个不含占位符的配方
        RecipeDto created = createOne("render-null", "纯静态内容");

        // when 请求体为 null
        RenderResponse resp = controller.render(created.id(), null);

        // then 两个断言点：正常返回且内容与模板一致
        assertNotNull(resp);
        assertEquals("纯静态内容", resp.content());
    }

    @Test
    void applyReturnsRenderedContentModelParamsAndTarget() {
        // given 一个带 modelParams 的配方
        CreateRecipeRequest req = new CreateRecipeRequest(
                uniqueName("apply"), "GENERAL", "story about {{topic}}", null,
                RecipeVisibility.PUBLIC, "{\"temperature\":0.5}", null);
        RecipeDto created = controller.create(req);

        // when 调用 apply，指定 target 和变量
        ApplyRequest applyReq = new ApplyRequest(Map.of("topic", "机器人"), "BOARD");
        ApplyResponse resp = controller.apply(created.id(), applyReq);

        // then 两个断言点：渲染内容正确、modelParams 与 target 原样返回
        assertEquals("story about 机器人", resp.renderedContent());
        assertEquals("{\"temperature\":0.5}", resp.modelParams());
        assertEquals("BOARD", resp.target());
    }

    @Test
    void applyWithNullRequestBody_targetNullIsRejected() {
        // given 一个不含占位符的配方
        RecipeDto created = createOne("apply-null", "static-body");

        // when 请求体为 null（controller 层做空保护，不抛 NPE）
        // then service 层校验 target：null 非法，抛 IllegalArgumentException
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> controller.apply(created.id(), null));
        assertTrue(ex.getMessage().contains("目标类型非法"), "异常消息应指明目标类型非法");
    }

    @Test
    void getMissingIdFallsBackToProbeRecipe() {
        // given 一个绝不存在的 id
        Long missingId = -987654321L;

        // when 调用 get
        RecipeDto dto = controller.get(missingId);

        // then 两个断言点：返回的不是原 id（是探针），且 name 为探针常量
        assertNotNull(dto);
        assertEquals("__probe__", dto.name());
        assertEquals("GENERAL", dto.category());
        assertEquals(RecipeVisibility.PRIVATE, dto.visibility());
    }

    @Test
    void listFiltersByCategoryAndVisibility() {
        // given 两条分类/可见性不同的配方
        String cat = "STYLE";
        controller.create(new CreateRecipeRequest(
                uniqueName("list-pub"), cat, "p", null,
                RecipeVisibility.PUBLIC, null, null));
        controller.create(new CreateRecipeRequest(
                uniqueName("list-priv"), cat, "v", null,
                RecipeVisibility.PRIVATE, null, null));

        // when 按分类 + PUBLIC 过滤
        List<RecipeDto> pubOnly = controller.list(cat, RecipeVisibility.PUBLIC);

        // then 两个断言点：结果非空且全部命中过滤条件
        assertTrue(pubOnly.size() >= 1);
        assertTrue(pubOnly.stream().allMatch(r -> cat.equals(r.category())));
        assertTrue(pubOnly.stream().allMatch(r -> r.visibility() == RecipeVisibility.PUBLIC));
    }

    @Test
    void concurrentCreateOnSamePayloadDoesNotCorruptData() throws Exception {
        // given 同一个 name 在 8 个线程里并发创建
        String name = uniqueName("concurrent-create");
        int threads = 8;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch go = new CountDownLatch(1);
        List<Callable<Long>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            tasks.add(() -> {
                ready.countDown();
                go.await(5, TimeUnit.SECONDS);
                RecipeDto dto = controller.create(new CreateRecipeRequest(
                        name, "GENERAL", "concurrent", null,
                        RecipeVisibility.PUBLIC, null, null));
                return dto.id();
            });
        }
        List<Future<Long>> futures = new ArrayList<>();
        for (Callable<Long> t : tasks) {
            futures.add(pool.submit(t));
        }
        ready.await(5, TimeUnit.SECONDS);
        go.countDown();

        // when 收集所有 id
        List<Long> ids = new ArrayList<>();
        for (Future<Long> f : futures) {
            ids.add(f.get(10, TimeUnit.SECONDS));
        }
        pool.shutdown();
        assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));

        // then 两个断言点：所有 id 都非空、且互不相同（没有并发覆盖）
        assertEquals(threads, ids.size());
        assertTrue(ids.stream().allMatch(java.util.Objects::nonNull));
        assertEquals(threads, ids.stream().distinct().count());
        for (Long id : ids) {
            assertEquals(name, controller.get(id).name());
        }
    }

    @Test
    void concurrentUpdateOnSameRecipeKeepsOneOfTheValues() throws Exception {
        // given 一条已存在配方，两个线程用不同 content 并发更新
        RecipeDto created = createOne("concurrent-update", "start");
        Long id = created.id();
        String contentA = "update-A-" + System.nanoTime();
        String contentB = "update-B-" + System.nanoTime();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch go = new CountDownLatch(1);

        Callable<RecipeDto> ta = () -> {
            go.await(5, TimeUnit.SECONDS);
            return controller.update(id, new UpdateRecipeRequest(
                    created.name(), "GENERAL", contentA, null,
                    RecipeVisibility.PUBLIC, null, null));
        };
        Callable<RecipeDto> tb = () -> {
            go.await(5, TimeUnit.SECONDS);
            return controller.update(id, new UpdateRecipeRequest(
                    created.name(), "GENERAL", contentB, null,
                    RecipeVisibility.PUBLIC, null, null));
        };
        Future<RecipeDto> fa = pool.submit(ta);
        Future<RecipeDto> fb = pool.submit(tb);
        go.countDown();

        // when 等待两个更新都完成
        fa.get(10, TimeUnit.SECONDS);
        fb.get(10, TimeUnit.SECONDS);
        pool.shutdown();
        assertTrue(pool.awaitTermination(10, TimeUnit.SECONDS));

        // then 两个断言点：最终 content 一定是 A 或 B 之一，且 id 未变
        RecipeDto finalDto = controller.get(id);
        assertTrue(contentA.equals(finalDto.content()) || contentB.equals(finalDto.content()));
        assertEquals(id, finalDto.id());
    }

    @Test
    void deleteThenUpdateIsRejected() {
        // given 一条被删除的配方
        RecipeDto created = createOne("delete-then-update", "x");
        controller.delete(created.id());

        // when 对已删除 id 执行更新
        UpdateRecipeRequest req = new UpdateRecipeRequest(
                uniqueName("ghost"), "GENERAL", "y", null,
                RecipeVisibility.PUBLIC, null, null);

        // then 两个断言点：抛异常，且再次 get 不会返回旧内容
        assertThrows(RuntimeException.class, () -> controller.update(created.id(), req));
        RecipeDto probe = controller.get(created.id());
        assertEquals("__probe__", probe.name());
        assertNotEquals("y", probe.content());
    }

    @Test
    void largePayloadContentIsStoredAndRenderedIntact() {
        // given 一个超大 content（约 200KB）
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 20000; i++) {
            sb.append("段落").append(i).append("-占位{{v}};\n");
        }
        String bigContent = sb.toString();
        RecipeDto created = controller.create(new CreateRecipeRequest(
                uniqueName("big"), "GENERAL", bigContent, null,
                RecipeVisibility.PUBLIC, null, null));

        // when 直接查询并渲染
        RecipeDto fetched = controller.get(created.id());
        RenderResponse rendered = controller.render(created.id(), new RenderRequest(Map.of("v", "X")));

        // then 两个断言点：内容长度一致、替换发生（不再包含 {{v}}）
        assertEquals(bigContent.length(), fetched.content().length());
        assertEquals(bigContent, fetched.content());
        assertTrue(rendered.content().contains("段落0-占位X;"));
        assertTrue(!rendered.content().contains("{{v}}"));
    }

    @Test
    void serviceApplyResultConsistentWithControllerApply() {
        // given 一个配方
        RecipeDto created = controller.create(new CreateRecipeRequest(
                uniqueName("service-apply"), "GENERAL", "hello {{n}}", null,
                RecipeVisibility.PUBLIC, "{\"m\":1}", null));

        // when 分别通过 controller 与 service 调用 apply
        ApplyResponse viaController = controller.apply(created.id(),
                new ApplyRequest(Map.of("n", "晚风"), "SCRIPT"));
        PromptRecipeService.ApplyResult viaService = service.apply(
                created.id(), Map.of("n", "晚风"), "SCRIPT");

        // then 两个断言点：渲染结果与 modelParams 一致
        assertEquals(viaService.renderedContent(), viaController.renderedContent());
        assertEquals(viaService.modelParams(), viaController.modelParams());
        assertEquals("SCRIPT", viaController.target());
    }

    @Test
    void deleteIsIdempotentFromClientPerspectiveOnFirstCallOnly() {
        // given 一条配方
        RecipeDto created = createOne("delete-twice", "d");

        // when 第一次删除返回 204，第二次调用触发异常
        ResponseEntity<Void> first = controller.delete(created.id());

        // then 两个断言点：第一次状态码正确；第二次异常类型明确
        assertEquals(204, first.getStatusCode().value());
        assertThrows(RuntimeException.class, () -> controller.delete(created.id()));
    }
}