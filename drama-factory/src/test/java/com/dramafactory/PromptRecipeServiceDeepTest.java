package com.dramafactory;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.repository.PromptRecipeRepository;
import com.dramafactory.service.PromptRecipeService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import jakarta.persistence.EntityManager;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.test.context.transaction.TestTransaction;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * PromptRecipeService 深度集成测试。
 * 覆盖 Run 全生命周期语义：状态机流转、幂等性、失败注入、并发、边界。
 */
@SpringBootTest
@ActiveProfiles("test")
@Transactional
class PromptRecipeServiceDeepTest {

    @Autowired
    private PromptRecipeService service;

    @Autowired
    private PromptRecipeRepository repository;

    @Autowired
    private EntityManager entityManager;

    private PromptRecipe baseRecipe;

    @BeforeEach
    void setUp() {
        repository.deleteAll();
        baseRecipe = service.create(
                "分镜基础模板",
                "BOARD",
                "镜头：{{shot}}，风格：{{style}}",
                "shot,style",
                RecipeVisibility.PUBLIC,
                "{\"temperature\":0.7}",
                "用于分镜的基础模板");
    }

    // ---------------------------------------------------------------------
    // 1. 状态机：apply 合法流转，usageCount 递增
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldIncrementUsageCount_whenTargetIsBoard() {
        // given: 初始 usageCount 为 0
        long before = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        Map<String, String> vars = new HashMap<>();
        vars.put("shot", "开场航拍");
        vars.put("style", "写实");

        // when: 执行一次 apply
        PromptRecipeService.ApplyResult result = service.apply(baseRecipe.getId(), vars, "BOARD");

        // then: 返回渲染文本 + target 正确，usageCount +1
        assertNotNull(result);
        assertEquals("镜头：开场航拍，风格：写实", result.renderedContent());
        assertEquals("BOARD", result.target());
        entityManager.clear();
        long after = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        assertEquals(before + 1, after);
    }

    // ---------------------------------------------------------------------
    // 2. 状态机：非法 target 拒绝，且不改变 usageCount
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldReject_whenTargetIsInvalid_andNotChangeUsageCount() {
        // given: 初始 usageCount 已知
        long before = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        Map<String, String> vars = Map.of("shot", "a", "style", "b");

        // when / then: 非法 target 抛异常，usageCount 不变
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.apply(baseRecipe.getId(), vars, "UNKNOWN"));
        assertTrue(ex.getMessage().contains("SCRIPT 或 BOARD"));
        long after = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        assertEquals(before, after);
    }

    // ---------------------------------------------------------------------
    // 3. 状态机：target 为 null 拒绝
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldReject_whenTargetIsNull() {
        // given
        Map<String, String> vars = Map.of("shot", "a", "style", "b");

        // when / then
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.apply(baseRecipe.getId(), vars, null));
        assertTrue(ex.getMessage().contains("目标类型非法"));
        assertTrue(ex.getMessage().contains("null"));
    }

    // ---------------------------------------------------------------------
    // 4. 幂等性：重复调用同一 apply，内容一致，usageCount 线性递增
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldBeIdempotentInContent_whenCalledTwice() {
        // given
        Map<String, String> vars = Map.of("shot", "特写", "style", "水墨");
        long before = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();

        // when: 连续两次 apply
        PromptRecipeService.ApplyResult first = service.apply(baseRecipe.getId(), vars, "SCRIPT");
        PromptRecipeService.ApplyResult second = service.apply(baseRecipe.getId(), vars, "SCRIPT");

        // then: 渲染内容一致（幂等），usageCount 精确 +2
        assertEquals(first.renderedContent(), second.renderedContent());
        assertEquals("SCRIPT", first.target());
        assertEquals("SCRIPT", second.target());
        entityManager.clear();
        long after = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        assertEquals(before + 2, after);
    }

    // ---------------------------------------------------------------------
    // 5. 幂等性：render 不改变 usageCount
    // ---------------------------------------------------------------------
    @Test
    void render_shouldNotChangeUsageCount() {
        // given
        long before = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        Map<String, String> vars = Map.of("shot", "远景", "style", "国风");

        // when
        String rendered = service.render(baseRecipe.getId(), vars);

        // then
        assertEquals("镜头：远景，风格：国风", rendered);
        long after = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        assertEquals(before, after);
    }

    // ---------------------------------------------------------------------
    // 6. 失败注入：render 缺少变量时抛异常，且 usageCount 不变
    // ---------------------------------------------------------------------
    @Test
    void render_shouldThrow_whenVariableMissing_andNotMutateState() {
        // given
        long before = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        Map<String, String> partial = Map.of("shot", "近景");

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.render(baseRecipe.getId(), partial));

        // then
        assertTrue(ex.getMessage().contains("缺少变量"));
        assertTrue(ex.getMessage().contains("style"));
        long after = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        assertEquals(before, after);
    }

    // ---------------------------------------------------------------------
    // 7. 失败注入：apply 缺少变量时抛异常，回滚 usageCount
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldRollbackUsageCount_whenVariableMissing() {
        // given
        long before = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.apply(baseRecipe.getId(), Map.of("shot", "中景"), "BOARD"));

        // then
        assertTrue(ex.getMessage().contains("缺少变量"));
        long after = repository.findById(baseRecipe.getId()).orElseThrow().getUsageCount();
        assertEquals(before, after);
    }

    // ---------------------------------------------------------------------
    // 8. 失败注入：apply 不存在的 id 抛 ResourceNotFoundException
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldThrow_whenRecipeNotFound() {
        // given
        // setUp 里已 service.create 一个 baseRecipe，本类 @Transactional，故 count() 初始为 1
        long before = repository.count();
        Long missingId = 999999L;

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> service.apply(missingId, Map.of("shot", "a", "style", "b"), "BOARD"));
        assertTrue(ex.getMessage().contains("PromptRecipe"));
        assertEquals(before, repository.count(), "apply 失败不应新增记录");
    }

    // ---------------------------------------------------------------------
    // 9. 并发：两线程同时 apply 同一 Run，usageCount 精确 +2 且不丢更新
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldHandleConcurrentCalls_whenTwoThreadsRace() throws Exception {
        // 并发线程是独立事务，看不到主线程未提交的数据；
        // 先把 setUp 所在事务提交，让 baseRecipe 对工作线程可见
        TestTransaction.flagForCommit();
        TestTransaction.end();

        // given
        Long id = baseRecipe.getId();
        long before = repository.findById(id).orElseThrow().getUsageCount();
        Map<String, String> vars = Map.of("shot", "并行", "style", "同步");
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        CountDownLatch doneGate = new CountDownLatch(threads);
        List<String> rendered = new ArrayList<>();
        AtomicInteger errors = new AtomicInteger();

        // when: 两线程同时推进
        for (int i = 0; i < threads; i++) {
            pool.submit(() -> {
                try {
                    startGate.await();
                    PromptRecipeService.ApplyResult r = service.apply(id, vars, "BOARD");
                    synchronized (rendered) {
                        rendered.add(r.renderedContent());
                    }
                } catch (Exception e) {
                    errors.incrementAndGet();
                } finally {
                    doneGate.countDown();
                }
            });
        }
        startGate.countDown();
        boolean finished = doneGate.await(20, TimeUnit.SECONDS);
        pool.shutdownNow();

        // then: 两线程都成功，usageCount 精确 +2，渲染内容一致
        assertTrue(finished, "并发任务应在 20 秒内完成");
        assertEquals(0, errors.get(), "并发执行不应出现异常");
        assertEquals(threads, rendered.size());
        assertEquals("镜头：并行，风格：同步", rendered.get(0));
        assertEquals("镜头：并行，风格：同步", rendered.get(1));
        long after = repository.findById(id).orElseThrow().getUsageCount();
        assertEquals(before + 2, after, "并发下 usageCount 必须精确 +2，不能丢更新");

        TestTransaction.start(); // 恢复事务，供框架回滚
    }

    // ---------------------------------------------------------------------
    // 10. 边界：空模板内容（无占位符）apply 也应成功
    // ---------------------------------------------------------------------
    @Test
    void apply_shouldWork_whenTemplateHasNoPlaceholders() {
        // given
        PromptRecipe plain = service.create(
                "纯文本模板",
                "GENERAL",
                "这是一段没有变量的固定文案。",
                null,
                RecipeVisibility.PRIVATE,
                null,
                null);

        // when
        PromptRecipeService.ApplyResult result = service.apply(plain.getId(), null, "SCRIPT");

        // then
        assertEquals("这是一段没有变量的固定文案。", result.renderedContent());
        assertNull(result.modelParams());
        assertEquals("SCRIPT", result.target());
    }

    // ---------------------------------------------------------------------
    // 11. 边界：超大 payload 渲染不丢失、不截断
    // ---------------------------------------------------------------------
    @Test
    void render_shouldHandleLargePayload_withoutTruncation() {
        // given: 10 万字符变量值
        StringBuilder big = new StringBuilder();
        for (int i = 0; i < 100000; i++) {
            big.append('X');
        }
        String bigValue = big.toString();
        Map<String, String> vars = new HashMap<>();
        vars.put("shot", bigValue);
        vars.put("style", "极简");

        // when
        String rendered = service.render(baseRecipe.getId(), vars);

        // then: 大 payload 完整保留
        assertNotNull(rendered);
        assertTrue(rendered.contains(bigValue), "超大变量值必须完整保留");
        assertEquals("镜头：" + bigValue + "，风格：极简", rendered);
        assertTrue(rendered.length() > 100000);
    }

    // ---------------------------------------------------------------------
    // 12. 边界：非法状态跳转 —— 更新不存在的 id 抛异常，仓库不被污染
    // ---------------------------------------------------------------------
    @Test
    void update_shouldThrow_whenRecipeNotFound_andNotCreateNewRow() {
        // given
        long before = repository.count();

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> service.update(424242L, "新名", "SCRIPT", "内容", null,
                        RecipeVisibility.PUBLIC, null, null));
        assertTrue(ex.getMessage().contains("PromptRecipe"));
        assertEquals(before, repository.count(), "失败更新不应新增记录");
    }

    // ---------------------------------------------------------------------
    // 13. 边界：create 空名称被拒，且不落库
    // ---------------------------------------------------------------------
    @Test
    void create_shouldRejectBlankName_andNotPersist() {
        // given
        long before = repository.count();

        // when / then
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.create("   ", "SCRIPT", "内容", null,
                        RecipeVisibility.PUBLIC, null, null));
        assertTrue(ex.getMessage().contains("配方名称不能为空"));
        assertEquals(before, repository.count(), "非法创建不应落库");
    }

    // ---------------------------------------------------------------------
    // 14. 边界：非法分类被拒，且不落库
    // ---------------------------------------------------------------------
    @Test
    void create_shouldRejectInvalidCategory_andNotPersist() {
        // given
        long before = repository.count();

        // when / then
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.create("名字", "UNKNOWN", "内容", null,
                        RecipeVisibility.PUBLIC, null, null));
        assertTrue(ex.getMessage().contains("分类非法"));
        assertEquals(before, repository.count());
    }

    // ---------------------------------------------------------------------
    // 15. 幂等性：delete 二次调用第二次抛 ResourceNotFoundException
    // ---------------------------------------------------------------------
    @Test
    void delete_shouldBeIdempotentOnlyOnce_thenThrowOnSecondCall() {
        // given
        Long id = baseRecipe.getId();
        long before = repository.count();

        // when: 第一次删除
        service.delete(id);

        // then: 记录被删除，第二次删除抛异常
        assertEquals(before - 1, repository.count());
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> service.delete(id));
        assertTrue(ex.getMessage().contains("PromptRecipe"));
        assertEquals(before - 1, repository.count());
    }

    // ---------------------------------------------------------------------
    // 16. 状态机：list 按 usageCount 倒序，apply 后排序变化可观测
    // ---------------------------------------------------------------------
    @Test
    void list_shouldOrderByUsageCountDesc_afterApply() {
        // given: 再创建一个初始 usageCount 相同的配方
        PromptRecipe other = service.create(
                "另一模板",
                "BOARD",
                "A：{{shot}}",
                "shot",
                RecipeVisibility.PUBLIC,
                null,
                null);
        Map<String, String> vars = Map.of("shot", "x", "style", "y");

        // when: 给 baseRecipe 连续 apply 两次，使 usageCount 反超
        service.apply(baseRecipe.getId(), vars, "BOARD");
        service.apply(baseRecipe.getId(), vars, "BOARD");
        List<PromptRecipe> ordered = service.list("BOARD", null);

        // then: baseRecipe 排第一，other 排第二
        assertTrue(ordered.size() >= 2);
        assertEquals(baseRecipe.getId(), ordered.get(0).getId());
        assertEquals(other.getId(), ordered.get(1).getId());
        assertNotEquals(ordered.get(0).getId(), ordered.get(1).getId());
    }
}