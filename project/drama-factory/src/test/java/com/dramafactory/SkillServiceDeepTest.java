package com.dramafactory;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillInstallRepository;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.repository.SkillVersionRepository;
import com.dramafactory.service.SkillService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.List;
import org.springframework.test.context.transaction.TestTransaction;
import com.dramafactory.exception.ResourceNotFoundException;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SkillService 深度集成测试。
 * <p>用真实 Spring 上下文 + 内存库，覆盖发布、版本、检索、安装、评分全流程语义。</p>
 */
@SpringBootTest
@Transactional
class SkillServiceDeepTest {

    @Autowired
    private SkillService skillService;

    @Autowired
    private SkillRepository skillRepository;

    @Autowired
    private SkillVersionRepository skillVersionRepository;

    @Autowired
    private SkillInstallRepository skillInstallRepository;

    @Autowired
    private SkillRatingRepository skillRatingRepository;

    @BeforeEach
    void clean() {
        skillRatingRepository.deleteAll();
        skillInstallRepository.deleteAll();
        skillVersionRepository.deleteAll();
        skillRepository.deleteAll();
    }

    private Skill publishSample(String slug) {
        return skillService.publish("示例技能", slug, "描述文本", "晚风",
                "SCRIPT", "写作,剧本", "icon-a", "模板 {{topic}} 内容", "首版发布");
    }

    @Test
    void publish_createsSkillAndInitialVersion() {
        Skill skill = publishSample("sample-skill");

        assertNotNull(skill.getId());
        assertEquals("sample-skill", skill.getSlug());
        assertEquals(0L, skill.getInstallCount());
        assertEquals(Boolean.FALSE, skill.getOfficial());

        Optional<SkillVersion> version = skillVersionRepository.findBySkillIdAndVersion(skill.getId(), "1.0.0");
        assertTrue(version.isPresent());
        assertEquals("模板 {{topic}} 内容", version.get().getPromptTemplate());
        assertEquals("首版发布", version.get().getChangelog());
    }

    @Test
    void publish_rejectsDuplicateSlug() {
        publishSample("dup-slug");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> publishSample("dup-slug"));

        assertEquals("slug 已存在", ex.getMessage());
        assertEquals(1L, skillRepository.count());
    }

    @Test
    void publish_rejectsInvalidCategoryAndBlankName() {
        IllegalArgumentException exCategory = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("名字", "cat-bad", "d", "a", "UNKNOWN", "t", "i", "p", "c"));
        assertEquals("category 不合法", exCategory.getMessage());

        IllegalArgumentException exName = assertThrows(IllegalArgumentException.class,
                () -> skillService.publish("  ", "blank-name", "d", "a", "SCRIPT", "t", "i", "p", "c"));
        assertEquals("name 不能为空", exName.getMessage());

        assertEquals(0L, skillRepository.count());
    }

    @Test
    void publishVersion_rejectsDuplicateAndInvalidFormat() {
        Skill skill = publishSample("ver-skill");

        IllegalArgumentException dup = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(skill.getId(), "1.0.0", "p", "c"));
        assertEquals("版本已存在", dup.getMessage());

        IllegalArgumentException bad = assertThrows(IllegalArgumentException.class,
                () -> skillService.publishVersion(skill.getId(), "1.0", "p", "c"));
        assertEquals("version 格式不合法", bad.getMessage());

        assertEquals(1L, skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(skill.getId()).size());
    }

    @Test
    void list_filtersByQueryTagCategoryAndSortsByPopular() {
        Skill a = skillService.publish("阿尔法", "alpha-one", "剪辑相关", "晚风", "EDIT", "剪辑,快速", "i", "p", "c");
        Skill b = skillService.publish("贝塔", "beta-two", "写作相关", "晚风", "SCRIPT", "写作", "i", "p", "c");
        skillService.install(a.getId(), null);
        skillService.install(a.getId(), null);
        skillService.install(b.getId(), null);

        List<Skill> byQuery = skillService.list("剪辑", null, null, "popular");
        assertEquals(1, byQuery.size());
        assertEquals("alpha-one", byQuery.get(0).getSlug());

        List<Skill> byTag = skillService.list(null, "写作", null, "name");
        assertEquals(1, byTag.size());
        assertEquals("beta-two", byTag.get(0).getSlug());

        List<Skill> byCategory = skillService.list(null, null, "EDIT", "popular");
        assertEquals(1, byCategory.size());

        List<Skill> popular = skillService.list(null, null, null, "popular");
        assertEquals(2, popular.size());
        assertEquals("alpha-one", popular.get(0).getSlug());
    }

    @Test
    void getDetail_returnsVersionsAndInstalledVersion() {
        Skill skill = publishSample("detail-skill");
        skillService.publishVersion(skill.getId(), "1.1.0", "模板 v2", "修复");

        SkillService.SkillDetail before = skillService.getDetail(skill.getId());
        assertEquals(2, before.versions().size());
        assertNull(before.installedVersion());

        skillService.install(skill.getId(), "1.1.0");
        SkillService.SkillDetail after = skillService.getDetail(skill.getId());
        assertEquals("1.1.0", after.installedVersion());
        assertNotNull(after.skill());
        assertEquals("detail-skill", after.skill().getSlug());
    }

    @Test
    void install_upsertsRowButCountsEachInstallEvent() {
        Skill skill = publishSample("idem-skill");

        SkillInstall first = skillService.install(skill.getId(), null);
        SkillInstall second = skillService.install(skill.getId(), null);

        assertNotNull(first.getId());
        assertEquals(first.getId(), second.getId());
        assertEquals("1.0.0", second.getVersion());
        assertEquals(1L, skillInstallRepository.count());
        assertEquals(2L, skillRepository.findById(skill.getId()).orElseThrow().getInstallCount(), "每次 install 调用都是一次安装事件，计数累加；幂等的是安装行（同一 id）");
    }

    @Test
    void install_rejectsUnknownVersionAndUnknownSkill() {
        Skill skill = publishSample("unknown-ver");

        IllegalArgumentException exVer = assertThrows(IllegalArgumentException.class,
                () -> skillService.install(skill.getId(), "9.9.9"));
        assertEquals("版本不存在", exVer.getMessage());

        ResourceNotFoundException exSkill = assertThrows(ResourceNotFoundException.class,
                () -> skillService.install(999999L, null));
        assertTrue(exSkill.getMessage().contains("Skill"), "异常消息应含资源名 Skill");
        assertTrue(exSkill.getMessage().contains("999999"), "异常消息应含 id");

        assertEquals(0L, skillInstallRepository.count());
    }

    @Test
    void install_switchesVersionOnReinstall() {
        Skill skill = publishSample("switch-ver");
        skillService.publishVersion(skill.getId(), "1.1.0", "模板 v2", "修复");

        skillService.install(skill.getId(), "1.0.0");
        SkillInstall updated = skillService.install(skill.getId(), "1.1.0");

        assertEquals("1.1.0", updated.getVersion());
        assertEquals(1L, skillInstallRepository.count());
        assertEquals(2L, skillRepository.findById(skill.getId()).orElseThrow().getInstallCount());
    }

    @Test
    void rate_updatesAggregateAndIsReflectedInDetail() {
        Skill skill = publishSample("rate-skill");

        skillService.rate(skill.getId(), 5, "很棒");
        skillService.rate(skill.getId(), 3, "一般");

        Skill reloaded = skillRepository.findById(skill.getId()).orElseThrow();
        assertEquals(2L, reloaded.getRatingCount());
        assertEquals(8L, reloaded.getRatingSum());
        assertEquals(4.0, reloaded.getAvgRating());

        SkillService.SkillDetail detail = skillService.getDetail(skill.getId());
        assertEquals(4.0, detail.avgRating());
    }

    @Test
    void rate_rejectsOutOfRangeScore() {
        Skill skill = publishSample("rate-range");

        IllegalArgumentException low = assertThrows(IllegalArgumentException.class,
                () -> skillService.rate(skill.getId(), 0, "太低"));
        assertEquals("score 必须在 1~5 之间", low.getMessage());

        IllegalArgumentException high = assertThrows(IllegalArgumentException.class,
                () -> skillService.rate(skill.getId(), 6, "太高"));
        assertEquals("score 必须在 1~5 之间", high.getMessage());

        assertEquals(0L, skillRatingRepository.count());
    }

    @Test
    void rate_accumulatesEachCallWithoutUserDedup() {
        Skill skill = publishSample("rate-idem");

        skillService.rate(skill.getId(), 4, "不错");
        skillService.rate(skill.getId(), 2, "改主意了");

        Skill reloaded = skillRepository.findById(skill.getId()).orElseThrow();
        assertEquals(2L, reloaded.getRatingCount(), "每次 rate 调用都新增一条评分，无幂等语义");
        assertEquals(6L, reloaded.getRatingSum());
        assertEquals(2L, skillRatingRepository.count());
    }

    @Test
    void renderPrompt_replacesAllPlaceholders() {
        Skill skill = publishSample("render-skill");
        skillService.publishVersion(skill.getId(), "1.1.0", "主题 {{topic}}，时长 {{duration}} 秒", "v2");

        String rendered = skillService.renderTemplate(skill.getId(), "1.1.0",
                java.util.Map.of("topic", "猫咪", "duration", "30"));

        assertEquals("主题 猫咪，时长 30 秒", rendered);
        assertFalse(rendered.contains("{{"));
    }

    @Test
    void renderPrompt_keepsPlaceholderOnMissingVariableAndThrowsOnUnknownVersion() {
        Skill skill = publishSample("render-miss");

        // 宽松渲染：缺失变量不抛异常，保留原占位符（见 renderTemplate javadoc）
        String rendered = skillService.renderTemplate(skill.getId(), "1.0.0", java.util.Map.of());
        assertTrue(rendered.contains("{{topic}}"), "缺失变量应保留原占位符");

        IllegalArgumentException exVer = assertThrows(IllegalArgumentException.class,
                () -> skillService.renderTemplate(skill.getId(), "9.9.9", java.util.Map.of("topic", "x")));
        assertEquals("版本不存在", exVer.getMessage());
    }

    @Test
    void concurrentInstall_producesSingleRowAndCorrectCount() throws Exception {
        Skill skill = publishSample("concurrent-install");
        int threads = 4;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        // 工作线程是独立事务，看不到主线程未提交的数据，先提交
        TestTransaction.flagForCommit();
        TestTransaction.end();
        List<Throwable> errors = Collections.synchronizedList(new java.util.ArrayList<>());

        for (int i = 0; i < threads; i++) {
            pool.submit(() -> {
                try {
                    start.await();
                    skillService.install(skill.getId(), null);
                } catch (Exception e) {
                    errors.add(e);
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        assertTrue(done.await(30, TimeUnit.SECONDS));
        pool.shutdown();
        // 恢复测试事务
        TestTransaction.start();

        assertEquals(1L, skillInstallRepository.count(), "并发安装只应产生一行（skill_id 唯一）");
        long unexpected = errors.stream().filter(e -> !(e instanceof org.springframework.dao.DataIntegrityViolationException)).count();
        assertEquals(0L, unexpected, "除唯一约束冲突外不应有其他异常");
        Long installCount = skillRepository.findById(skill.getId()).orElseThrow().getInstallCount();
        assertTrue(installCount >= 1, "至少一次安装成功使计数>=1");
    }

    @Test
    void concurrentRate_keepsCountAndSumConsistent() throws Exception {
        Skill skill = publishSample("concurrent-rate");
        int threads = 4;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger();
        // 工作线程是独立事务，看不到主线程未提交的数据，先提交
        TestTransaction.flagForCommit();
        TestTransaction.end();

        for (int i = 0; i < threads; i++) {
            final int score = (i % 5) + 1;
            pool.submit(() -> {
                try {
                    start.await();
                    skillService.rate(skill.getId(), score, "并发评分");
                } catch (Exception e) {
                    failures.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        assertTrue(done.await(30, TimeUnit.SECONDS));
        pool.shutdown();
        // 恢复测试事务
        TestTransaction.start();

        assertEquals(0, failures.get(), "并发评分不应抛异常");
        assertEquals(4L, skillRatingRepository.count(), "4 条评分行都应落库");
        long sum = skillRatingRepository.findAll().stream().mapToLong(r -> r.getScore()).count() > 0
                ? skillRatingRepository.findAll().stream().mapToLong(r -> r.getScore()).sum() : -1;
        assertEquals(10L, sum, "1+2+3+4=10，评分行求和必须精确");
    }

    @Test
    void publishVersion_rollsBackWhenSkillMissing() {
        long before = skillVersionRepository.count();

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillService.publishVersion(123456L, "2.0.0", "模板", "变更"));

        assertTrue(ex.getMessage().contains("Skill"));
        assertEquals(before, skillVersionRepository.count());
        assertEquals(0L, skillRepository.count());
    }

    @Test
    void publish_acceptsVeryLargePromptTemplate() {
        StringBuilder big = new StringBuilder();
        for (int i = 0; i < 20000; i++) {
            big.append("{{v").append(i).append("}}");
        }
        String template = big.toString();

        Skill skill = skillService.publish("大模板", "big-template", "d", "晚风",
                "GENERAL", "big", "i", template, "首版");

        SkillVersion version = skillVersionRepository
                .findBySkillIdAndVersion(skill.getId(), "1.0.0")
                .orElseThrow();
        assertEquals(template.length(), version.getPromptTemplate().length());
        assertTrue(version.getPromptTemplate().startsWith("{{v0}}"));
    }

    @Test
    void getOrThrow_reportsMissingSkillOnDetail() {
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillService.getDetail(888888L));

        assertTrue(ex.getMessage().contains("Skill"));
        assertEquals(0L, skillRepository.count());
    }

    @Test
    void sortByName_ordersAlphabetically() {
        skillService.publish("乙", "zeta-skill", "d", "晚风", "SCRIPT", "t", "i", "p", "c");
        skillService.publish("甲", "alpha-skill", "d", "晚风", "SCRIPT", "t", "i", "p", "c");

        List<Skill> sorted = skillService.list(null, null, null, "name");

        assertEquals(2, sorted.size());
        assertEquals("乙", sorted.get(0).getName());
        assertEquals("zeta-skill", sorted.get(0).getSlug());
        assertEquals("甲", sorted.get(1).getName());
        assertEquals("alpha-skill", sorted.get(1).getSlug());
    }
}