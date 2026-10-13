package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.SceneService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@Tag(name = "Scenes", description = "剧集场景的增删改查接口")
public class SceneController {

    private final SceneService sceneService;

    public SceneController(SceneService sceneService) {
        this.sceneService = sceneService;
    }

    @GetMapping("/api/episodes/{episodeId}/scenes")
    @Operation(summary = "按剧集查询场景列表")
    public List<Records.SceneResponse> listByEpisode(@PathVariable Long episodeId) {
        return sceneService.listByEpisode(episodeId);
    }

    @PostMapping("/api/episodes/{episodeId}/scenes")
    @Operation(summary = "创建场景")
    public ResponseEntity<Records.SceneResponse> create(@PathVariable Long episodeId,
                                                        @Valid @RequestBody Records.SceneRequest request) {
        Records.SceneResponse response = sceneService.create(episodeId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @PutMapping("/api/scenes/{id}")
    @Operation(summary = "更新场景")
    public Records.SceneResponse update(@PathVariable Long id,
                                        @Valid @RequestBody Records.SceneRequest request) {
        return sceneService.update(id, request);
    }

    @DeleteMapping("/api/scenes/{id}")
    @Operation(summary = "删除场景")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        sceneService.delete(id);
        return ResponseEntity.noContent().build();
    }
}
