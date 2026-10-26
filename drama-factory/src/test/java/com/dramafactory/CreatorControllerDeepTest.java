package com.dramafactory;

import com.dramafactory.controller.CreatorController;
import com.dramafactory.controller.CreatorController.CreateCreatorRequest;
import com.dramafactory.controller.CreatorController.UpdateCreatorRequest;
import com.dramafactory.controller.CreatorController.CreatorDetailDto;
import com.dramafactory.exception.ResourceNotFoundException;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.mock.web.MockHttpServletRequest;
import com.dramafactory.exception.ForbiddenException;
import com.dramafactory.repository.CreatorFollowRepository;
import com.dramafactory.repository.CreatorProfileRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.service.CreatorService;
import com.dramafactory.service.SkillService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * CreatorController 深度集成测试。
 *
 * <p>直接针对真实 Spring 上下文中的控制器进行方法级调用，
 * 不经过 HTTP 层，覆盖创作者注册、资料查询、关注关系与技能发布等核心业务链路，
 * 以验证服务层、仓储层与数据库之间的完整交互行为。</p>
 */
@SpringBootTest
class CreatorControllerDeepTest {

    @Autowired
    private CreatorController creatorController;

    @Autowired
    private CreatorService creatorService;

    @Autowired
    private SkillService skillService;

    @Autowired
    private CreatorProfileRepository profileRepository;

    @Autowired
    private CreatorFollowRepository followRepository;

    @Autowired
    private SkillRepository skillRepository;

    /**
     * 每个测试用例执行前清空相关仓储数据，保证测试之间互不干扰。
     */
    @BeforeEach
    void setUp() {
        followRepository.deleteAll();
        skillRepository.deleteAll();
        profileRepository.deleteAll();
    }

    /**
     * 基于给定前缀生成全局唯一的 handle。
     * 追加纳秒时间戳保证唯一性，并清理所有不合法字符后截断至最多 50 个字符。
     */
    private String uniqueHandle(String base) {
        String cleaned = (base + "-" + System.nanoTime()).replaceAll("[^a-z0-9-]", "");
        return cleaned.length() > 50 ? cleaned.substring(0, 50) : cleaned;
    }

    /**
     * 使用指定 handle 与显示名称创建创作者资料，简介由 handle 自动拼接生成。
     */
    private CreatorDetailDto createProfile(String handle, String displayName) {
        return creatorController.create(new CreateCreatorRequest(handle, displayName, "bio-" + handle, null));
    }

    /**
     * 以指定作者身份发布一个模板技能，技能名称与标识均由 slug 派生。
     */
    private void publishSkillFor(String author, String slug) {
        skillService.publish("skill-" + slug, slug, "desc", author, "GENERAL", "t1", "puzzle", "tpl {{x}}", "v1");
    }

/**
     * 创建创作者后，应能通过 detail 接口正确读取其基础信息。
     */
    @Test
    void createThenDetailReadable() {
        String handle = uniqueHandle("creator");
        createProfile(handle, "Creator One");
        var detail = creatorController.detail(handle);
        assertEquals(handle, detail.handle());
        assertEquals("Creator One", detail.displayName());
        assertEquals(0, detail.skillCount());
        assertEquals(0, detail.followerCount());
    }

    /**
     * 使用重复的 handle 创建创作者时应抛出 IllegalArgumentException。
     */
    @Test
    void duplicateHandleRejected() {
        String handle = uniqueHandle("dup");
        createProfile(handle, "Dup");
        assertThrows(IllegalArgumentException.class, () -> createProfile(handle, "Dup Again"));
    }

    /**
     * 使用非法 handle（包含空格或特殊字符）创建创作者时应抛出 IllegalArgumentException。
     */
    @Test
    void invalidHandleRejected() {
        assertThrows(IllegalArgumentException.class, () -> createProfile("Bad Handle!", "Bad"));
    }

    /**
     * 详情接口在创作者不存在时应抛出 ResourceNotFoundException。
     */
    @Test
    void detailMissingThrows() {
        assertThrows(ResourceNotFoundException.class, () -> creatorController.detail("no-such-creator-xyz"));
    }

    /**
     * 详情与列表应正确聚合创作者发布的技能数量与安装数。
     */
    @Test
    void statsAggregateSkills() {
        String handle = uniqueHandle("stat");
        createProfile(handle, "Stat Maker");
        publishSkillFor(handle, uniqueHandle("sk-a"));
        publishSkillFor(handle, uniqueHandle("sk-b"));
        publishSkillFor("Stat Maker", uniqueHandle("sk-c"));

        var detail = creatorController.detail(handle);
        assertEquals(3, detail.skillCount());
        assertEquals(0, detail.totalInstalls());

        var listed = creatorController.list(handle, "newest");
        assertTrue(listed.stream().anyMatch(item -> item.handle().equals(handle) && item.skillCount() == 3));
    }

    /**
     * 关注与取消关注应完整往返：重复关注返回 false，且粉丝数随之正确变化。
     */
    @Test
    void followUnfollowRoundTrip() {
        String handle = uniqueHandle("fol");
        createProfile(handle, "Follow Me");
        assertEquals(Boolean.TRUE, creatorController.follow(handle).get("followed"));
        assertEquals(1L, creatorController.detail(handle).followerCount());
        assertTrue(creatorController.detail(handle).followedByMe());
        assertEquals(Boolean.FALSE, creatorController.follow(handle).get("followed"));
        assertEquals(1L, creatorController.detail(handle).followerCount());
        creatorController.unfollow(handle);
        assertEquals(0L, creatorController.detail(handle).followerCount());
        creatorController.unfollow(handle);
        assertEquals(0L, creatorController.detail(handle).followerCount());
    }

    /**
     * 更新接口应修改创作者的简介与网站，并保留其 handle。
     */
    @Test
    void updateChangesBioAndWebsite() {
        String handle = uniqueHandle("upd");
        createProfile(handle, "Updater");

        var updated = creatorController.update(handle, new CreatorController.UpdateCreatorRequest("Updater", "new bio", "https://example.com"));
        assertEquals("new bio", updated.bio());
        assertEquals("https://example.com", updated.website());
        assertEquals(handle, updated.handle());
    }

/**
 * 关注一个不存在的创作者时，应抛出 ResourceNotFoundException。
 */
@Test
void followMissingThrows() {
    assertThrows(ResourceNotFoundException.class, () -> creatorController.follow("no-such-creator-xyz"));
}

/**
 * 当请求用户并非资料所有者时，更新他人资料应抛出 ForbiddenException。
 */
@Test
void updateForbiddenForOtherOwner() {
    String handle = uniqueHandle("forbid");
    createProfile(handle, "Owner One");
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setAttribute("auth.userId", "other-user");
    RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
    try {
        assertThrows(ForbiddenException.class,
                () -> creatorController.update(handle, new CreatorController.UpdateCreatorRequest("Owner One", "hacked bio", null)));
    } finally {
        RequestContextHolder.resetRequestAttributes();
    }
}
}
