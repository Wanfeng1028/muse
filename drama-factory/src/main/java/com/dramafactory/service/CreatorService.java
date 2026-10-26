package com.dramafactory.service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.dramafactory.model.CreatorFollow;
import com.dramafactory.model.CreatorProfile;
import com.dramafactory.model.Skill;
import com.dramafactory.exception.ForbiddenException;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.CreatorFollowRepository;
import com.dramafactory.repository.CreatorProfileRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.config.CurrentUser;

/**
 * 创作者档案服务，提供创作者的创建、修改、查询、关注以及统计能力。
 *
 * <p>统计口径说明：技能（{@link Skill}）实体的 author 字段是自由填写的展示字符串，
 * 并不强制等于创作者 handle，因此统计时同时用 handle 与 displayName 去匹配
 * Skill.author，并按技能 id 去重后再计数与汇总。
 *
 * <p>本服务刻意不计算、也不暴露任何收益或分成等金额字段：商业激励规则尚未确定，
 * 待规则明确后再补充相关字段与计算逻辑。
 */
@Service
public class CreatorService {

    /** handle 合法格式：3-50 位小写字母、数字或中划线。 */
    private static final Pattern HANDLE_PATTERN = Pattern.compile("^[a-z0-9-]{3,50}$");

    private final CreatorProfileRepository profileRepository;

    private final CreatorFollowRepository followRepository;

    private final SkillRepository skillRepository;

    private final CurrentUser currentUser;

    /**
     * 通过构造函数注入依赖。
     *
     * @param profileRepository 创作者档案仓储
     * @param followRepository  关注关系仓储
     * @param skillRepository   技能仓储
     * @param currentUser       当前登录用户
     */
    public CreatorService(CreatorProfileRepository profileRepository,
            CreatorFollowRepository followRepository,
            SkillRepository skillRepository,
            CurrentUser currentUser) {
        this.profileRepository = profileRepository;
        this.followRepository = followRepository;
        this.skillRepository = skillRepository;
        this.currentUser = currentUser;
    }

    /**
     * 创建创作者档案。
     *
     * <p>先校验 handle 与各字段格式，再检查 handle 是否重复，重复时抛出
     * {@link IllegalArgumentException}；创建成功时档案的 ownerId 记录为当前登录用户。
     *
     * @param handle      创作者 handle，须匹配 {@code ^[a-z0-9-]{3,50}$}
     * @param displayName 展示名称，非空白且不超过 100 字符
     * @param bio         简介，可为空，不超过 500 字符
     * @param website     主页链接，可为空，不超过 500 字符
     * @return 保存后的创作者档案
     * @throws IllegalArgumentException handle 不合法、handle 已存在或字段校验失败
     */
    @Transactional
    public CreatorProfile create(String handle, String displayName, String bio, String website) {
        validateHandle(handle);
        validateProfileFields(displayName, bio, website);
        profileRepository.findByHandle(handle).ifPresent(existing -> {
            throw new IllegalArgumentException("handle 已存在");
        });
        CreatorProfile profile = new CreatorProfile();
        profile.setHandle(handle);
        profile.setDisplayName(displayName);
        profile.setBio(bio);
        profile.setWebsite(website);
        profile.setOwnerId(currentUser.currentUserId());
        return profileRepository.save(profile);
    }

    /**
     * 更新创作者档案（handle 不可修改）。
     *
     * <p>仅档案拥有者可以更新；displayName、bio、website 按规则校验，handle 保持不变。
     *
     * @param handle      用于定位档案的 handle
     * @param displayName 新的展示名称
     * @param bio         新的简介
     * @param website     新的主页链接
     * @return 更新后的创作者档案
     * @throws ResourceNotFoundException 指定 handle 的档案不存在
     * @throws ForbiddenException        当前用户不是该档案的拥有者
     * @throws IllegalArgumentException  字段校验失败
     */
    @Transactional
    public CreatorProfile update(String handle, String displayName, String bio, String website) {
        CreatorProfile profile = profileRepository.findByHandle(handle)
                .orElseThrow(() -> ResourceNotFoundException.withKey("CreatorProfile", handle));
        if (!Objects.equals(profile.getOwnerId(), currentUser.currentUserId())) {
            throw new ForbiddenException("CreatorProfile", handle);
        }
        validateProfileFields(displayName, bio, website);
        profile.setDisplayName(displayName);
        profile.setBio(bio);
        profile.setWebsite(website);
        return profileRepository.save(profile);
    }

    /**
     * 按 handle 查询创作者档案，不存在时抛出 {@link ResourceNotFoundException}。
     *
     * @param handle 创作者 handle
     * @return 对应的创作者档案
     * @throws ResourceNotFoundException 档案不存在
     */
    @Transactional(readOnly = true)
    public CreatorProfile getByHandle(String handle) {
        return profileRepository.findByHandle(handle)
                .orElseThrow(() -> ResourceNotFoundException.withKey("CreatorProfile", handle));
    }

    /**
     * 查询创作者列表，默认按档案创建时间倒序返回。
     *
     * <p>search 非空白时，仅保留 handle 或 displayName 不区分大小写包含关键字的档案；
     * sort 为 {@code followers} 时按关注数倒序、创建时间倒序排列，sort 为 {@code skills}
     * 时按技能数倒序、创建时间倒序排列，其余情况保持创建时间倒序。
     *
     * @param search 搜索关键字，可为空
     * @param sort   排序方式，支持 followers、skills，可为空
     * @return 列表项携带档案创建时间以及统计出的技能数与关注数
     */
    @Transactional(readOnly = true)
    public List<CreatorListItem> list(String search, String sort) {
        List<CreatorProfile> profiles = profileRepository.findAllByOrderByCreatedAtDesc();
        if (search != null && !search.isBlank()) {
            String keyword = search.toLowerCase(Locale.ROOT);
            profiles = profiles.stream()
                    .filter(profile -> profile.getHandle().toLowerCase(Locale.ROOT).contains(keyword)
                            || (profile.getDisplayName() != null
                                    && profile.getDisplayName().toLowerCase(Locale.ROOT).contains(keyword)))
                    .toList();
        }
        List<CreatorListItem> items = new ArrayList<>();
        for (CreatorProfile profile : profiles) {
            items.add(new CreatorListItem(
                    profile.getId(),
                    profile.getHandle(),
                    profile.getDisplayName(),
                    profile.getBio(),
                    skillCountFor(profile),
                    followRepository.countByCreatorId(profile.getId()),
                    profile.getCreatedAt()));
        }
        Comparator<CreatorListItem> byCreatedAtDesc =
                Comparator.comparing(CreatorListItem::createdAt).reversed();
        if ("followers".equals(sort)) {
            items.sort(Comparator.comparingLong(CreatorListItem::followerCount).reversed()
                    .thenComparing(byCreatedAtDesc));
        } else if ("skills".equals(sort)) {
            items.sort(Comparator.comparingLong(CreatorListItem::skillCount).reversed()
                    .thenComparing(byCreatedAtDesc));
        }
        return items;
    }

    /**
     * 查询创作者详情。
     *
     * <p>技能列表由 handle 与 displayName 各自匹配到的技能按 id 合并去重，并按安装量倒序排列；
     * 统计信息基于合并后的技能列表与关注数计算，同时返回当前用户是否已关注该创作者。
     *
     * @param handle 创作者 handle
     * @return 创作者详情（档案、统计、技能列表、当前用户是否已关注）
     * @throws ResourceNotFoundException 档案不存在
     */
    @Transactional(readOnly = true)
    public CreatorDetail detail(String handle) {
        CreatorProfile profile = getByHandle(handle);
        Map<Long, Skill> uniqueSkills = new LinkedHashMap<>();
        for (Skill skill : skillRepository.findByAuthor(profile.getHandle())) {
            uniqueSkills.putIfAbsent(skill.getId(), skill);
        }
        if (profile.getDisplayName() != null) {
            for (Skill skill : skillRepository.findByAuthor(profile.getDisplayName())) {
                uniqueSkills.putIfAbsent(skill.getId(), skill);
            }
        }
        List<Skill> skills = new ArrayList<>(uniqueSkills.values());
        skills.sort(Comparator.comparingLong(
                (Skill skill) -> skill.getInstallCount() == null ? 0L : skill.getInstallCount()).reversed());
        CreatorStats stats = statsFor(profile, skills);
        boolean followedByMe = followRepository.existsByCreatorIdAndFollowerId(
                profile.getId(), currentUser.currentUserId());
        return new CreatorDetail(profile, stats, skills, followedByMe);
    }

    /**
     * 关注指定创作者。
     *
     * @param handle 创作者 handle
     * @return 本次是否新建了关注关系，已关注时返回 {@code false}
     * @throws ResourceNotFoundException 档案不存在
     */
    @Transactional
    public boolean follow(String handle) {
        CreatorProfile profile = getByHandle(handle);
        String followerId = currentUser.currentUserId();
        if (followRepository.existsByCreatorIdAndFollowerId(profile.getId(), followerId)) {
            return false;
        }
        CreatorFollow follow = new CreatorFollow();
        follow.setCreatorId(profile.getId());
        follow.setFollowerId(followerId);
        followRepository.save(follow);
        return true;
    }

    /**
     * 取消关注指定创作者。
     *
     * @param handle 创作者 handle
     * @return 本次是否删除了关注关系，未关注时返回 {@code false}
     * @throws ResourceNotFoundException 档案不存在
     */
    @Transactional
    public boolean unfollow(String handle) {
        CreatorProfile profile = getByHandle(handle);
        return followRepository
                .findByCreatorIdAndFollowerId(profile.getId(), currentUser.currentUserId())
                .map(follow -> {
                    followRepository.delete(follow);
                    return true;
                })
                .orElse(false);
    }

@Transactional(readOnly = true)
public List<CreatorFeedItem> feed(int limit) {
  if (limit < 1 || limit > 50) throw new IllegalArgumentException("limit 参数非法");
  String followerId = currentUser.currentUserId();
  Map<Long, Skill> skillsById = new LinkedHashMap<>();
  Map<Long, CreatorProfile> creatorBySkillId = new LinkedHashMap<>();
  for (CreatorFollow follow : followRepository.findByFollowerId(followerId)) {
    CreatorProfile profile = profileRepository.findById(follow.getCreatorId()).orElse(null);
    if (profile == null) continue;
    List<Skill> found = new ArrayList<>(skillRepository.findByAuthor(profile.getHandle()));
    if (profile.getDisplayName() != null) found.addAll(skillRepository.findByAuthor(profile.getDisplayName()));
    for (Skill skill : found) {
      skillsById.putIfAbsent(skill.getId(), skill);
      creatorBySkillId.putIfAbsent(skill.getId(), profile);
    }
  }
  List<CreatorFeedItem> items = new ArrayList<>();
  for (Skill skill : skillsById.values()) {
    CreatorProfile profile = creatorBySkillId.get(skill.getId());
    items.add(new CreatorFeedItem(profile.getHandle(), profile.getDisplayName(), skill.getId(), skill.getName(), skill.getSlug(), skill.getDescription(), skill.getCategory(), skill.getInstallCount(), skill.getAvgRating(), skill.getCreatedAt()));
  }
  items.sort(Comparator.comparing(CreatorFeedItem::createdAt, Comparator.nullsLast(Comparator.reverseOrder())));
  return items.size() > limit ? items.subList(0, limit) : items;
}

    /**
     * 基于去重后的技能列表与关注数计算创作者统计。
     *
     * <p>安装量与评分字段为 null 时按 0 处理；评分总数为 0 时不计算平均分（返回 null），
     * 否则平均分四舍五入保留 1 位小数。
     *
     * @param profile 创作者档案
     * @param skills  去重后的技能列表
     * @return 创作者统计数据
     */
    private CreatorStats statsFor(CreatorProfile profile, List<Skill> skills) {
        long totalInstalls = 0L;
        long ratingSum = 0L;
        long ratingCount = 0L;
        for (Skill skill : skills) {
            totalInstalls += skill.getInstallCount() == null ? 0L : skill.getInstallCount();
            ratingSum += skill.getRatingSum() == null ? 0L : skill.getRatingSum();
            ratingCount += skill.getRatingCount() == null ? 0L : skill.getRatingCount();
        }
        Double avgRating = null;
        if (ratingCount >0) {
            avgRating = Math.round((double) ratingSum / ratingCount * 10.0) / 10.0;
        }
        return new CreatorStats(skills.size(), totalInstalls, avgRating, followRepository.countByCreatorId(profile.getId()));
    }

    /**
     * 校验 handle 是否合法：仅允许小写字母、数字和中划线，长度 3-50。
     */
    private void validateHandle(String handle) {
        if (handle == null || handle.isBlank() || !handle.matches("^[a-z0-9-]{3,50}$")) {
            throw new IllegalArgumentException("handle 仅允许小写字母、数字和中划线，长度为 3-50 个字符");
        }
    }

    /**
     * 校验创作者资料字段。
     */
    private void validateProfileFields(String displayName, String bio, String website) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("displayName 不能为空");
        }
        if (displayName.length() > 100) {
            throw new IllegalArgumentException("displayName 不能超过 100 个字符");
        }
        if (bio != null && bio.length() > 500) {
            throw new IllegalArgumentException("bio 不能超过 500 个字符");
        }
        if (website != null && website.length() > 500) {
            throw new IllegalArgumentException("website 不能超过 500 个字符");
        }
    }

    /**
     * 统计创作者名下技能数量，按技能 id 去重。
     */
    private long skillCountFor(CreatorProfile profile) {
        List<Skill> skills = new java.util.ArrayList<>(skillRepository.findByAuthor(profile.getHandle()));
        if (profile.getDisplayName() != null) {
            skills.addAll(skillRepository.findByAuthor(profile.getDisplayName()));
        }
        return skills.stream().map(Skill::getId).distinct().count();
    }

    /**
     * 创作者统计数据。
     */
    public static record CreatorStats(long skillCount, long totalInstalls, Double avgRating, long followerCount) {
    }

    /**
     * 创作者列表项。
     */
    public static record CreatorListItem(Long id, String handle, String displayName, String bio, long skillCount, long followerCount, LocalDateTime createdAt) {
    }

    /**
     * 创作者详情。
     */
    public static record CreatorDetail(CreatorProfile profile, CreatorStats stats, List<Skill> skills, boolean followedByMe) {
    }

/**
 * 关注动态条目：一条为某位已关注创作者名下发布的一个 Skill，createdAt 为该 Skill 的发布时间。
 */
public static record CreatorFeedItem(String handle, String displayName, Long skillId, String skillName, String skillSlug, String skillDescription, String category, Long installCount, Double avgRating, LocalDateTime createdAt) {
}
}
