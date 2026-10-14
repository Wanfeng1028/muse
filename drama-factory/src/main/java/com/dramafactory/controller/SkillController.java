package com.dramafactory.controller;

import com.dramafactory.model.Skill;
import com.dramafactory.model.SkillInstall;
import com.dramafactory.model.SkillRating;
import com.dramafactory.model.SkillVersion;
import com.dramafactory.repository.SkillRatingRepository;
import com.dramafactory.repository.SkillVersionRepository;
import com.dramafactory.service.SkillService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Skill 市场接口。
 */
@RestController
@RequestMapping("/api/skills")
@Tag(name = "Skill 市场", description = "Agent 技能的发布、安装与评分")
public class SkillController {

    private final SkillService skillService;
    private final SkillVersionRepository skillVersionRepository;
    private final SkillRatingRepository skillRatingRepository;

    /**
     * 构造器注入。
     *
     * @param skillService           Skill 业务服务
     * @param skillVersionRepository Skill 版本仓库
     * @param skillRatingRepository  Skill 评分仓库
     */
    public SkillController(SkillService skillService,
                           SkillVersionRepository skillVersionRepository,
                           SkillRatingRepository skillRatingRepository) {
        this.skillService = skillService;
        this.skillVersionRepository = skillVersionRepository;
        this.skillRatingRepository = skillRatingRepository;
    }

    /** 发布请求体 */
    public record CreateSkillRequest(String name, String slug, String description, String author,
                                     String category, String tags, String icon,
                                     String promptTemplate, String changelog) {
    }

    /** 发布版本请求体 */
    public record PublishVersionRequest(String version, String promptTemplate, String changelog) {
    }

    /** 安装请求体 */
    public record InstallRequest(String version) {
    }

    /** 评分请求体 */
    public record RateRequest(Integer score, String comment) {
    }

    /** 渲染请求体 */
    public record RenderRequest(String version, Map<String, String> variables) {
    }

    /** 渲染响应体 */
    public record RenderResponse(String content) {
    }

    /** Skill 列表 DTO */
    public record SkillDto(Long id, String name, String slug, String description, String author,
                           String category, String tags, String icon, Boolean official,
                           Long installCount, Double avgRating, String latestVersion,
                           String installedVersion, LocalDateTime createdAt) {
        /**
         * 由实体构建 DTO。
         *
         * @param skill            Skill 实体
         * @param latestVersion    最新版本号
         * @param installedVersion 已安装版本号，可空
         * @return DTO
         */
        public static SkillDto from(Skill skill, String latestVersion, String installedVersion) {
            return new SkillDto(skill.getId(), skill.getName(), skill.getSlug(), skill.getDescription(),
                    skill.getAuthor(), skill.getCategory(), skill.getTags(), skill.getIcon(), skill.getOfficial(),
                    skill.getInstallCount(), skill.getAvgRating(), latestVersion, installedVersion,
                    skill.getCreatedAt());
        }
    }

    /** Skill 版本 DTO */
    public record SkillVersionDto(Long id, Long skillId, String version, String promptTemplate,
                                  String changelog, LocalDateTime createdAt) {
        /**
         * 由实体构建 DTO。
         *
         * @param v SkillVersion 实体
         * @return DTO
         */
        public static SkillVersionDto from(SkillVersion v) {
            return new SkillVersionDto(v.getId(), v.getSkillId(), v.getVersion(), v.getPromptTemplate(),
                    v.getChangelog(), v.getCreatedAt());
        }
    }

    /** Skill 详情 DTO */
    public record SkillDetailDto(Long id, String name, String slug, String description, String author,
                                 String category, String tags, String icon, Boolean official,
                                 Long installCount, Double avgRating, String latestVersion,
                                 String installedVersion,
                                 List<SkillVersionDto> versions, List<RatingDto> ratings,
                                 LocalDateTime createdAt) {
        /**
         * 由实体构建 DTO。
         *
         * @param skill            Skill 实体
         * @param versions         版本列表
         * @param ratings          最新评分列表
         * @param installedVersion 已安装版本号，可空
         * @return DTO
         */
        public static SkillDetailDto from(Skill skill, List<SkillVersionDto> versions,
                                          List<RatingDto> ratings, String installedVersion) {
            String latest = versions == null || versions.isEmpty() ? null : versions.get(0).version();
            return new SkillDetailDto(skill.getId(), skill.getName(), skill.getSlug(), skill.getDescription(),
                    skill.getAuthor(), skill.getCategory(), skill.getTags(), skill.getIcon(), skill.getOfficial(),
                    skill.getInstallCount(), skill.getAvgRating(), latest, installedVersion, versions, ratings,
                    skill.getCreatedAt());
        }
    }

    /** 安装记录 DTO */
    public record InstallDto(Long id, Long skillId, String version, LocalDateTime installedAt) {
        /**
         * 由实体构建 DTO。
         *
         * @param install SkillInstall 实体
         * @return DTO
         */
        public static InstallDto from(SkillInstall install) {
            return new InstallDto(install.getId(), install.getSkillId(), install.getVersion(),
                    install.getInstalledAt());
        }
    }

    /** 已安装 Skill DTO */
    public record InstalledSkillDto(SkillDto skill, InstallDto install) {
    }

    /** 评分 DTO */
    public record RatingDto(Long id, Long skillId, Integer score, String comment, LocalDateTime createdAt) {
        /**
         * 由实体构建 DTO。
         *
         * @param r SkillRating 实体
         * @return DTO
         */
        public static RatingDto from(SkillRating r) {
            return new RatingDto(r.getId(), r.getSkillId(), r.getScore(), r.getComment(), r.getCreatedAt());
        }
    }

    /**
     * 发布新 Skill。
     *
     * @param request 发布请求
     * @return 创建的 Skill
     */
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "发布 Skill")
    public SkillDto publish(@RequestBody CreateSkillRequest request) {
        Skill skill = skillService.publish(request.name(), request.slug(), request.description(),
                request.author(), request.category(), request.tags(), request.icon(),
                request.promptTemplate(), request.changelog());
        String latest = latestVersionOf(skill.getId());
        return SkillDto.from(skill, latest, null);
    }

    /**
     * 检索 Skill 市场。
     *
     * @param q        关键字
     * @param tag      标签
     * @param category 分类
     * @param sort     排序
     * @return Skill 列表
     */
    @GetMapping
    @Operation(summary = "检索 Skill")
    public List<SkillDto> list(@RequestParam(value = "q", required = false) String q,
                               @RequestParam(value = "tag", required = false) String tag,
                               @RequestParam(value = "category", required = false) String category,
                               @RequestParam(value = "sort", required = false) String sort) {
        List<Skill> skills = skillService.list(q, tag, category, sort);
        List<SkillDto> result = new ArrayList<>();
        for (Skill skill : skills) {
            String latest = latestVersionOf(skill.getId());
            String installed = skillService.getDetail(skill.getId()).installedVersion();
            result.add(SkillDto.from(skill, latest, installed));
        }
        return result;
    }

    /**
     * 已安装 Skill 列表。
     *
     * @return 已安装列表
     */
    @GetMapping("/installed")
    @Operation(summary = "已安装 Skill 列表")
    public List<InstalledSkillDto> installed() {
        List<InstalledSkillDto> result = new ArrayList<>();
        for (SkillService.InstalledSkill item : skillService.installedList()) {
            Skill skill = item.skill();
            String latest = latestVersionOf(skill.getId());
            result.add(new InstalledSkillDto(
                    SkillDto.from(skill, latest, item.install().getVersion()),
                    InstallDto.from(item.install())));
        }
        return result;
    }

    /**
     * Skill 详情。
     *
     * @param id Skill ID
     * @return 详情 DTO
     */
    @GetMapping("/{id}")
    @Operation(summary = "Skill 详情")
    public SkillDetailDto get(@PathVariable("id") Long id) {
        SkillService.SkillDetail detail = skillService.getDetail(id);
        List<SkillVersionDto> versions = new ArrayList<>();
        for (SkillVersion v : detail.versions()) {
            versions.add(SkillVersionDto.from(v));
        }
        List<RatingDto> ratings = new ArrayList<>();
        List<SkillRating> all = skillRatingRepository.findBySkillIdOrderByCreatedAtDesc(id);
        for (int i = 0; i < all.size() && i < 5; i++) {
            ratings.add(RatingDto.from(all.get(i)));
        }
        return SkillDetailDto.from(detail.skill(), versions, ratings, detail.installedVersion());
    }

    /**
     * 发布新版本。
     *
     * @param id      Skill ID
     * @param request 发布版本请求
     * @return 创建的版本
     */
    @PostMapping("/{id}/versions")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "发布 Skill 版本")
    public SkillVersionDto publishVersion(@PathVariable("id") Long id,
                                          @RequestBody PublishVersionRequest request) {
        SkillVersion version = skillService.publishVersion(id, request.version(),
                request.promptTemplate(), request.changelog());
        return SkillVersionDto.from(version);
    }

    /**
     * 安装 Skill。
     *
     * @param id      Skill ID
     * @param request 安装请求
     * @return 安装记录
     */
    @PostMapping("/{id}/install")
    @Operation(summary = "安装 Skill")
    public InstallDto install(@PathVariable("id") Long id, @RequestBody(required = false) InstallRequest request) {
        String version = request == null ? null : request.version();
        SkillInstall install = skillService.install(id, version);
        return InstallDto.from(install);
    }

    /**
     * 卸载 Skill。
     *
     * @param id Skill ID
     */
    @DeleteMapping("/{id}/install")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @Operation(summary = "卸载 Skill")
    public void uninstall(@PathVariable("id") Long id) {
        skillService.uninstall(id);
    }

    /**
     * 评分。
     *
     * @param id      Skill ID
     * @param request 评分请求
     * @return 评分记录
     */
    @PostMapping("/{id}/rate")
    @Operation(summary = "评分 Skill")
    public RatingDto rate(@PathVariable("id") Long id, @RequestBody RateRequest request) {
        SkillRating rating = skillService.rate(id, request.score(), request.comment());
        return RatingDto.from(rating);
    }

    /**
     * 渲染模板。
     *
     * @param id      Skill ID
     * @param request 渲染请求
     * @return 渲染结果
     */
    @PostMapping("/{id}/render")
    @Operation(summary = "渲染 Skill 模板")
    public RenderResponse render(@PathVariable("id") Long id, @RequestBody RenderRequest request) {
        String content = skillService.renderTemplate(id, request.version(), request.variables());
        return new RenderResponse(content);
    }

    /**
     * 获取 Skill 最新版本号，无版本返回 null。
     *
     * @param skillId Skill ID
     * @return 最新版本号或 null
     */
    private String latestVersionOf(Long skillId) {
        List<SkillVersion> versions = skillVersionRepository.findBySkillIdOrderByCreatedAtDesc(skillId);
        return versions.isEmpty() ? null : versions.get(0).getVersion();
    }
}
