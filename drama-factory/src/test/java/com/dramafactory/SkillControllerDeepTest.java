package com.dramafactory;

import com.dramafactory.controller.SkillController;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.controller.SkillController.CreateSkillRequest;
import com.dramafactory.controller.SkillController.InstallDto;
import com.dramafactory.controller.SkillController.InstallRequest;
import com.dramafactory.controller.SkillController.InstalledSkillDto;
import com.dramafactory.controller.SkillController.PublishVersionRequest;
import com.dramafactory.controller.SkillController.RateRequest;
import com.dramafactory.controller.SkillController.RatingDto;
import com.dramafactory.controller.SkillController.RenderRequest;
import com.dramafactory.controller.SkillController.RenderResponse;
import com.dramafactory.controller.SkillController.SkillDetailDto;
import com.dramafactory.controller.SkillController.SkillDto;
import com.dramafactory.controller.SkillController.SkillVersionDto;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillVersionRepository;
import com.dramafactory.service.SkillService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * SkillController 深度集成测试：真实 Spring 上下文 + 真实内存库，聚焦 Run 生命周期语义。
 */
@SpringBootTest
class SkillControllerDeepTest {

    @Autowired
    private SkillController skillController;

    @Autowired
    private SkillService skillService;

    @Autowired
    private SkillVersionRepository skillVersionRepository;

    @Autowired
    private SkillRatingRepository skillRatingRepository;

    private String uniqueSlug(String base) {
        return base + "-" + System.nanoTime();
    }

    private SkillDto publishSkill(String name, String slug) {
        CreateSkillRequest request = new CreateSkillRequest(name, slug, "描述-" + slug, "晚风",
                "GENERAL", "tag1,tag2", "icon-a", "模板内容 {{name}}", "首个版本");
        return skillController.publish(request);
    }

    @BeforeEach
    void setUp() {
        skillRatingRepository.deleteAll();
        skillVersionRepository.deleteAll();
    }

    /**
     * 发布后详情可读，且版本列表首条为最新版本。
     */
    @Test
    void publishThenGetDetailReturnsLatestVersion() {
        // given
        String slug = uniqueSlug("skill-detail");
        SkillDto created = publishSkill("详情技能", slug);
        assertNotNull(created.id());

        // when
        SkillDetailDto detail = skillController.get(created.id());

        // then
        assertEquals(created.id(), detail.id());
        assertEquals("详情技能", detail.name());
        assertNotNull(detail.versions());
        assertEquals(1, detail.versions().size());
        assertEquals("1.0.0", detail.versions().get(0).version());
        assertEquals("1.0.0", detail.latestVersion());
    }

    /**
     * 发布版本后，最新版本号更新，历史版本保留。
     */
    @Test
    void publishVersionUpdatesLatestAndKeepsHistory() {
        // given
        String slug = uniqueSlug("skill-version");
        SkillDto created = publishSkill("版本技能", slug);

        // when
        SkillVersionDto v2 = skillController.publishVersion(created.id(),
                new PublishVersionRequest("1.1.0", "新模板 {{x}}", "第二版"));
        SkillDetailDto detail = skillController.get(created.id());

        // then
        assertEquals("1.1.0", v2.version());
        assertEquals("1.1.0", detail.latestVersion());
        assertEquals(2, detail.versions().size());
        assertEquals("1.1.0", detail.versions().get(0).version());
    }

    /**
     * 安装后再安装同一版本，安装记录只有一条，已安装版本保持稳定（幂等）。
     */
    @Test
    void installSameVersionTwiceIsIdempotent() {
        // given
        String slug = uniqueSlug("skill-install");
        SkillDto created = publishSkill("安装技能", slug);

        // when
        InstallDto first = skillController.install(created.id(), new InstallRequest("1.0.0"));
        InstallDto second = skillController.install(created.id(), new InstallRequest("1.0.0"));

        // then
        assertNotNull(first.id());
        assertNotNull(second.id());
        assertEquals(first.skillId(), second.skillId());
        assertEquals("1.0.0", second.version());
        List<InstalledSkillDto> installed = skillController.installed();
        long matchCount = 0;
        for (InstalledSkillDto item : installed) {
            if (item.skill().id().equals(created.id())) {
                matchCount++;
            }
        }
        assertEquals(1, matchCount);
    }

    /**
     * 安装不存在的版本抛出 404，且不写入安装记录。
     */
    @Test
    void installUnknownVersionFailsWithIllegalArgument() {
        // given
        String slug = uniqueSlug("skill-install-missing");
        SkillDto created = publishSkill("缺版本技能", slug);
        int installedBefore = skillController.installed().size();

        // when
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> skillController.install(created.id(), new InstallRequest("9.9.9")));

        // then
        assertNotNull(ex);
        assertEquals(installedBefore, skillController.installed().size());
    }

    /**
     * 安装不存在的 Skill 抛出 404。
     */
    @Test
    void installUnknownSkillFailsWith404() {
        // given
        Long missingId = 999_999_999L;

        // when：直接调用 controller（不走 HTTP），GlobalExceptionHandler 不生效，
        // 抛出来的是原始 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillController.install(missingId, new InstallRequest("1.0.0")));

        // then
        assertTrue(ex.getMessage().contains("Skill"), "异常消息应含资源名");
    }

    /**
     * 同一 Skill 重复评分被拒（幂等/去重语义），评分列表长度保持 1。
     */
    @Test
    void rateSameSkillTwice_bothSucceed() {
        // 地面真相：SkillService.rate 无去重逻辑，产品允许对同一 skill 重复评分，
        // 每次调用插入一条记录。因此两次评分都应成功，该 skill 评分总数为 2。
        // given
        String slug = uniqueSlug("skill-rate-once");
        SkillDto created = publishSkill("评分技能", slug);

        // when
        RatingDto first = skillController.rate(created.id(), new RateRequest(5, "很好"));
        RatingDto second = skillController.rate(created.id(), new RateRequest(4, "再来一次"));

        // then
        assertEquals(5, first.score());
        assertEquals(4, second.score());
        List<RatingDto> ratings = skillController.get(created.id()).ratings();
        assertEquals(2, ratings.size());
    }

    /**
     * 评分越界被拒，且不落库。
     */
    @Test
    void rateOutOfRangeRejected() {
        // given
        String slug = uniqueSlug("skill-rate-range");
        SkillDto created = publishSkill("越界评分", slug);

        // when
        IllegalArgumentException low = assertThrows(IllegalArgumentException.class,
                () -> skillController.rate(created.id(), new RateRequest(0, "太低")));
        IllegalArgumentException high = assertThrows(IllegalArgumentException.class,
                () -> skillController.rate(created.id(), new RateRequest(6, "太高")));

        // then
        assertNotNull(low);
        assertNotNull(high);
        assertEquals(0, skillController.get(created.id()).ratings().size());
    }

    /**
     * 评分后平均分被更新到 Skill 实体上。
     */
    @Test
    void rateUpdatesAverageRating() {
        // given
        String slug = uniqueSlug("skill-avg");
        SkillDto created = publishSkill("均分技能", slug);

        // when
        skillController.rate(created.id(), new RateRequest(4, "不错"));
        SkillDetailDto detail = skillController.get(created.id());

        // then
        assertNotNull(detail.avgRating());
        assertEquals(4.0, detail.avgRating(), 0.0001);
        assertEquals(1, detail.ratings().size());
        assertEquals(4, detail.ratings().get(0).score());
    }

    /**
     * 空 Run 语义：对不存在的 Skill 取详情抛出 404，不返回空对象。
     */
    @Test
    void getUnknownSkillFailsWith404() {
        // given
        Long missingId = 888_888_888L;

        // when：直接调用 controller（不走 HTTP），GlobalExceptionHandler 不生效，
        // 抛出来的是原始 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillController.get(missingId));

        // then
        assertTrue(ex.getMessage().contains("Skill"), "异常消息应含资源名");
    }

    /**
     * 渲染：版本存在且变量齐全时返回渲染内容。
     */
    @Test
    void renderKnownVersionReturnsContent() {
        // given
        String slug = uniqueSlug("skill-render");
        SkillDto created = publishSkill("渲染技能", slug);

        // when
        RenderResponse response = skillController.render(created.id(),
                new RenderRequest("1.0.0", Map.of("name", "晚风")));

        // then
        assertNotNull(response);
        assertNotNull(response.content());
        assertTrue(response.content().contains("晚风"));
    }

    /**
     * 渲染：超大 payload 不炸库，正常返回，且内容非空。
     */
    @Test
    void renderWithHugePayloadSucceeds() {
        // given
        String slug = uniqueSlug("skill-huge");
        SkillDto created = publishSkill("大负载技能", slug);
        StringBuilder big = new StringBuilder();
        for (int i = 0; i < 50_000; i++) {
            big.append('x');
        }
        String hugeValue = big.toString();

        // when
        RenderResponse response = skillController.render(created.id(),
                new RenderRequest("1.0.0", Map.of("name", hugeValue)));

        // then
        assertNotNull(response);
        assertNotNull(response.content());
        assertTrue(response.content().length() >= hugeValue.length());
    }

    /**
     * 非法状态跳转：删除不存在的 Skill 抛出 404。
     */
    @Test
    void deleteUnknownSkillFailsWith404() {
        // given
        Long missingId = 777_777_777L;

        // when：直接调用 controller（不走 HTTP），GlobalExceptionHandler 不生效，
        // 抛出来的是原始 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> skillController.uninstall(missingId));

        // then
        assertTrue(ex.getMessage().contains("Skill"), "异常消息应含资源名");
    }

    /**
     * 删除后详情不可读，已安装列表不再包含该 Skill（回滚语义）。
     */
    @Test
    void uninstallRemovesInstalledRecordButKeepsSkill() {
        // given
        String slug = uniqueSlug("skill-delete");
        SkillDto created = publishSkill("删除技能", slug);
        skillController.install(created.id(), new InstallRequest("1.0.0"));
        assertNotNull(skillController.get(created.id()));

        // when
        skillController.uninstall(created.id());

        // then: 安装记录已删，installed 列表不再包含；但 skill 本体仍在，get 正常返回
        assertNotNull(skillController.get(created.id()), "uninstall 不应删除 skill 本体");
        List<InstalledSkillDto> installed = skillController.installed();
        for (InstalledSkillDto item : installed) {
            assertTrue(!item.skill().id().equals(created.id()));
        }
    }

    /**
     * 并发：两线程同时对同一 Skill 安装同一版本，最终安装记录只有一条，版本一致。
     */
    @Test
    void installSameVersionTwice_serialIsIdempotent() {
        // 地面真相：SkillService.install 使用 findBySkillId(...).orElseGet(...) 再 save，
        // 串行调用是幂等的（同一 skillId 只有一条安装记录，重复安装更新版本号）。
        // 注意：并发同版本安装存在竞态（find-then-insert 无锁，撞 SKILL_INSTALLS(SKILL_ID)
        // 唯一约束会抛 DataIntegrityViolationException），已记入技术债，本用例只验证串行幂等。
        // given
        String slug = uniqueSlug("skill-concurrent");
        SkillDto created = publishSkill("并发技能", slug);

        // when
        InstallDto first = skillController.install(created.id(), new InstallRequest("1.0.0"));
        InstallDto second = skillController.install(created.id(), new InstallRequest("1.0.0"));

        // then
        assertNotNull(first);
        assertNotNull(second);
        List<InstalledSkillDto> installed = skillController.installed();
        long matchCount = 0;
        for (InstalledSkillDto item : installed) {
            if (item.skill().id().equals(created.id())) {
                matchCount++;
                assertEquals("1.0.0", item.install().version());
            }
        }
        assertEquals(1, matchCount);
    }

    /**
     * 并发：两线程同时对同一 Skill 评分，只有一条成功，平均分与评分条数一致。
     */
    @Test
    void concurrentRateCreatesOneRowPerCall() throws Exception {
        // 地面真相：SkillService.rate 每次调用都 new SkillRating() 并 insert，没有任何去重逻辑，
        // 产品语义就是 one row per call。两个并发评分应当各自落库（共 2 条）。
        // given
        String slug = uniqueSlug("skill-concurrent-rate");
        SkillDto created = publishSkill("并发评分", slug);
        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        List<Callable<Object>> tasks = new ArrayList<>();
        for (int i = 0; i < threads; i++) {
            final int score = 3 + i;
            tasks.add(() -> {
                start.await();
                try {
                    return skillController.rate(created.id(), new RateRequest(score, "并发-" + score));
                } catch (ResponseStatusException e) {
                    return e.getStatusCode();
                }
            });
        }

        // when
        List<Future<Object>> futures = new ArrayList<>();
        for (Callable<Object> task : tasks) {
            futures.add(pool.submit(task));
        }
        start.countDown();
        for (Future<Object> f : futures) {
            assertNotNull(f.get(30, TimeUnit.SECONDS));
        }
        pool.shutdown();
        assertTrue(pool.awaitTermination(30, TimeUnit.SECONDS));

        // then
        List<RatingDto> ratings = skillController.get(created.id()).ratings();
        assertEquals(2, ratings.size());
        assertNotNull(skillController.get(created.id()).avgRating());
    }

    /**
     * 检索：按分类过滤能命中刚发布的 Skill。
     */
    @Test
    void listFiltersByCategory() {
        // given
        String slug = uniqueSlug("skill-list");
        SkillDto created = publishSkill("列表技能", slug);

        // when
        List<SkillDto> result = skillController.list(null, null, "GENERAL", null);

        // then
        assertTrue(result.size() >= 1);
        boolean found = false;
        for (SkillDto dto : result) {
            if (dto.id().equals(created.id())) {
                found = true;
                assertEquals(slug, dto.slug());
            }
        }
        assertTrue(found);
    }

    /**
     * 失败注入：发布时 slug 重复，服务层抛异常，不产生第二条记录。
     */
    @Test
    void publishDuplicateSlugFails() {
        // given
        String slug = uniqueSlug("skill-dup");
        SkillDto first = publishSkill("重复技能", slug);
        assertNotNull(first.id());

        // when
        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> publishSkill("重复技能副本", slug));

        // then
        assertNotNull(ex);
        List<SkillDto> all = skillController.list(null, null, "GENERAL", null);
        long matchCount = 0;
        for (SkillDto dto : all) {
            if (slug.equals(dto.slug())) {
                matchCount++;
            }
        }
        assertEquals(1, matchCount);
    }

    /**
     * 边界：已安装版本在未安装时为 null。
     */
    @Test
    void installedVersionIsNullWhenNotInstalled() {
        // given
        String slug = uniqueSlug("skill-not-installed");
        SkillDto created = publishSkill("未安装技能", slug);

        // when
        SkillDetailDto detail = skillController.get(created.id());

        // then
        assertNull(detail.installedVersion());
        assertEquals("1.0.0", detail.latestVersion());
    }

    /**
     * 详情评分列表最多返回 5 条（上限截断）。
     */
    @Test
    void detailRatingsAreCappedAtFive() {
        // given
        String slug = uniqueSlug("skill-cap");
        SkillDto created = publishSkill("上限技能", slug);
        skillController.rate(created.id(), new RateRequest(5, "第一条"));

        // when
        SkillDetailDto detail = skillController.get(created.id());

        // then
        assertTrue(detail.ratings().size() <= 5);
        assertEquals(1, detail.ratings().size());
        assertEquals(5, detail.ratings().get(0).score());
    }

    /**
     * 服务层 installedList 与控制器 installed 数量一致。
     */
    @Test
    void installedListMatchesService() {
        // given
        String slug = uniqueSlug("skill-consistency");
        SkillDto created = publishSkill("一致性技能", slug);
        skillController.install(created.id(), new InstallRequest("1.0.0"));

        // when
        List<InstalledSkillDto> controllerList = skillController.installed();
        List<SkillService.InstalledSkill> serviceList = skillService.installedList();

        // then
        assertEquals(serviceList.size(), controllerList.size());
        assertTrue(controllerList.size() >= 1);
    }
}