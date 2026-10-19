package com.dramafactory.controller;

import com.dramafactory.service.skill.SkillHubClient;
import com.dramafactory.service.skill.SkillInstallService;
import com.dramafactory.service.skill.SkillRegistry;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/official-skills")
@Tag(name = "官方技能库", description = "官方 Skill 库（我们就是官方）：内置 skill 与官网 skillhub 的列表、安装、卸载")
public class OfficialSkillController {

    private static final Logger log = LoggerFactory.getLogger(OfficialSkillController.class);

    private final SkillRegistry registry;
    private final SkillInstallService installService;
    private final SkillHubClient hubClient;

    public OfficialSkillController(SkillRegistry registry,
                           SkillInstallService installService,
                           SkillHubClient hubClient) {
        this.registry = registry;
        this.installService = installService;
        this.hubClient = hubClient;
    }

    public record OfficialSkillDto(String id, String name, String version, String description,
                                   String author, String license, String source,
                                   boolean installed, String installedVersion) {}

    public record InstalledSkillDto(String id, String version) {}

    public record InstallRequest(String version) {}

    public record UninstallResponse(String id, boolean removed) {}

    @GetMapping("/official")
    @Operation(summary = "官方 skill 列表")
    public ResponseEntity<List<OfficialSkillDto>> official() {
        Map<String, SkillRegistry.InstalledSkill> installedMap = registry.installed().stream()
                .collect(Collectors.toMap(SkillRegistry.InstalledSkill::id, Function.identity(), (a, b) -> a));
        List<OfficialSkillDto> result = new ArrayList<>();
        for (var d : registry.bundled()) {
            SkillRegistry.InstalledSkill inst = installedMap.get(d.getId());
            result.add(new OfficialSkillDto(d.getId(), d.getName(), d.getVersion(), d.getDescription(),
                    d.getAuthor(), d.getLicense(), "bundled",
                    inst != null, inst == null ? "" : inst.version()));
        }
        if (hubClient.isEnabled()) {
            try {
                for (SkillHubClient.HubSkill h : hubClient.fetchSkills()) {
                    if (registry.bundledOf(h.id()).isEmpty()) {
                        SkillRegistry.InstalledSkill inst = installedMap.get(h.id());
                        result.add(new OfficialSkillDto(h.id(), h.name(), h.version(), h.description(),
                                h.author(), h.license(), "skillhub",
                                inst != null, inst == null ? "" : inst.version()));
                    }
                }
            } catch (RuntimeException e) {
                log.warn("skillhub 远端列表获取失败，仅返回内置：{}", e.getMessage());
            }
        }
        result.sort(Comparator.comparing(OfficialSkillDto::id));
        return ResponseEntity.ok(result);
    }

    @PostMapping("/install/{id}")
    @Operation(summary = "安装 skill")
    public ResponseEntity<SkillInstallService.InstallResult> install(
            @PathVariable String id,
            @RequestBody(required = false) InstallRequest body) {
        String version = body == null ? null : body.version();
        return ResponseEntity.ok(installService.install(id, version));
    }

    @GetMapping("/installed")
    @Operation(summary = "已安装 skill 列表")
    public ResponseEntity<List<InstalledSkillDto>> installed() {
        List<InstalledSkillDto> list = registry.installed().stream()
                .map(s -> new InstalledSkillDto(s.id(), s.version()))
                .sorted(Comparator.comparing(InstalledSkillDto::id))
                .toList();
        return ResponseEntity.ok(list);
    }

    @DeleteMapping("/installed/{id}")
    @Operation(summary = "卸载 skill")
    public ResponseEntity<UninstallResponse> uninstall(@PathVariable String id) {
        return ResponseEntity.ok(new UninstallResponse(id, installService.uninstall(id)));
    }
}
