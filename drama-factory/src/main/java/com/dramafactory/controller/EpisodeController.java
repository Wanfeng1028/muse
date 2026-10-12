package com.dramafactory.controller;

import com.dramafactory.dto.Records;
import com.dramafactory.service.EpisodeService;
import com.dramafactory.service.ScriptService;
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
public class EpisodeController {

    private final EpisodeService episodeService;
    private final ScriptService scriptService;

    public EpisodeController(EpisodeService episodeService, ScriptService scriptService) {
        this.episodeService = episodeService;
        this.scriptService = scriptService;
    }

    @GetMapping("/api/projects/{projectId}/episodes")
    public List<Records.EpisodeResponse> listByProject(@PathVariable Long projectId) {
        return episodeService.listByProject(projectId);
    }

    @PostMapping("/api/projects/{projectId}/episodes")
    public ResponseEntity<Records.EpisodeResponse> create(
            @PathVariable Long projectId,
            @Valid @RequestBody Records.EpisodeRequest request) {
        Records.EpisodeResponse response = episodeService.create(projectId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/api/episodes/{id}")
    public Records.EpisodeResponse get(@PathVariable Long id) {
        return episodeService.get(id);
    }

    @PutMapping("/api/episodes/{id}")
    public Records.EpisodeResponse update(
            @PathVariable Long id,
            @Valid @RequestBody Records.EpisodeRequest request) {
        return episodeService.update(id, request);
    }

    @DeleteMapping("/api/episodes/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        episodeService.delete(id);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/api/episodes/{id}/generate-script")
    public Records.GenerateScriptResponse generateScript(@PathVariable Long id) {
        return scriptService.generate(id);
    }
}
