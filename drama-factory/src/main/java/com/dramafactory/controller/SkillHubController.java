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
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

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
    @Operation(summary = "获取自有 SkillHub 索引", description = "返回内置与社区收录的 skills 列表，供软件内一键安装")
    public ResponseEntity<SkillHubIndex> index() {
        String updatedAt = DateTimeFormatter.ISO_INSTANT.format(Instant.now().atOffset(ZoneOffset.UTC));
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
        SkillHubIndex body = new SkillHubIndex(HUB_NAME, HUB_VERSION, updatedAt, items);
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
        boolean installed = !installedVersion.isEmpty();

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
