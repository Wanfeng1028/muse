package com.dramafactory.controller;

import com.dramafactory.model.CreatorProfile;
import com.dramafactory.service.CreatorService;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 创作者计划控制器，提供创作者主页、资料与关注相关接口。
 *
 * <p>包含创作者列表检索、主页详情查看、创作者资料创建与更新，以及关注与取消关注能力。</p>
 *
 * <p>创作者激励与收益分成规则尚待商业决策，本接口有意不暴露任何激励或收益分成相关内容。</p>
 */
@Tag(name = "创作者计划", description = "创作者主页、资料与关注")
@RestController
@RequestMapping("/api/creators")
public class CreatorController {

    private final CreatorService creatorService;

    /**
     * 构造控制器并注入创作者服务。
     *
     * @param creatorService 创作者服务
     */
    public CreatorController(CreatorService creatorService) {
        this.creatorService = creatorService;
    }

    /**
     * 查询创作者列表，可按关键词搜索并按指定方式排序。
     *
     * @param search 搜索关键词，为空时不过滤
     * @param sort   排序方式，默认 newest（最新创建优先）
     * @return 创作者列表项集合，与服务层列表结果一一对应（含创建时间）
     */
    @GetMapping
    public List<CreatorListItemDto> list(
            @RequestParam(required = false) String search,
            @RequestParam(defaultValue = "newest") String sort) {
        return creatorService.list(search, sort).stream()
                .map(item -> new CreatorListItemDto(
                        item.id(),
                        item.handle(),
                        item.displayName(),
                        item.bio(),
                        item.skillCount(),
                        item.followerCount(),
                        item.createdAt()))
                .toList();
    }

    /**
     * 查询指定创作者的主页详情，包含技能列表与统计信息。
     *
     * @param handle 创作者唯一标识
     * @return 创作者主页详情
     */
    @GetMapping("/{handle}")
    public CreatorDetailDto detail(@PathVariable String handle) {
        return toDetailDto(creatorService.detail(handle));
    }

    /**
     * 创建创作者资料，创建成功后返回其主页详情。
     *
     * @param req 创建创作者请求体
     * @return 新建创作者的主页详情
     */
/**
 * 创建创作者
 *
 * @param req 创建请求参数
 * @return 创作者详情 DTO
 */
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public CreatorDetailDto create(@RequestBody CreateCreatorRequest req) {
    CreatorProfile profile = creatorService.create(req.handle(), req.displayName(), req.bio(), req.website());
    return toDetailDto(creatorService.detail(profile.getHandle()));
}

    /**
     * 更新指定创作者的资料，返回更新后的主页详情。
     *
     * @param handle 创作者唯一标识
     * @param req    更新创作者资料请求体
     * @return 更新后的创作者主页详情
     */
    @PutMapping("/{handle}")
    public CreatorDetailDto update(@PathVariable String handle, @RequestBody UpdateCreatorRequest req) {
        creatorService.update(handle, req.displayName(), req.bio(), req.website());
        return toDetailDto(creatorService.detail(handle));
    }

    /**
     * 关注指定创作者。
     *
     * @param handle 创作者唯一标识
     * @return followed 为关注后的状态，followerCount 为关注后的最新粉丝数
     */
/**
 * 关注指定创作者
 *
 * @param handle 创作者唯一标识
 * @return 关注结果及最新粉丝数
 */
@PostMapping("/{handle}/follow")
public Map<String, Object> follow(@PathVariable String handle) {
    boolean followed = creatorService.follow(handle);
    long followerCount = creatorService.detail(handle).stats().followerCount();
    return Map.of("followed", followed, "followerCount", followerCount);
}

    /**
     * 取消关注指定创作者。
     *
     * @param handle 创作者唯一标识
     * @return followed 恒为 false，followerCount 为取消关注后的最新粉丝数
     */
/**
 * 取消关注指定创作者
 *
 * @param handle 创作者唯一标识
 * @return 取消关注结果及最新粉丝数
 */
@DeleteMapping("/{handle}/follow")
public Map<String, Object> unfollow(@PathVariable String handle) {
    creatorService.unfollow(handle);
    long followerCount = creatorService.detail(handle).stats().followerCount();
    return Map.of("followed", false, "followerCount", followerCount);
}

    /**
     * 将服务层创作者详情转换为响应 DTO，其中技能列表逐项映射为技能 DTO。
     *
     * @param detail 服务层创作者详情
     * @return 创作者主页详情 DTO
     */
/**
 * 将服务层创作者详情转换为响应 DTO
 *
 * @param detail 服务层创作者详情
 * @return 创作者详情 DTO
 */
private CreatorDetailDto toDetailDto(CreatorService.CreatorDetail detail) {
    CreatorProfile profile = detail.profile();
    CreatorService.CreatorStats stats = detail.stats();
    List<CreatorSkillDto> skills = detail.skills().stream()
            .map(skill -> new CreatorSkillDto(
                    skill.getId(),
                    skill.getName(),
                    skill.getSlug(),
                    skill.getDescription(),
                    skill.getCategory(),
                    skill.getInstallCount(),
                    skill.getAvgRating()))
            .toList();
    return new CreatorDetailDto(
            profile.getId(),
            profile.getHandle(),
            profile.getDisplayName(),
            profile.getBio(),
            profile.getWebsite(),
            stats.skillCount(),
            stats.totalInstalls(),
            stats.avgRating(),
            stats.followerCount(),
            detail.followedByMe(),
            skills,
            profile.getCreatedAt(),
            profile.getUpdatedAt());
}

    /**
     * 创建创作者请求体。
     *
     * @param handle      创作者唯一标识
     * @param displayName 展示名称
     * @param bio         个人简介
     * @param website     个人主页链接
     */
    public record CreateCreatorRequest(String handle, String displayName, String bio, String website) {
    }

    /**
     * 更新创作者资料请求体。
     *
     * @param displayName 展示名称
     * @param bio         个人简介
     * @param website     个人主页链接
     */
    public record UpdateCreatorRequest(String displayName, String bio, String website) {
    }

    /**
     * 创作者列表项 DTO。
     *
     * @param id            创作者 ID
     * @param handle        创作者唯一标识
     * @param displayName   展示名称
     * @param bio           个人简介
     * @param skillCount    技能数量
     * @param followerCount 粉丝数
     * @param createdAt     创建时间
     */
    public record CreatorListItemDto(
            Long id,
            String handle,
            String displayName,
            String bio,
            long skillCount,
            long followerCount,
            LocalDateTime createdAt) {
    }

    /**
     * 创作者技能摘要 DTO。
     *
     * @param id           技能 ID
     * @param name         技能名称
     * @param slug         技能短标识
     * @param description  技能描述
     * @param category     技能分类
     * @param installCount 安装次数
     * @param avgRating    平均评分
     */
    public record CreatorSkillDto(
            Long id,
            String name,
            String slug,
            String description,
            String category,
            Long installCount,
            Double avgRating) {
    }

    /**
     * 创作者主页详情 DTO。
     *
     * @param id            创作者 ID
     * @param handle        创作者唯一标识
     * @param displayName   展示名称
     * @param bio           个人简介
     * @param website       个人主页链接
     * @param skillCount    技能数量
     * @param totalInstalls 技能总安装次数
     * @param avgRating     技能平均评分
     * @param followerCount 粉丝数
     * @param followedByMe  当前用户是否已关注
     * @param skills        技能列表
     * @param createdAt     创建时间
     * @param updatedAt     更新时间
     */
    public record CreatorDetailDto(
            Long id,
            String handle,
            String displayName,
            String bio,
            String website,
            long skillCount,
            long totalInstalls,
            Double avgRating,
            long followerCount,
            boolean followedByMe,
            List<CreatorSkillDto> skills,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {
    }
}