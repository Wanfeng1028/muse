package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.ScriptService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@Tag(name = "剧集管理", description = "剧集的增删改查与剧本生成接口")

public class EpisodeController {

    private final EpisodeService episodeService;
    private final ScriptService scriptService;

    public EpisodeController(EpisodeService episodeService, ScriptService scriptService) {
        this.episodeService = episodeService;
        this.scriptService = scriptService;
    }

    @GetMapping("/api/projects/{projectId}/episodes")
    @Operation(summary = "查询项目下的剧集列表")
    public List<Records.EpisodeResponse> listByProject(@PathVariable Long projectId) {
        return episodeService.listByProject(projectId);
    }

    @PostMapping("/api/projects/{projectId}/episodes")
    @Operation(summary = "创建剧集")
    public ResponseEntity<Records.EpisodeResponse> create(
            @PathVariable Long projectId,
            @Valid @RequestBody Records.EpisodeRequest request) {
        Records.EpisodeResponse response = episodeService.create(projectId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/api/episodes/{id}")
    @Operation(summary = "按 ID 查询剧集")
    public Records.EpisodeResponse get(@PathVariable Long id) {
        return episodeService.get(id);
    }

    @PutMapping("/api/episodes/{id}")
    @Operation(summary = "更新剧集")
    public Records.EpisodeResponse update(
            @PathVariable Long id,
            @Valid @RequestBody Records.EpisodeRequest request) {
        return episodeService.update(id, request);
    }

    @DeleteMapping("/api/episodes/{id}")
    @Operation(summary = "删除剧集")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        episodeService.delete(id);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/episodes/{id}/generate-script")
    @Operation(summary = "生成剧集剧本（可选 skillId 选用已安装 Skill）")
    public Records.GenerateScriptResponse generateScript(@PathVariable Long id,
                                                         @RequestParam(defaultValue = "ai") String mode,
                                                         @RequestParam(required = false) Long skillId) {
        return scriptService.generate(id, mode, skillId);
    }
}
