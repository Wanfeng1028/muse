package com.dramafactory.service;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillRating;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillInstallRepository;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillRepository;
import com.dramafactory.repository.SkillVersionRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Skill 市场业务服务。
 * <p>负责技能发布、多版本管理、市场检索、安装与评分。</p>
 */
@Service
public class SkillService {

    /** slug 合法格式 */
    private static final Pattern SLUG_PATTERN = Pattern.compile("^[a-z0-9-]{3,100}$");

    /** 版本号合法格式 */
    private static final Pattern VERSION_PATTERN = Pattern.compile("^\\d+\\.\\d+\\.\\d+$");

    /** 模板占位符正则 */
    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{([^}]+)}}");

    /** 合法分类 */
    private static final Set<String> VALID_CATEGORIES = Set.of("SCRIPT", "BOARD", "VIDEO", "EDIT", "GENERAL");

    private final SkillRepository skillRepository;
    private final SkillVersionRepository skillVersionRepository;
    private final SkillInstallRepository skillInstallRepository;
    private final SkillRatingRepository skillRatingRepository;

    /**
     * 构造器注入。
     *
     * @param skillRepository        Skill 仓库
     * @param skillVersionRepository Skill 版本仓库
     * @param skillInstallRepository Skill 安装记录仓库
     * @param skillRatingRepository  Skill 评分仓库
     */
    public SkillService(SkillRepository skillRepository,
                        SkillVersionRepository skillVersionRepository,
                        SkillInstallRepository skillInstallRepository,
                        SkillRatingRepository skillRatingRepository) {
        this.skillRepository = skillRepository;
        this.skillVersionRepository = skillVersionRepository;
        this.skillInstallRepository = skillInstallRepository;
        this.skillRatingRepository = skillRatingRepository;
    }

    /**
     * 发布新 Skill，同时创建 1.0.0 版本。
     *
     * @param name           名称，非空
     * @param slug           唯一标识，格式 ^[a-z0-9-]{3,100}$
     * @param description    说明
     * @param author         作者
     * @param category       分类，合法值 SCRIPT/BOARD/VIDEO/EDIT/GENERAL
     * @param tags           逗号分隔标签
     * @param icon           图标标识
     * @param promptTemplate prompt 模板，非空
     * @param changelog      版本变更说明，空则记「首版发布」
     * @return 创建的 Skill
     */
    @Transactional
    public Skill publish(String name, String slug, String description, String author,
                         String category, String tags, String icon,
                         String promptTemplate, String changelog) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name 不能为空");
        }
        if (slug == null || slug.isBlank()) {
            throw new IllegalArgumentException("slug 不能为空");
        }
        if (!SLUG_PATTERN.matcher(slug).matches()) {
            throw new IllegalArgumentException("slug 格式不合法");
        }
        if (skillRepository.findBySlug(slug).isPresent()) {
            throw new IllegalArgumentException("slug 已存在");
        }
        if (category == null || !VALID_CATEGORIES.contains(category)) {
            throw new IllegalArgumentException("category 不合法");
        }
        if (promptTemplate == null || promptTemplate.isBlank()) {
            throw new IllegalArgumentException("promptTemplate 不能为空");
        }

        Skill skill = new Skill();
        skill.setName(name);
        skill.setSlug(slug);
        skill.setDescription(description);
        skill.setAuthor(author == null || author.isBlank() ? "官方" : author);
        skill.setCategory(category);
        skill.setTags(tags);
        skill.setIcon(icon);
        skill.setOfficial(Boolean.FALSE);
        skill.setInstallCount(0L);
        skill.setRatingSum(0L);
        skill.setRatingCount(0L);
        Skill saved = skillRepository.save(skill);

        SkillVersion version = new SkillVersion();
        version.setSkillId(saved.getId());
        version.setVersion("1.0.0");
        version.setPromptTemplate(promptTemplate);
        version.setChangelog(changelog == null || changelog.isBlank() ? "首版发布" : changelog);
        skillVersionRepository.save(version);

        return saved;
    }

    /**
     * 为已有 Skill 发布新版本。
     *
     * @param skillId        Skill ID
     * @param version        版本号，格式 ^\d+\.\d+\.\d+$
     * @param promptTemplate prompt 模板，非空
     * @param changelog      变更说明
     * @return 创建的 SkillVersion
     */
    @Transactional
    public SkillVersion publishVersion(Long skillId, String version, String promptTemplate, String changelog) {
        if (version == null || !VERSION_PATTERN.matcher(version).matches()) {
            throw new IllegalArgumentException("version 格式不合法");
        }
        if (promptTemplate == null || promptTemplate.isBlank()) {
            throw new IllegalArgumentException("promptTemplate 不能为空");
        }
        Skill skill = getOrThrow(skillId);
        if (skillVersionRepository.findBySkillIdAndVersion(skill.getId(), version).isPresent()) {
            throw new IllegalArgumentException("版本已存在");
        }

        SkillVersion skillVersion = new SkillVersion();
        skillVersion.setSkillId(skill.getId());
        skillVersion.setVersion(version);
        skillVersion.setPromptTemplate(promptTemplate);
        skillVersion.setChangelog(changelog);
        return skillVersionRepository.save(skillVersion);
    }

    /**
     * 市场检索 Skill。
     *
     * @param query    关键字，忽略大小写匹配 name/description/tags，可空
     * @param tag      标签精确匹配，可空
     * @param category 分类精确匹配，可空
     * @param sort     排序：popular（默认）/rating/newest/name
     * @return 过滤排序后的 Skill 列表
     */
    @Transactional(readOnly = true)
    public List<Skill> list(String query, String tag, String category, String sort) {
        List<Skill> all = skillRepository.findAll();
        List<Skill> filtered = new ArrayList<>();
        for (Skill skill : all) {
            if (query != null && !query.isBlank()) {
                String lower = query.toLowerCase();
                boolean matchName = skill.getName() != null && skill.getName().toLowerCase().contains(lower);
                boolean matchDesc = skill.getDescription() != null && skill.getDescription().toLowerCase().contains(lower);
                boolean matchTags = skill.getTags() != null && skill.getTags().toLowerCase().contains(lower);
                boolean matchSlug = skill.getSlug() != null && skill.getSlug().toLowerCase().contains(lower);
                if (!matchName && !matchDesc && !matchTags && !matchSlug) {
                    continue;
                }
            }
            if (tag != null && !tag.isBlank()) {
                if (skill.getTags() == null) {
                    continue;
                }
                boolean tagMatch = false;
                for (String t : skill.getTags().split(",")) {
                    if (t.trim().equals(tag)) {
                        tagMatch = true;
                        break;
                    }
                }
                if (!tagMatch) {
                    continue;
                }
            }
            if (category != null && !category.isBlank() && !category.equals(skill.getCategory())) {
                continue;
            }
            filtered.add(skill);
        }

        String sortKey = (sort == null || sort.isBlank()) ? "popular" : sort;
        switch (sortKey) {
            case "rating" -> filtered.sort(Comparator.comparing(
                    (Skill s) -> s.getAvgRating() == null ? Double.NEGATIVE_INFINITY : s.getAvgRating()).reversed());
            case "newest" -> filtered.sort(Comparator.comparing(
                    Skill::getCreatedAt,
                    Comparator.nullsLast(Comparator.reverseOrder())));
            case "name" -> filtered.sort(Comparator.comparing(
                    Skill::getName,
                    Comparator.nullsLast(Comparator.naturalOrder())));
            case "popular" -> filtered.sort(Comparator.comparing(
                    Skill::getInstallCount,
                    Comparator.nullsLast(Comparator.reverseOrder())));
            default -> filtered.sort(Comparator.comparing(
                    Skill::getInstallCount,
                    Comparator.nullsLast(Comparator.reverseOrder())));
        }
        return filtered;
    }

    /**
     * Skill 详情。
     *
     * @param skillId Skill ID
     * @return 详情记录，含版本列表、已安装版本与平均分
     */
    @Transactional(readOnly = true)
    public SkillDetail getDetail(Long skillId) {
        Skill skill = getOrThrow(skillId);
        List<SkillVersion> versions = skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(skillId);
        String installedVersion = skillInstallRepository.findBySkillId(skillId)
                .map(SkillInstall::getVersion)
                .orElse(null);
        return new SkillDetail(skill, versions, installedVersion, skill.getAvgRating());
    }

    /**
     * 安装 Skill（幂等）。
     *
     * @param skillId Skill ID
     * @param version 版本号，为空则使用最新版
     * @return 安装记录
     */
    @Transactional
    public SkillInstall install(Long skillId, String version) {
        Skill skill = getOrThrow(skillId);
        String targetVersion = version;
        if (targetVersion == null || targetVersion.isBlank()) {
            targetVersion = latestVersion(skillId);
        }
        skillVersionRepository.findBySkillIdAndVersion(skillId, targetVersion)
                .orElseThrow(() -> new IllegalArgumentException("版本不存在"));

        SkillInstall install = skillInstallRepository.findBySkillId(skillId).orElseGet(SkillInstall::new);
        install.setSkillId(skillId);
        install.setVersion(targetVersion);
        if (install.getInstalledAt() == null) {
            install.setInstalledAt(java.time.LocalDateTime.now());
        }
        SkillInstall saved = skillInstallRepository.save(install);

        skill.setInstallCount((skill.getInstallCount() == null ? 0L : skill.getInstallCount()) + 1);
        skillRepository.save(skill);
        return saved;
    }

    /**
     * 卸载 Skill。
     *
     * @param skillId Skill ID
     */
    @Transactional
    public void uninstall(Long skillId) {
        SkillInstall install = skillInstallRepository.findBySkillId(skillId)
                .orElseThrow(() -> new com.dramafactory.exception.ResourceNotFoundException("SkillInstall", skillId));
        skillInstallRepository.delete(install);
    }

    /**
     * 为 Skill 评分。
     *
     * @param skillId Skill ID
     * @param score   分数，1~5
     * @param comment 评论，可空
     * @return 评分记录
     */
    @Transactional
    public SkillRating rate(Long skillId, Integer score, String comment) {
        if (score == null || score < 1 || score > 5) {
            throw new IllegalArgumentException("score 必须在 1~5 之间");
        }
        Skill skill = getOrThrow(skillId);
        SkillRating rating = new SkillRating();
        rating.setSkillId(skillId);
        rating.setScore(score);
        rating.setComment(comment);
        SkillRating saved = skillRatingRepository.save(rating);

        skill.setRatingSum((skill.getRatingSum() == null ? 0L : skill.getRatingSum()) + score);
        skill.setRatingCount((skill.getRatingCount() == null ? 0L : skill.getRatingCount()) + 1);
        skillRepository.save(skill);
        return saved;
    }

    /**
     * 宽松渲染模板。
     * <p>与 PromptRecipeService 的严格渲染不同：此处对缺失变量不抛异常，保留原占位符，
     * 以适配市场中大量第三方模板，避免因个别变量缺失导致整个安装不可用。</p>
     *
     * @param skillId   Skill ID
     * @param version   版本号，为空则使用最新版
     * @param variables 变量名到取值的映射
     * @return 渲染后的字符串
     */
    @Transactional(readOnly = true)
    public String renderTemplate(Long skillId, String version, Map<String, String> variables) {
        getOrThrow(skillId);
        String targetVersion = version;
        if (targetVersion == null || targetVersion.isBlank()) {
            targetVersion = latestVersion(skillId);
        }
        SkillVersion skillVersion = skillVersionRepository.findBySkillIdAndVersion(skillId, targetVersion)
                .orElseThrow(() -> new IllegalArgumentException("版本不存在"));
        String template = skillVersion.getPromptTemplate();
        if (template == null) {
            return "";
        }
        Map<String, String> vars = variables == null ? Map.of() : variables;
        Matcher matcher = VARIABLE_PATTERN.matcher(template);
        StringBuilder sb = new StringBuilder();
        while (matcher.find()) {
            String varName = matcher.group(1).trim();
            String value = vars.get(varName);
            if (value == null) {
                value = matcher.group(0);
            }
            matcher.appendReplacement(sb, Matcher.quoteReplacement(value));
        }
        matcher.appendTail(sb);
        return sb.toString();
    }

    /**
     * 已安装 Skill 列表，按安装时间倒序。
     *
     * @return 安装记录与对应 Skill
     */
    @Transactional(readOnly = true)
    public List<InstalledSkill> installedList() {
        List<SkillInstall> installs = skillInstallRepository.findAllByOrderByInstalledAtDesc();
        List<InstalledSkill> result = new ArrayList<>();
        for (SkillInstall install : installs) {
            skillRepository.findById(install.getSkillId())
                    .ifPresent(skill -> result.add(new InstalledSkill(skill, install)));
        }
        return result;
    }

    /**
     * 获取 Skill 的最新版本号。
     *
     * @param skillId Skill ID
     * @return 最新版本号
     */
    private String latestVersion(Long skillId) {
        List<SkillVersion> versions = skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(skillId);
        if (versions.isEmpty()) {
            throw new IllegalArgumentException("尚无版本");
        }
        return versions.get(0).getVersion();
    }

    /**
     * 按 ID 获取 Skill，不存在则抛 404。
     *
     * @param skillId Skill ID
     * @return Skill 实体
     */
    private Skill getOrThrow(Long skillId) {
        return skillRepository.findById(skillId)
                .orElseThrow(() -> new com.dramafactory.exception.ResourceNotFoundException("Skill", skillId));
    }

    /** Skill 详情记录 */
    public record SkillDetail(Skill skill, List<SkillVersion> versions, String installedVersion, Double avgRating) {
    }

    /** 已安装 Skill 记录 */
    public record InstalledSkill(Skill skill, SkillInstall install) {
    }

    /**
     * 解析可用的 Skill：必须已安装，返回渲染后的 prompt 与版本信息。
     *
     * <p>若该 Skill 尚未安装，抛出 IllegalArgumentException，调用方不应静默降级。</p>
     *
     * @param skillId   Skill ID
     * @param variables 模板变量（宽松渲染，缺失变量保留占位符）
     * @return 解析结果，含渲染后的 prompt 与版本
     */
    public ResolvedSkill resolveForUse(Long skillId, Map<String, String> variables) {
        SkillDetail detail = getDetail(skillId);
        if (detail.installedVersion() == null) {
            throw new IllegalArgumentException("Skill 尚未安装，请先安装后再使用：id=" + skillId);
        }
        String rendered = renderTemplate(skillId, detail.installedVersion(), variables);
        return new ResolvedSkill(skillId, detail.skill().getName(), detail.installedVersion(), rendered);
    }

    /**
     * 可用的 Skill 解析结果。
     *
     * @param skillId        Skill ID
     * @param name           Skill 名称
     * @param version        使用的版本号
     * @param renderedPrompt 渲染后的 prompt 模板
     */
    public record ResolvedSkill(Long skillId, String name, String version, String renderedPrompt) {
    }
}
