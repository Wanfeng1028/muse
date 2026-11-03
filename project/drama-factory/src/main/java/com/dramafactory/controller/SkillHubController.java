package com.dramafactory.controller;

import com.dramafactory.service.skill.SkillInstallService;
import com.dramafactory.service.skill.SkillRegistry;
import com.dramafactory.service.skill.SkillDescriptor;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@RestController
@RequestMapping("/api/skillhub")
@Tag(name = "自有 SkillHub", description = "我们自己的 skillhub 索引：内置与社区收录 skills，供软件内一键安装")
public class SkillHubController {

    private static final Logger log = LoggerFactory.getLogger(SkillHubController.class);

    private static final String HUB_NAME = "playhouse-skillhub";
    private static final int HUB_VERSION = 1;

    private final SkillRegistry registry;
    private final SkillInstallService skillInstallService;

    public SkillHubController(SkillRegistry registry, SkillInstallService skillInstallService) {
        this.registry = registry;
        this.skillInstallService = skillInstallService;
    }

    public record SkillHubIndex(
            String hub,
            int version,
            String updatedAt,
            int total,
            int page,
            int size,
            int totalPages,
            List<SkillHubItem> skills
    ) {
    }

    public record SkillHubItem(
            String id,
            String name,
            String version,
            String description,
            String author,
            String license,
            String source,
            String sourceUrl,
            boolean installed,
            String installedVersion,
            boolean installable
    ) {
    }

    @GetMapping("/index")
    @Operation(summary = "获取自有 SkillHub 索引", description = "返回内置与社区收录的 skills 列表，供软件内一键安装。始终分页，无参默认第 0 页、每页 50 条，total 为过滤后全量。page 不能为负数，size 必须在 1 到 200 之间，越界返回 400。")
    public ResponseEntity<SkillHubIndex> index(
            @RequestParam(required = false) Integer page,
            @RequestParam(required = false) Integer size,
            @RequestParam(required = false) String q,
            @RequestParam(required = false) String source) {
        int pageNum = page == null ? 0 : page;
        if (pageNum < 0) {
            throw new IllegalArgumentException("page 参数非法");
        }
        int sizeNum = size == null ? 50 : size;
        if (sizeNum < 1 || sizeNum > 200) {
            throw new IllegalArgumentException("size 参数非法");
        }
        Instant loadedAt = registry.bundledLoadedAt();
        String updatedAt = loadedAt == null ? ""
                : DateTimeFormatter.ISO_INSTANT.format(loadedAt.atOffset(ZoneOffset.UTC));
        List<SkillHubItem> items = new ArrayList<>();
        try {
            Map<String, String> installedMap = new HashMap<>();
            for (SkillRegistry.InstalledSkill is : registry.installed()) {
                if (is == null) {
                    continue;
                }
                String iid = is.id() == null ? "" : is.id();
                String iver = is.version() == null ? "" : is.version();
                installedMap.put(iid, iver);
            }

            List<SkillDescriptor> bundled = registry.bundled();
            if (bundled != null) {
                List<SkillDescriptor> sorted = new ArrayList<>(bundled);
                sorted.sort(Comparator.comparing(
                        d -> d == null || d.getId() == null ? "" : d.getId()
                ));
                for (SkillDescriptor d : sorted) {
                    if (d == null) {
                        continue;
                    }
                    try {
                        items.add(toItem(d, installedMap));
                    } catch (Exception e) {
                        log.warn("skillhub index: skip malformed entry: {}", e.getMessage());
                    }
                }
            }
        } catch (Exception e) {
            log.error("skillhub index failed, returning empty list", e);
            items = new ArrayList<>();
        }

        String keyword = q == null ? null : q.trim();
        boolean hasQ = keyword != null && !keyword.isEmpty();
        boolean hasSource = "官方出品".equals(source) || "社区收录".equals(source);

        List<SkillHubItem> filtered = items;
        if (hasQ || hasSource) {
            filtered = new ArrayList<>();
            for (SkillHubItem item : items) {
                boolean match = true;
                if (hasQ) {
                    String lowerKeyword = keyword.toLowerCase(Locale.ROOT);
                    match = item.id().toLowerCase(Locale.ROOT).contains(lowerKeyword)
                            || item.name().toLowerCase(Locale.ROOT).contains(lowerKeyword)
                            || item.description().toLowerCase(Locale.ROOT).contains(lowerKeyword)
                            || item.author().toLowerCase(Locale.ROOT).contains(lowerKeyword);
                }
                if (match && hasSource) {
                    match = source.equals(item.source());
                }
                if (match) {
                    filtered.add(item);
                }
            }
        }

        int total = filtered.size();
        int effectivePage = pageNum;
        int effectiveSize = sizeNum;
        int totalPages = total == 0 ? 0 : (int) Math.ceil((double) total / effectiveSize);
        int from = Math.min(effectivePage * effectiveSize, total);
        int to = Math.min(from + effectiveSize, total);
        List<SkillHubItem> pageItems = filtered.subList(from, to);

        SkillHubIndex body = new SkillHubIndex(
                HUB_NAME,
                HUB_VERSION,
                updatedAt,
                total,
                effectivePage,
                effectiveSize,
                totalPages,
                pageItems
        );
        return ResponseEntity.ok(body);
    }

    private SkillHubItem toItem(SkillDescriptor d, Map<String, String> installedMap) {
        String id = safe(d.getId());
        String name = safe(d.getName());
        String version = safe(d.getVersion());
        String description = safe(d.getDescription());
        String author = safe(d.getAuthor());
        String license = safe(d.getLicense());
        String sourceUrl = safe(d.getSourceUrl());

        String source = "playhouse".equals(author) ? "官方出品" : "社区收录";

        String installedVersion = installedMap.getOrDefault(id, "");
        if (installedVersion == null) {
            installedVersion = "";
        }
        // 已安装以注册表里有记录为准，不以版本号非空为准：版本号本身为空
        // 的 skill（如 02ui-video-copy）装完后 installedVersion 仍为空串，
        // 旧写法会误报未安装，与 OfficialSkillController 的 inst != null 口径不一致。
        boolean installed = installedMap.containsKey(id);

        return new SkillHubItem(
                id,
                name,
                version,
                description,
                author,
                license,
                source,
                sourceUrl,
                installed,
                installedVersion,
                true
        );
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }
}